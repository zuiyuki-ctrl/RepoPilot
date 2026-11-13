"""A draft is not a Case registration or an Agent Run."""
from pathlib import PurePosixPath
from uuid import UUID
from pydantic import Field, StrictBool, model_validator
from .platform_run import ProtocolModel
from .platform_catalog import BenchmarkCaseBinding, BenchmarkRegistration
from .experiment import ExperimentCase
from .experiment_definition import AcceptanceRule


class DraftText(ProtocolModel):
    title: str = Field(min_length=1, max_length=100)
    user_request: str = Field(min_length=1, max_length=850)
    editable_files: list[str] = Field(min_length=1, max_length=30)

    @model_validator(mode='after')
    def prose(self):
        if not self.title.strip() or not self.user_request.strip():
            raise ValueError('题名和题面不能为空')
        if any(marker in self.title + self.user_request for marker in ('```', 'diff --git', '*** Begin Patch', '@@ ')):
            raise ValueError('题面不能包含修复补丁或代码块')
        return self


class DraftSelection(ProtocolModel):
    repository_id: UUID
    repository_commit: str = Field(pattern=r'^[0-9a-f]{40}$')
    source_files: list[str] = Field(min_length=1, max_length=30)
    protected_test_files: list[str] = Field(min_length=1, max_length=20)
    acceptance: AcceptanceRule
    test_image: str = Field(pattern=r'^sha256:[0-9a-f]{64}$')
    background: str = Field(default='', max_length=1000)

    def binding(self, text=None, *, case_id='draft', case_version='v1'):
        text = text or DraftText(title='草稿', user_request='待生成', editable_files=self.source_files)
        if not set(text.editable_files) <= set(self.source_files):
            raise ValueError('允许修改的文件必须来自已授权的源码选择，不能添加测试或其他文件')
        return BenchmarkCaseBinding(repository_id=self.repository_id, test_image=self.test_image,
            acceptance=self.acceptance, case=ExperimentCase(case_id=case_id, case_version=case_version,
                task_type='bug_fix', user_request=f'{text.title}\n\n{text.user_request}',
                repository_commit=self.repository_commit, editable_files=text.editable_files,
                protected_test_files=self.protected_test_files, test_profile='python-basic'))

    @model_validator(mode='after')
    def contract(self):
        self.binding()  # Reuse the existing Case path, scope and acceptance validators.
        if any(PurePosixPath(p).name in ('conftest.py', '__init__.py') for p in self.protected_test_files):
            raise ValueError('只支持独立测试模块，不支持 conftest.py 或 __init__.py')
        if len(self.acceptance.required_tests) > 200 or len(self.acceptance.baseline_failure_tests) > 200:
            raise ValueError('第一版最多声明 200 个测试项')
        if self.acceptance.manual_criteria:
            raise ValueError('草稿第一版只支持自动化验收规则')
        if any(len(t.classname) > 500 or len(t.name) > 1000 for t in self.acceptance.required_tests):
            raise ValueError('测试标识过长')
        return self


class DraftCreate(ProtocolModel):
    selection: DraftSelection
    preview_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    request_key: UUID
    allow_model: StrictBool
    allow_baseline_tests: StrictBool

    @model_validator(mode='after')
    def consent(self):
        if not self.allow_model or not self.allow_baseline_tests:
            raise ValueError('必须显式授权发送预览文件并运行隔离基线测试')
        return self


class DraftRevision(ProtocolModel):
    revision: int = Field(ge=0)


class DraftEdit(DraftRevision):
    text: DraftText


class DraftConfirm(DraftRevision):
    suite_name: str = Field(min_length=1, max_length=100, pattern=r'^\S(?:.*\S)?$')
    suite_version: str = Field(min_length=1, max_length=100, pattern=r'^\S(?:.*\S)?$')
    case_id: str = Field(min_length=1, max_length=100, pattern=r'^\S(?:.*\S)?$')
    case_version: str = Field(min_length=1, max_length=100, pattern=r'^\S(?:.*\S)?$')

    def registration(self, selection, text):
        return BenchmarkRegistration(name=self.suite_name, version=self.suite_version,
            cases=[selection.binding(text, case_id=self.case_id, case_version=self.case_version)])
