from __future__ import annotations

import json

import httpx
import pytest

from app.ai.json_client import OpenAICompatibleJSONClient
from app.ai.errors import ProviderResponseError
from app.models import AIProviderConfig


def config(*, supports_json_schema: bool = True):
    return AIProviderConfig(
        id="default",
        provider_name="Test",
        base_url="https://example.com/v1",
        text_model="test-model",
        vision_model=None,
        temperature=0.1,
        timeout_seconds=20,
        supports_json_schema=supports_json_schema,
        supports_vision=False,
    )


def test_generic_json_client_uses_same_openai_compatible_transport_and_schema_contract():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("Authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"matches":[]}'}}]},
        )

    client = OpenAICompatibleJSONClient(
        config(),
        "sk-secret",
        transport=httpx.MockTransport(handler),
    )
    result = client.complete_json(
        messages=[{"role": "user", "content": "map fields"}],
        schema_name="browser_field_mapping",
        schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["matches"],
            "properties": {"matches": {"type": "array", "items": {"type": "object"}}},
        },
    )

    assert result == {"matches": []}
    assert captured["url"] == "https://example.com/v1/chat/completions"
    assert captured["authorization"] == "Bearer sk-secret"
    assert captured["body"]["model"] == "test-model"
    assert captured["body"]["response_format"]["type"] == "json_schema"
    assert captured["body"]["response_format"]["json_schema"]["name"] == "browser_field_mapping"


def test_generic_json_client_rejects_non_json_completion():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "not-json"}}]})

    client = OpenAICompatibleJSONClient(
        config(supports_json_schema=False),
        "sk-secret",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ProviderResponseError):
        client.complete_json(
            messages=[{"role": "user", "content": "map"}],
            schema_name="ignored",
            schema={"type": "object"},
        )
