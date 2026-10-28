"""Unit tests for the BentoML prediction service schemas and logic (Gate 9)."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from pydantic import ValidationError

from services.prediction.service import (
    ConversionService,
    PredictionRequest,
    PredictionResponse,
    HealthResponse,
)


def valid_payload_dict() -> dict[str, str | int]:
    return {
        "channelGrouping": "Organic Search",
        "device_category": "desktop",
        "browser": "Chrome",
        "operating_system": "Windows",
        "country": "United States",
        "continent": "Americas",
        "traffic_source": "google",
        "traffic_medium": "organic",
        "visitNumber": 1,
        "visits": 1,
        "hits": 10,
        "pageviews": 8,
        "time_on_site": 150,
    }


def test_valid_prediction_request() -> None:
    req = PredictionRequest(**valid_payload_dict())
    assert req.channelGrouping == "Organic Search"
    assert req.hits == 10
    assert req.time_on_site == 150


def test_prediction_request_rejects_empty_categorical() -> None:
    data = valid_payload_dict()
    data["browser"] = ""  # empty string should fail min_length=1
    with pytest.raises(ValidationError):
        PredictionRequest(**data)


def test_prediction_request_rejects_invalid_numeric_bounds() -> None:
    # visitNumber must be >= 1
    data = valid_payload_dict()
    data["visitNumber"] = 0
    with pytest.raises(ValidationError):
        PredictionRequest(**data)

    # hits must be >= 0
    data = valid_payload_dict()
    data["hits"] = -1
    with pytest.raises(ValidationError):
        PredictionRequest(**data)

    # time_on_site must be >= 0
    data = valid_payload_dict()
    data["time_on_site"] = -10
    with pytest.raises(ValidationError):
        PredictionRequest(**data)


def test_prediction_request_missing_required_fields() -> None:
    data = valid_payload_dict()
    del data["channelGrouping"]
    with pytest.raises(ValidationError):
        PredictionRequest(**data)


def test_conversion_service_missing_model_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    bogus_path = Path("models/does_not_exist.joblib")
    monkeypatch.setenv("MODEL_PATH", str(bogus_path))
    with pytest.raises(FileNotFoundError, match="Model artifact not found"):
        ConversionService()


def test_conversion_service_predict_and_health() -> None:
    service = ConversionService()
    health = service.health()
    assert isinstance(health, HealthResponse)
    assert health.status == "ok"
    assert "baseline-logreg-v1" in health.model_version

    req = PredictionRequest(**valid_payload_dict())
    resp = service.predict(req)
    assert isinstance(resp, PredictionResponse)
    assert resp.prediction in (0, 1)
    assert 0.0 <= resp.conversion_probability <= 1.0
    assert resp.model_version == "baseline-logreg-v1"

    # Verify request_id is a valid UUID4
    parsed_uuid = uuid.UUID(resp.request_id, version=4)
    assert str(parsed_uuid) == resp.request_id
