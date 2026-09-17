"""Session-token trust boundary for the sidecar mode."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

TOKEN = "secret-launch-token"


@pytest.fixture
def token_client(tmp_path, monkeypatch):
    monkeypatch.setenv("XIAOYUE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("XIAOYUE_SESSION_TOKEN", TOKEN)
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
    ok = token_client.get("/api/jobs/stats", headers={"Authorization": f"Bearer {TOKEN}"})
    assert ok.status_code == 200


def test_no_token_configured_means_open_local_api(tmp_path, monkeypatch):
    monkeypatch.setenv("XIAOYUE_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("XIAOYUE_SESSION_TOKEN", raising=False)
    client = TestClient(create_app())
    assert client.get("/api/jobs/stats").status_code == 200


def test_401_body_never_echoes_any_token(token_client):
    response = token_client.get("/api/jobs/stats", headers={"Authorization": "Bearer attacker-guess"})
    assert response.status_code == 401
    assert "attacker-guess" not in response.text
    assert TOKEN not in response.text


def test_api_rejects_foreign_origin(token_client):
    headers = {"Authorization": f"Bearer {TOKEN}", "Origin": "https://evil.example.com"}
    response = token_client.get("/api/jobs/stats", headers=headers)
    assert response.status_code == 403


def test_api_allows_tauri_origin(token_client):
    headers = {"Authorization": f"Bearer {TOKEN}", "Origin": "tauri://localhost"}
    response = token_client.get("/api/jobs/stats", headers=headers)
    assert response.status_code == 200


def _every_api_route_path(application) -> list[str]:
    """Walk included routers: newer FastAPI wraps include_router results in
    _IncludedRouter; older versions expose APIRoute entries directly."""
    paths: list[str] = []
    for route in application.routes:
        inner_router = getattr(route, "original_router", None)
        if inner_router is not None:
            paths.extend(
                inner.path for inner in inner_router.routes if getattr(inner, "path", None)
            )
        else:
            path = getattr(route, "path", None)
            if path:
                paths.append(path)
    return [path for path in paths if path.startswith("/api")]


def test_every_api_route_is_behind_the_guard(token_client):
    """Every registered route must live under /api: the middleware protects
    /api/* (health exempt), so any future router — including high-privilege
    Browser Agent routes — cannot accidentally sit outside the guard."""
    paths = _every_api_route_path(token_client.app)
    assert paths, "no routes discovered; walker needs updating"
    escaped = [path for path in paths if not path.startswith("/api/")]
    assert escaped == [], f"routes escaped the /api prefix: {escaped}"

    guarded = [path for path in paths if path != "/api/health"]
    assert len(guarded) >= 20, f"suspiciously few guarded routes: {guarded}"
    for path in guarded:
        method = "GET" if not path.endswith("/import") else "POST"
        response = token_client.request(method, path)
        assert response.status_code == 401, f"{method} {path} leaked without token"


def test_token_never_reaches_the_database(token_client, tmp_path):
    headers = {"Authorization": f"Bearer {TOKEN}"}
    assert token_client.get("/api/jobs/stats", headers=headers).status_code == 200
    db_bytes = (tmp_path / "xiaoyue.db").read_bytes()
    assert TOKEN.encode() not in db_bytes
