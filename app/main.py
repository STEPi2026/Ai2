from fastapi import FastAPI
from app.api.tutor import router

app = FastAPI(title="STEPi AI② Adaptive Tutor", version="0.1.0")
app.include_router(router)
