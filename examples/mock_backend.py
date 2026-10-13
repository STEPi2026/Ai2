"""Local Backend reference adapter; fixture only, no DB/OCR/AI① integration."""
import json
import os
from pathlib import Path
from fastapi import FastAPI
from app.models.integration import BackendCatalog, DecisionEnvelope, RemoteDecisionResult
from app.models.learning import LearningRequest
from app.services.remote_client import TutorApiClient

app = FastAPI(title="STEPi Mock Backend — 연동 확인용")


@app.post('/demo/attempt', response_model=RemoteDecisionResult)
def attempt(request: LearningRequest):
    catalog = BackendCatalog.model_validate(json.loads(Path(__file__).with_name('backend_catalog.json').read_text()))
    client = TutorApiClient(os.getenv('TUTOR_API_BASE_URL', 'http://127.0.0.1:8000'))
    try:
        return client.decide(DecisionEnvelope(catalog=catalog, learning=request))
    finally:
        client.close()
