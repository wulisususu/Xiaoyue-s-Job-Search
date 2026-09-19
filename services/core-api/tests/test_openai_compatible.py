from __future__ import annotations

import json

import httpx
import pytest

from app.ai.errors import ProviderInputError
from app.ai.openai_compatible import (
    MAX_INPUT_CHARS,
    MAX_OUTPUT_CHARS,
    OPENAI_COMPATIBLE_PROVIDER_ID,
    OPENAI_COMPATIBLE_PROMPT_VERSION,
    OPENAI_COMPATIBLE_SCHEMA_VERSION,
    OpenAICompatibleExtractionProvider,
    ProviderRequestError,
    ProviderResponseError,
    ProviderTimeoutError,
)
from app.models import AIProviderConfig
from app.profile.extraction import ExtractionMetadata, ProfileExtractionProvider
from test_unified_extraction_contract import check_bundle_contract

def make_config(
    *,
    supports_json_schema: bool = True,
    timeout_seconds: int = 23,
    base_url: str = "https://example.com/v1",
    text_model: str = "reasoning-model",
) -> AIProviderConfig:
    return AIProviderConfig(
        id="default",
        provider_name="Test Provider",
        base_url=base_url,
        text_model=text_model,
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


def bundle_payload(
    *,
    candidates: list[dict[str, object]] | None = None,
    collections: list[dict[str, object]] | None = None,
) -> str:
    payload: dict[str, object] = {"candidates": candidates or []}
    if collections is not None:
        payload["collections"] = collections
    return json.dumps(payload, ensure_ascii=False)


VALID_CANDIDATES = [
    {"field_key": "contact.email", "value": "name@example.com", "confidence": 0.99},
    {"field_key": "education.school", "value": "三江学院", "confidence": 0.98},
]
VALID_COLLECTIONS = [
    {"kind": "education", "payload": {"school": "三江学院", "major": "视觉传达设计"}, "confidence": 0.96},
    {"kind": "skill", "payload": {"name": "Python", "level": "熟练"}, "confidence": 0.88},
]


def make_provider(handler, config: AIProviderConfig | None = None) -> OpenAICompatibleExtractionProvider:
    return OpenAICompatibleExtractionProvider(
        config or make_config(),
        "sk-test-secret",
        transport=httpx.MockTransport(handler),
    )


def test_provider_sends_configured_request_and_returns_unified_bundle():
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("Authorization")
        captured["content_type"] = request.headers.get("Content-Type")
        captured["body"] = json.loads(request.content)
        captured["timeout"] = request.extensions.get("timeout")
        return completion(bundle_payload(candidates=VALID_CANDIDATES, collections=VALID_COLLECTIONS))

    bundle = make_provider(handler).extract("姓名：测试\n学校：三江学院")

    assert str(captured["url"]) == "https://example.com/v1/chat/completions"
    assert captured["authorization"] == "Bearer sk-test-secret"
    assert captured["content_type"] == "application/json"
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["model"] == "reasoning-model"
    assert body["temperature"] == 0.2
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True
    schema = body["response_format"]["json_schema"]["schema"]
    assert set(schema["properties"]) == {"candidates", "collections"}
    prompt_text = json.dumps(body["messages"], ensure_ascii=False)
    assert "education.school" in prompt_text
    assert "job.target_roles" in prompt_text
    assert "education" in prompt_text
    assert "school" in prompt_text
    assert "skill" in prompt_text
    assert "三江学院" in prompt_text
    timeout = captured["timeout"]
    assert isinstance(timeout, dict)
    assert timeout["read"] == 23.0

    assert bundle.metadata == ExtractionMetadata(
        provider=OPENAI_COMPATIBLE_PROVIDER_ID,
        model="reasoning-model",
        prompt_version=OPENAI_COMPATIBLE_PROMPT_VERSION,
        schema_version=OPENAI_COMPATIBLE_SCHEMA_VERSION,
    )


def test_provider_returns_scalar_fields_and_structured_collections_in_one_bundle():
    bundle = make_provider(lambda request: completion(bundle_payload(
        candidates=VALID_CANDIDATES,
        collections=VALID_COLLECTIONS,
    ))).extract("resume")

    check_bundle_contract(bundle)
    assert {(candidate.field_key, candidate.value) for candidate in bundle.fields} == {
        ("contact.email", "name@example.com"),
        ("education.school", "三江学院"),
    }
    assert [(candidate.kind, candidate.payload) for candidate in bundle.collections] == [
        ("education", {"school": "三江学院", "major": "视觉传达设计"}),
        ("skill", {"name": "Python", "level": "熟练"}),
    ]


def test_provider_satisfies_the_unified_contract_protocol():
    provider = make_provider(lambda request: completion(bundle_payload()))
    assert isinstance(provider, ProfileExtractionProvider)


def test_provider_metadata_reflects_endpoint_configuration_without_network():
    provider = make_provider(
        lambda request: (_ for _ in ()).throw(AssertionError("must not call the network"))
    )

    assert provider.metadata() == ExtractionMetadata(
        provider=OPENAI_COMPATIBLE_PROVIDER_ID,
        model="reasoning-model",
        prompt_version=OPENAI_COMPATIBLE_PROMPT_VERSION,
        schema_version=OPENAI_COMPATIBLE_SCHEMA_VERSION,
    )


def test_endpoint_and_model_switching_requires_no_business_layer_change():
    """/"DeepSeek" vs "Qwen" only changes AIProviderConfig; the provider class,
    the extraction entrypoint and the resulting bundle shape stay identical."""
    captured: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append({"url": str(request.url), "body": json.loads(request.content)})
        return completion(bundle_payload(candidates=VALID_CANDIDATES, collections=VALID_COLLECTIONS))

    def run_extraction(config: AIProviderConfig) -> str:
        bundle = make_provider(handler, config=config).extract("同一份简历文本")
        assert bundle.fields and bundle.collections
        return bundle.metadata.model

    deepseek = make_config(base_url="https://api.deepseek.example/v1", text_model="deepseek-chat")
    qwen = make_config(base_url="https://dashscope.example/compatible-mode", text_model="qwen-plus")

    assert run_extraction(deepseek) == "deepseek-chat"
    assert run_extraction(qwen) == "qwen-plus"

    assert [entry["url"] for entry in captured] == [
        "https://api.deepseek.example/v1/chat/completions",
        "https://dashscope.example/compatible-mode/v1/chat/completions",
    ]
    assert [entry["body"]["model"] for entry in captured] == ["deepseek-chat", "qwen-plus"]


def test_plain_json_without_json_schema_capability_and_legacy_scalar_only_shape():
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return completion(bundle_payload(candidates=VALID_CANDIDATES))

    bundle = make_provider(handler, config=make_config(supports_json_schema=False)).extract("resume")

    assert isinstance(captured["body"], dict)
    assert "response_format" not in captured["body"]
    assert bundle.collections == []
    assert {candidate.field_key for candidate in bundle.fields} == {"contact.email", "education.school"}


def test_markdown_fenced_json_content_is_accepted():
    def handler(request: httpx.Request) -> httpx.Response:
        return completion(
            "```json\n"
            '{"candidates":[{"field_key":"job.target_roles","value":["平面设计"],"confidence":0.9}]}'
            "\n```"
        )

    bundle = make_provider(handler).extract("目标岗位：平面设计")
    assert bundle.fields[0].field_key == "job.target_roles"
    assert bundle.fields[0].value == ["平面设计"]


def test_invalid_candidates_are_dropped_while_valid_ones_survive():
    def handler(request: httpx.Request) -> httpx.Response:
        return completion(bundle_payload(
            candidates=[
                {"field_key": "contact.email", "value": "name@example.com", "confidence": 0.9},
                {"field_key": 123, "value": "x", "confidence": 0.9},
                {"field_key": "contact.fax", "value": "000", "confidence": 0.9},
                {"field_key": "education.school", "value": {"x": 1}, "confidence": 0.9},
                {"field_key": "contact.phone", "value": "13800138000", "confidence": "high"},
                {"field_key": "education.major", "value": 42, "confidence": 0.9},
                {"field_key": "job.target_roles", "value": "not-a-list", "confidence": 0.9},
                {"field_key": "identity.name", "value": ["not", "a", "string"], "confidence": 0.9},
            ],
            collections=[
                {"kind": "education", "payload": {"school": "三江学院", "major": "视觉传达设计"}, "confidence": 0.96},
                {"kind": "mystery", "payload": {"x": "y"}, "confidence": 0.9},
                {"kind": "project", "payload": {"description": "missing required name"}, "confidence": 0.9},
                {"kind": "award", "payload": {"unknown_field": True}, "confidence": 0.9},
                {"kind": "skill", "payload": {"name": "Python"}, "confidence": "sure"},
                {"kind": "certificate", "payload": [1, 2, 3], "confidence": 0.9},
            ],
        ))

    bundle = make_provider(handler).extract("resume")

    assert [(candidate.field_key, candidate.value) for candidate in bundle.fields] == [
        ("contact.email", "name@example.com")
    ]
    assert [(candidate.kind, candidate.payload) for candidate in bundle.collections] == [
        ("education", {"school": "三江学院", "major": "视觉传达设计"})
    ]


@pytest.mark.parametrize(
    "response_json",
    [
        {},
        {"choices": []},
        {"choices": [{"message": {}}]},
        {"choices": [{"message": {"content": "not json"}}]},
        {"choices": [{"message": {"content": '{"wrong": []}'}}]},
        {"choices": [{"message": {"content": '{"candidates": {"nested": true}}'}}]},
        {"choices": [{"message": {"content": '{"candidates": [], "collections": "nope"}'}}]},
        {"choices": [{"message": {"content": ""}}]},
        {"choices": [{"message": {"content": "   "}}]},
    ],
)
def test_malformed_provider_responses_are_rejected(response_json):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=response_json)

    with pytest.raises(ProviderResponseError):
        make_provider(handler).extract("resume")


