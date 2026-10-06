# Backend 연동 준비 목록

이 문서는 현재 구현 계약과 실제 연동에서 합의해야 하는 사항입니다.

1. Skill Catalog: skill_id, prerequisites, next_skills, concept 콘텐츠, 지원 problem template.
2. Student State: Skill별 mastery/evidence_count, 최근 시도(오래된 순서), 단계 진행, 재시도 횟수.
3. AI①: 기존 schema_version 1.0 그대로 analysis 필드에 전달. 원문제의 구조화된 a/b/template은 별도 전달.
4. 콘텐츠 Pool: content_id, skill_id, 숙련도 구간, 제목, 실제 URL. 현재 example.com URL은 실제 영상이 아님.
5. 재도전: 서버 발행 토큰·학생 답안, Backend가 확정한 previous_mastery/mastery_after 및 오개념 해소 여부.
6. 보상: event_id 고유 제약으로 중복 제거, 저장과 XP/Badge 정책은 Backend 소유.
7. 운영: Backend 호출 인증, 모든 worker가 공유하는 TUTOR_TOKEN_SECRET, 토큰 만료/재발행 UX.

## 소유권

AI②는 Action/콘텐츠/검증/채점/Event 제안을 담당합니다.
Backend는 학생 신원·시도 기록·진행 단계·숙련도 갱신·보상 저장을 담당합니다.
초기 Knowledge Map의 정답 비율은 테스트용 추정치이며 운영 숙련도 모델과 합의해야 합니다.
클라이언트가 mastery/오개념 해소를 임의로 제출한 값을 보상 근거로 사용하지 않습니다.

## 오류 처리

입력 모델 검증 실패: HTTP 422 (FastAPI validation detail).
학습 문맥/토큰/Skill/답안 수식 오류: HTTP 422, detail.code=INVALID_LEARNING_CONTEXT.
분석 미완료: HTTP 422, detail.code=ANALYSIS_UNAVAILABLE.
지원 불가능하거나 검증 실패한 변형문제: HTTP 200 RETRY, content.problem=null.
잘못된 수학 답안: HTTP 200, 보상 Event 없이 복습 또는 동기부여 Action.

진단 토큰과 단계 토큰은 상태 재전송을 허용합니다. 서버 DB 없이 학습 진행의 중복이나
되돌리기를 막지 않으므로 Backend가 현재 세션/문제/시도를 검증합니다.
