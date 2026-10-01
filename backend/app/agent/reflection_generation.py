from pydantic import ValidationError

from ..core.exceptions import InvalidReflectionError
from ..schemas.plan import ChangePlan
from ..schemas.reflection import ReflectionDecision

import json

from ..rag.generation import request_tool_turn
from ..schemas.testing import TestExecutionEventPayload
from .policy import (
    REFLECTION_SYSTEM_PROMPT,
    REFLECTION_FINAL_INSTRUCTION,
)


# 校验反思提出的修改范围：每个目标必须是原批准计划中的 Python 文件。
# 返回校验后的决策；这里只检查范围，不生成代码或写入文件。
def validate_reflection_decision(
    decision: ReflectionDecision,
    *,
    plan: ChangePlan,
) -> ReflectionDecision:
    """
    限制 Reflection 只能重新修改原批准计划中的 Python 文件。
    """

    approved_files = {
        file_path
        for step in plan.steps
        for file_path in step.files
    }

    for action in decision.actions:
        # file_path 必须以 .py 结尾。
        if not action.file_path.endswith(".py"):
            raise InvalidReflectionError("Reflection target must be a Python file")

        # file_path 必须精确存在于 approved_files。
        # 不做 strip、大小写转换或路径自动修正。
        if action.file_path not in approved_files:
            raise InvalidReflectionError("Reflection target is outside the approved plan")

    return decision


# 把模型返回的 JSON 解析成 ReflectionDecision，再检查修改范围是否超出批准计划。
# 结构不合法时转为 InvalidReflectionError，供上层统一处理模型输出错误。
def parse_reflection_decision(
    content: str,
    *,
    plan: ChangePlan,
) -> ReflectionDecision:
    try:
        # 使用 model_validate_json 解析模型 JSON。
        decision = ReflectionDecision.model_validate_json(content)
    except ValidationError as exc:
        raise InvalidReflectionError("Model returned an invalid reflection structure") from exc

    return validate_reflection_decision(
        decision,
        plan=plan,
    )

MAX_REFLECTION_STREAM_CHARS = 12_000


# 根据用户需求、批准计划和测试结果调用模型，生成是否重试及修复方向的决策。
def generate_reflection_decision(
    user_request: str,
    *,
    plan: ChangePlan,
    test_result: TestExecutionEventPayload,
) -> ReflectionDecision:
    # 1. 校验 user_request，去除首尾空白后长度为 1～1000
    if not isinstance(user_request, str):
        raise ValueError("User request must be a string")

    user_request = user_request.strip()
    if not 1 <= len(user_request) <= 1000:
        raise ValueError("User request must be between 1 and 1000")

    # 2. 已通过的测试结果不应送入失败分析，提前拒绝。
    if test_result.passed:
        raise ValueError("Passed tests do not require reflection")

    # 3. 组织模型输入
    # 4. 创建 test_data 字典
    test_data = test_result.model_dump(mode="json")

    # 5. 保存原始 stdout 和 stderr
    original_stdout = test_data["stdout"]
    original_stderr = test_data["stderr"]

    # 6. 截取两路输出，更新 test_data 中的文本和截断标志。
    #    具体写法见下面的说明。
    test_data["stdout"] = original_stdout[
        -MAX_REFLECTION_STREAM_CHARS:
    ]

    test_data["stdout_truncated"] = (
        test_result.stdout_truncated
        or len(original_stdout) > MAX_REFLECTION_STREAM_CHARS
    )

    test_data["stderr"] = original_stderr[
        -MAX_REFLECTION_STREAM_CHARS:
    ]

    test_data["stderr_truncated"] = (
        test_result.stderr_truncated
        or len(original_stderr) > MAX_REFLECTION_STREAM_CHARS
    )
    # 7. 创建 reflection_input 字典。
    #    包含需求、计划、测试结果和输出 Schema。
    reflection_input = {
        "user_request": user_request,
        "plan": plan.model_dump(mode="json"),
        "test_result": test_data,
        "output_schema": ReflectionDecision.model_json_schema(),
    }

    # 8. 创建 messages 列表，包含 system 和 user 两条消息。
    messages = [
        {"role": "system", "content": REFLECTION_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(reflection_input, ensure_ascii=False)},
    ]

    # 9. 调用 request_tool_turn
    assistant_message = request_tool_turn(
        messages,
        allow_tools=False,
        final_instruction=REFLECTION_FINAL_INSTRUCTION,
    )

    # 10. 调用 parse_reflection_decision，返回解析后的决策。
    return parse_reflection_decision(assistant_message["content"], plan=plan)