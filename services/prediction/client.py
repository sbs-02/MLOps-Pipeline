"""Example client for the purchase-conversion prediction service (Gate 9)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.prediction.service import ConversionService, PredictionRequest


def main() -> None:
    print("Initializing local ConversionService...")
    service = ConversionService()

    # Health check
    health = service.health()
    print("\n--- Health Check ---")
    print(json.dumps(health.model_dump(), indent=2))

    # Example 1: Typical non-converting session (single hit, bounced, mobile)
    non_converter_payload = PredictionRequest(
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

    print("\n--- Example 1: Low-intent session ---")
    print("Input:", json.dumps(non_converter_payload.model_dump(), indent=2))
    resp1 = service.predict(non_converter_payload)
    print("Response:", json.dumps(resp1.model_dump(), indent=2))

    # Example 2: High-intent returning session (desktop, multiple pageviews, long duration)
    converter_payload = PredictionRequest(
        channelGrouping="Referral",
        device_category="desktop",
        browser="Chrome",
        operating_system="Windows",
        country="United States",
        continent="Americas",
        traffic_source="mall.googleplex.com",
        traffic_medium="referral",
        visitNumber=4,
        visits=1,
        hits=45,
        pageviews=35,
        time_on_site=900,
    )

    print("\n--- Example 2: High-intent returning session ---")
    print("Input:", json.dumps(converter_payload.model_dump(), indent=2))
    resp2 = service.predict(converter_payload)
    print("Response:", json.dumps(resp2.model_dump(), indent=2))


if __name__ == "__main__":
    main()
