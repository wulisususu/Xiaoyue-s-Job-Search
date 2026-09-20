from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ConfirmedProfileSnapshot:
    scalars: dict[str, Any]
    collections: dict[str, list[dict[str, Any]]]


@dataclass(slots=True)
class FormFieldDescriptor:
    field_id: str
    tag: str
    input_type: str
    label: str
    name: str
    placeholder: str
    aria_label: str
    section: str
    required: bool
    options: list[str]
    disabled: bool = False
    readonly: bool = False
    dom_id: str = ""
    adapter_source_path: str = ""


@dataclass(slots=True)
class FormScan:
    url: str
    title: str
    fields: list[FormFieldDescriptor]
    target_id: str = ""


@dataclass(slots=True)
class FillPlanItem:
    field_id: str
    label: str
    control_type: str
    value: Any
    source_path: str
    confidence: float
    reason: str
    requires_confirmation: bool


@dataclass(slots=True)
class PlanFieldSummary:
    field_id: str
    label: str
    control_type: str


@dataclass(slots=True)
class FillPlan:
    token: str
    session_id: str
    page_url: str
    page_revision: str = ""
    adapter_id: str = "generic"
    adapter_display_name: str = "通用招聘表单"
    adapter_implementation: str = "generic_dom"
    adapter_capabilities: list[str] = field(default_factory=list)
    adapter_limitations: list[str] = field(default_factory=list)
    items: list[FillPlanItem] = field(default_factory=list)
    unmatched: list[PlanFieldSummary] = field(default_factory=list)
    blocked: list[PlanFieldSummary] = field(default_factory=list)


@dataclass(slots=True)
class BrowserAgentSessionInfo:
    id: str
    application_id: int
    url: str
    status: str
    browser: str
    mode: str = "fill"
