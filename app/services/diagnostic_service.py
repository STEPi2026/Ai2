from app.models.diagnostic import DiagnosticAnswer, DiagnosticResponse
from app.models.learning import SkillState
from app.services.catalog import FixtureCatalog
from app.services.math_validator import MathValidator
from app.services.tokens import TokenService


class DiagnosticService:
    def __init__(self, catalog: FixtureCatalog, validator: MathValidator, tokens: TokenService):
        self.catalog, self.validator, self.tokens = catalog, validator, tokens

    def knowledge_map(self, history: list[dict]) -> list[SkillState]:
        result = []
        for skill_id in self.catalog.skills:
            rows = [row for row in history if row['skill_id'] == skill_id]
            result.append(SkillState(skill_id=skill_id,
                mastery=sum(row['correct'] for row in rows) / len(rows) if rows else None,
                evidence_count=len(rows)))
        return result

    def select(self, history: list[dict]) -> dict | None:
        answered = {row['question_id'] for row in history}
        states = {s.skill_id: s.mastery for s in self.knowledge_map(history)}
        questions = self.catalog.data['diagnostic_questions']
        if history and not history[-1]['correct']:
            candidates = [q for q in questions if q['skill_id'] == history[-1]['skill_id'] and q['question_id'] not in answered]
            if candidates:
                return candidates[0]
        # Do not diagnose a dependent skill before there is successful prerequisite evidence.
        for question in questions:
            skill = self.catalog.skill(question['skill_id'])
            if question['question_id'] not in answered and all(
                states.get(p) is not None and states[p] >= 0.5 for p in skill['prerequisites']):
                return question
        return None

    def response(self, student_id: str, history: list[dict], last_correct: bool | None = None) -> DiagnosticResponse:
        question = self.select(history)
        return DiagnosticResponse(completed=question is None,
            question={k: question[k] for k in ['question_id', 'skill_id', 'prompt']} if question else None,
            session_token=self.tokens.issue('diagnostic', {'student_id': student_id, 'history': history,
                'question_id': question['question_id']}) if question else None,
            knowledge_map=self.knowledge_map(history), answered_count=len(history), last_correct=last_correct)

    def start(self, student_id: str) -> DiagnosticResponse:
        return self.response(student_id, [])

    def answer(self, request: DiagnosticAnswer) -> DiagnosticResponse:
        data = self.tokens.read(request.session_token, 'diagnostic', request.student_id)
        if data['question_id'] != request.question_id:
            raise ValueError("현재 진단문제와 question_id가 다릅니다.")
        question = next(q for q in self.catalog.data['diagnostic_questions'] if q['question_id'] == request.question_id)
        correct = self.validator.matches_task(request.answer, question['answer'],
            self.catalog.skill(question['skill_id'])['answer_form'])
        history = data['history'] + [{"question_id": question['question_id'],
            "skill_id": question['skill_id'], "correct": correct}]
        return self.response(request.student_id, history, correct)
