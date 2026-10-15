"""Versioned non-secret registrations; user cannot set Ready or validated capabilities."""
from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import Field, model_validator
from .platform_run import ProtocolModel, CapabilityName
from .process_agent import ProcessConfiguration
from .run_config import AgentRunConfig
from .experiment import ExperimentCase
from .experiment_definition import AcceptanceRule


class AgentRegistration(ProtocolModel):
    protocol_version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=100, pattern=r'^\S(?:.*\S)?$')
    version: str = Field(min_length=1, max_length=100, pattern=r'^\S(?:.*\S)?$')
    adapter: Literal['native', 'process']
    process: ProcessConfiguration | None = None
    native: AgentRunConfig | None = None
    declared_capabilities: list[CapabilityName] = Field(default_factory=lambda: ['execution'])

    @model_validator(mode='after')
    def coherent(self):
        if (self.adapter == 'process') != (self.process is not None):
            raise ValueError('Process adapter requires exactly its process configuration')
        if (self.adapter == 'native') != (self.native is not None):
            raise ValueError('Native adapter requires exactly its native configuration')
        if len(set(self.declared_capabilities)) != len(self.declared_capabilities):
            raise ValueError('Duplicate capability declaration')
        return self


class BenchmarkCaseBinding(ProtocolModel):
    repository_id: UUID
    case: ExperimentCase
    acceptance: AcceptanceRule
    test_image: str = Field(pattern=r'^sha256:[0-9a-f]{64}$')

    @model_validator(mode='after')
    def contract(self):
        if self.case.test_profile != 'python-basic':
            raise ValueError('Only python-basic is supported')
        if self.case.task_type == 'bug_fix' and not self.acceptance.baseline_failure_tests:
            raise ValueError('Bug fix requires declared baseline failures')
        modules = [p[:-3].replace('/', '.') for p in self.case.protected_test_files]
        if any(not any(t.classname == m or t.classname.startswith(m + '.') for m in modules)
               for t in self.acceptance.required_tests):
            raise ValueError('Required tests must belong to protected test modules')
        return self


class BenchmarkRegistration(ProtocolModel):
    protocol_version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=100, pattern=r'^\S(?:.*\S)?$')
    version: str = Field(min_length=1, max_length=100, pattern=r'^\S(?:.*\S)?$')
    cases: list[BenchmarkCaseBinding] = Field(min_length=1, max_length=20)

    @model_validator(mode='after')
    def unique_cases(self):
        identities = [(item.case.case_id, item.case.case_version) for item in self.cases]
        if len(set(identities)) != len(identities):
            raise ValueError('Duplicate case versions in suite')
        return self


class ValidationRequest(ProtocolModel):
    request_key: UUID


class CatalogRead(ProtocolModel):
    id: UUID
    name: str
    version: str
    content_sha256: str
    status: str
    descriptor: dict
    validation: dict | None
    created_at: datetime


class ValidationRead(ProtocolModel):
    id: UUID
    status: str
    report: dict | None
    created_at: datetime
    completed_at: datetime | None
