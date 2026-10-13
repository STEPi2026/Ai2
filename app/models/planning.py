from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from app.models.learning import SkillState, RecentAttempt
from app.models.mastery import MasteryLevel


class LevelResult(BaseModel):
    mastery: float | None
    level: MasteryLevel | None
    label_ko: str


class PlanningRequest(BaseModel):
    student_id: str = Field(min_length=1)
    skills: list[SkillState] = Field(default_factory=list, max_length=100)
    goal_skill_ids: list[str] = Field(default_factory=list, max_length=100)
    recent_attempts: list[RecentAttempt] = Field(default_factory=list, max_length=20)
    previous_roadmap_id: str | None = None


class PriorityItem(BaseModel):
    skill_id: str
    mastery: float | None
    level: MasteryLevel | None
    score: float
    ready: bool
    reasons: list[str]


class RoadmapStep(BaseModel):
    order: int
    skill_id: str
    kind: Literal["DIAGNOSTIC", "CONCEPT_REVIEW", "PRACTICE"]
    prerequisites: list[str]
    ready: bool
    reason: str


class PlanningResponse(BaseModel):
    student_id: str
    roadmap_id: str
    previous_roadmap_id: str | None
    priorities: list[PriorityItem]
    steps: list[RoadmapStep]
    next_skill_id: str | None
    completed: bool
    data_source: str


class Observation(BaseModel):
    attempt_id: str = Field(min_length=1)
    skill_id: str = Field(min_length=1)
    correct: bool
    used_hint: bool = False


class StateUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    student_id: str = Field(min_length=1)
    expected_version: int = Field(ge=0, strict=True)
    skills: list[SkillState] = Field(default_factory=list, max_length=100)
    observation: Observation
    applied_attempt_ids: list[str] = Field(default_factory=list, max_length=500)


class StateUpdateResponse(BaseModel):
    update_id: str
    student_id: str
    expected_version: int
    proposed_version: int
    applied: bool
    skills: list[SkillState]
    changed_skill: LevelResult
    policy_version: str = "ewma-proposal-1.0"
    persistence_owner: str = "Backend"
