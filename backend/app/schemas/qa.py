from uuid import UUID
from pydantic import BaseModel, Field

class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=10)


class SourceReference(BaseModel):
    source_id: str
    chunk_id: UUID
    file_path: str
    symbol_name: str
    start_line: int
    end_line: int


class QuestionResponse(BaseModel):
    repository_id: UUID
    answer: str
    sources: list[SourceReference]