from __future__ import annotations

import json
import math
from dataclasses import dataclass

import httpx

from ..models import AIProviderConfig
from ..profile.registry import FIELD_REGISTRY, FieldDefinition
from .provider import chat_completions_url


@dataclass(frozen=True, slots=True)
class RawAICandidate:
    field_key: str
    value: object
    confidence: float


class ProviderRequestError(RuntimeError):
    pass


class ProviderTimeoutError(RuntimeError):
    pass


class ProviderResponseError(RuntimeError):
    pass


def _registry_prompt(registry: dict[str, FieldDefinition]) -> str:
    lines = [
        "Extract only facts explicitly supported by the resume text.",
        "Do not infer or invent missing information.",
        "Return only field keys from the allowed registry below.",
        "Allowed fields:",
    ]
    for key, definition in registry.items():
        multiplicity = "multiple" if definition.multiple else "single"
        lines.append(
            f"- {key}: label={definition.label}; type={definition.value_type}; multiplicity={multiplicity}"
        )
    lines.append(
        'Return JSON with exactly this top-level shape: {"candidates":[{"field_key":"...","value":"...","confidence":0.0}]}.'
    )
    return "\n".join(lines)


def _response_schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["candidates"],
        "properties": {
            "candidates": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["field_key", "value", "confidence"],
                    "properties": {
                        "field_key": {"type": "string"},
                        "value": {
                            "oneOf": [
                                {"type": "string"},
                                {"type": "array", "items": {"type": "string"}},
                            ]
                        },
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                },
            }
        },
    }


def _strip_json_fence(content: str) -> str:
    stripped = content.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    if not lines:
        return stripped
    first = lines[0].strip().lower()
    if first not in {"```", "```json"}:
        return stripped
    lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _parse_candidates(payload: object) -> list[RawAICandidate]:
    if not isinstance(payload, dict) or "candidates" not in payload:
        raise ProviderResponseError("AI provider returned an invalid candidate payload")
    candidates = payload["candidates"]
    if not isinstance(candidates, list):
        raise ProviderResponseError("AI provider returned an invalid candidate list")

    parsed: list[RawAICandidate] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ProviderResponseError("AI provider returned an invalid candidate")
        field_key = candidate.get("field_key")
        value = candidate.get("value")
        confidence = candidate.get("confidence")

        if not isinstance(field_key, str):
            raise ProviderResponseError("AI provider candidate field_key must be a string")
        if not (
            isinstance(value, str)
            or (isinstance(value, list) and all(isinstance(item, str) for item in value))
        ):
            raise ProviderResponseError("AI provider candidate value must be a string or list of strings")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise ProviderResponseError("AI provider candidate confidence must be numeric")
        confidence_value = float(confidence)
        if not math.isfinite(confidence_value):
            raise ProviderResponseError("AI provider candidate confidence must be finite")

        parsed.append(
            RawAICandidate(
                field_key=field_key,
                value=value,
                confidence=confidence_value,
            )
        )
    return parsed


class OpenAICompatibleClient:
    def __init__(self, *, transport: httpx.BaseTransport | None = None):
        self._transport = transport

    def extract_candidates(
        self,
        config: AIProviderConfig,
        api_key: str,
        resume_text: str,
        registry: dict[str, FieldDefinition] = FIELD_REGISTRY,
    ) -> list[RawAICandidate]:
        messages = [
            {"role": "system", "content": _registry_prompt(registry)},
            {"role": "user", "content": resume_text},
        ]
        body: dict[str, object] = {
            "model": config.text_model,
            "temperature": config.temperature,
            "messages": messages,
        }
        if config.supports_json_schema:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "profile_candidates",
                    "strict": True,
                    "schema": _response_schema(),
                },
            }

        try:
            with httpx.Client(
                transport=self._transport,
                timeout=float(config.timeout_seconds),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            ) as client:
                response = client.post(chat_completions_url(config.base_url), json=body)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("AI provider request timed out") from exc
        except httpx.RequestError as exc:
            raise ProviderRequestError("AI provider request failed") from exc

        if response.status_code >= 400:
            raise ProviderRequestError(f"AI provider returned HTTP {response.status_code}")

        try:
            response_payload = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise ProviderResponseError("AI provider returned invalid JSON") from exc

        if not isinstance(response_payload, dict):
            raise ProviderResponseError("AI provider returned an invalid response")
        choices = response_payload.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ProviderResponseError("AI provider response has no completion choice")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise ProviderResponseError("AI provider response has no completion message")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ProviderResponseError("AI provider response has no completion content")

        try:
            candidate_payload = json.loads(_strip_json_fence(content))
        except json.JSONDecodeError as exc:
            raise ProviderResponseError("AI provider completion content is not valid JSON") from exc
        return _parse_candidates(candidate_payload)
