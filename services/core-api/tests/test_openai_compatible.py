from __future__ import annotations

import json

import httpx
import pytest

from app.ai.openai_compatible import (
    OpenAICompatibleClient,
    ProviderRequestError,
    ProviderResponseError,
    ProviderTimeoutError,
)
from app.models import AIProviderConfig


def make_config(*, supports_json_schema: bool = True, timeout_seconds: int = 23) -> AIProviderConfig:
    return AIProviderConfig(
        id="default",
        provider_name="Test Provider",
        base_url="https://example.com/v1",
        text_model="reasoning-model",
        vision_model=None,
        temperature=0.2,
        timeout_seconds=timeout_seconds,
        supports_json_schema=supports_json_schema,
        supports_vision=False,
    )


def completion(content: str, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code,
        json={"choices": [{"message": {"content": content}}]},
    )


def test_client_sends_configured_openai_compatible_request_with_json_schema():
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("Authorization")
        captured["content_type"] = request.headers.get("Content-Type")
        captured["body"] = json.loads(request.content)
        captured["timeout"] = request.extensions.get("timeout")
        return completion(
            json.dumps(
                {
                    "candidates": [
                        {"field_key": "education.school", "value": "三江学院", "confidence": 0.98},
                    ]
                },
                ensure_ascii=False,
            )
        )

    client = OpenAICompatibleClient(transport=httpx.MockTransport(handler))
    result = client.extract_candidates(make_config(), "sk-test-secret", "姓名：测试\n学校：三江学院")

    assert str(captured["url"]) == "https://example.com/v1/chat/completions"
    assert captured["authorization"] == "Bearer sk-test-secret"
    assert captured["content_type"] == "application/json"
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["model"] == "reasoning-model"
    assert body["temperature"] == 0.2
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True
    prompt_text = json.dumps(body["messages"], ensure_ascii=False)
    assert "education.school" in prompt_text
    assert "job.target_roles" in prompt_text
    assert "三江学院" in prompt_text
    timeout = captured["timeout"]
    assert isinstance(timeout, dict)
    assert timeout["read"] == 23.0
    assert result[0].field_key == "education.school"
    assert result[0].value == "三江学院"
    assert result[0].confidence == 0.98


def test_client_can_request_plain_json_without_json_schema_capability():
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return completion('{"candidates": []}')

    client = OpenAICompatibleClient(transport=httpx.MockTransport(handler))
    assert client.extract_candidates(make_config(supports_json_schema=False), "sk-test", "resume") == []
    body = captured["body"]
    assert isinstance(body, dict)
    assert "response_format" not in body


def test_client_accepts_markdown_fenced_json_content():
    def handler(request: httpx.Request) -> httpx.Response:
        return completion(
            "```json\n"
            '{"candidates":[{"field_key":"job.target_roles","value":["平面设计"],"confidence":0.9}]}'
            "\n```"
        )

    result = OpenAICompatibleClient(transport=httpx.MockTransport(handler)).extract_candidates(
        make_config(), "sk-test", "目标岗位：平面设计"
    )
    assert result[0].field_key == "job.target_roles"
    assert result[0].value == ["平面设计"]


@pytest.mark.parametrize("status_code", [401, 500])
def test_upstream_http_errors_are_safe_and_do_not_echo_api_key(status_code):
    secret = "sk-never-echo-this"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"error": {"message": "provider rejected request"}})

    with pytest.raises(ProviderRequestError) as error:
        OpenAICompatibleClient(transport=httpx.MockTransport(handler)).extract_candidates(
            make_config(), secret, "private resume text"
        )

    assert f"HTTP {status_code}" in str(error.value)
    assert secret not in str(error.value)
    assert "private resume text" not in str(error.value)


def test_provider_timeout_maps_to_safe_domain_error():
    secret = "sk-never-echo-this"

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("simulated timeout", request=request)

    with pytest.raises(ProviderTimeoutError) as error:
        OpenAICompatibleClient(transport=httpx.MockTransport(handler)).extract_candidates(
            make_config(), secret, "private resume text"
        )

    assert secret not in str(error.value)
    assert "private resume text" not in str(error.value)


@pytest.mark.parametrize(
    "response_json",
    [
        {},
        {"choices": []},
        {"choices": [{"message": {}}]},
        {"choices": [{"message": {"content": "not json"}}]},
        {"choices": [{"message": {"content": '{"wrong": []}'}}]},
        {"choices": [{"message": {"content": '{"candidates":[{"field_key":1,"value":"x","confidence":0.5}]}'}}]},
        {"choices": [{"message": {"content": '{"candidates":[{"field_key":"education.school","value":{"x":1},"confidence":0.5}]}'}}]},
    ],
)
def test_malformed_provider_responses_are_rejected(response_json):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=response_json)

    with pytest.raises(ProviderResponseError):
        OpenAICompatibleClient(transport=httpx.MockTransport(handler)).extract_candidates(
            make_config(), "sk-test", "resume"
        )
