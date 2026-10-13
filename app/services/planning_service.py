import hashlib
import json
from app.models.planning import (LevelResult, MasteryLevel, PlanningRequest, PlanningResponse,
    PriorityItem, RoadmapStep, StateUpdateRequest, StateUpdateResponse)
from app.models.learning import SkillState
from app.policies.planning_policy import PlanningPolicy
from app.services.catalog import FixtureCatalog


def classify(mastery: float | None, policy: PlanningPolicy | None = None) -> LevelResult:
    if mastery is None:
        return LevelResult(mastery=None, level=None, label_ko="미진단")
    if not 0 <= mastery <= 1:
        raise ValueError("mastery must be in [0, 1]")
    policy = policy or PlanningPolicy()
    index = sum(mastery >= boundary for boundary in policy.level_boundaries)
    levels = list(MasteryLevel)
    return LevelResult(mastery=mastery, level=levels[index],
        label_ko=["기초 시작", "기초 이해", "발전 중", "능숙", "숙달"][index])


class PlanningService:
    def __init__(self, catalog: FixtureCatalog, policy: PlanningPolicy | None = None):
        self.catalog = catalog
        self.policy = policy or PlanningPolicy()

    def plan(self, request: PlanningRequest) -> PlanningResponse:
        mastery = self.catalog.state_map(request.skills)
        if len(set(request.goal_skill_ids)) != len(request.goal_skill_ids):
            raise ValueError("목표 Skill이 중복되었습니다.")
        goals = request.goal_skill_ids or list(self.catalog.skills)
        needed = set()
        def include(skill_id):
            skill = self.catalog.skill(skill_id)
            if skill_id in needed:
                return
            needed.add(skill_id)
            for predecessor in skill['prerequisites']:
                include(predecessor)
        for goal in goals:
            include(goal)
        failures = {}
        seen = set()
        for attempt in request.recent_attempts:
            self.catalog.skill(attempt.skill_id)
            if attempt.attempt_id in seen:
                raise ValueError("최근 시도 ID가 중복되었습니다.")
            seen.add(attempt.attempt_id)
            failures[attempt.skill_id] = 0 if attempt.correct else failures.get(attempt.skill_id, 0) + 1
        candidates = needed - {s for s, m in mastery.items() if m is not None and m >= self.policy.mastery_threshold}
        priorities = []
        for skill_id in sorted(candidates):
            value = mastery.get(skill_id)
            dependencies = sum(skill_id in self.catalog.skill(other)['prerequisites'] for other in needed)
            score = (self.policy.deficit_weight * (1 - value if value is not None else 0.5)
                     + self.policy.failure_weight * min(failures.get(skill_id, 0) / 3, 1)
                     + self.policy.dependency_weight * dependencies / max(len(needed) - 1, 1))
            predecessors = self.catalog.skill(skill_id)['prerequisites']
            ready = all(mastery.get(p) is not None and mastery[p] >= self.policy.mastery_threshold for p in predecessors)
            reasons = ["숙련도 미확인: 진단 필요" if value is None else f"숙련도 {value:.2f}"]
            if failures.get(skill_id):
                reasons.append(f"최근 연속 실패 {failures[skill_id]}회")
            if dependencies:
                reasons.append(f"후속 Skill {dependencies}개의 선수개념")
            if not ready:
                reasons.append("선수 Skill 확인/학습 필요")
            priorities.append(PriorityItem(skill_id=skill_id, mastery=value,
                level=classify(value, self.policy).level, score=round(score, 6), ready=ready, reasons=reasons))
        priorities.sort(key=lambda item: (-item.score, item.skill_id))
        pending = {item.skill_id for item in priorities}
        ordered = []
        while pending:
            eligible = [item for item in priorities if item.skill_id in pending and
                        not (set(self.catalog.skill(item.skill_id)['prerequisites']) & pending)]
            if not eligible:
                raise ValueError("선수 Skill 그래프에 순환 관계가 있습니다.")
            chosen = eligible[0]
            ordered.append(chosen)
            pending.remove(chosen.skill_id)
        steps = [RoadmapStep(order=i + 1, skill_id=item.skill_id,
            kind='DIAGNOSTIC' if item.mastery is None else
                 'CONCEPT_REVIEW' if item.mastery < 0.4 else 'PRACTICE',
            prerequisites=self.catalog.skill(item.skill_id)['prerequisites'],
            ready=item.ready, reason=' / '.join(item.reasons)) for i, item in enumerate(ordered)]
        identity = json.dumps({'student': request.student_id, 'goals': sorted(goals),
            'states': sorted([s.model_dump() for s in request.skills], key=lambda s: s['skill_id']),
            'recent': [s.model_dump() for s in request.recent_attempts], 'policy': self.policy.model_dump(),
            'catalog': self.catalog.data}, sort_keys=True, ensure_ascii=False)
        return PlanningResponse(student_id=request.student_id,
            roadmap_id='roadmap-' + hashlib.sha256(identity.encode()).hexdigest()[:24],
            previous_roadmap_id=request.previous_roadmap_id, priorities=priorities,
            steps=steps, next_skill_id=steps[0].skill_id if steps else None,
            completed=not steps, data_source=self.catalog.data_source)

    def update(self, request: StateUpdateRequest) -> StateUpdateResponse:
        self.catalog.state_map(request.skills)
        observation = request.observation
        self.catalog.skill(observation.skill_id)
        states = {s.skill_id: s.model_copy(deep=True) for s in request.skills}
        current = states.get(observation.skill_id, SkillState(skill_id=observation.skill_id))
        duplicate = observation.attempt_id in request.applied_attempt_ids
        if duplicate and observation.skill_id not in states:
            raise ValueError('이미 적용된 시도의 현재 Skill 상태가 필요합니다.')
        if not duplicate:
            previous = current.mastery if current.mastery is not None else self.policy.unknown_prior
            gain = self.policy.success_gain * (self.policy.hint_weight if observation.used_hint else 1)
            after = previous + gain * (1 - previous) if observation.correct else previous * (1 - self.policy.wrong_penalty)
            current = SkillState(skill_id=observation.skill_id, mastery=round(after, 6),
                                 evidence_count=current.evidence_count + 1)
            states[observation.skill_id] = current
        update_id = hashlib.sha256(f"{request.student_id}:{observation.attempt_id}".encode()).hexdigest()
        return StateUpdateResponse(update_id=update_id, student_id=request.student_id,
            expected_version=request.expected_version,
            proposed_version=request.expected_version + (0 if duplicate else 1), applied=not duplicate,
            skills=list(states.values()), changed_skill=classify(current.mastery, self.policy))