def test_output_length_is_bounded():
    def handler(request: httpx.Request) -> httpx.Response:
        return completion("x" * (MAX_OUTPUT_CHARS + 1))

    with pytest.raises(ProviderResponseError):
        make_provider(handler).extract("resume")


def test_input_length_is_bounded_before_any_network_call():
    called = {"http": False}

    def handler(request: httpx.Request) -> httpx.Response:
        called["http"] = True
        return completion(bundle_payload())

    with pytest.raises(ProviderInputError):
        make_provider(handler).extract("x" * (MAX_INPUT_CHARS + 1))
    assert called["http"] is False


@pytest.mark.parametrize("status_code", [401, 500])
def test_upstream_http_errors_are_safe_and_do_not_echo_api_key(status_code):
    secret = "sk-never-echo-this"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"error": {"message": "provider rejected request"}})

    with pytest.raises(ProviderRequestError) as error:
        make_provider(handler).extract("private resume text")

    assert f"HTTP {status_code}" in str(error.value)
    assert secret not in str(error.value)
    assert "private resume text" not in str(error.value)


def test_network_connection_error_maps_to_provider_request_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(ProviderRequestError):
        make_provider(handler).extract("resume")


def test_provider_timeout_maps_to_safe_domain_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("simulated timeout", request=request)

    with pytest.raises(ProviderTimeoutError) as error:
        make_provider(handler).extract("private resume text")


def test_blank_api_key_is_rejected_upfront():
    with pytest.raises(ValueError):
        OpenAICompatibleExtractionProvider(make_config(), "   ")


def test_sensitive_profile_fields_are_not_sent_to_ai_extraction_schema_or_prompt():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"candidates":[],"collections":[]}'}}]},
        )

    make_provider(handler).extract("resume")
    body = captured["body"]
    system_prompt = body["messages"][0]["content"]
    scalar_schema = body["response_format"]["json_schema"]["schema"]["properties"]["candidates"]["items"]
    allowed = scalar_schema["properties"]["field_key"]["enum"]

    assert "identity.id_number" not in system_prompt
    assert "identity.id_number" not in allowed
