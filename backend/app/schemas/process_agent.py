"""Day 3 offline container protocol. No host mounts, environment or shell configuration."""
from typing import Literal
from pydantic import Field, model_validator, model_serializer
from .model_gateway import ModelPolicy
from .platform_run import ProtocolModel, Hash


class ProcessConfiguration(ProtocolModel):
    protocol_version: Literal[1] = 1
    image: str = Field(pattern=r'^sha256:[0-9a-f]{64}$')
    argv: list[str] = Field(min_length=1, max_length=32)
    trace: bool = False
    model_policy: ModelPolicy | None = None

    @model_serializer(mode='wrap')
    def stable_offline_configuration(self, handler):
        value = handler(self)
        # Do not add a null field to old registered descriptors/config hashes.
        if self.model_policy is None:
            value.pop('model_policy', None)
        return value

    @model_validator(mode='after')
    def bounded_arguments(self):
        if any(not arg or len(arg) > 2048 or '\x00' in arg for arg in self.argv):
            raise ValueError('Invalid process argument')
        return self


class ProcessTraceEvent(ProtocolModel):
    protocol_version: Literal[1] = 1
    event_id: str = Field(min_length=1, max_length=100)
    run_id: str = Field(min_length=1, max_length=36)
    kind: Literal['model_call', 'tool_call', 'retrieval', 'context', 'planning', 'reflection']
    call_id: str | None = Field(default=None, max_length=100)
    # Deliberately no arbitrary payload or secret environment in this first projection.
    input_tokens: int | None = Field(default=None, ge=0, strict=True)
    output_tokens: int | None = Field(default=None, ge=0, strict=True)
    total_tokens: int | None = Field(default=None, ge=0, strict=True)
    content_sha256: Hash | None = None

    @model_validator(mode='after')
    def coherent_usage(self):
        values = (self.input_tokens, self.output_tokens, self.total_tokens)
        if any(v is not None for v in values) and (self.kind != 'model_call' or not self.call_id):
            raise ValueError('Usage requires a model call identity')
        if all(v is not None for v in values) and values[0] + values[1] != values[2]:
            raise ValueError('Inconsistent token counts')
        return self
