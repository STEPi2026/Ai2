class MotivationAgent:
    def message(self, recent_failures: int) -> str:
        if recent_failures >= 3:
            return "여러 번 시도했어요. 이번에는 전체 풀이 대신 부호 하나만 확인하는 작은 목표로 시작해볼까요?"
        return "한 단계만 다시 확인해볼까요? 짧게 쉬었다가 이어서 풀어도 좋아요."

    def praise(self, used_hint: bool, overcame_error: bool) -> str:
        if overcame_error:
            return "앞서 틀렸던 유형과 같은 원리의 문제를 이번에는 정확하게 해결했어요."
        if used_hint:
            return "힌트를 확인한 뒤 스스로 풀이를 수정해 확인 문제를 해결했어요."
        return "같은 풀이 원리를 새 숫자에 적용해 확인 문제를 정확하게 해결했어요."
