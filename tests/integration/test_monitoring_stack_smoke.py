"""Integration smoke test for Prometheus & Grafana configurations and schemas (Gate 11)."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_prometheus_configuration_valid() -> None:
    prom_path = PROJECT_ROOT / "monitoring" / "prometheus" / "prometheus.yml"
    assert prom_path.exists()

    config = yaml.safe_load(prom_path.read_text(encoding="utf-8"))
    assert "scrape_configs" in config

    job_names = {job["job_name"] for job in config["scrape_configs"]}
    assert "prometheus" in job_names
    assert "drift_monitoring" in job_names
    assert "prediction_service" in job_names
    assert "approval_service" in job_names


def test_grafana_dashboard_json_valid() -> None:
    dash_path = PROJECT_ROOT / "monitoring" / "grafana" / "dashboards" / "drift_monitoring.json"
    assert dash_path.exists()

    dash = json.loads(dash_path.read_text(encoding="utf-8"))
    assert dash["title"] == "Model Drift & Quality Monitoring"
    assert len(dash["panels"]) >= 5

    # Check panel queries contain our expected metric names
    all_exprs: list[str] = []
    for p in dash["panels"]:
        for target in p.get("targets", []):
            if "expr" in target:
                all_exprs.append(target["expr"])

    assert any("model_data_drift_detected" in e for e in all_exprs)
    assert any("model_drifted_features_count" in e for e in all_exprs)
    assert any("model_concept_drift_status" in e for e in all_exprs)
    assert any("model_batch_f1_score" in e for e in all_exprs)


def test_grafana_alert_rules_yaml_valid() -> None:
    alert_path = PROJECT_ROOT / "monitoring" / "grafana" / "provisioning" / "alerting" / "alert_rules.yaml"
    assert alert_path.exists()

    alert_config = yaml.safe_load(alert_path.read_text(encoding="utf-8"))
    assert "groups" in alert_config

    rules = alert_config["groups"][0]["rules"]
    assert len(rules) >= 2

    rule_titles = [r["title"] for r in rules]
    assert any("Data Drift" in t for t in rule_titles)
    assert any("Concept Drift" in t for t in rule_titles)

    # Check that annotations contain local approval URL
    for r in rules:
        runbook = r["annotations"].get("runbook_url", "")
        assert "127.0.0.1:8000/approvals" in runbook


def test_docker_compose_yaml_valid() -> None:
    compose_path = PROJECT_ROOT / "docker-compose.yml"
    assert compose_path.exists()

    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    assert "services" in compose
    services = compose["services"]
    assert "prometheus" in services
    assert "grafana" in services
