from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing import Annotated

class PlanStep(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )
    id: int = Field(ge=1)

    description: str = Field(min_length=1, max_length=1000)

    # 预计涉及的文件，可以包含准备新建的文件
    # Annotated 在这里表示：仍然是字符串，但附加“不要自动去掉首尾空白”的校验配置
    files: list[
        Annotated[str, StringConstraints(strip_whitespace=False)]
    ] = Field(min_length=1, max_length=10)

    # 表示提出这一步的现有代码依据
    source_ids: list[str] = Field(min_length=1, max_length=10)

    # 如何确认这一步达到了目的
    verification: str = Field(min_length=1, max_length=1000)


class ChangePlan(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    summary: str = Field(min_length=1, max_length=1000)

    steps: list[PlanStep] = Field(min_length=1, max_length=8)