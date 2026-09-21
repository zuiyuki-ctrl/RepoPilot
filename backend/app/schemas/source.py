from uuid import UUID
from pydantic import BaseModel

# 定义源码片段的返回格式
class SourceRead(BaseModel):
    repository_id: UUID
    file_path: str # 仓库相对路径
    file_hash: str # 本次读取内容的哈希
    start_line: int
    end_line: int # 实际返回的行号
    total_lines: int # 文件总行数
    content: str # 选中的原始源码
