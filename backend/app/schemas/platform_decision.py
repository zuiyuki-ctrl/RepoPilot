"""Batch quality gates; resource gates are not yet supported."""
from typing import Literal
from uuid import UUID
from pydantic import ConfigDict, Field
from .platform_run import ProtocolModel


class QualityPolicy(ProtocolModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    version: Literal[1] = 1
    min_pairs: int = Field(ge=1, le=20, strict=True)
    min_cases: int = Field(ge=1, le=20, strict=True)
    max_regressions: int = Field(ge=0, le=20, strict=True)
    min_pass_delta_pp: float = Field(ge=-100, le=100)


class ExperimentReviewRequest(ProtocolModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    request_key: UUID
    comparison_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    reviewer: str = Field(min_length=1, max_length=100)
    action: Literal['adopt_candidate', 'keep_baseline', 'continue_experiment']
    rationale: str = Field(min_length=1, max_length=2000)
