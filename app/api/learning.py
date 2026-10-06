from fastapi import APIRouter, HTTPException
from app.agent.orchestrator import AnalysisUnavailableError
from app.models.diagnostic import DiagnosticStart, DiagnosticAnswer, DiagnosticResponse
from app.models.learning import (LearningRequest, LearningResponse, RetryRequest,
    LessonRequest, LessonAnswerRequest)
from app.services.catalog import FixtureCatalog
from app.services.diagnostic_service import DiagnosticService
from app.services.learning_service import LearningService
from app.services.math_validator import MathValidator
from app.services.tokens import tokens

router = APIRouter(prefix='/api/tutor', tags=['Adaptive learning (fixture MVP)'])
catalog = FixtureCatalog()
validator = MathValidator()
learning = LearningService(catalog, validator, tokens)
diagnostic = DiagnosticService(catalog, validator, tokens)


def run(function, request):
    try:
        return function(request)
    except AnalysisUnavailableError as exc:
        raise HTTPException(status_code=422, detail={'code': 'ANALYSIS_UNAVAILABLE', 'message': str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={'code': 'INVALID_LEARNING_CONTEXT', 'message': str(exc)}) from exc


@router.post('/diagnostic/start', response_model=DiagnosticResponse)
def start(request: DiagnosticStart):
    return run(diagnostic.start, request.student_id)


@router.post('/diagnostic/answer', response_model=DiagnosticResponse)
def answer(request: DiagnosticAnswer):
    return run(diagnostic.answer, request)


@router.post('/learning/decision', response_model=LearningResponse)
def decide(request: LearningRequest):
    return run(learning.decide, request)


@router.post('/learning/step', response_model=LearningResponse)
def lesson(request: LessonRequest):
    return run(learning.lesson, request)


@router.post('/learning/check', response_model=LearningResponse)
def lesson_answer(request: LessonAnswerRequest):
    return run(learning.lesson_answer, request)


@router.post('/learning/retry', response_model=LearningResponse)
def retry(request: RetryRequest):
    return run(learning.retry, request)
