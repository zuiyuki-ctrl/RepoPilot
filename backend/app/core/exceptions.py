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