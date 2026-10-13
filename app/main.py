from fastapi import FastAPI
from app.api.tutor import router
from app.api.learning import router as learning_router

app = FastAPI(title="STEPi AI② Adaptive Tutor", version="0.2.0")
app.include_router(router)
app.include_router(learning_router)
