import httpx
from pydantic import ValidationError
from app.models.integration import DecisionEnvelope, RemoteDecisionResult
from app.models.learning import LearningResponse


class TutorApiClient:
    """Backend-side reference client. Never used to fetch data from a DB."""
    def __init__(self, base_url: str, transport: httpx.BaseTransport | None = None,
                 timeout_seconds: float = 3, max_attempts: int = 2):
        if timeout_seconds <= 0 or not 1 <= max_attempts <= 3:
            raise ValueError("timeout must be positive and max_attempts in 1..3")
        self.client = httpx.Client(base_url=base_url, timeout=timeout_seconds, transport=transport)
        self.max_attempts = max_attempts

    def close(self):
        self.client.close()

    def decide(self, request: DecisionEnvelope) -> RemoteDecisionResult:
        for _ in range(self.max_attempts):
            try:
                response = self.client.post('/api/tutor/integration/decision', json=request.model_dump(mode='json'))
                if 400 <= response.status_code < 500:
                    return RemoteDecisionResult(status='REJECTED', reason=f'HTTP {response.status_code}')
                response.raise_for_status()
                parsed = LearningResponse.model_validate(response.json())
                return RemoteDecisionResult(status='OK', response=parsed)
            except (httpx.RequestError, httpx.HTTPStatusError, ValidationError, ValueError):
                continue
        return RemoteDecisionResult(status='UNAVAILABLE', fallback_action='RETRY',
            reason='Tutor 응답을 확인할 수 없어 재요청이 필요합니다.')
