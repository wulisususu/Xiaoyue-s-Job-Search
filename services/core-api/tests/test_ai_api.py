from __future__ import annotations

from sqlalchemy.orm import Session

from app.ai.provider import ProviderProbeResult
from app.ai.secrets import DEFAULT_AI_API_KEY_REF, CredentialStoreUnavailableError
from app.config import get_settings
from app.db import get_engine
from app.models import AIProviderConfig
from app.routes import ai as ai_routes


class MemorySecretStore:
    def __init__(self):
        self.values: dict[str, str] = {}

    def set_secret(self, ref: str, value: str) -> None:
        self.values[ref] = value

    def get_secret(self, ref: str) -> str | None:
        return self.values.get(ref)

    def delete_secret(self, ref: str) -> None:
        self.values.pop(ref, None)


class UnavailableSecretStore(MemorySecretStore):
    def set_secret(self, ref: str, value: str) -> None:
        raise CredentialStoreUnavailableError("credential backend unavailable")

    def get_secret(self, ref: str) -> str | None:
        raise CredentialStoreUnavailableError("credential backend unavailable")

    def delete_secret(self, ref: str) -> None:
        raise CredentialStoreUnavailableError("credential backend unavailable")


PROVIDER_PAYLOAD = {
    "provider_name": "OpenAI Compatible",
    "base_url": "https://example.com/v1/",
    "text_model": "reasoning-model",
    "vision_model": "vision-model",
    "temperature": 0.0,
    "timeout_seconds": 60,
    "supports_json_schema": True,
    "supports_vision": True,
}


def test_provider_api_starts_unconfigured_and_saves_only_non_secret_settings(client, monkeypatch):
    store = MemorySecretStore()
    monkeypatch.setattr(ai_routes, "get_secret_store", lambda: store)

    initial = client.get("/api/ai/provider")
    assert initial.status_code == 200
    assert initial.json() is None

    saved = client.put("/api/ai/provider", json=PROVIDER_PAYLOAD)
    assert saved.status_code == 200
    payload = saved.json()
    assert payload == {
        "id": "default",
        "provider_name": "OpenAI Compatible",
        "base_url": "https://example.com/v1",
        "text_model": "reasoning-model",
        "vision_model": "vision-model",
        "temperature": 0.0,
        "timeout_seconds": 60,
        "supports_json_schema": True,
        "supports_vision": True,
        "has_api_key": False,
        "created_at": payload["created_at"],
        "updated_at": payload["updated_at"],
    }
    assert "api_key" not in payload
    assert "secret_ref" not in payload

    fetched = client.get("/api/ai/provider")
    assert fetched.status_code == 200
    assert fetched.json()["base_url"] == "https://example.com/v1"
    assert fetched.json()["has_api_key"] is False


def test_api_key_uses_dedicated_secret_endpoint_and_never_returns_secret(client, monkeypatch):
    store = MemorySecretStore()
    monkeypatch.setattr(ai_routes, "get_secret_store", lambda: store)
    assert client.put("/api/ai/provider", json=PROVIDER_PAYLOAD).status_code == 200

    secret_value = "sk-super-secret-value"
    saved = client.put("/api/ai/provider/api-key", json={"api_key": secret_value})
    assert saved.status_code == 200
    payload = saved.json()
    assert payload["has_api_key"] is True
    assert "api_key" not in payload
    assert "secret_ref" not in payload
    assert secret_value not in saved.text

    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            row = session.get(AIProviderConfig, "default")
            assert row is not None
            # The key lives under a unique rotation ref, never a predictable
            # shared one, and never leaks into DB columns.
            assert row.secret_ref is not None
            assert row.secret_ref.startswith(DEFAULT_AI_API_KEY_REF)
            assert store.values[row.secret_ref] == secret_value
            assert secret_value not in "|".join(
                str(value)
                for value in (
                    row.id,
                    row.provider_name,
                    row.base_url,
                    row.text_model,
                    row.vision_model,
                    row.secret_ref,
                )
            )
    finally:
        engine.dispose()

    removed = client.delete("/api/ai/provider/api-key")
    assert removed.status_code == 200
    assert removed.json()["has_api_key"] is False
    assert all(not ref.startswith(DEFAULT_AI_API_KEY_REF) for ref in store.values)

    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            row = session.get(AIProviderConfig, "default")
            assert row is not None
            assert row.secret_ref is None
    finally:
        engine.dispose()


def test_api_key_requires_provider_configuration(client, monkeypatch):
    monkeypatch.setattr(ai_routes, "get_secret_store", lambda: MemorySecretStore())

    response = client.put("/api/ai/provider/api-key", json={"api_key": "sk-test"})
    assert response.status_code == 409


def test_credential_store_unavailable_maps_to_503(client, monkeypatch):
    monkeypatch.setattr(ai_routes, "get_secret_store", lambda: UnavailableSecretStore())
    assert client.put("/api/ai/provider", json=PROVIDER_PAYLOAD).status_code == 200

    response = client.put("/api/ai/provider/api-key", json={"api_key": "sk-test"})
    assert response.status_code == 503
    assert "sk-test" not in response.text


def test_invalid_provider_configuration_is_rejected(client, monkeypatch):
    monkeypatch.setattr(ai_routes, "get_secret_store", lambda: MemorySecretStore())

    bad_url = client.put("/api/ai/provider", json={**PROVIDER_PAYLOAD, "base_url": "ftp://example.com"})
    assert bad_url.status_code == 422

    bad_temperature = client.put("/api/ai/provider", json={**PROVIDER_PAYLOAD, "temperature": 3.0})
    assert bad_temperature.status_code == 422

    bad_timeout = client.put("/api/ai/provider", json={**PROVIDER_PAYLOAD, "timeout_seconds": 1})
    assert bad_timeout.status_code == 422


def test_provider_connection_test_uses_saved_secret_without_echoing_it(client, monkeypatch):
    store = MemorySecretStore()
    monkeypatch.setattr(ai_routes, "get_secret_store", lambda: store)
    assert client.put("/api/ai/provider", json=PROVIDER_PAYLOAD).status_code == 200
    secret = "sk-probe-secret"
    assert client.put("/api/ai/provider/api-key", json={"api_key": secret}).status_code == 200

    captured: dict[str, object] = {}

    def fake_probe_provider(**kwargs):
        captured.update(kwargs)
        return ProviderProbeResult(status_code=200, latency_ms=17)

    monkeypatch.setattr(ai_routes, "probe_provider", fake_probe_provider)
    response = client.post("/api/ai/provider/test")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "provider_name": "OpenAI Compatible",
        "model": "reasoning-model",
        "latency_ms": 17,
    }
    assert captured["base_url"] == "https://example.com/v1"
    assert captured["api_key"] == secret
    assert secret not in response.text


def test_provider_connection_test_requires_provider_and_key(client, monkeypatch):
    store = MemorySecretStore()
    monkeypatch.setattr(ai_routes, "get_secret_store", lambda: store)

    assert client.post("/api/ai/provider/test").status_code == 409
    assert client.put("/api/ai/provider", json=PROVIDER_PAYLOAD).status_code == 200
    response = client.post("/api/ai/provider/test")
    assert response.status_code == 409
