from enum import Enum
from pydantic import BaseModel


class TutorAction(str, Enum):
    SOCRATIC_HINT = "SOCRATIC_HINT"
    CONCEPT_REVIEW = "CONCEPT_REVIEW"
    PREREQUISITE_REVIEW = "PREREQUISITE_REVIEW"
    REMEDIATION = "REMEDIATION"
    VARIANT_PROBLEM = "VARIANT_PROBLEM"
    RETRY = "RETRY"
    NEXT_SKILL = "NEXT_SKILL"
    PRAISE = "PRAISE"
    MOTIVATION = "MOTIVATION"


class TutorTarget(BaseModel):
    skill_id: str
    error_type: str | None = None
    error_subtype: str | None = None


class TutorContent(BaseModel):
    message: str


class TutorResponse(BaseModel):
    action_type: TutorAction
    target: TutorTarget
    content: TutorContent
    next_step: TutorAction | None = None
    reward_event: None = None
