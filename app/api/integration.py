from fastapi import APIRouter
from app.api.learning import run
from app.models.integration import (DecisionEnvelope, PlanEnvelope, UpdateEnvelope, RetryEnvelope,
    LessonEnvelope, CheckEnvelope, DiagnosticEnvelope, DiagnosticAnswerEnvelope)
from app.models.learning import LearningResponse
from app.models.diagnostic import DiagnosticResponse
from app.models.planning import PlanningResponse, StateUpdateResponse
from app.services.backend_adapter import runtime_catalog
from app.services.learning_service import LearningService
from app.services.diagnostic_service import DiagnosticService
from app.services.planning_service import PlanningService
from app.services.math_validator import MathValidator
from app.services.tokens import tokens

router = APIRouter(prefix='/api/tutor/integration', tags=['Backend contract proposal v1'])


def learning_call(request, name, field):
    def execute(value):
        catalog = runtime_catalog(value.catalog)
        service = LearningService(catalog, MathValidator(), tokens)
        response = getattr(service, name)(getattr(value, field))
        response.data_source = catalog.data_source
        return response
    return run(execute, request)


@router.post('/decision', response_model=LearningResponse)
def decision(request: DecisionEnvelope):
    return learning_call(request, 'decide', 'learning')


@router.post('/lesson', response_model=LearningResponse)
def lesson(request: LessonEnvelope):
    return learning_call(request, 'lesson', 'lesson')


@router.post('/check', response_model=LearningResponse)
def check(request: CheckEnvelope):
    return learning_call(request, 'lesson_answer', 'check')


@router.post('/retry', response_model=LearningResponse)
def retry(request: RetryEnvelope):
    return learning_call(request, 'retry', 'retry')


@router.post('/roadmap', response_model=PlanningResponse)
def roadmap(request: PlanEnvelope):
    return run(lambda value: PlanningService(runtime_catalog(value.catalog)).plan(value.planning), request)


@router.post('/state-update', response_model=StateUpdateResponse)
def update(request: UpdateEnvelope):
    return run(lambda value: PlanningService(runtime_catalog(value.catalog)).update(value.update), request)


@router.post('/diagnostic/start', response_model=DiagnosticResponse)
def start(request: DiagnosticEnvelope):
    return run(lambda value: DiagnosticService(runtime_catalog(value.catalog), MathValidator(), tokens).start(value.start.student_id), request)


@router.post('/diagnostic/answer', response_model=DiagnosticResponse)
def answer(request: DiagnosticAnswerEnvelope):
    return run(lambda value: DiagnosticService(runtime_catalog(value.catalog), MathValidator(), tokens).answer(value.answer), request)


@router.get('/contract-status')
def status():
    return {'schema_version': '1.0', 'agreement_status': 'PROPOSED',
        'student_state_owner': 'Backend', 'reward_persistence_owner': 'Backend',
        'real_backend_e2e_verified': False, 'real_ai1_e2e_verified': False,
        'schemas': '/openapi.json'}
