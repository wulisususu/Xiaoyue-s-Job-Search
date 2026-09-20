from __future__ import annotations

from dataclasses import dataclass

from ..verification.ats import detect_ats
from .moka import apply_moka_scan_hints
from .models import FormScan

_GENERIC_CAPABILITIES = (
    "dom_scan",
    "text_input",
    "native_select",
    "radio_group",
    "ant_element_combobox",
    "date_picker",
    "post_fill_readback",
)

_GENERIC_LIMITATIONS = (
    "file_upload",
    "cascading_select",
    "repeatable_sections",
    "iframe_forms",
    "multi_step_navigation",
    "auto_submit",
)


@dataclass(frozen=True, slots=True)
class BrowserATSAdapter:
    """Declared Browser Agent behavior for one ATS family.

    The implementation field is intentionally explicit. A recognized ATS may
    still use the generic DOM engine until a dedicated adapter exists; the
    UI/API must not imply dedicated support merely because the host was
    identified.
    """

    id: str
    display_name: str
    implementation: str
    capabilities: tuple[str, ...]
    limitations: tuple[str, ...]


_GENERIC = BrowserATSAdapter(
    id="generic",
    display_name="通用招聘表单",
    implementation="generic_dom",
    capabilities=_GENERIC_CAPABILITIES,
    limitations=_GENERIC_LIMITATIONS,
)

_ADAPTERS: dict[str, BrowserATSAdapter] = {
    "moka": BrowserATSAdapter(
        id="moka",
        display_name="Moka",
        implementation="moka_dom_v1",
        capabilities=(
            *_GENERIC_CAPABILITIES,
            "moka_native_field_paths",
            "indexed_repeatable_mapping",
            "resume_upload",
        ),
        limitations=(
            "additional_attachments",
            "cascading_select",
            "repeatable_sections_without_native_paths",
            "practice_experience_disambiguation",
            "iframe_forms",
            "multi_step_navigation",
            "moka_custom_fields",
            "auto_submit",
        ),
    ),
    "beisen": BrowserATSAdapter(
        id="beisen",
        display_name="北森",
        implementation="generic_dom",
        capabilities=_GENERIC_CAPABILITIES,
        limitations=_GENERIC_LIMITATIONS,
    ),
    "feishu": BrowserATSAdapter(
        id="feishu",
        display_name="飞书招聘",
        implementation="generic_dom",
        capabilities=_GENERIC_CAPABILITIES,
        limitations=_GENERIC_LIMITATIONS,
    ),
    "hotjob": BrowserATSAdapter(
        id="hotjob",
        display_name="Hotjob",
        implementation="generic_dom",
        capabilities=_GENERIC_CAPABILITIES,
        limitations=_GENERIC_LIMITATIONS,
    ),
}


def select_browser_adapter(url: str) -> BrowserATSAdapter:
    """Use the verifier's ATS identity as the single site-detection source."""
    ats = detect_ats(url, "")
    return _ADAPTERS.get(ats or "", _GENERIC)


def get_browser_adapter(adapter_id: str) -> BrowserATSAdapter:
    if adapter_id == "generic":
        return _GENERIC
    return _ADAPTERS.get(adapter_id, _GENERIC)


def list_browser_adapters() -> tuple[BrowserATSAdapter, ...]:
    return (_GENERIC, *_ADAPTERS.values())


def adapt_scan_for_browser_adapter(
    adapter: BrowserATSAdapter,
    scan: FormScan,
) -> FormScan:
    if adapter.id == "moka":
        return apply_moka_scan_hints(scan)
    return scan
