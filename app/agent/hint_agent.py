from app.models.tutor_request import TutorRequest


class HintAgent:
    def build(self, request: TutorRequest, max_level: int = 3) -> tuple[int, str]:
        level = min(request.hint_count + 1, max_level)
        error = request.first_error
        step = error.step_no if error else 1
        text = error.latex_text if error else ""
        # Recognize the mathematical operation, not a particular Skill ID.
        multiplication = "\\times" in text or "×" in text or "*" in text
        opposite_signs = "(+" in text and "(-" in text
        if error and error.error_type == "calculation" and multiplication and opposite_signs:
            hints = [f"{step}번째 풀이 단계에서 두 수를 곱한 부분을 다시 확인해볼까요?",
                     "곱하는 두 수의 부호가 같은가요, 다른가요? 결과의 부호를 먼저 생각해보세요.",
                     "양수와 음수를 곱하면 어떤 부호가 되나요? 부호를 정한 뒤 절댓값끼리 곱해보세요."]
        else:
            hints = [f"{step}번째 풀이 단계에서 사용한 계산이나 규칙을 다시 확인해볼까요?",
                     f"{step}번째 단계로 넘어갈 때 어떤 규칙을 사용했나요? 조건이 맞는지 확인해보세요.",
                     "해당 단계를 작은 계산으로 나누고, 각 계산에서 사용한 규칙을 하나씩 확인해보세요."]
        return level, hints[level - 1]
