from fastapi import APIRouter, Depends, HTTPException
from app.agent.orchestrator import AnalysisUnavailableError
from app.models.tutor_request import TutorRequest
from app.models.tutor_response import TutorResponse
from app.services.decision_service import DecisionService

router = APIRouter(prefix="/api/tutor", tags=["Tutor"])


def get_decision_service() -> DecisionService:
    return DecisionService()


@router.post("/decision", response_model=TutorResponse,
             responses={422: {"description": "입력 검증 실패 또는 분석 미완료"}})
def decide(request: TutorRequest,
           service: DecisionService = Depends(get_decision_service)) -> TutorResponse:
    try:
        return service.decide(request)
    except AnalysisUnavailableError as exc:
        raise HTTPException(status_code=422, detail={
            "code": "ANALYSIS_UNAVAILABLE", "message": str(exc)
        }) from exc
