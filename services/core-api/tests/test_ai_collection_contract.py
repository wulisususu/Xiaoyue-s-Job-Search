from __future__ import annotations

import json

import httpx

from app.ai.openai_compatible import OpenAICompatibleClient
from app.models import AIProviderConfig


def make_config() -> AIProviderConfig:
    return AIProviderConfig(
        id="default",
        provider_name="Test Provider",
        base_url="https://example.com/v1",
        text_model="reasoning-model",
        vision_model=None,
        temperature=0.0,
        timeout_seconds=30,
        supports_json_schema=True,
        supports_vision=False,
    )


def test_ai_extraction_bundle_preserves_scalar_candidates_and_adds_structured_collections():
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "candidates": [
                                        {
                                            "field_key": "contact.email",
                                            "value": "name@example.com",
                                            "confidence": 0.99,
                                        }
                                    ],
                                    "collections": [
                                        {
                                            "kind": "education",
                                            "payload": {
                                                "school": "三江学院",
                                                "major": "视觉传达设计",
                                            },
                                            "confidence": 0.96,
                                        },
                                        {
                                            "kind": "skill",
                                            "payload": {"name": "Python", "level": "熟练"},
                                            "confidence": 0.88,
                                        },
                                    ],
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            },
        )

    client = OpenAICompatibleClient(transport=httpx.MockTransport(handler))
    bundle = client.extract_profile_candidates(make_config(), "sk-test", "resume text")

    assert bundle.fields[0].field_key == "contact.email"
    assert bundle.fields[0].value == "name@example.com"
    assert bundle.collections[0].kind == "education"
    assert bundle.collections[0].payload == {"school": "三江学院", "major": "视觉传达设计"}
    assert bundle.collections[1].kind == "skill"

    body = captured["body"]
    assert isinstance(body, dict)
    prompt = json.dumps(body["messages"], ensure_ascii=False)
    assert "education" in prompt
    assert "school" in prompt
    assert "skill" in prompt
    schema = body["response_format"]["json_schema"]["schema"]
    assert set(schema["properties"]) == {"candidates", "collections"}


def test_legacy_scalar_extraction_api_remains_compatible_when_collections_are_returned():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "candidates": [
                                        {
                                            "field_key": "contact.email",
                                            "value": "name@example.com",
                                            "confidence": 0.99,
                                        }
                                    ],
                                    "collections": [
                                        {
                                            "kind": "education",
                                            "payload": {"school": "三江学院"},
                                            "confidence": 0.96,
                                        }
                                    ],
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            },
        )

    result = OpenAICompatibleClient(transport=httpx.MockTransport(handler)).extract_candidates(
        make_config(), "sk-test", "resume text"
    )
    assert len(result) == 1
    assert result[0].field_key == "contact.email"
