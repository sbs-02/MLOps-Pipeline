"""BentoML prediction service for the purchase-conversion model (Gate 9)."""

from __future__ import annotations

import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any

import bentoml
import joblib
from fastapi import FastAPI
import pandas as pd
from pydantic import BaseModel, Field

logger = logging.getLogger("services.prediction")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [services.prediction] %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_PATH = REPO_ROOT / "models" / "baseline_logreg.joblib"
MODEL_PATH = Path(os.environ.get("MODEL_PATH", str(DEFAULT_MODEL_PATH)))
MODEL_VERSION = os.environ.get("MODEL_VERSION", "baseline-logreg-v1")

# Auxiliary FastAPI app mounted into the BentoML server to expose a GET /health
# endpoint (BentoML APIs are POST-only by default).
prediction_app = FastAPI(title="Prediction Health", docs_url=None, redoc_url=None)

_prediction_service = None


@prediction_app.get("/health")
def prediction_health() -> dict[str, str]:
    global _prediction_service
    if _prediction_service is None:
        _prediction_service = ConversionService()
    health = _prediction_service.health()
    return {
        "status": health.status,
        "model_version": health.model_version,
        "model_path": health.model_path,
    }


class PredictionRequest(BaseModel):
    """Input features for session-level purchase-conversion prediction."""

    channelGrouping: str = Field(
        ..., min_length=1, description="Acquisition channel (e.g. 'Organic Search', 'Direct')"
    )
    device_category: str = Field(
        ..., min_length=1, description="Device category ('desktop', 'mobile', 'tablet')"
    )
    browser: str = Field(
        ..., min_length=1, description="Browser family (e.g. 'Chrome', 'Safari')"
    )
    operating_system: str = Field(
        ..., min_length=1, description="Client OS (e.g. 'Windows', 'Macintosh', 'iOS')"
    )
    country: str = Field(
        ..., min_length=1, description="Country of origin (e.g. 'United States')"
    )
    continent: str = Field(
        ..., min_length=1, description="Continent (e.g. 'Americas', 'Europe')"
    )
    traffic_source: str = Field(
        ..., min_length=1, description="Source domain or entity (e.g. 'google', 'direct')"
    )
    traffic_medium: str = Field(
        ..., min_length=1, description="Medium classification (e.g. 'organic', 'cpc', 'referral')"
    )
    visitNumber: int = Field(
        ..., ge=1, description="Sequence number of visit for this cookie (>= 1)"
    )
    visits: int = Field(
        ..., ge=0, description="Session counter flag (typically 1 for valid sessions)"
    )
    hits: int = Field(
        ..., ge=0, description="Total interaction events within the session"
    )
    pageviews: int = Field(
        ..., ge=0, description="Total page views within the session"
    )
    time_on_site: int = Field(
        ..., ge=0, description="Session engagement duration in seconds"
    )


class PredictionResponse(BaseModel):
    """Model output payload for session-level conversion."""

    prediction: int = Field(
        ..., description="Binary prediction: 1 if converted (>= threshold 0.5), 0 otherwise"
    )
    conversion_probability: float = Field(
        ..., ge=0.0, le=1.0, description="Predicted probability of conversion [0.0, 1.0]"
    )
    model_version: str = Field(
        ..., description="Identifier of the serving model version"
    )
    request_id: str = Field(
        ..., description="Unique UUID4 correlation ID for auditing and delayed-label joining"
    )


class HealthResponse(BaseModel):
    """Health check payload."""

    status: str
    model_version: str
    model_path: str


@bentoml.asgi_app(prediction_app, path="/")
@bentoml.service(name="conversion_service")
class ConversionService:
    """BentoML local serving service for the purchase-conversion model."""

    def __init__(self) -> None:
        target_path = Path(os.environ.get("MODEL_PATH", str(DEFAULT_MODEL_PATH)))
        if not target_path.exists():
            raise FileNotFoundError(f"Model artifact not found: {target_path}")
        self.model_path = target_path
        self.pipeline = joblib.load(target_path)
        self.model_version = os.environ.get("MODEL_VERSION", "baseline-logreg-v1")
        logger.info(
            "ConversionService initialized with model_version=%s from path=%s",
            self.model_version,
            self.model_path,
        )

    @bentoml.api
    def predict(self, request: PredictionRequest) -> PredictionResponse:
        start_time = time.perf_counter()
        request_id = str(uuid.uuid4())

        row = pd.DataFrame(
            [
                {
                    "channelGrouping": request.channelGrouping,
                    "device_category": request.device_category,
                    "browser": request.browser,
                    "operating_system": request.operating_system,
                    "country": request.country,
                    "continent": request.continent,
                    "traffic_source": request.traffic_source,
                    "traffic_medium": request.traffic_medium,
                    "visitNumber": request.visitNumber,
                    "visits": request.visits,
                    "hits": request.hits,
                    "pageviews": request.pageviews,
                    "time_on_site": request.time_on_site,
                }
            ]
        )

        proba = float(self.pipeline.predict_proba(row)[0, 1])
        prediction = int(proba >= 0.5)

        latency_ms = (time.perf_counter() - start_time) * 1000.0
        logger.info(
            "request_id=%s prediction=%d probability=%.4f latency_ms=%.2f",
            request_id,
            prediction,
            proba,
            latency_ms,
        )

        return PredictionResponse(
            prediction=prediction,
            conversion_probability=proba,
            model_version=self.model_version,
            request_id=request_id,
        )

    def health(self) -> HealthResponse:
        return HealthResponse(
            status="ok",
            model_version=self.model_version,
            model_path=str(self.model_path),
        )

