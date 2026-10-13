from fastapi import FastAPI
from app.api.tutor import router
from app.api.learning import router as learning_router

app = FastAPI(title="STEPi AI② Adaptive Tutor", version="0.3.0")
app.include_router(router)
app.include_router(learning_router)

from app.api.planning import router as planning_router
from app.api.integration import router as integration_router
app.include_router(planning_router)
app.include_router(integration_router)


@app.get('/health', tags=['Health'])
def health():
    return {'status': 'ok'}
