from typing import Literal, Protocol
from pydantic import Field
from ...schemas.platform_run import AgentRunRequest, ProtocolModel


class StepResult(ProtocolModel):
    state: dict = Field(default_factory=dict)
    next_stage: str | None = None
    checkpoint_kind: Literal['plan', 'candidate'] | None = None
    checkpoint_payload: dict | None = None
    execution_status: Literal['completed', 'failed', 'cancelled', 'timed_out'] | None = None


class Adapter(Protocol):
    def metadata(self) -> dict: ...
    def prepare(self, request: AgentRunRequest, state: dict) -> StepResult: ...
    def run(self, request: AgentRunRequest, stage: str, state: dict) -> StepResult: ...
    def cleanup(self) -> dict: ...


def get_adapter(name: str) -> Adapter:
    if name == 'native':
        from .native import NativeAdapter
        return NativeAdapter()
    if name == 'process':
        from .process import ProcessAdapter
        return ProcessAdapter()
    raise ValueError('Adapter is not implemented')
