"""Inference API - skeleton.

Intended flow per request: entity keys (+ request data) in -> online features
for the model's feature service -> predictor -> predictions out.

TODO:
  * load the production ModelArtifact from the model registry at start-up
  * instantiate the predictor from ``predictor_registry`` by artifact.framework
  * shadow / canary model support, request logging for monitoring
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="shalf inference api", version="0.1.0")


class PredictRequest(BaseModel):
    entities: dict[str, list[Any]]
    request_data: dict[str, list[Any]] | None = None


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/models/{model_name}/predict")
def predict(model_name: str, request: PredictRequest) -> dict[str, Any]:
    raise HTTPException(501, f"Model serving for {model_name!r} is not implemented yet")
