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


class SemanticMappingProvider(Protocol):
    def suggest(
        self,
        *,
        fields: list[FormFieldDescriptor],
        candidates: dict[str, Any],
    ) -> list[dict[str, Any]]: ...


def flatten_confirmed_snapshot(snapshot: ConfirmedProfileSnapshot) -> dict[str, Any]:
    candidates: dict[str, Any] = {}
    for path in sorted(snapshot.scalars):
        try:
            definition = get_field_definition(path)
        except KeyError:
            continue
        if definition.sensitive:
            continue
        value = snapshot.scalars[path]
        if isinstance(value, str) and value.strip():
            candidates[path] = value
        elif isinstance(value, list) and value and all(isinstance(item, str) for item in value):
            candidates[path] = value

    for kind in sorted(snapshot.collections):
        for index, payload in enumerate(snapshot.collections[kind]):
            for field in sorted(payload):
                value = payload[field]
                if isinstance(value, str) and value.strip():
                    candidates[f"collections.{kind}[{index}].{field}"] = value
                elif isinstance(value, list) and value and all(isinstance(item, str) for item in value):
                    candidates[f"collections.{kind}[{index}].{field}"] = value
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
                        "selected_option",
                    ],
                    "properties": {
                        "field_id": {"type": "string", "enum": field_ids},
                        "source_path": {"type": "string", "enum": source_paths},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "reason": {"type": "string"},
                        "selected_option": {
                            "oneOf": [
                                {"type": "string"},
                                {"type": "null"},
                            ]
                        },
                    },
                },
            }
        },
    }


class OpenAICompatibleSemanticMappingProvider:
    """AI may select only a field id + confirmed source path.

    It never supplies the user's underlying value. The server resolves the
    selected source path back against the confirmed snapshot after the model
    answers, so invented personal data cannot cross this boundary.
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
        candidates: dict[str, Any],
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
                    "You map Chinese recruitment form controls to an existing confirmed profile. "
                    "Never invent personal information. Choose field_id only from the supplied fields "
                    "and source_path only from the supplied confirmed candidates. If uncertain, omit "
                    "the field. For select/radio-like controls, selected_option must exactly equal one "
                    "of that field's supplied options; otherwise omit it. Return JSON only."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "fields": field_payload,
                        "confirmed_candidates": candidates,
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
        if not isinstance(source_path, str) or source_path not in candidates:
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
        source_value = candidates[source_path]
        control_type = (descriptor.input_type or descriptor.tag or "text").lower()
        selected_option = suggestion.get("selected_option")

        if descriptor.options or control_type == "select":
            if not isinstance(selected_option, str) or selected_option not in descriptor.options:
                continue
            value: Any = selected_option
        else:
            value = source_value

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
