# STEPi AI② Adaptive Tutor — PHASE 1

AI① 분석 JSON을 받아 규칙 기반으로 학습 개입을 결정하는 FastAPI 서비스입니다.
OCR, DB, LLM, LangGraph를 사용하지 않습니다.

## 실행 및 검증

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Swagger: http://127.0.0.1:8000/docs → POST /api/tutor/decision → Try it out.
`examples/decision_request.json`과 동일한 입력 예제가 표시됩니다.

```sh
curl -X POST http://127.0.0.1:8000/api/tutor/decision \
  -H 'Content-Type: application/json' --data-binary @examples/decision_request.json
python -m unittest discover -s tests -v
```

예제 결과는 `SOCRATIC_HINT`, `next_step: RETRY`, `reward_event: null`입니다.

## 입력과 정책

제공된 schema_version 1.0의 필드 이름과 중첩 구조를 유지합니다.
`first_error`는 오류가 없으면 명시적으로 null을 전달합니다.
숙련도와 신뢰도는 0–1, 횟수는 0 이상의 정수, 풀이 단계는 1 이상의 정수입니다.
Skill/오류 ID와 `state_after`는 교체 가능한 문자열이며 특정 코드에 의존하지 않습니다.
`mastery_after`를 숙련도 판단 기준으로 사용합니다.

정책은 다음 순서로 적용합니다.

1. analysis_status != ANALYZED: HTTP 422, detail.code = ANALYSIS_UNAVAILABLE.
2. mastery_after < 0.25: CONCEPT_REVIEW.
3. 현재 오류가 있고 consecutive_wrong >= 3: REMEDIATION.
4. 현재 오류가 있고 hint_count == 0: SOCRATIC_HINT.
5. 현재 오류가 있고 힌트를 이미 사용: RETRY.
6. 현재 오류가 없고 mastery_after >= 0.8: NEXT_SKILL.
7. 그 외: RETRY.

경계값 0.25는 개념 복습 대상에서 제외하고, 0.8은 다음 Skill 진행 대상에 포함합니다.
반복 오류는 첫 힌트보다 우선합니다. 현재 오류가 있으면 높은 숙련도만으로 진행하지 않습니다.
`consecutive_wrong`은 제공된 반복 실패 신호로 사용하며 같은 오류의 반복인지는
이 Schema만으로 확인할 수 없습니다. 실패 횟수는 Backend가 관리합니다.

`TutorPolicy`에서 임계값을 변경하거나 `TutorOrchestrator(policy)`로 주입할 수 있습니다.
API 정책 교체는 `get_decision_service` 의존성을 대체하여 적용할 수 있습니다.
응답은 skill_id와 현재 오류 유형, 메시지, 후속 행동을 반환합니다.
NEXT_SKILL은 구체적인 다음 Skill ID를 선택하지 않으며 Backend가 처리합니다.

## 구현 범위

9개 Action은 Enum으로 정의합니다. PHASE 1에서는 힌트·개념복습·반복오류 보완의
기본 안내와 RETRY/NEXT_SKILL 판단만 제공합니다. 단계별 힌트 콘텐츠는 PHASE 2,
선수 Skill 판단은 PHASE 3, 검증된 변형 문제 및 성공 판단은 PHASE 4에서 구현합니다.
현 입력에는 재도전 성공, 이전 숙련도, 선수 Skill 정보가 없으므로 PRAISE,
MOTIVATION, PREREQUISITE_REVIEW, VARIANT_PROBLEM과 보상 Event는 생성하지 않습니다.
반환 메시지는 복습 자료 자체가 아닌 다음 학습 행동 안내입니다.

`app/models`는 계약, `app/policies`는 설정, `app/agent/orchestrator.py`는 판단,
`app/services/decision_service.py`는 응답 조립, `app/api/tutor.py`는 HTTP 계층입니다.
실행 디렉터리는 이 README가 있는 저장소 루트입니다.

## GitHub 규칙

Issue당 최신 main에서 `feature/#이슈번호-기능명` 브랜치를 생성합니다.
커밋은 `[이모지 type #이슈번호]: 작업 내용`, PR 제목은 `[#이슈번호] 작업 내용`입니다.
main 직접 개발·Push를 금지하며, PR 확인 후 Merge하고 작업 브랜치를 삭제합니다.
.env, 인증키, 비밀번호 및 개인정보를 커밋하지 않습니다.
