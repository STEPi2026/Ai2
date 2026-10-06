import hashlib
import sympy as sp
from app.models.learning import LearningRequest
from app.services.catalog import FixtureCatalog
from app.services.math_validator import MathValidator
from app.services.tokens import TokenService


class ProblemUnavailable(ValueError):
    pass


class ProblemGenerator:
    def __init__(self, catalog: FixtureCatalog, validator: MathValidator, tokens: TokenService):
        self.catalog, self.validator, self.tokens = catalog, validator, tokens

    def generate(self, request: LearningRequest) -> dict[str, str]:
        source = request.source_problem
        skill = self.catalog.skill(request.analysis.focus_skill.skill_id)
        if source is None or source.template not in skill['templates']:
            raise ProblemUnavailable("이 Skill에 지원되는 원문제의 구조 정보가 필요합니다.")
        error = request.analysis.first_error
        # Fixture generation is scoped to arithmetic sign/calculation correction.
        if error and (error.error_type != 'calculation' or error.error_subtype not in
                      ('arithmetic_slip', 'sign_error', 'sign_multiplication')):
            raise ProblemUnavailable("현재 문제 템플릿은 계산 오류 교정만 지원합니다.")
        if source.a == 0 or source.b == 0:
            raise ProblemUnavailable("현재 템플릿은 0이 아닌 인수만 지원합니다.")
        candidates = [(a, b) for a in range(-9, 10) for b in range(-9, 10)
                      if a * source.a > 0 and b * source.b > 0
                      and a != source.a and b != source.b]
        seed = f"{request.analysis.analysis_id}:{request.variant_index}"
        position = int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16) % len(candidates)
        a, b = candidates[position]
        if source.template == 'signed_multiplication':
            prompt = f"({a:+d}) × ({b:+d})를 계산하세요."
            answer = str(a * b)
        else:
            prompt = f"(x{a:+d})(x{b:+d})를 전개하세요. 곱셈은 *로 입력하세요."
            x = sp.Symbol('x')
            answer = str(sp.expand((x + a) * (x + b)))
        if not self.validator.validate_problem(source.template, a, b, answer):
            raise ProblemUnavailable("수학 검증에 실패하여 문제를 제공하지 않습니다.")
        problem_id = 'variant-' + hashlib.sha256(
            f"{request.analysis.student_id}:{seed}:{source.template}:{a}:{b}".encode()).hexdigest()[:24]
        token = self.tokens.issue('problem', {'student_id': request.analysis.student_id,
            'skill_id': skill['skill_id'], 'problem_id': problem_id, 'template': source.template,
            'a': a, 'b': b, 'analysis_id': request.analysis.analysis_id,
            'hint_count': request.analysis.hint_count,
            'has_error': error is not None,
            'misconception_ids': error.misconception_ids if error else []})
        return {'problem_id': problem_id, 'prompt': prompt, 'problem_token': token,
                'difficulty': source.difficulty}
