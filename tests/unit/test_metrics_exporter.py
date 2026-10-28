"""Unit tests for Prometheus metrics exporter and cardinality bounds (Gate 11)."""

from __future__ import annotations

import pytest
from prometheus_client import CollectorRegistry

from analytics_ml.monitoring.metrics_exporter import DriftMetricsManager


def test_metrics_manager_registers_expected_gauges() -> None:
    registry = CollectorRegistry()
    manager = DriftMetricsManager(registry=registry)

    exposition = manager.generate_exposition()
    assert "model_data_drift_detected" in exposition
    assert "model_drift_share" in exposition
    assert "model_drifted_features_count" in exposition
    assert "model_feature_drift" in exposition
    assert "model_concept_drift_status" in exposition
    assert "model_batch_f1_score" in exposition


def test_metrics_labels_are_strictly_bounded() -> None:
    """Never allow visitor IDs, session IDs, or PII as Prometheus labels."""
    registry = CollectorRegistry()
    manager = DriftMetricsManager(registry=registry)

    forbidden_labels = {"fullVisitorId", "visitId", "user_id", "email", "ip", "client_id"}

    for collector in registry.collect():
        for sample in collector.samples:
            sample_label_keys = set(sample.labels.keys())
            assert sample_label_keys.isdisjoint(forbidden_labels)


def test_update_from_summary_data_drift_and_pending_labels() -> None:
    registry = CollectorRegistry()
    manager = DriftMetricsManager(registry=registry)

    mock_summary = {
        "data_drift": {
            "dataset_drift_detected": True,
            "drift_share": 0.6154,
            "drifted_features_count": 8,
            "per_feature_metrics": {
                "hits": {"method": "kolmogorov_smirnov", "drift_detected": True},
                "channelGrouping": {"method": "jensen_shannon", "drift_detected": False},
            },
        },
        "concept_drift": {
            "concept_drift_status": "labels_pending",
            "concept_drift_detected": False,
        },
    }

    manager.update_from_summary(mock_summary, model_version="test-v1")
    exposition = manager.generate_exposition()

    assert 'model_data_drift_detected{model_version="test-v1"} 1.0' in exposition
    assert 'model_drift_share{model_version="test-v1"} 0.6154' in exposition
    assert 'model_drifted_features_count{model_version="test-v1"} 8.0' in exposition
    assert 'model_concept_drift_status{model_version="test-v1"} 0.0' in exposition
    assert (
        'model_feature_drift{feature="hits",method="kolmogorov_smirnov",model_version="test-v1"} 1.0'
        in exposition
    )
    assert (
        'model_feature_drift{feature="channelGrouping",method="jensen_shannon",model_version="test-v1"} 0.0'
        in exposition
    )


def test_update_from_summary_evaluated_concept_drift() -> None:
    registry = CollectorRegistry()
    manager = DriftMetricsManager(registry=registry)

    mock_summary = {
        "data_drift": {
            "dataset_drift_detected": False,
            "drift_share": 0.1,
            "drifted_features_count": 1,
            "per_feature_metrics": {},
        },
        "concept_drift": {
            "concept_drift_status": "evaluated",
            "concept_drift_detected": True,  # degraded
            "batch_f1": 0.25,
            "batch_pr_auc": 0.31,
        },
    }

    manager.update_from_summary(mock_summary, model_version="test-v2")
    exposition = manager.generate_exposition()

    assert 'model_data_drift_detected{model_version="test-v2"} 0.0' in exposition
    assert 'model_concept_drift_status{model_version="test-v2"} 2.0' in exposition
    assert 'model_batch_f1_score{model_version="test-v2"} 0.25' in exposition
    assert 'model_batch_pr_auc_score{model_version="test-v2"} 0.31' in exposition
