class InvalidRepositoryInputError(ValueError):
    """仓库输入不符合业务要求。"""

class RepositoryInspectionError(RuntimeError):
    """源仓库检查因运行环境或执行问题失败。"""

class WorkspaceCreationError(RuntimeError):
    """无法创建仓库工作副本。"""

class RepositoryScanError(RuntimeError):
    """无法扫描工作目录"""

class FileSkippedError(Exception):
    """文件因明确的处理策略被跳过。"""

class RepositoryBusyError(RuntimeError):
    """仓库当前被其他操作占用。"""

class InvalidAnswerCitationError(RuntimeError):
    """生成回答缺少引用，或引用了不存在的证据编号。"""

class InvalidTaskInputError(ValueError):
    """任务输入不符合业务要求。"""

class TaskStateConflictError(RuntimeError):
    """任务当前状态不允许执行。"""

class TaskExecutionError(RuntimeError):
    """任务执行无法完成。"""

class InvalidPlanError(ValueError):
    """模型生成的计划格式或引用不合法。"""

class InsufficientPlanEvidenceError(RuntimeError):
    """当前没有足够的代码证据用于生成计划。"""

class InvalidWorkspacePathError(ValueError):
    """计划中的文件路径不能安全地映射到仓库工作副本。"""

class WorkspaceWriteError(RuntimeError):
    """向仓库工作副本写入文件失败。"""

class PlanScopeViolationError(RuntimeError):
    """执行操作超出了用户批准的计划范围。"""

class WorkspaceDiffError(RuntimeError):
    """无法安全读取仓库工作副本的 Git 差异。"""

class WorkspaceWritePersistenceError(RuntimeError):
    """文件已写入，但修改事件或事务提交未确认成功。"""

class InvalidEditProposalError(ValueError):
    """模型生成的文件修改格式、目标或源码不合法。"""

class WorkspaceFileConflictError(RuntimeError):
    """当前文件与生成候选时的原文不一致。"""

class SandboxPreparationError(RuntimeError):
    """无法准备测试沙箱的输入快照。"""

class SandboxExecutionError(RuntimeError):
    """无法启动或管理 Docker 测试沙箱。"""

class RetryBudgetExceededError(RuntimeError):
    """任务已经用完允许的 Reflection 重试次数。"""

class InvalidReflectionError(ValueError):
    """模型返回的 Reflection 决策不合法。"""