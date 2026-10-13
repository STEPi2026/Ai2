from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import streamlit as st
from pydantic import ValidationError
from app.models.learning import LearningRequest
from app.policies.tutor_policy import TutorPolicy
from app.services.catalog import FixtureCatalog
from app.services.learning_service import LearningService
from app.services.math_validator import MathValidator
from app.services.tokens import tokens

st.set_page_config(page_title="STEPi AI② 판단 실험실", layout="wide")
st.title("STEPi AI② 판단 실험실")
st.caption("테스트용 학생 상황과 정책을 바꿔 실제 판단·콘텐츠를 비교합니다. 변경한 정책은 이 화면에서만 적용됩니다.")
catalog = FixtureCatalog()

with st.sidebar:
    st.header("판단 정책")
    concept = st.slider("개념 복습 기준 (미만)", 0.0, 0.95, 0.25, 0.05)
    mastered = st.slider("숙달 기준 (이상)", 0.05, 1.0, 0.8, 0.05)
    repeats = st.number_input("반복 오류 기준", 2, 10, 3)
    max_hints = st.slider("최대 힌트 단계", 1, 3, 3)
    motivation = st.number_input("동기부여 개입 실패 기준", 1, 10, 3)
    st.info("기본 정책과 조정 정책을 같은 학생 상황에 적용합니다.")

left, right = st.columns(2)
with left:
    st.subheader("학생 상황")
    skill_id = st.selectbox("Skill", list(catalog.skills), format_func=lambda value: catalog.skill(value)['name_ko'])
    mastery = st.slider("현재 숙련도", 0.0, 1.0, 0.35, 0.05)
    wrong = st.number_input("연속 실패 횟수", 0, 20, 2)
    hint_count = st.number_input("이미 사용한 힌트 횟수", 0, 10, 0)
    has_error = st.checkbox("현재 오류 있음", True)
    disengaged = st.checkbox("학습 이탈 신호 있음", False)
    stage = st.selectbox("학습 진행 상태", ['decision', 'hint_complete', 'concept_complete', 'check'])
    prerequisite_mastery = st.slider("선수 Skill 숙련도", 0.0, 1.0, 0.9, 0.05)
    missing_prerequisites = st.checkbox("선수 Skill 정보 없음", False)

sample = json.loads((ROOT / 'examples/learning_request.json').read_text())
sample['analysis']['focus_skill'].update(skill_id=skill_id, name_ko=catalog.skill(skill_id)['name_ko'], mastery_after=mastery)
sample['analysis'].update(consecutive_wrong=int(wrong), hint_count=int(hint_count))
if not has_error:
    sample['analysis']['first_error'] = None
sample.update(recent_attempts=[], recent_failures=int(wrong), disengaged=disengaged, stage=stage)
sample['skills'] = [] if missing_prerequisites else [
    {'skill_id': value, 'mastery': prerequisite_mastery} for value in catalog.skills if value != skill_id]
sample['source_problem']['template'] = 'signed_multiplication' if skill_id == 'arithmetic' else 'binomial_expansion'

with right:
    st.subheader("판단 결과")
    try:
        request = LearningRequest.model_validate(sample)
        adjusted = TutorPolicy(concept_review_threshold=concept, mastery_threshold=mastered,
            repeated_wrong_threshold=int(repeats), max_hint_level=max_hints,
            motivation_failure_threshold=int(motivation))
        baseline = LearningService(catalog, MathValidator(), tokens, TutorPolicy()).decide(request)
        result = LearningService(catalog, MathValidator(), tokens, adjusted).decide(request)
        a, b = st.columns(2)
        a.metric("기본 정책", baseline.action_type.value)
        b.metric("조정 정책", result.action_type.value)
        if baseline.action_type != result.action_type:
            st.success("같은 학생 상황에서 정책 변경으로 Action이 달라졌습니다.")
        st.write(result.content.message)
        for title, field in [('개념 설명', 'explanation'), ('예제', 'example'), ('확인문제', 'check_question')]:
            value = getattr(result.content, field)
            if value:
                st.markdown(f"**{title}**")
                st.write(value)
        if result.content.hint_level:
            st.caption(f"힌트 Level {result.content.hint_level}")
        if result.content.problem:
            st.markdown("**변형문제**")
            st.write(result.content.problem['prompt'])
        if result.next_skill_id:
            st.write("다음 Skill:", catalog.skill(result.next_skill_id)['name_ko'])
        if result.content.video:
            st.caption("영상은 테스트용 메타데이터이며 실제 재생 URL이 아닙니다.")
        with st.expander("정책·요청·응답 자세히 보기"):
            st.json(adjusted.model_dump())
            st.json(sample)
            response = result.model_dump(mode='json')
            if response['content']['problem']:
                response['content']['problem'].pop('problem_token', None)
            st.json(response)
    except ValidationError:
        st.error("개념 복습 기준은 숙달 기준보다 작아야 합니다. 왼쪽 정책값을 조정해주세요.")
    except ValueError as exc:
        st.error(str(exc))

