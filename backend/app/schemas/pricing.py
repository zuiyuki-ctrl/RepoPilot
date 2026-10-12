"""用户核实的价格快照；不内置或联网获取供应商价格。"""
from datetime import date
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field


class ModelPrice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_per_million: Decimal = Field(ge=0, allow_inf_nan=False)
    output_per_million: Decimal = Field(ge=0, allow_inf_nan=False)
    # None 表示输入统一计价；非 None 需要供应商返回缓存计数。
    cached_input_per_million: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)


class PricingSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str = Field(min_length=1)
    currency: str = Field(min_length=1)
    effective_date: date
    source: str = Field(min_length=1)
    models: dict[str, ModelPrice] = Field(min_length=1)
