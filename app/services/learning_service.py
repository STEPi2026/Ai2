from app.agent.concept_agent import ConceptAgent
from app.agent.hint_agent import HintAgent
from app.agent.motivation_agent import MotivationAgent
from app.agent.orchestrator import AnalysisUnavailableError
from app.models.learning import (LearningContent, LearningRequest, LearningResponse,
    LessonRequest, LessonAnswerRequest, RetryRequest, SkillState)
from app.models.tutor_response import TutorAction
from app.policies.tutor_policy import TutorPolicy
from app.services.catalog import FixtureCatalog
from app.services.math_validator import MathValidator
from app.services.problem_generator import ProblemGenerator, ProblemUnavailable
from app.services.reward_service import RewardService
from app.services.tokens import TokenService


class LearningService:
    def __init__(self, catalog: FixtureCatalog, validator: MathValidator, tokens: TokenService,
                 policy: TutorPolicy | None = None):
        self.catalog, self.validator, self.tokens = catalog, validator, tokens
        self.policy = policy if policy is not None else TutorPolicy()
        self.hints, self.concepts = HintAgent(), ConceptAgent(catalog)
        self.motivation = MotivationAgent()
        self.problems = ProblemGenerator(catalog, validator, tokens)
        self.rewards = RewardService()

    def review(self, action: TutorAction, skill_id: str, mastery: float, message: str) -> LearningResponse:
        concept = self.concepts.build(skill_id, mastery)
        return LearningResponse(action_type=action, target_skill_id=skill_id,
            content=LearningContent(message=message, **concept,
                video=self.catalog.video(skill_id, mastery)),
            next_step=TutorAction.RETRY, next_stage='explanation')

    def decide(self, request: LearningRequest) -> LearningResponse:
        analysis = request.analysis
        if analysis.analysis_status != 'ANALYZED':
            raise AnalysisUnavailableError("분석이 완료되지 않아 학습 개입을 결정할 수 없습니다.")
        current = analysis.focus_skill.skill_id
        self.catalog.skill(current)
        self.catalog.state_map(request.skills)
        # AI① focus mastery is authoritative for the current skill.
        states = [s for s in request.skills if s.skill_id != current] + [SkillState(
            skill_id=current, mastery=analysis.focus_skill.mastery_after)]
        mastery = analysis.focus_skill.mastery_after
        repeated_wrong = analysis.consecutive_wrong
        if request.recent_attempts:
            # Backend sends oldest → newest, excluding the current analyzed attempt.
            repeated_wrong = 1 if analysis.first_error else 0
            seen_attempts = {analysis.attempt_id}
            for attempt in request.recent_attempts:
                self.catalog.skill(attempt.skill_id)
                if attempt.attempt_id in seen_attempts:
                    raise ValueError("최근 기록의 attempt_id가 중복되거나 현재 시도와 같습니다.")
                seen_attempts.add(attempt.attempt_id)
            for attempt in reversed(request.recent_attempts):
                if (not analysis.first_error or attempt.correct or attempt.skill_id != current
                        or attempt.error_subtype != analysis.first_error.error_subtype):
                    break
                repeated_wrong += 1
        prerequisite = self.catalog.deficient_prerequisite(current, states, self.policy.mastery_threshold)
        if prerequisite:
            prior_mastery = self.catalog.state_map(states)[prerequisite]
            return self.review(TutorAction.PREREQUISITE_REVIEW, prerequisite, prior_mastery,
                '현재 Skill에 필요한 선수개념부터 짧게 복습해볼까요?')
        unknown = self.catalog.unknown_prerequisite(current, states)
        if unknown:
            return self.review(TutorAction.PREREQUISITE_REVIEW, unknown, 0,
                '선수 Skill의 숙련도 정보가 없어 진단이나 복습으로 먼저 확인해야 해요.')
        if request.disengaged:
            return LearningResponse(action_type=TutorAction.MOTIVATION, target_skill_id=current,
                content=LearningContent(message=self.motivation.message(request.recent_failures)),
                next_step=TutorAction.RETRY)
        if request.stage in ('concept_complete', 'hint_complete', 'check'):
            try:
                problem = self.problems.generate(request)
            except ProblemUnavailable:
                return LearningResponse(action_type=TutorAction.RETRY, target_skill_id=current,
                    content=LearningContent(message='검증된 변형문제를 준비할 수 없어 원래 문제를 다시 풀어보세요.'),
                    next_step=TutorAction.RETRY)
            return LearningResponse(action_type=TutorAction.VARIANT_PROBLEM, target_skill_id=current,
                content=LearningContent(message='같은 풀이 원리를 새 숫자에 적용해볼까요?', problem=problem),
                next_step=TutorAction.RETRY)
        if mastery < self.policy.concept_review_threshold:
            return self.review(TutorAction.CONCEPT_REVIEW, current, mastery, '핵심 개념부터 확인해볼까요?')
        if analysis.first_error:
            if repeated_wrong >= self.policy.repeated_wrong_threshold:
                return self.review(TutorAction.REMEDIATION, current, mastery,
                    '반복해서 어려웠던 계산을 설명과 예제로 나누어 확인해볼까요?')
            if analysis.hint_count < self.policy.max_hint_level:
                level, message = self.hints.build(analysis, self.policy.max_hint_level)
                return LearningResponse(action_type=TutorAction.SOCRATIC_HINT, target_skill_id=current,
                    content=LearningContent(message=message, hint_level=level), next_step=TutorAction.RETRY)
            return self.review(TutorAction.CONCEPT_REVIEW, current, mastery,
                '힌트 이후에도 어려우면 사용한 규칙을 예제로 다시 확인해볼까요?')
        if mastery >= self.policy.mastery_threshold:
            following = self.catalog.next_skill(current, states, self.policy.mastery_threshold)
            return LearningResponse(action_type=TutorAction.NEXT_SKILL if following else TutorAction.PRAISE,
                target_skill_id=current, next_skill_id=following,
                content=LearningContent(message='현재 Skill의 숙련도가 충분해요.' +
                    (' 다음 Skill로 진행해볼까요?' if following else ' 현재 경로의 학습을 마쳤어요.')))
        return LearningResponse(action_type=TutorAction.RETRY, target_skill_id=current,
            content=LearningContent(message='같은 원리를 적용하는 문제를 한 번 더 풀어볼까요?'), next_step=TutorAction.RETRY)

    def lesson(self, request: LessonRequest) -> LearningResponse:
        skill = self.catalog.skill(request.skill_id)
        if request.stage == 'explanation':
            content = LearningContent(message='핵심 규칙을 읽어보세요.', explanation=skill['explanation_easy'])
            next_stage = 'example'
        elif request.stage == 'example':
            content = LearningContent(message='예제에서 규칙이 어떻게 쓰이는지 확인해보세요.', example=skill['example'])
            next_stage = 'check'
        else:
            token = self.tokens.issue('lesson', {'student_id': request.student_id, 'skill_id': request.skill_id})
            content = LearningContent(message='스스로 확인 문제를 풀어보세요.',
                check_question=skill['check_question'], problem={'check_token': token})
            next_stage = None
        return LearningResponse(action_type=TutorAction.CONCEPT_REVIEW, target_skill_id=request.skill_id,
            content=content, next_stage=next_stage)

    def lesson_answer(self, request: LessonAnswerRequest) -> LearningResponse:
        data = self.tokens.read(request.check_token, 'lesson', request.student_id)
        skill = self.catalog.skill(data['skill_id'])
        correct = self.validator.matches_task(request.answer, skill['check_answer'], skill['answer_form'])
        return LearningResponse(action_type=TutorAction.PRAISE if correct else TutorAction.CONCEPT_REVIEW,
            target_skill_id=data['skill_id'], content=LearningContent(message=
                '설명과 예제에서 확인한 규칙을 스스로 적용했어요.' if correct else '예제로 돌아가 사용한 규칙을 다시 확인해볼까요?'),
            next_step=TutorAction.RETRY if correct else TutorAction.CONCEPT_REVIEW,
            next_stage='concept_complete' if correct else 'example')

    def retry(self, request: RetryRequest) -> LearningResponse:
        problem = self.tokens.read(request.problem_token, 'problem', request.student_id)
        self.catalog.skill(problem['skill_id'])
        self.catalog.state_map(request.skills)
        a, b = problem['a'], problem['b']
        expected = str(a * b) if problem['template'] == 'signed_multiplication' else f'(x+({a}))*(x+({b}))'
        correct = self.validator.matches_task(request.answer, expected,
            'expanded' if problem['template'] == 'binomial_expansion' else 'integer')
        if not correct:
            if request.retry_count + 1 >= self.policy.motivation_failure_threshold:
                return LearningResponse(action_type=TutorAction.MOTIVATION, target_skill_id=problem['skill_id'],
                    content=LearningContent(message=self.motivation.message(3)), next_step=TutorAction.CONCEPT_REVIEW,
                    next_stage='explanation')
            return self.review(TutorAction.REMEDIATION, problem['skill_id'], request.mastery_after or 0,
                '이번 풀이에서도 계산을 다시 확인해야 해요. 예제를 보고 재도전해볼까요?')
        events = self.rewards.success_events(request, problem, self.policy.mastery_threshold)
        following = None
        if request.mastery_after is not None and request.mastery_after >= self.policy.mastery_threshold:
            states = [s for s in request.skills if s.skill_id != problem['skill_id']] + [SkillState(
                skill_id=problem['skill_id'], mastery=request.mastery_after)]
            prerequisite = self.catalog.deficient_prerequisite(problem['skill_id'], states, self.policy.mastery_threshold)
            if prerequisite:
                response = self.review(TutorAction.PREREQUISITE_REVIEW, prerequisite,
                    self.catalog.state_map(states)[prerequisite], '이번 문제는 해결했어요. 다음 학습 전에 선수 Skill을 확인해볼까요?')
                response.events = events
                return response
            unknown = self.catalog.unknown_prerequisite(problem['skill_id'], states)
            if unknown:
                response = self.review(TutorAction.PREREQUISITE_REVIEW, unknown, 0,
                    '확인 문제는 해결했어요. 다음 학습 전에 선수 Skill의 숙련도를 확인해주세요.')
                response.events = events
                return response
            following = self.catalog.next_skill(problem['skill_id'], states, self.policy.mastery_threshold)
        return LearningResponse(action_type=TutorAction.NEXT_SKILL if following else TutorAction.PRAISE,
            target_skill_id=problem['skill_id'], next_skill_id=following,
            content=LearningContent(message=self.motivation.praise(problem['hint_count'] > 0, problem['has_error'])),
            next_step=TutorAction.NEXT_SKILL if following else TutorAction.RETRY, events=events)
