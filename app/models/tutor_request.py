from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from app.models.student_state import StudentState


class FocusSkill(BaseModel):
    skill_id: str = Field(min_length=1)
    name_ko: str = Field(min_length=1)
    mastery_after: float = Field(ge=0, le=1, allow_inf_nan=False)
    state_after: str = Field(min_length=1)


class FirstError(BaseModel):
    step_no: int = Field(ge=1, strict=True)
    latex_text: str = Field(min_length=1)
    error_type: str = Field(min_length=1)
    error_subtype: str = Field(min_length=1)
    misconception_ids: list[str]
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)


class TutorRequest(StudentState):
    model_config = ConfigDict(json_schema_extra={"examples": [{'schema_version': '1.0', 'student_id': '17', 'attempt_id': 'attempt-17-02', 'analysis_id': 'analysis-17-02-1', 'analysis_status': 'ANALYZED', 'focus_skill': {'skill_id': 'arithmetic', 'name_ko': '사칙연산과 부호 처리', 'mastery_after': 0.35, 'state_after': 'needs_practice'}, 'first_error': {'step_no': 3, 'latex_text': '(+2) \\times (-3) = +6', 'error_type': 'calculation', 'error_subtype': 'arithmetic_slip', 'misconception_ids': [], 'confidence': 0.75}, 'consecutive_wrong': 2, 'hint_count': 0}]})
    schema_version: Literal["1.0"]
    student_id: str = Field(min_length=1)
    attempt_id: str = Field(min_length=1)
    analysis_id: str = Field(min_length=1)
    analysis_status: str = Field(min_length=1)
    focus_skill: FocusSkill
    first_error: FirstError | None
