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

# 检查候选的目标路径、摘要、源码大小及 Python 语法，供生成和应用流程复用。
# 语法通过不代表功能正确；计划权限和原文版本由服务层检查。
def validate_file_edit_proposal(
    proposal: FileEditProposal,
    *,
    expected_file_path: str,
) -> FileEditProposal:
    # 1. expected_file_path 必须是 .py 文件路径。
    if (
        not isinstance(expected_file_path, str)
        or not expected_file_path.endswith(".py")
    ):
        raise InvalidEditProposalError(
            "Target file must be a Python file"
        )

    # 2. proposal.file_path 必须和预期路径精确相等。
    if proposal.file_path != expected_file_path:
        raise InvalidEditProposalError(
            "Proposed file path does not match the requested target"
        )

    # 3. summary 和 content 不能是纯空白。
    if not proposal.summary.strip():
        raise InvalidEditProposalError(
            "Edit summary must not be blank"
        )

    if not proposal.content.strip():
        raise InvalidEditProposalError(
            "Proposed source must not be blank"
        )

    # 4. 将候选源码编码为 UTF-8。
    try:
        content_bytes = proposal.content.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise InvalidEditProposalError(
            "Proposed source cannot be encoded as UTF-8"
        ) from exc

    # 5. 检查 UTF-8 字节长度。
    if len(content_bytes) > MAX_EDIT_OUTPUT_BYTES:
        raise InvalidEditProposalError(
            "Proposed source exceeds the output size limit"
        )

    # 6. 检查 Python 语法。
    try:
        ast.parse(
            content_bytes,
            filename=expected_file_path,
        )
    except (SyntaxError, ValueError) as exc:
        raise InvalidEditProposalError(
            "Proposed source is not valid Python syntax"
        ) from exc

    # 7. 返回同一个已验证候选。
    return proposal

# 将模型返回的 JSON 解析为 FileEditProposal，再调用公共校验函数检查候选内容。
def parse_file_edit(
    content: str,
    *,
    expected_file_path: str,
) -> FileEditProposal:
    # 1. 只负责把 JSON 转成 Pydantic 模型。
    try:
        proposal = FileEditProposal.model_validate_json(content)
    except ValidationError as exc:
        raise InvalidEditProposalError(
            "Model returned an invalid edit structure"
        ) from exc

    # 2. 所有业务校验交给公共函数。
    return validate_file_edit_proposal(
        proposal,
        expected_file_path=expected_file_path,
    )


# 结合用户需求、相关计划步骤和文件原文调用模型，生成并校验单文件完整源码候选。
# 只返回候选，不直接覆盖工作副本；落盘由后续应用流程负责。
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