st.caption("값을 바꾸면 자동으로 다시 판단합니다. 실제 학습 효과를 검증한 결과가 아니라 현재 규칙의 동작을 확인하는 화면입니다.")


st.divider()
st.header("학습경로·상태 갱신·영상 실험")
st.caption("아래 실험은 화면 안의 가상 학생 상태만 변경하며 Backend DB에는 저장하지 않습니다.")
from app.models.learning import SkillState
from app.models.planning import PlanningRequest, StateUpdateRequest
from app.policies.planning_policy import PlanningPolicy
from app.services.planning_service import PlanningService, classify
from app.models.integration import VideoRankRequest, VideoCandidate
from app.services.video_service import VideoService

path_tab, update_tab, video_tab = st.tabs(["학습경로·숙련도", "학습 후 상태 갱신", "영상 후보 Ranking"])
with path_tab:
    st.caption("숙련도 단계: 0.2 / 0.4 / 0.6 / 0.8 경계로 기초 시작 → 기초 이해 → 발전 중 → 능숙 → 숙달")
    if 'map_skills' not in st.session_state:
        st.session_state.map_skills = [SkillState(skill_id=value, mastery=0.35).model_dump() for value in catalog.skills]
        st.session_state.map_version = 0
        st.session_state.map_applied = []
    roadmap_states = []
    for value in catalog.skills:
        with st.container():
            amount = st.slider(catalog.skill(value)['name_ko'] + " 숙련도", 0.0, 1.0, 0.35, 0.05, key='map_' + value)
            unknown = st.checkbox(catalog.skill(value)['name_ko'] + " 미진단", key='unknown_' + value)
            roadmap_states.append(SkillState(skill_id=value, mastery=None if unknown else amount))
    goals = st.multiselect("목표 Skill (비우면 전체)", list(catalog.skills), default=['factoring'],
                           format_func=lambda value: catalog.skill(value)['name_ko'])
    planner = PlanningService(catalog)
    path_request = PlanningRequest(student_id='dashboard-student', skills=roadmap_states, goal_skill_ids=goals,
                                  previous_roadmap_id=st.session_state.get('previous_roadmap'))
    path = planner.plan(path_request)
    st.dataframe([{'Skill': catalog.skill(item.skill_id)['name_ko'],
                   '숙련도': item.mastery, '단계': classify(item.mastery).label_ko,
                   '우선순위 점수': item.score, '바로 학습 가능': item.ready,
                   '근거': ' / '.join(item.reasons)} for item in path.priorities], hide_index=True)
    if path.priorities:
        st.bar_chart({catalog.skill(item.skill_id)['name_ko']: item.score for item in path.priorities})
    for step in path.steps:
        st.write(f"{step.order}. {catalog.skill(step.skill_id)['name_ko']} — {step.kind}")
    if path.completed:
        st.success("선택한 목표와 선수 Skill이 모두 숙달 기준을 충족합니다.")
    else:
        st.info("다음 학습: " + catalog.skill(path.next_skill_id)['name_ko'])
    if st.button("이 상태로 가상 Knowledge Map 설정"):
        st.session_state.map_skills = [item.model_dump() for item in roadmap_states]
        st.session_state.map_version = 0
        st.session_state.map_applied = []
        st.session_state.previous_roadmap = path.roadmap_id
        st.success("상태 갱신 실험의 시작 상태를 설정했습니다.")

