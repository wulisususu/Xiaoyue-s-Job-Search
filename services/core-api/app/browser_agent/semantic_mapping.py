from __future__ import annotations

import json
import math
import uuid
from typing import Any, Protocol

from ..ai.json_client import OpenAICompatibleJSONClient
from ..models import AIProviderConfig
from ..profile.registry import get_field_definition
from .models import (
    ConfirmedProfileSnapshot,
    FillPlan,
    FillPlanItem,
    FormFieldDescriptor,
    FormScan,
)
from .value_normalization import normalize_value_for_control


class SemanticMappingProvider(Protocol):
    def suggest(
        self,
        *,
        fields: list[FormFieldDescriptor],
        candidates: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]: ...


def _confirmed_value_map(snapshot: ConfirmedProfileSnapshot) -> dict[str, Any]:
    """Resolve confirmed SSOT values locally.

    This value map must never be serialized into an AI-provider request. It is
    used only after the provider has selected an allowed source_path.
    """
    values: dict[str, Any] = {}
    for path in sorted(snapshot.scalars):
        try:
            get_field_definition(path)
        except KeyError:
            continue
        value = snapshot.scalars[path]
        if isinstance(value, str) and value.strip():
            values[path] = value
        elif isinstance(value, list) and value and all(isinstance(item, str) for item in value):
            values[path] = value

    for kind in sorted(snapshot.collections):
        for index, payload in enumerate(snapshot.collections[kind]):
            for field in sorted(payload):
                value = payload[field]
                if isinstance(value, str) and value.strip():
                    values[f"collections.{kind}[{index}].{field}"] = value
                elif isinstance(value, list) and value and all(isinstance(item, str) for item in value):
                    values[f"collections.{kind}[{index}].{field}"] = value
    return values


def flatten_confirmed_snapshot(snapshot: ConfirmedProfileSnapshot) -> dict[str, dict[str, Any]]:
    """Return schema-only candidate metadata safe to send to an AI provider.

    The provider can see which confirmed profile paths exist and what each path
    means, but it never receives the underlying personal value. Sensitive paths
    are allowed as schema candidates because the value remains local and every
    AI-added mapping still requires explicit user confirmation before fill.
    """
    values = _confirmed_value_map(snapshot)
    candidates: dict[str, dict[str, Any]] = {}

    for path in sorted(snapshot.scalars):
        if path not in values:
            continue
        try:
            definition = get_field_definition(path)
        except KeyError:
            continue
        candidates[path] = {
            "path": path,
            "label": definition.label,
            "category": definition.category,
            "value_type": definition.value_type,
            "multiple": definition.multiple,
            "sensitive": definition.sensitive,
        }

    for kind in sorted(snapshot.collections):
        for index, payload in enumerate(snapshot.collections[kind]):
            for field in sorted(payload):
                path = f"collections.{kind}[{index}].{field}"
                if path not in values:
                    continue
                value = values[path]
                candidates[path] = {
                    "path": path,
                    "label": f"{kind}.{field}",
                    "category": f"collection:{kind}",
                    "value_type": "string_list" if isinstance(value, list) else "string",
                    "multiple": isinstance(value, list),
                    "sensitive": False,
                    "collection_index": index,
                }
    return candidates


def _mapping_schema(field_ids: list[str], source_paths: list[str]) -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["matches"],
        "properties": {
            "matches": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "field_id",
                        "source_path",
                        "confidence",
                        "reason",
                    ],
                    "properties": {
                        "field_id": {"type": "string", "enum": field_ids},
                        "source_path": {"type": "string", "enum": source_paths},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "reason": {"type": "string"},
                    },
                },
            }
        },
    }


