from pydantic import BaseModel, Field


class StudentState(BaseModel):
    consecutive_wrong: int = Field(ge=0, strict=True)
    hint_count: int = Field(ge=0, strict=True)
