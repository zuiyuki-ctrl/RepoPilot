from pydantic import BaseModel, ConfigDict, Field


class SearchCodeArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    query: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=5)


class ReadSourceArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    file_path: str = Field(min_length=1)
    start_line: int = Field(default=1, ge=1)
    end_line: int = Field(default=100, ge=1)