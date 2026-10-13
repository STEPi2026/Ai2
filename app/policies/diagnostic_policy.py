from pydantic import BaseModel, ConfigDict, Field


class DiagnosticPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)
    prerequisite_threshold: float = Field(default=0.5, ge=0, le=1, allow_inf_nan=False)
    max_questions: int = Field(default=12, ge=1, le=50, strict=True)
    evidence_per_skill: int = Field(default=2, ge=1, le=10, strict=True)
