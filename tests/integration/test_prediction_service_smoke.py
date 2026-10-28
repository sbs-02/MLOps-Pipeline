"""Integration test: exercise the BentoML ConversionService against the real model artifact (Gate 9)."""

from __future__ import annotations

import json
from pathlib import Path

from services.prediction.service import ConversionService, PredictionRequest

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_service_with_real_artifact_and_schemas() -> None:
    # 1. Verify feature schema matches request fields
    schema_path = PROJECT_ROOT / "models" / "feature_schema.json"
    assert schema_path.exists(), "Feature schema must exist in models/"
    feature_schema = json.loads(schema_path.read_text(encoding="utf-8"))

    expected_features = set(feature_schema["features"])

    low_intent = PredictionRequest(
        channelGrouping="Organic Search",
        device_category="mobile",
        browser="Chrome",
        operating_system="Android",
        country="India",
        continent="Asia",
        traffic_source="google",
        traffic_medium="organic",
        visitNumber=1,
        visits=1,
        hits=1,
        pageviews=1,
        time_on_site=0,
    )

    high_intent = PredictionRequest(
        channelGrouping="Referral",
        device_category="desktop",
        browser="Chrome",
        operating_system="Windows",
        country="United States",
        continent="Americas",
        traffic_source="mall.googleplex.com",
        traffic_medium="referral",
        visitNumber=5,
        visits=1,
        hits=50,
        pageviews=40,
        time_on_site=1200,
    )

    assert set(low_intent.model_dump().keys()) == expected_features
    assert set(high_intent.model_dump().keys()) == expected_features

    # 2. Instantiate real service and predict
    service = ConversionService()
    resp_low = service.predict(low_intent)
    resp_high = service.predict(high_intent)

    # High-intent session should have significantly higher conversion probability
    assert resp_high.conversion_probability > resp_low.conversion_probability
    assert resp_high.conversion_probability >= 0.5
    assert resp_high.prediction == 1
