"""OpenAI-compatible implementation of the unified extraction contract.

Any endpoint that speaks the ``/chat/completions`` dialect (OpenAI, DeepSeek,
Qwen, ...) works here by changing ``AIProviderConfig`` only; nothing in the
business layer changes when the endpoint or model is swapped.
"""
from __future__ import annotations

import json
import math

import httpx

from ..models import AIProviderConfig
from ..profile.collections import (
    COLLECTION_REGISTRY,
    CollectionDefinition,
    validate_collection_payload,
)
from ..profile.extraction import (
    CollectionDraftCandidate,
    DraftCandidate,
    ExtractionMetadata,
    ProfileExtractionBundle,
)
from ..profile.registry import FIELD_REGISTRY, FieldDefinition, extractable_field_registry
from .errors import (
    ProviderError,
    ProviderInputError,
    ProviderRequestError,
    ProviderResponseError,
    ProviderTimeoutError,
)
from .json_client import OpenAICompatibleJSONClient

__all__ = [
    "MAX_INPUT_CHARS",
    "MAX_OUTPUT_CHARS",
    "OPENAI_COMPATIBLE_PROMPT_VERSION",
    "OPENAI_COMPATIBLE_PROVIDER_ID",
    "OPENAI_COMPATIBLE_SCHEMA_VERSION",
    "OpenAICompatibleExtractionProvider",
    "ProviderError",
    "ProviderInputError",
    "ProviderRequestError",
    "ProviderResponseError",
    "ProviderTimeoutError",
]

OPENAI_COMPATIBLE_PROVIDER_ID = "openai_compatible"
OPENAI_COMPATIBLE_PROMPT_VERSION = "registry-prompt-v2"
OPENAI_COMPATIBLE_SCHEMA_VERSION = "bundle-v1"

MAX_INPUT_CHARS = 200_000
MAX_OUTPUT_CHARS = 200_000


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


def _scalar_candidate_schema(
    registry: dict[str, FieldDefinition] = FIELD_REGISTRY,
) -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["field_key", "value", "confidence"],
        "properties": {
            "field_key": {"type": "string", "enum": list(registry)},
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


def _response_schema(
    registry: dict[str, FieldDefinition] = FIELD_REGISTRY,
) -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["candidates", "collections"],
        "properties": {
            "candidates": {
                "type": "array",
                "items": _scalar_candidate_schema(registry),
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


def _valid_confidence(value: object) -> float | None:
    """Per-item policy: invalid confidence drops the candidate, never the bundle."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    confidence = float(value)
    if not math.isfinite(confidence) or confidence < 0 or confidence > 1:
        return None
    return confidence


def _shape_matches_definition(value: object, definition: FieldDefinition) -> bool:
    if definition.multiple:
        return isinstance(value, list) and all(isinstance(item, str) for item in value)
    return isinstance(value, str)


def _parse_candidates(
    payload: object,
    registry: dict[str, FieldDefinition],
) -> list[DraftCandidate]:
    if not isinstance(payload, dict) or "candidates" not in payload:
        raise ProviderResponseError("AI provider returned an invalid candidate payload")
    candidates = payload["candidates"]
    if not isinstance(candidates, list):
        raise ProviderResponseError("AI provider returned an invalid candidate list")

    parsed: list[DraftCandidate] = []
    for candidate in candidates:
        # Partial-validity policy: structurally invalid or unknown scalar
        # candidates are dropped one by one; the valid remainder survives.
        if not isinstance(candidate, dict):
            continue
        field_key = candidate.get("field_key")
        value = candidate.get("value")
        confidence = _valid_confidence(candidate.get("confidence"))
        definition = registry.get(field_key) if isinstance(field_key, str) else None
        if definition is None or confidence is None:
            continue
        if not _shape_matches_definition(value, definition):
            continue
        parsed.append(
            DraftCandidate(
                field_key=field_key,
                value=value,
                value_type=definition.value_type,
                confidence=confidence,
                extractor_name=OPENAI_COMPATIBLE_PROVIDER_ID,
            )
        )
    return parsed


def _parse_collection_candidates(payload: object) -> list[CollectionDraftCandidate]:
    if not isinstance(payload, dict):
        raise ProviderResponseError("AI provider returned an invalid candidate payload")
    # Tolerate providers that still return the legacy scalar-only shape when
    # JSON-schema enforcement is unavailable. New schema-aware requests always
    # require this property.
    collections = payload.get("collections", [])
    if not isinstance(collections, list):
        raise ProviderResponseError("AI provider returned an invalid collection candidate list")

    parsed: list[CollectionDraftCandidate] = []
    for candidate in collections:
        # Partial-validity policy: invalid kind/payload/confidence rejects
        # only that item; valid items survive the response.
        if not isinstance(candidate, dict):
            continue
        kind = candidate.get("kind")
        raw_payload = candidate.get("payload")
        confidence = _valid_confidence(candidate.get("confidence"))
        if not isinstance(kind, str) or not isinstance(raw_payload, dict) or confidence is None:
            continue
        try:
            normalized_payload = validate_collection_payload(kind, raw_payload)
        except (KeyError, ValueError):
            continue
        parsed.append(
            CollectionDraftCandidate(
                kind=kind,
                payload=normalized_payload,
                confidence=confidence,
                extractor_name=OPENAI_COMPATIBLE_PROVIDER_ID,
            )
        )
    return parsed


class OpenAICompatibleExtractionProvider:
    """Unified-contract provider backed by an OpenAI-compatible endpoint."""

    def __init__(
        self,
        config: AIProviderConfig,
        api_key: str,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if api_key is None or not api_key.strip():
            raise ValueError("AI provider API key is required")
        self._config = config
        self._api_key = api_key
        self._transport = transport

    def metadata(self) -> ExtractionMetadata:
        return ExtractionMetadata(
            provider=OPENAI_COMPATIBLE_PROVIDER_ID,
            model=self._config.text_model,
            prompt_version=OPENAI_COMPATIBLE_PROMPT_VERSION,
            schema_version=OPENAI_COMPATIBLE_SCHEMA_VERSION,
        )

    def extract(
        self,
        text: str,
        registry: dict[str, FieldDefinition] = FIELD_REGISTRY,
        collection_registry: dict[str, CollectionDefinition] = COLLECTION_REGISTRY,
    ) -> ProfileExtractionBundle:
        resume_text = text or ""
        if len(resume_text) > MAX_INPUT_CHARS:
            raise ProviderInputError(
                f"resume text exceeds the {MAX_INPUT_CHARS}-character provider input limit"
            )

        safe_registry = extractable_field_registry(registry)
        messages = [
            {"role": "system", "content": _registry_prompt(safe_registry, collection_registry)},
            {"role": "user", "content": resume_text},
        ]
        client = OpenAICompatibleJSONClient(
            self._config,
            self._api_key,
            transport=self._transport,
        )
        candidate_payload = client.complete_json(
            messages=messages,
            schema_name="profile_candidates",
            schema=_response_schema(safe_registry),
            max_output_chars=MAX_OUTPUT_CHARS,
        )

        return ProfileExtractionBundle(
            fields=_parse_candidates(candidate_payload, safe_registry),
            collections=_parse_collection_candidates(candidate_payload),
            metadata=self.metadata(),
        )
