from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from app.models.tutor_request import TutorRequest
from app.models.tutor_response import TutorAction


class SkillState(BaseModel):
    skill_id: str = Field(min_length=1)
    mastery: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    evidence_count: int = Field(default=0, ge=0, strict=True)


class SourceProblem(BaseModel):
    template: Literal["signed_multiplication", "binomial_expansion"]
    a: int = Field(ge=-9, le=9, strict=True)
    b: int = Field(ge=-9, le=9, strict=True)
    difficulty: Literal["easy"] = "easy"


class RecentAttempt(BaseModel):
    attempt_id: str = Field(min_length=1)
    skill_id: str = Field(min_length=1)
    correct: bool
    error_subtype: str | None = None
    used_hint: bool = False


class LearningRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{'analysis': {'schema_version': '1.0', 'student_id': '17', 'attempt_id': 'attempt-17-02', 'analysis_id': 'analysis-17-02-1', 'analysis_status': 'ANALYZED', 'focus_skill': {'skill_id': 'arithmetic', 'name_ko': '사칙연산과 부호 처리', 'mastery_after': 0.35, 'state_after': 'needs_practice'}, 'first_error': {'step_no': 3, 'latex_text': '(+2) \\times (-3) = +6', 'error_type': 'calculation', 'error_subtype': 'arithmetic_slip', 'misconception_ids': [], 'confidence': 0.75}, 'consecutive_wrong': 2, 'hint_count': 0}, 'skills': [{'skill_id': 'arithmetic', 'mastery': 0.35, 'evidence_count': 2}], 'stage': 'decision', 'source_problem': {'template': 'signed_multiplication', 'a': 2, 'b': -3, 'difficulty': 'easy'}, 'recent_attempts': [{'attempt_id': 'attempt-17-01', 'skill_id': 'arithmetic', 'correct': False, 'error_subtype': 'arithmetic_slip', 'used_hint': False}]}]})
    analysis: TutorRequest
    skills: list[SkillState] = Field(default_factory=list, max_length=100)
    stage: Literal["decision", "concept_complete", "hint_complete", "check"] = "decision"
    source_problem: SourceProblem | None = None
    variant_index: int = Field(default=0, ge=0, le=10000, strict=True)
    recent_attempts: list[RecentAttempt] = Field(default_factory=list, max_length=20)
    recent_failures: int = Field(default=0, ge=0, le=1000, strict=True)
    disengaged: bool = False


class LearningContent(BaseModel):
    message: str
    hint_level: int | None = None
    explanation: str | None = None
    example: str | None = None
    check_question: str | None = None
    video: dict[str, str] | None = None
    problem: dict[str, str] | None = None


class RewardEvent(BaseModel):
    event_id: str
    event_type: Literal["RETRY_SUCCESS", "MISCONCEPTION_OVERCOME", "SKILL_IMPROVED", "SKILL_MASTERED", "DAILY_GOAL_PROGRESS"]
    student_id: str
    attempt_id: str
    skill_id: str
    metadata: dict[str, str] = Field(default_factory=dict)


class LearningResponse(BaseModel):
    action_type: TutorAction
    target_skill_id: str
    next_skill_id: str | None = None
    content: LearningContent
    next_step: TutorAction | None = None
    next_stage: str | None = None
    events: list[RewardEvent] = Field(default_factory=list)
    data_source: str = "fixture"


class RetryRequest(BaseModel):
    student_id: str = Field(min_length=1)
    attempt_id: str = Field(min_length=1)
    problem_token: str = Field(min_length=1, max_length=10000)
    answer: str = Field(min_length=1, max_length=200)
    skills: list[SkillState] = Field(default_factory=list, max_length=100)
    mastery_after: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    previous_mastery: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    misconception_resolved: bool = False
    retry_count: int = Field(default=0, ge=0, le=1000, strict=True)


class LessonRequest(BaseModel):
    student_id: str = Field(min_length=1)
    skill_id: str = Field(min_length=1)
    stage: Literal["explanation", "example", "check"] = "explanation"


class LessonAnswerRequest(BaseModel):
    student_id: str = Field(min_length=1)
    check_token: str = Field(min_length=1, max_length=10000)
    answer: str = Field(min_length=1, max_length=200)
