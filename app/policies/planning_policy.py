from pydantic import BaseModel, ConfigDict, Field, model_validator


class PlanningPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)
    level_boundaries: tuple[float, float, float, float] = (0.2, 0.4, 0.6, 0.8)
    mastery_threshold: float = Field(default=0.8, gt=0, le=1, allow_inf_nan=False)
    deficit_weight: float = Field(default=0.6, ge=0, le=1, allow_inf_nan=False)
    failure_weight: float = Field(default=0.25, ge=0, le=1, allow_inf_nan=False)
    dependency_weight: float = Field(default=0.15, ge=0, le=1, allow_inf_nan=False)
    success_gain: float = Field(default=0.15, gt=0, le=1, allow_inf_nan=False)
    wrong_penalty: float = Field(default=0.1, gt=0, le=1, allow_inf_nan=False)
    hint_weight: float = Field(default=0.5, gt=0, le=1, allow_inf_nan=False)
    unknown_prior: float = Field(default=0.5, ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_policy(self):
        bounds = self.level_boundaries
        if not all(0 < b < 1 for b in bounds) or any(a >= b for a, b in zip(bounds, bounds[1:])):
            raise ValueError("level_boundaries must be strictly increasing in (0, 1)")
        if abs(self.deficit_weight + self.failure_weight + self.dependency_weight - 1) > 1e-8:
            raise ValueError("priority weights must sum to 1")
        return self
