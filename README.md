# STEPi AI② Adaptive Tutor — 전체 기능 Fixture MVP

AI① 분석 결과와 Backend가 전달한 학생 상태로 학습 행동을 결정하는 FastAPI 서비스입니다.
표의 기능 전체에 대한 테스트 가능한 최소 흐름을 구현했습니다. **실제 Backend 연동,
교육과정 전체 데이터, 실제 영상 추천 자료 및 운영 배포는 포함하지 않습니다.**
DB, OCR, LLM, LangGraph를 사용하지 않습니다.

## 실행

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Swagger: http://127.0.0.1:8000/docs. 기존 AI① 입력 예제와 확장 학습 입력 예제가 표시됩니다.

```sh
python -m unittest discover -s tests -v
python -m examples.run_demo
curl -X POST http://127.0.0.1:8000/api/tutor/learning/decision \
  -H 'Content-Type: application/json' --data-binary @examples/learning_request.json
```

실행 위치는 이 README가 있는 저장소 루트입니다.

## 구현 상태

| 기능 | Fixture MVP 동작 | 실제 연동 시 필요한 자료 |
|---|---|---|
| 초기 진단 제어 | 답안을 채점하고 실패 Skill의 추가 문제 또는 선수 조건을 충족하는 문제 선택 | 진단 문제 은행·진단 정책 |
| 초기 Knowledge Map | Skill별 정답 비율과 evidence_count 산출, 미진단은 mastery=null | 실제 숙련도 추정 모델 |
| 학생 상태 해석 | AI① 숙련도·오류, 최근 동일 오류 연속 기록, 힌트 사용 해석 | Backend 시도 기록 |
| 선수개념 추적 | 선수 그래프를 재귀 조회, 부족하거나 정보 없는 선수 Skill 확인 | Skill 코드·선수 관계 |
| 다음 학습 결정 | Rule-based Action 선택 | 검토한 정책 임계값 |
| 소크라틱 힌트 | 부호 곱셈 오류 Level 1–3, 기타 오류는 일반 질문 | 오류별 콘텐츠 확충 |
| 개념학습 | 수준별 설명·예제·확인문제 | 교육과정에 맞는 개념 자료 |
| 단계별 학습 | 설명 → 예제 → 확인문제 → 채점 후 학습/복습 안내 | Backend 진행 단계 저장 |
| 영상 추천 | Skill·숙련도 구간으로 fixture 콘텐츠 선택 | 실제 Backend 콘텐츠 Pool·URL |
| 변형문제 생성 | 부호 곱셈·다항식 전개에서 인수의 부호와 template/difficulty 유지, 숫자 변경 | 원문제 구조·더 많은 템플릿 |
| 문제 검증 | SymPy 검증 성공한 문제만 제공, 실패/미지원은 RETRY | 검증 가능한 추가 문제 유형 |
| 재도전 판단 | 서버 발행 문제 토큰 기반 채점, 성공/실패별 Action 선택 | Backend 재시도 횟수·숙련도 갱신 |
| 학습경로 재계획 | 선수 복습, 현재 Skill 재도전, 숙달된 후속 Skill 건너뛰기 | 실제 Skill 그래프 |
| 동기부여 개입 | 힌트 사용·오류 극복 기반 칭찬, 반복 실패/이탈 신호에 작은 목표 | 참여도 판단 신호 |
| 보상 연계 | 교육 Event와 안정적인 event_id 반환 | Backend 중복 제거 및 XP/Badge 저장 |

fixture 파일은 `data/tutor_fixtures.json`이며 arithmetic → polynomial → factoring의
3개 Skill과 진단문제 6개만 포함합니다. 영상 URL은 example.com의 **플레이스홀더**입니다.
확장 API는 fixture에 없는 Skill을 422로 거절합니다. 코드는 ID 의미를 해석하지 않으며
실제 STP/SKL/MIS 코드는 Catalog·콘텐츠·요청 자료를 함께 교체하여 연결해야 합니다.

## API 계약

| API (POST /api/tutor 하위) | 용도 |
|---|---|
| /decision | 기존 PHASE 1 schema_version=1.0 입력과 응답 유지 |
| /diagnostic/start | student_id로 진단 시작 |
| /diagnostic/answer | session_token, question_id, answer로 다음 진단문제/초기 Map 반환 |
| /learning/decision | analysis + Skill 상태·단계·원문제·최근 기록으로 학습 개입 결정 |
| /learning/step | student_id, skill_id, stage(explanation/example/check)로 단계별 학습 제공 |
| /learning/check | check_token, student_id, answer로 확인문제 채점 |
| /learning/retry | problem_token, student_id, attempt_id, answer로 변형문제 재도전 채점 |

기존 AI① 입력 Schema는 변경하지 않았습니다. 확장 정보는 별도의 LearningRequest의
`analysis` 주변 필드로 받습니다. /decision은 PHASE 1 동작을 보존하고 reward_event=null이며,
새 기능과 `events`는 /learning API를 사용해야 합니다. API 모델 정의는 Swagger에서 확인하세요.

### 학습 요청과 정책

`examples/learning_request.json`을 /learning/decision에 전달하면 1단계 힌트를 받습니다.
analysis.hint_count를 1, 2로 바꾸면 2, 3단계 힌트입니다. stage를 hint_complete,
concept_complete 또는 check로 바꾸면 지원 가능한 source_problem에 한해 검증된 변형문제를 반환합니다.
이 완료 신호는 Backend가 학생의 실제 진행을 확인하고 전달해야 합니다.

