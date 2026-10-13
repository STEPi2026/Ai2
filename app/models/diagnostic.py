from pydantic import BaseModel, Field
from app.models.learning import SkillState


class DiagnosticStart(BaseModel):
    student_id: str = Field(min_length=1)


class DiagnosticAnswer(BaseModel):
    student_id: str = Field(min_length=1)
    session_token: str = Field(min_length=1, max_length=20000)
    question_id: str = Field(min_length=1)
    answer: str = Field(min_length=1, max_length=200)


class DiagnosticResponse(BaseModel):
    completed: bool
    question: dict[str, str] | None = None
    session_token: str | None = None
    knowledge_map: list[SkillState]
    answered_count: int
    last_correct: bool | None = None
    data_source: str = "fixture"
