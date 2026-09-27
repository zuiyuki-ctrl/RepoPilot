import json
import ast

from pydantic import ValidationError

from ..rag.generation import request_tool_turn

from ..schemas.plan import ChangePlan
from ..core.exceptions import InvalidEditProposalError
from ..schemas.edit import FileEditProposal
from .policy import EDIT_SYSTEM_PROMPT, EDIT_FINAL_INSTRUCTION

MAX_EDIT_INPUT_BYTES = 20_000
MAX_EDIT_OUTPUT_BYTES = 50_000

# 候选解析函数
def parse_file_edit(
    content: str,
    *,
    expected_file_path: str,
) -> FileEditProposal:
    # 1. FileEditProposal.model_validate_json(content)。
    #    ValidationError 转换为 InvalidEditProposalError，保留异常链。
    try:
        proposal = FileEditProposal.model_validate_json(content)
    except ValidationError as exc:
        raise InvalidEditProposalError("Model returned an invalid edit structure") from exc

    # 2. proposal.file_path 必须与 expected_file_path 精确相等。
    #    不去空白、不改变大小写，不允许模型换目标。
    if proposal.file_path != expected_file_path:
        raise InvalidEditProposalError("Proposed file path does not match the requested target")

    # 3. summary 和源码 content 不能是纯空白。
    if not proposal.summary.strip() or not proposal.content.strip():
        raise InvalidEditProposalError("Edit summary and source content must not be blank")

    # 4. 将源码编码为 UTF-8，检查字节数不超过候选输出上限。
    try:
        content_bytes = proposal.content.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise InvalidEditProposalError("Proposed source cannot be encoded as UTF-8") from exc

    if len(content_bytes) > MAX_EDIT_OUTPUT_BYTES:
        raise InvalidEditProposalError("Proposed source exceeds the output size limit")

    # 5. 用 ast.parse 检查候选 Python 源码语法。
    try:
        ast.parse(content_bytes, filename=expected_file_path)
    except (SyntaxError, ValueError) as exc:
        raise InvalidEditProposalError("Proposed source is not valid Python syntax") from exc
    return proposal


# 候选生成函数
# 组织修改任务，调用模型，再检查候选代码
def generate_file_edit(
    user_request: str,
    *,
    plan: ChangePlan,
    file_path: str,
    original_content: str,
) -> FileEditProposal:
    # 1. 校验需求长度、文件类型及原文大小。
    if not isinstance(user_request, str):
        raise ValueError("User request must be a string")

    normalized_request = user_request.strip()

    if not 1 <= len(normalized_request) <= 1000:
        raise ValueError("User request must contain 1 to 1000 characters")


    if not isinstance(original_content, str):
        raise ValueError("Original content must be a string")

    original_bytes = original_content.encode("utf-8")
    if len(original_bytes) > MAX_EDIT_INPUT_BYTES:
        raise ValueError("Original source exceeds the input size limit")

    if not isinstance(file_path, str) or not file_path.endswith(".py"):
        raise ValueError("Target file must be a Python file")


    # 2. 从 plan.steps 中找出 files 包含 file_path 的步骤。
    #    一个也没有时，在模型调用前拒绝。
    relevant_steps = []

    for step in plan.steps:
        if file_path in step.files:
            relevant_steps.append(step)

    # relevant_steps 为空，说明目标不属于计划。
    if not relevant_steps:
        raise ValueError("Target file is not included in the plan")

    # 3. 组织需求、计划、目标路径、完整原文和输出 Schema
    edit_input = {
        "user_request": normalized_request,
        "plan_summary": plan.summary,
        "relevant_steps": [
            step.model_dump(mode="json")
            for step in relevant_steps
        ],
        "file_path": file_path,
        "original_content": original_content,
        "output_schema": FileEditProposal.model_json_schema(),
    }

    messages = [
        {
            "role": "system",
            "content": EDIT_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": json.dumps(edit_input, ensure_ascii=False),
        },
    ]

    # 4. 调用 request_tool_turn，禁用工具，使用修改专用收尾指令。
    assistant_message = request_tool_turn(
        messages=messages,
        allow_tools=False,
        final_instruction=EDIT_FINAL_INSTRUCTION
    )

    # 5. 把返回 content 交给 parse_file_edit。
    return parse_file_edit(
        content=assistant_message["content"],
        expected_file_path=file_path,
    )