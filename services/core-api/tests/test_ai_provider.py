import pytest

import httpx

from app.ai.provider import chat_completions_url, normalize_base_url, probe_provider
from app.models import Base


def test_ai_provider_table_contains_only_non_secret_configuration():
    table = Base.metadata.tables["ai_provider_configs"]

    expected = {
        "id",
        "provider_name",
        "base_url",
        "text_model",
        "vision_model",
        "temperature",
        "timeout_seconds",
        "supports_json_schema",
        "supports_vision",
        "secret_ref",
        "created_at",
        "updated_at",
    }
    assert expected == set(table.c.keys())
    assert "api_key" not in table.c
    assert table.c.id.primary_key is True


def test_provider_base_url_is_normalized_and_chat_endpoint_is_stable():
    assert normalize_base_url("https://example.com/v1/") == "https://example.com/v1"
    assert chat_completions_url("https://example.com/v1/") == "https://example.com/v1/chat/completions"
    assert chat_completions_url("http://127.0.0.1:8000") == "http://127.0.0.1:8000/v1/chat/completions"
    assert chat_completions_url("https://open.bigmodel.cn/api/paas/v4") == "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    assert chat_completions_url("https://generativelanguage.googleapis.com/v1beta/openai") == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "ftp://example.com/v1",
        "https://user:pass@example.com/v1",
        "https://example.com/v1?token=secret",
        "https://example.com/v1#fragment",
        "https:///v1",
    ],
)
def test_provider_base_url_rejects_unsafe_or_ambiguous_values(value):
    with pytest.raises(ValueError):
        normalize_base_url(value)


def test_provider_probe_uses_openai_chat_shape_and_authorization_header():
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("Authorization")
        captured["body"] = request.read().decode("utf-8")
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})

    result = probe_provider(
        base_url="https://open.bigmodel.cn/api/paas/v4",
        api_key="sk-secret",
        model="glm-4.7",
        timeout_seconds=30,
        transport=httpx.MockTransport(handler),
    )

    assert result.status_code == 200
    assert captured["url"] == "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    assert captured["authorization"] == "Bearer sk-secret"
    assert '"model":"glm-4.7"' in str(captured["body"])
