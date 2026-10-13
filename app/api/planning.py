from fastapi import APIRouter
from app.api.learning import catalog, run
from app.models.planning import PlanningRequest, PlanningResponse, StateUpdateRequest, StateUpdateResponse, LevelResult
from app.models.integration import VideoRankRequest, VideoRankResponse
from app.services.planning_service import PlanningService, classify
from app.services.video_service import VideoService

router = APIRouter(prefix='/api/tutor', tags=['Planning and State'])
planner = PlanningService(catalog)


@router.get('/mastery/level', response_model=LevelResult)
def level(mastery: float | None = None):
    return run(classify, mastery)


@router.post('/planning/roadmap', response_model=PlanningResponse)
def plan(request: PlanningRequest):
    return run(planner.plan, request)


@router.post('/state/update', response_model=StateUpdateResponse)
def update(request: StateUpdateRequest):
    return run(planner.update, request)


@router.post('/videos/rank', response_model=VideoRankResponse)
def videos(request: VideoRankRequest):
    return run(VideoService().rank, request)