정책 순서: 분석 미완료 차단 → 부족한 선수 Skill → 정보 없는 선수 Skill 확인 →
명시적인 disengaged 신호 → 학습 이후 확인문제 → 낮은 숙련도 개념복습 →
반복 오류 보완 → 단계별 힌트/힌트 소진 시 복습 → 충분한 숙련도에서 후속 Skill → 재도전.

`TutorPolicy`의 기본값은 concept_review_threshold=0.25, mastery_threshold=0.8,
repeated_wrong_threshold=3, max_hint_level=3, motivation_failure_threshold=3입니다.
API 서비스 생성 시 Policy를 주입하여 교체할 수 있습니다.

- 현재 Skill 숙련도는 analysis.focus_skill.mastery_after를 우선합니다.
- skills는 Skill별 mastery와 evidence_count 목록입니다. 중복/미등록 Skill은 거절합니다.
- recent_attempts는 현재 시도를 제외한 최근 기록 20개 이하를 **오래된 순서 → 최신 순서**로 받습니다.
  같은 Skill·error_subtype의 연속 실패를 계산하고, 정답/다른 오류에서 연속성이 끊깁니다.
  기록이 없으면 기존 consecutive_wrong을 대리 신호로 사용합니다.
- state_after는 임의 코드 문자열로 유지하며 현재 정책은 수치 mastery를 사용합니다.
- Unknown mastery를 낮은 숙련도로 추정하지 않습니다. 선수 정보가 없으면 확인을 요청합니다.
- source_problem은 template, a, b, difficulty=easy의 구조화된 원문제 자료입니다.
  기존 first_error.latex_text만으로 원문제 전체를 복원하지 않습니다.
- 변형문제는 signed_multiplication, binomial_expansion과 계산 오류 중
  arithmetic_slip/sign_error/sign_multiplication만 지원합니다. 0이 아닌 -9~9 인수의 부호,
  연산/전개 원리와 easy 난이도 범주를 유지합니다. 숫자의 정확한 체감 난이도까지 보장하지 않습니다.
- source_problem 누락·미지원 오류·검증 실패 시 문제를 내보내지 않고 RETRY를 반환합니다.

### 단계별 학습과 재도전

/learning/step에 stage=explanation → example → check를 전달합니다.
check 단계에서 반환한 check_token을 /learning/check에 전달하면 성공은
concept_complete, 실패는 example 복습을 안내합니다. 단계는 Backend가 저장하고 전달합니다.
AI②는 세션 진행이나 Student State를 DB에 저장하지 않습니다.

학생 답안은 정수·x·+·-·*·^ 또는 **(0~4 정수 지수) 수식으로 받습니다.
곱셈은 *로 입력합니다. 나눗셈·함수·임의 Python 코드 등은 지원하지 않습니다.
수식 크기와 다항식 차수를 제한하며 eval/sympify로 사용자 텍스트를 실행하지 않습니다.
정답과 동치인지 검증한 후, 계산 문제는 정수 답, 전개는 전개된 항의 합,
인수분해는 x를 포함하는 인수의 곱인지 확인합니다.

변형문제 응답에는 정답을 포함하지 않습니다. /learning/retry에는 발행된 problem_token을
그대로 전달합니다. 잘못된 답은 REMEDIATION, 반복 실패는 MOTIVATION을 반환합니다.
성공은 PRAISE 또는 NEXT_SKILL을 반환하며, 실제 다음 Skill 선택에는 Backend가 제공하는
mastery_after와 선수 Skill 상태가 필요합니다. AI②가 숙련도를 임의로 증가시키지 않습니다.

### Event와 토큰

정답 재도전은 RETRY_SUCCESS, DAILY_GOAL_PROGRESS를 생성합니다.
previous_mastery < mastery_after인 경우 SKILL_IMPROVED,
0.8 경계를 처음 넘은 경우 SKILL_MASTERED를 추가합니다.
MISCONCEPTION_OVERCOME는 원분석의 misconception_ids가 있고 Backend가
misconception_resolved=true로 확인한 경우만 반환합니다.

같은 학생·변형문제·Event 종류는 attempt_id가 달라도 같은 event_id입니다.
Backend는 event_id를 고유 키로 처리하여 보상을 한 번만 지급하고, 실제 시도/숙련도/오개념
전이를 검증해야 합니다. Event에는 XP 수치나 Badge를 직접 배정하지 않습니다.
이 MVP는 인증을 구현하지 않으므로 운영에서는 신뢰할 수 있는 Backend를 통해 호출해야 합니다.

진단·확인문제·변형문제 토큰은 HMAC 서명과 학생·용도·1시간 만료 검사를 사용합니다.
토큰은 암호화되지 않으며 학생 데이터와 문제 구조가 들어 있으므로 로그에 남기지 마세요.
TUTOR_TOKEN_SECRET이 없으면 프로세스마다 임시 키를 만듭니다. 재시작/여러 worker에서는
같은 32바이트 이상의 secret을 환경 변수로 전달해야 합니다. .env는 자동 로드하지 않습니다.
실제 토큰은 Swagger 예제에 고정하지 않고 먼저 각 발행 API에서 받아야 합니다.

## GitHub 규칙

Issue당 `feature/#이슈번호-기능명` 브랜치, 커밋은 `[이모지 type #이슈번호]: 작업 내용`,
PR은 `[#이슈번호] 작업 내용`으로 관리합니다. main에 직접 Push하지 않습니다.
이번 작업은 사용자 요청에 따라 별도 비Git 작업 폴더에서 구현·검증 후 Issue와 브랜치에 반영합니다.
.env·인증키·비밀번호·개인정보를 커밋하지 않습니다. PR 확인 후 Merge하고 작업 브랜치를 삭제합니다.
