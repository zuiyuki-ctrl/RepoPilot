import os
from pathlib import PurePosixPath, PureWindowsPath

import pydantic

from ..schemas.agent import AgentSourceReference
from ..schemas.plan import ChangePlan

from ..core.exceptions import InvalidPlanError


# 检查模型生成的计划能不能被程序接受
def parse_change_plan(
    content: str,
    *,
    sources: list[AgentSourceReference],
) -> ChangePlan:
    # 1. 用 ChangePlan.model_validate_json(content) 解析。
    #    捕获 pydantic.ValidationError，转换为 InvalidPlanError。
    #    使用 raise ... from exc 保留异常原因。
    try:
        plan = ChangePlan.model_validate_json(content)
    except pydantic.ValidationError as exc:
        raise InvalidPlanError("模型返回的计划不符合要求的 JSON 结构") from exc

    # 2. 检查步骤编号。
    #    实际编号列表必须等于 list(range(1, len(plan.steps) + 1))。
    actual_ids = [step.id for step in plan.steps]
    expected_ids = list(range(1, len(plan.steps) + 1))
    if actual_ids != expected_ids:
        raise InvalidPlanError("步骤编号必须从 1 开始连续递增")

    # 3. 从 sources 建立合法证据编号集合。
    #    每一步的 source_ids 必须全部属于该集合。
    #    同一步内不允许重复引用编号。
    allowed_ids = {source.source_id for source in sources}
    for step in plan.steps:
        cited_ids = set(step.source_ids)

        if len(cited_ids) != len(step.source_ids):
            raise InvalidPlanError(f"第 {step.id} 步存在重复证据编号")

        unknown_ids = cited_ids - allowed_ids

        if unknown_ids:
            raise InvalidPlanError(f"第 {step.id} 步引用了不存在的证据")

        # 4. 逐项检查每一步的 files，具体规则见下文。
        seen_file = set()

        for file_path in step.files:
            # 空字符串、纯空白字符串、首尾有空白：拒绝。
            if not file_path.strip():
                raise InvalidPlanError(f"第 {step.id} 步包含空文件路径")

            if file_path != file_path.strip():
                raise InvalidPlanError(f"文件路径不能包含首尾空白：{file_path!r}")

            # 含反斜杠 \：拒绝，计划统一使用 /。
            if '\\' in file_path or ':' in file_path:
                raise InvalidPlanError(f"文件路径必须使用 /，且不能包含冒号：{file_path}")

            # PurePosixPath(path).is_absolute() 为真：拒绝。
            if PurePosixPath(file_path).is_absolute():
                raise InvalidPlanError(f"文件路径必须相对于仓库：{file_path}")

            # PureWindowsPath(path).drive 或 .root 非空：拒绝，覆盖 D:/... 和 D:foo.py 等形式。
            if PureWindowsPath(file_path).drive or PureWindowsPath(file_path).root:
                raise InvalidPlanError(f"文件路径必须相对于仓库：{file_path}")

            # path.split("/") 中出现 ""、 "." 或 ".."：拒绝。
            parts = file_path.split("/")
            for part in parts:
                if part in ("", ".", ".."):
                    raise InvalidPlanError(f"文件路径包含不允许的路径段：{file_path}")

            # 同一步的文件路径重复：拒绝。
            if file_path in seen_file:
                raise InvalidPlanError(f"第 {step.id} 步包含重复文件路径：{file_path}")
            seen_file.add(file_path)

    # 5. 校验全部通过后，返回 plan。
    return plan
