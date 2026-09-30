from pydantic import ValidationError

from ..core.exceptions import InvalidReflectionError
from ..schemas.plan import ChangePlan
from ..schemas.reflection import ReflectionDecision


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
        # TODO 1：
        # file_path 必须以 .py 结尾。
        if ...:
            raise InvalidReflectionError(
                "Reflection target must be a Python file"
            )

        # TODO 2：
        # file_path 必须精确存在于 approved_files。
        # 不做 strip、大小写转换或路径自动修正。
        if ...:
            raise InvalidReflectionError(
                "Reflection target is outside the approved plan"
            )

    return decision


def parse_reflection_decision(
    content: str,
    *,
    plan: ChangePlan,
) -> ReflectionDecision:
    try:
        # TODO 3：
        # 使用 model_validate_json 解析模型 JSON。
        decision = ...
    except ValidationError as exc:
        raise InvalidReflectionError(
            "Model returned an invalid reflection structure"
        ) from exc

    return validate_reflection_decision(
        decision,
        plan=plan,
    )