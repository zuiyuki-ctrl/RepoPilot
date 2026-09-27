from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# 模型提出的修改候选
class FileEditProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    # 准备修改的那个文件
    file_path: str = Field(min_length=1)

    # 简短说明本次改了什么
    summary: str = Field(min_length=1, max_length=1000)

    # 修改后的完整文件内容
    content: str = Field(min_length=1)


# 告诉程序“这次生成哪个文件的候选”
class TaskFileEditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    # 非空字符串，不自动去除首尾空白。
    file_path: str = Field(min_length=1)


# 程序返回给用户的完整生成结果
class TaskFileEditRead(BaseModel):
    task_id: UUID

    repository_id: UUID

    # 读取原文件时得到的 SHA-256。
    base_file_hash: str

    proposal: FileEditProposal


# 用户要求应用候选
class TaskFileEditApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    # 必须是 64 位小写十六进制字符
    base_file_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    proposal: FileEditProposal