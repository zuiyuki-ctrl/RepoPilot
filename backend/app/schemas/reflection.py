from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator, StringConstraints,
)


class ReflectionFileAction(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    file_path: Annotated[
        str,
        StringConstraints(strip_whitespace=False, min_length=1),
    ]
    instruction: str = Field(min_length=1, max_length=2000)


class ReflectionDecision(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    diagnosis: str = Field(min_length=1, max_length=4000)

    # False 表示根据当前证据无法提出可靠修复，
    # 应停止本轮自动重试。
    should_retry: bool

    actions: list[ReflectionFileAction] = Field(
        default_factory=list,
        max_length=10,
    )

    # 校验决策内部一致性：重试必须提供修改动作，停止重试不能携带动作，文件路径不能重复。
    # 这是数据结构校验；是否属于批准计划，由反思生成模块另外检查。
    @model_validator(mode="after")
    def validate_action_consistency(self):
        # should_retry=True 时至少需要一个 action。
        if self.should_retry and not self.actions:
            raise ValueError("Retrying reflection requires at least one file action")

        # should_retry=False 时不能携带 action。
        if not self.should_retry and self.actions:
            raise ValueError("Stopped reflection cannot contain file actions")

        # file_path 不能重复。
        paths = [action.file_path for action in self.actions]

        if len(paths) != len(set(paths)):
            raise ValueError("Reflection file paths must be unique")

        return self
    

class TaskReflectionRead(BaseModel):
    task_id: UUID

    decision: ReflectionDecision


# 完成事件载荷
class ReflectionFinishedEventPayload(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
    )

    step_id: Literal["reflect"]
    attempt: int = Field(ge=1)

    # 这次 Reflection 分析的是哪条测试结果
    test_event_sequence: int = Field(ge=1)
    decision: ReflectionDecision

    # 这条事件自己的编号
    sequence: int = Field(ge=1)
    schema_version: Literal[1]