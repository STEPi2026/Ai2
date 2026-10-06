import hashlib
from app.models.learning import RewardEvent, RetryRequest


class RewardService:
    def success_events(self, request: RetryRequest, problem: dict, mastery_threshold: float) -> list[RewardEvent]:
        kinds = ['RETRY_SUCCESS', 'DAILY_GOAL_PROGRESS']
        # Backend supplies confirmed misconception and mastery transitions.
        if request.misconception_resolved and problem['misconception_ids']:
            kinds.append('MISCONCEPTION_OVERCOME')
        before, after = request.previous_mastery, request.mastery_after
        if before is not None and after is not None and after > before:
            kinds.append('SKILL_IMPROVED')
            if before < mastery_threshold <= after:
                kinds.append('SKILL_MASTERED')
        events = []
        for kind in kinds:
            # Stable for one student/problem, including repeated HTTP submissions/attempt IDs.
            identity = f"{request.student_id}:{problem['problem_id']}:{kind}"
            events.append(RewardEvent(event_id=hashlib.sha256(identity.encode()).hexdigest(),
                event_type=kind, student_id=request.student_id, attempt_id=request.attempt_id,
                skill_id=problem['skill_id'], metadata={'problem_id': problem['problem_id']}))
        return events
