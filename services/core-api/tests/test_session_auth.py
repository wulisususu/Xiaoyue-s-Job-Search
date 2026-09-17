"""Session-token trust boundary for the sidecar mode."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def token_client(tmp_path, monkeypatch):
    monkeypatch.setenv("XIAOYUE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("XIAOYUE_SESSION_TOKEN", "secret-launch-token")
    # Bind to the loopback host the sidecar middleware expects.
    return TestClient(create_app(), base_url="http://127.0.0.1")


def test_health_stays_open_for_sidecar_probe(token_client):
    assert token_client.get("/api/health").status_code == 200


def test_api_rejects_disallowed_host(token_client):
    response = token_client.get("/api/jobs/stats", headers={"Host": "evil.example.com:8765"})
    assert response.status_code == 403


def test_api_rejects_missing_or_wrong_token(token_client):
    missing = token_client.get("/api/jobs")
    assert missing.status_code == 401
    wrong = token_client.get("/api/jobs", headers={"Authorization": "Bearer nope"})
    assert wrong.status_code == 401


def test_api_accepts_correct_bearer_token(token_client):
    ok = token_client.get("/api/jobs/stats", headers={"Authorization": "Bearer secret-launch-token"})
    assert ok.status_code == 200


def test_no_token_configured_means_open_local_api(tmp_path, monkeypatch):
    monkeypatch.setenv("XIAOYUE_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("XIAOYUE_SESSION_TOKEN", raising=False)
    client = TestClient(create_app())
    assert client.get("/api/jobs/stats").status_code == 200
