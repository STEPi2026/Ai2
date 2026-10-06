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
