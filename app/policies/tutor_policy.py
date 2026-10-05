from pydantic import BaseModel, ConfigDict, Field, model_validator


class TutorPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)
    concept_review_threshold: float = Field(default=0.25, ge=0, le=1, allow_inf_nan=False)
    mastery_threshold: float = Field(default=0.8, ge=0, le=1, allow_inf_nan=False)
    repeated_wrong_threshold: int = Field(default=3, ge=2, strict=True)

    @model_validator(mode="after")
    def validate_thresholds(self) -> "TutorPolicy":
        if self.concept_review_threshold >= self.mastery_threshold:
            raise ValueError("concept_review_threshold must be below mastery_threshold")
        return self
