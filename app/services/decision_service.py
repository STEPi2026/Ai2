from app.agent.orchestrator import TutorOrchestrator
from app.models.tutor_request import TutorRequest
from app.models.tutor_response import TutorAction, TutorContent, TutorResponse, TutorTarget


class DecisionService:
    def __init__(self, orchestrator: TutorOrchestrator | None = None):
        self.orchestrator = orchestrator if orchestrator is not None else TutorOrchestrator()

    def decide(self, request: TutorRequest) -> TutorResponse:
        action = self.orchestrator.decide(request)
        skill = request.focus_skill
        error = request.first_error
        messages = {
            TutorAction.CONCEPT_REVIEW: f"{skill.name_ko}의 핵심 개념을 확인한 뒤 다시 풀어볼까요?",
            TutorAction.REMEDIATION: f"{skill.name_ko}에서 어려움이 반복되고 있어요. 틀린 단계에 사용한 규칙을 확인해볼까요?",
            TutorAction.SOCRATIC_HINT: f"{error.step_no if error else ''}번째 풀이 단계에서 사용한 계산이나 규칙을 다시 확인해볼까요?",
            TutorAction.RETRY: "풀이에 사용한 규칙을 확인하고 스스로 다시 풀어볼까요?",
            TutorAction.NEXT_SKILL: f"{skill.name_ko}의 숙련도가 충분해요. 다음 Skill 학습으로 진행해볼까요?",
        }
        return TutorResponse(
            action_type=action,
            target=TutorTarget(skill_id=skill.skill_id,
                               error_type=error.error_type if error else None,
                               error_subtype=error.error_subtype if error else None),
            content=TutorContent(message=messages[action]),
            next_step=None if action == TutorAction.NEXT_SKILL else TutorAction.RETRY,
            reward_event=None,
        )
