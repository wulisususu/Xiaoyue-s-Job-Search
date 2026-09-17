from __future__ import annotations

import json
import math
from dataclasses import dataclass

import httpx

from ..models import AIProviderConfig
from ..profile.collections import COLLECTION_REGISTRY, CollectionDefinition, validate_collection_payload
from ..profile.registry import FIELD_REGISTRY, FieldDefinition
from .provider import chat_completions_url


@dataclass(frozen=True, slots=True)
class RawAICandidate:
    field_key: str
    value: object
    confidence: float


@dataclass(frozen=True, slots=True)
class RawAICollectionCandidate:
    kind: str
    payload: dict[str, object]
    confidence: float


@dataclass(frozen=True, slots=True)
class RawAIExtractionBundle:
    fields: list[RawAICandidate]
    collections: list[RawAICollectionCandidate]


class ProviderRequestError(RuntimeError):
    pass


class ProviderTimeoutError(RuntimeError):
    pass


class ProviderResponseError(RuntimeError):
    pass


def _registry_prompt(
    registry: dict[str, FieldDefinition],
    collection_registry: dict[str, CollectionDefinition] = COLLECTION_REGISTRY,
) -> str:
    lines = [
        "Extract only facts explicitly supported by the resume text.",
        "Do not infer or invent missing information.",
        "Return scalar facts under candidates and repeatable records under collections.",
        "Return only field keys and collection kinds/fields from the allowed registries below.",
        "Allowed scalar fields:",
    ]
    for key, definition in registry.items():
        multiplicity = "multiple" if definition.multiple else "single"
        lines.append(
            f"- {key}: label={definition.label}; type={definition.value_type}; multiplicity={multiplicity}"
        )

    lines.append("Allowed repeatable collections:")
    for kind, definition in collection_registry.items():
        field_parts = []
        for field in definition.fields:
            multiplicity = "multiple" if field.multiple else "single"
            required = "required" if field.required else "optional"
            field_parts.append(
                f"{field.key}({field.label};{field.value_type};{multiplicity};{required})"
            )
        lines.append(f"- {kind}: label={definition.label}; fields={'; '.join(field_parts)}")

    lines.append(
        'Return JSON with exactly this top-level shape: '
        '{"candidates":[{"field_key":"...","value":"...","confidence":0.0}],'
        '"collections":[{"kind":"education","payload":{"school":"..."},"confidence":0.0}]}.'
    )
    return "\n".join(lines)


def _scalar_candidate_schema() -> dict[str, object]:
    return {
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
    }


def _collection_payload_schema(definition: CollectionDefinition) -> dict[str, object]:
    properties: dict[str, object] = {}
    required: list[str] = []
    for field in definition.fields:
        if field.multiple:
            properties[field.key] = {"type": "array", "items": {"type": "string"}}
        else:
            properties[field.key] = {"type": "string"}
        if field.required:
            required.append(field.key)
    return {
        "type": "object",
        "additionalProperties": False,
        "required": required,
        "properties": properties,
    }


def _collection_candidate_schema() -> dict[str, object]:
    variants: list[dict[str, object]] = []
    for kind, definition in COLLECTION_REGISTRY.items():
        variants.append(
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["kind", "payload", "confidence"],
                "properties": {
                    "kind": {"const": kind},
                    "payload": _collection_payload_schema(definition),
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            }
        )
    return {"oneOf": variants}


def _response_schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["candidates", "collections"],
        "properties": {
            "candidates": {
                "type": "array",
                "items": _scalar_candidate_schema(),
            },
            "collections": {
                "type": "array",
                "items": _collection_candidate_schema(),
            },
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


def _parse_confidence(value: object, *, candidate_type: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProviderResponseError(f"AI provider {candidate_type} confidence must be numeric")
    confidence = float(value)
    if not math.isfinite(confidence) or confidence < 0 or confidence > 1:
        raise ProviderResponseError(f"AI provider {candidate_type} confidence must be between 0 and 1")
    return confidence


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

        parsed.append(
            RawAICandidate(
                field_key=field_key,
                value=value,
                confidence=_parse_confidence(confidence, candidate_type="candidate"),
            )
        )
    return parsed


def _parse_collection_candidates(payload: object) -> list[RawAICollectionCandidate]:
    if not isinstance(payload, dict):
        raise ProviderResponseError("AI provider returned an invalid candidate payload")
    # Tolerate providers that still return the legacy scalar-only shape when
    # JSON-schema enforcement is unavailable. New schema-aware requests always
    # require this property.
    collections = payload.get("collections", [])
    if not isinstance(collections, list):
        raise ProviderResponseError("AI provider returned an invalid collection candidate list")

    parsed: list[RawAICollectionCandidate] = []
    for candidate in collections:
        if not isinstance(candidate, dict):
            raise ProviderResponseError("AI provider returned an invalid collection candidate")
        kind = candidate.get("kind")
        raw_payload = candidate.get("payload")
        confidence = candidate.get("confidence")
        if not isinstance(kind, str):
            raise ProviderResponseError("AI provider collection candidate kind must be a string")
        if not isinstance(raw_payload, dict):
            raise ProviderResponseError("AI provider collection candidate payload must be an object")
        try:
            normalized_payload = validate_collection_payload(kind, raw_payload)
        except (KeyError, ValueError) as exc:
            raise ProviderResponseError(f"AI provider collection candidate is invalid: {exc}") from exc
        parsed.append(
            RawAICollectionCandidate(
                kind=kind,
                payload=normalized_payload,
                confidence=_parse_confidence(confidence, candidate_type="collection candidate"),
            )
        )
    return parsed


def _parse_extraction_bundle(payload: object) -> RawAIExtractionBundle:
    return RawAIExtractionBundle(
        fields=_parse_candidates(payload),
        collections=_parse_collection_candidates(payload),
    )


class OpenAICompatibleClient:
    def __init__(self, *, transport: httpx.BaseTransport | None = None):
        self._transport = transport

    def extract_profile_candidates(
        self,
        config: AIProviderConfig,
        api_key: str,
        resume_text: str,
        registry: dict[str, FieldDefinition] = FIELD_REGISTRY,
        collection_registry: dict[str, CollectionDefinition] = COLLECTION_REGISTRY,
    ) -> RawAIExtractionBundle:
        messages = [
            {"role": "system", "content": _registry_prompt(registry, collection_registry)},
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
        return _parse_extraction_bundle(candidate_payload)

    def extract_candidates(
        self,
        config: AIProviderConfig,
        api_key: str,
        resume_text: str,
        registry: dict[str, FieldDefinition] = FIELD_REGISTRY,
    ) -> list[RawAICandidate]:
        """Backward-compatible scalar view of the richer extraction bundle."""
        return self.extract_profile_candidates(
            config,
            api_key,
            resume_text,
            registry=registry,
        ).fields