class OpenAICompatibleSemanticMappingProvider:
    """Map form semantics to confirmed profile schema paths only.

    AI never receives or supplies the user's underlying value. The server
    resolves source_path against the confirmed snapshot and normalizes the
    value for the target control locally after the model answers.
    """

    def __init__(
        self,
        config: AIProviderConfig,
        api_key: str,
        *,
        client: OpenAICompatibleJSONClient | None = None,
    ) -> None:
        self._client = client or OpenAICompatibleJSONClient(config, api_key)

    def suggest(
        self,
        *,
        fields: list[FormFieldDescriptor],
        candidates: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not fields or not candidates:
            return []

        field_payload = [
            {
                "field_id": field.field_id,
                "label": field.label,
                "name": field.name,
                "placeholder": field.placeholder,
                "aria_label": field.aria_label,
                "section": field.section,
                "control_type": field.input_type or field.tag,
                "options": field.options,
            }
            for field in fields
        ]
        messages = [
            {
                "role": "system",
                "content": (
                    "You map Chinese recruitment form controls to existing confirmed profile schema paths. "
                    "You are given schema metadata only, never personal values. Choose field_id only from "
                    "the supplied fields and source_path only from the supplied profile_schema_candidates. "
                    "Do not infer or output any personal value and do not choose a final select/radio value. "
                    "If the semantic mapping is uncertain, omit the field. Return JSON only."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "fields": field_payload,
                        "profile_schema_candidates": candidates,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            },
        ]
        payload = self._client.complete_json(
            messages=messages,
            schema_name="browser_field_mapping",
            schema=_mapping_schema(
                [field.field_id for field in fields],
                list(candidates),
            ),
            max_output_chars=50_000,
        )
        matches = payload.get("matches")
        if not isinstance(matches, list):
            return []
        return [item for item in matches if isinstance(item, dict)]


def apply_semantic_suggestions(
    snapshot: ConfirmedProfileSnapshot,
    scan: FormScan,
    plan: FillPlan,
    provider: SemanticMappingProvider,
) -> FillPlan:
    values = _confirmed_value_map(snapshot)
    candidates = flatten_confirmed_snapshot(snapshot)
    unmatched_ids = {item.field_id for item in plan.unmatched}
    field_by_id = {
        field.field_id: field
        for field in scan.fields
        if field.field_id in unmatched_ids
    }
    fields = [field_by_id[item.field_id] for item in plan.unmatched if item.field_id in field_by_id]
    suggestions = provider.suggest(fields=fields, candidates=candidates)

    best_by_field: dict[str, dict[str, Any]] = {}
    for suggestion in suggestions:
        field_id = suggestion.get("field_id")
        source_path = suggestion.get("source_path")
        confidence = suggestion.get("confidence")
        if not isinstance(field_id, str) or field_id not in field_by_id:
            continue
        if not isinstance(source_path, str) or source_path not in candidates or source_path not in values:
            continue
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            continue
        score = float(confidence)
        if not math.isfinite(score) or not 0 <= score <= 1:
            continue
        reason = suggestion.get("reason")
        if not isinstance(reason, str):
            continue
        normalized = dict(suggestion)
        normalized["confidence"] = score
        current = best_by_field.get(field_id)
        if current is None or score > float(current["confidence"]):
            best_by_field[field_id] = normalized

    additions: list[FillPlanItem] = []
    accepted_ids: set[str] = set()
    for item in plan.unmatched:
        suggestion = best_by_field.get(item.field_id)
        if suggestion is None:
            continue
        descriptor = field_by_id.get(item.field_id)
        if descriptor is None:
            continue
        source_path = str(suggestion["source_path"])
        source_value = values[source_path]
        control_type = (descriptor.input_type or descriptor.tag or "text").lower()
        value = normalize_value_for_control(source_path, source_value, descriptor)
        if value is None:
            continue

        additions.append(
            FillPlanItem(
                field_id=descriptor.field_id,
                label=descriptor.label
                or descriptor.aria_label
                or descriptor.placeholder
                or descriptor.name
                or descriptor.field_id,
                control_type=control_type,
                value=value,
                source_path=source_path,
                confidence=float(suggestion["confidence"]),
                reason=str(suggestion["reason"]),
                requires_confirmation=True,
            )
        )
        accepted_ids.add(descriptor.field_id)

    return FillPlan(
        token=uuid.uuid4().hex,
        session_id=plan.session_id,
        page_url=plan.page_url,
        items=[*plan.items, *additions],
        unmatched=[item for item in plan.unmatched if item.field_id not in accepted_ids],
        blocked=list(plan.blocked),
    )
