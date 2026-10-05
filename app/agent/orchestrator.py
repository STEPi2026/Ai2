from app.models.tutor_request import TutorRequest
from app.models.tutor_response import TutorAction
from app.policies.tutor_policy import TutorPolicy


class AnalysisUnavailableError(ValueError):
    """The analysis cannot support a tutoring decision."""


class TutorOrchestrator:
    def __init__(self, policy: TutorPolicy | None = None):
        self.policy = policy if policy is not None else TutorPolicy()

    def decide(self, request: TutorRequest) -> TutorAction:
        if request.analysis_status != "ANALYZED":
            raise AnalysisUnavailableError("분석이 완료되지 않아 학습 개입을 결정할 수 없습니다.")
        if request.focus_skill.mastery_after < self.policy.concept_review_threshold:
            return TutorAction.CONCEPT_REVIEW
        if request.first_error is not None:
            if request.consecutive_wrong >= self.policy.repeated_wrong_threshold:
                return TutorAction.REMEDIATION
            if request.hint_count == 0:
                return TutorAction.SOCRATIC_HINT
            return TutorAction.RETRY
        if request.focus_skill.mastery_after >= self.policy.mastery_threshold:
            return TutorAction.NEXT_SKILL
        return TutorAction.RETRY
