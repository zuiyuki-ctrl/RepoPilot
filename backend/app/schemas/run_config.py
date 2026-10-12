from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


RetrievalStrategy = Literal["vector", "keyword", "hybrid"]
RetrievalPolicy = Literal["auto", "vector", "hybrid"]


class AgentRunConfig(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
    )

    schema_version: Literal[1] = 1
    retrieval_policy: RetrievalPolicy = "auto"
    max_tool_calls: int = Field(default=4, ge=1, le=8)
    runtime_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    index_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    test_image_id: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    experiment_contract_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    def resolve_retrieval_strategy(
        self,
        requested_strategy: RetrievalStrategy,
    ) -> RetrievalStrategy:
        if self.retrieval_policy == "auto":
            return requested_strategy

        return self.retrieval_policy
