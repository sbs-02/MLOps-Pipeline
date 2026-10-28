"""Prometheus metrics exporter for data drift and model-quality signals (Gate 11).

All metrics use bounded cardinality labels per CONTEXT.md principles (never session/visitor IDs or PII).
"""

from __future__ import annotations

import logging
from typing import Any

from prometheus_client import CollectorRegistry, Counter, Gauge, Summary, generate_latest

logger = logging.getLogger("services.metrics")


class DriftMetricsManager:
    """Manages Prometheus metrics for data drift, concept drift, and model serving."""

    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        self.registry = registry or CollectorRegistry(auto_describe=True)

        # 1. Data drift gauges (bounded labels: model_version)
        self.data_drift_detected = Gauge(
            "model_data_drift_detected",
            "1 if overall dataset data drift is detected, 0 otherwise",
            ["model_version"],
            registry=self.registry,
        )
        self.drift_share = Gauge(
            "model_drift_share",
            "Fraction of features exhibiting statistical drift [0.0, 1.0]",
            ["model_version"],
            registry=self.registry,
        )
        self.drifted_features_count = Gauge(
            "model_drifted_features_count",
            "Number of individual features exhibiting statistical drift",
            ["model_version"],
            registry=self.registry,
        )

        # 2. Per-feature drift indicators (bounded labels: feature, method, model_version)
        self.feature_drift = Gauge(
            "model_feature_drift",
            "1 if this specific feature has drifted, 0 otherwise",
            ["feature", "method", "model_version"],
            registry=self.registry,
        )

        # 3. Concept drift / model quality gauges
        # Status encoding: 0 = labels_pending, 1 = evaluated_healthy, 2 = evaluated_degraded
        self.concept_drift_status = Gauge(
            "model_concept_drift_status",
            "Concept drift state: 0=labels_pending, 1=evaluated_healthy, 2=evaluated_degraded",
            ["model_version"],
            registry=self.registry,
        )
        self.batch_f1 = Gauge(
            "model_batch_f1_score",
            "F1 score of model evaluated on latest labeled batch",
            ["model_version"],
            registry=self.registry,
        )
        self.batch_pr_auc = Gauge(
            "model_batch_pr_auc_score",
            "PR-AUC (average precision) of model evaluated on latest labeled batch",
            ["model_version"],
            registry=self.registry,
        )

        # 4. Serving throughput and latency metrics
        self.prediction_requests = Counter(
            "model_prediction_requests_total",
            "Total prediction requests served",
            ["model_version", "status"],
            registry=self.registry,
        )
        self.prediction_latency = Summary(
            "model_prediction_latency_seconds",
            "Inference request latency in seconds",
            ["model_version"],
            registry=self.registry,
        )

    def update_from_summary(
        self,
        drift_results: dict[str, Any],
        model_version: str = "baseline-logreg-v1",
    ) -> None:
        """Update Prometheus gauges from DriftDetector evaluation output."""
        data_drift = drift_results.get("data_drift") or (
            drift_results if "dataset_drift_detected" in drift_results else {}
        )
        concept_drift = drift_results.get("concept_drift") or (
            drift_results if "concept_drift_status" in drift_results else {}
        )

        # Update data drift metrics
        if data_drift:
            self.data_drift_detected.labels(model_version=model_version).set(
                1.0 if data_drift.get("dataset_drift_detected", False) else 0.0
            )
            self.drift_share.labels(model_version=model_version).set(
                float(data_drift.get("drift_share", 0.0))
            )
            self.drifted_features_count.labels(model_version=model_version).set(
                float(data_drift.get("drifted_features_count", 0))
            )

            # Per-feature drift flags
            for feat, res in data_drift.get("per_feature_metrics", {}).items():
                method = res.get("method", "unknown")
                drift_flag = 1.0 if res.get("drift_detected", False) else 0.0
                self.feature_drift.labels(
                    feature=feat, method=method, model_version=model_version
                ).set(drift_flag)

        # Update concept drift metrics
        if concept_drift:
            status_str = concept_drift.get("concept_drift_status", "labels_pending")
            if status_str == "labels_pending":
                status_code = 0.0
            elif concept_drift.get("concept_drift_detected", False):
                status_code = 2.0  # degraded
            else:
                status_code = 1.0  # healthy

            self.concept_drift_status.labels(model_version=model_version).set(status_code)

            if "batch_f1" in concept_drift:
                self.batch_f1.labels(model_version=model_version).set(
                    float(concept_drift["batch_f1"])
                )
            if "batch_pr_auc" in concept_drift:
                self.batch_pr_auc.labels(model_version=model_version).set(
                    float(concept_drift["batch_pr_auc"])
                )

    def generate_exposition(self) -> str:
        """Return Prometheus text exposition format string."""
        return generate_latest(self.registry).decode("utf-8")


def main() -> None:
    from analytics_ml.monitoring.drift_detector import run_drift_pipeline

    print("Generating sample drift evaluation...")
    summary = run_drift_pipeline()

    manager = DriftMetricsManager()
    # Update metrics with the holdout 2017Q3 results
    manager.update_from_summary(summary["holdout_2017Q3"], model_version="baseline-logreg-v1")

    exposition = manager.generate_exposition()
    print("\n--- Sample Prometheus Exposition (excerpt) ---")
    lines = [line for line in exposition.splitlines() if not line.startswith("#") and line.strip()]
    for line in lines[:15]:
        print(" ", line)
    print(f" ... ({len(lines)} active metrics)")


if __name__ == "__main__":
    main()
