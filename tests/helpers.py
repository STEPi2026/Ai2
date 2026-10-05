import json
from pathlib import Path


def payload():
    return json.loads((Path(__file__).resolve().parents[1] / "examples/decision_request.json").read_text())
