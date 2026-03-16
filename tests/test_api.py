from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

import api


@pytest.fixture(autouse=True)
def clear_pending_incidents():
    with api.pending_incidents_lock:
        api.pending_incidents.clear()
    yield
    with api.pending_incidents_lock:
        api.pending_incidents.clear()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(api.app)


def test_health_endpoints(client: TestClient):
    live = client.get("/healthz")
    assert live.status_code == 200
    assert live.json()["status"] == "ok"

    ready = client.get("/readyz")
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"


def test_webhook_accepts_alert_and_starts_background_task(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    calls: list[tuple[str, dict, bool]] = []

    def fake_run_graph_thread(thread_id: str, state: dict | None = None, resume: bool = False):
        calls.append((thread_id, state or {}, resume))

    monkeypatch.setattr(api, "run_graph_thread", fake_run_graph_thread)

    payload = {
        "service": "api-gateway",
        "alert_name": "HighLatency",
        "severity": "critical",
        "metrics": {"latency_ms": 3500.0, "cpu_pct": 98.0},
    }

    response = client.post("/webhook/alert", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "accepted"
    assert "thread_id" in body

    assert len(calls) == 1
    assert calls[0][0] == body["thread_id"]
    assert calls[0][2] is False


def test_pending_incidents_returns_data(client: TestClient):
    with api.pending_incidents_lock:
        api.pending_incidents["thread-1"] = {
            "service": "payment-gateway",
            "action": "restart_pod",
            "confidence": 0.9,
            "rationale": "Test rationale",
            "rollback": "rollback_restart_pod({...})",
        }

    response = client.get("/api/incidents/pending")
    assert response.status_code == 200
    data = response.json()
    assert data["pending_count"] == 1
    assert "thread-1" in data["incidents"]


def test_approve_returns_404_for_unknown_thread(client: TestClient):
    response = client.post("/api/incidents/does-not-exist/approve")
    assert response.status_code == 404


def test_reject_returns_404_for_unknown_thread(client: TestClient):
    response = client.post("/api/incidents/does-not-exist/reject")
    assert response.status_code == 404


def test_optional_api_key_enforced_when_enabled(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    monkeypatch.setattr(api.settings, "api_key_enabled", True)
    monkeypatch.setattr(api.settings, "api_key", "secret123")

    payload = {
        "service": "api-gateway",
        "alert_name": "HighLatency",
        "severity": "critical",
        "metrics": {"latency_ms": 3500.0, "cpu_pct": 98.0},
    }

    unauthorized = client.post("/webhook/alert", json=payload)
    assert unauthorized.status_code == 401

    authorized = client.post("/webhook/alert", json=payload, headers={"x-api-key": "secret123"})
    assert authorized.status_code == 200

    monkeypatch.setattr(api.settings, "api_key_enabled", False)
    monkeypatch.setattr(api.settings, "api_key", "")