with update_tab:
    st.caption("정답은 숙련도를 올리고 오답은 낮춥니다. 힌트 사용 정답은 더 적게 반영하는 초기 제안 정책입니다.")
    update_skill = st.selectbox("결과를 반영할 Skill", list(catalog.skills), key='update_skill',
                                format_func=lambda value: catalog.skill(value)['name_ko'])
    answer_correct = st.checkbox("정답으로 확인됨", True)
    answer_hint = st.checkbox("힌트 사용 후 정답")
    attempt_id = st.text_input("시도 ID (새 시도에는 새 ID)", 'dashboard-attempt-1')
    gain = st.slider("정답 반영률", 0.05, 0.5, 0.15, 0.05)
    penalty = st.slider("오답 감쇠율", 0.05, 0.5, 0.1, 0.05)
    hint_weight = st.slider("힌트 사용 정답 반영 비율", 0.1, 1.0, 0.5, 0.1)
    if st.button("가상 학생 상태에 결과 반영"):
        try:
            update_service = PlanningService(catalog, PlanningPolicy(success_gain=gain, wrong_penalty=penalty, hint_weight=hint_weight))
            proposal = update_service.update(StateUpdateRequest(student_id='dashboard-student',
                expected_version=st.session_state.map_version,
                skills=st.session_state.map_skills, applied_attempt_ids=st.session_state.map_applied,
                observation={'attempt_id': attempt_id, 'skill_id': update_skill,
                             'correct': answer_correct, 'used_hint': answer_hint}))
            st.session_state.map_skills = [item.model_dump() for item in proposal.skills]
            st.session_state.map_version = proposal.proposed_version
            if proposal.applied:
                st.session_state.map_applied.append(attempt_id)
                st.success(f"가상 상태 반영: {proposal.changed_skill.mastery:.3f} ({proposal.changed_skill.label_ko})")
            else:
                st.info("이미 반영한 시도라 다시 증가시키지 않았습니다.")
        except (ValueError, ValidationError) as exc:
            st.error(str(exc))
    mapped = [SkillState.model_validate(item) for item in st.session_state.map_skills]
    st.dataframe([{'Skill': catalog.skill(item.skill_id)['name_ko'], '숙련도': item.mastery,
                   '단계': classify(item.mastery).label_ko, '반영한 결과 수': item.evidence_count} for item in mapped], hide_index=True)
    after_path = planner.plan(PlanningRequest(student_id='dashboard-student', skills=mapped,
        goal_skill_ids=goals, previous_roadmap_id=st.session_state.get('previous_roadmap')))
    st.write("갱신 후 학습경로:", ' → '.join(catalog.skill(step.skill_id)['name_ko'] for step in after_path.steps) or '목표 달성')

with video_tab:
    st.caption("실제 영상 조회는 수행하지 않습니다. 아래 URL은 테스트 자료이며 후보 점수·제외 조건을 확인합니다.")
    approved_demo = st.checkbox("테스트 영상 후보를 승인된 자료로 가정", False)
    candidates = [VideoCandidate(content_id=f'demo-video-{i}', skill_id=skill_id,
        title=title, url=f'https://example.com/demo-video-{i}', approved=approved_demo,
        min_mastery=minimum, max_mastery=maximum, quality_score=quality, duration_seconds=duration)
        for i, (title, minimum, maximum, quality, duration) in enumerate([
            ('기초 규칙 짧은 설명', 0, 0.4, 0.8, 180), ('예제로 적용하기', 0.2, 0.7, 0.9, 480),
            ('응용 문제 설명', 0.6, 1.0, 0.85, 600)])]
    ranked = VideoService().rank(VideoRankRequest(skill_id=skill_id, mastery=mastery, candidates=candidates))
    if ranked.items:
        st.dataframe([{'순위': i + 1, '제목': item.candidate.title, '점수': item.score,
                       '길이(초)': item.candidate.duration_seconds, '근거': ' / '.join(item.reasons)}
                      for i, item in enumerate(ranked.items)], hide_index=True)
    else:
        st.info("현재 수준과 승인 조건을 충족하는 영상 후보가 없습니다.")
