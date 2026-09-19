from __future__ import annotations

from app.browser_agent.models import ConfirmedProfileSnapshot, FillPlan, FormFieldDescriptor, FormScan, PlanFieldSummary
from app.browser_agent.semantic_mapping import apply_semantic_suggestions


class FakeSemanticProvider:
    def __init__(self, suggestions):
        self.suggestions = suggestions
        self.seen_fields = None
        self.seen_candidates = None

    def suggest(self, *, fields, candidates):
        self.seen_fields = fields
        self.seen_candidates = candidates
        return self.suggestions


def descriptor(field_id: str, label: str, *, input_type: str = "text", options: list[str] | None = None):
    return FormFieldDescriptor(
        field_id=field_id,
        tag="select" if input_type == "select" else "input",
        input_type=input_type,
        label=label,
        name="",
        placeholder="",
        aria_label="",
        section="基本信息",
        required=False,
        options=options or [],
    )


def test_ai_semantic_mapping_can_only_reference_confirmed_snapshot_paths_and_requires_confirmation():
    snapshot = ConfirmedProfileSnapshot(
        scalars={"location.hukou": "安徽", "identity.name": "赵新悦"},
        collections={"education": [{"degree": "本科"}]},
    )
    scan = FormScan(
        url="https://ats.example.com/apply",
        title="网申",
        fields=[
            descriptor("origin", "生源地"),
            descriptor("degree", "学历层次", input_type="select", options=["大学本科", "硕士研究生"]),
            descriptor("emergency", "紧急联系人"),
        ],
    )
    plan = FillPlan(
        token="plan-old",
        session_id="agent-1",
        page_url=scan.url,
        unmatched=[
            PlanFieldSummary("origin", "生源地", "text"),
            PlanFieldSummary("degree", "学历层次", "select"),
            PlanFieldSummary("emergency", "紧急联系人", "text"),
        ],
    )
    provider = FakeSemanticProvider([
        {
            "field_id": "origin",
            "source_path": "location.hukou",
            "confidence": 0.91,
            "reason": "生源地通常对应户籍来源地",
            "selected_option": None,
        },
        {
            "field_id": "degree",
            "source_path": "collections.education[0].degree",
            "confidence": 0.97,
            "reason": "学历层次",
            "selected_option": "大学本科",
        },
        # Must be ignored: the model cannot invent a source path/value.
        {
            "field_id": "emergency",
            "source_path": "invented.emergency_contact",
            "confidence": 1.0,
            "reason": "invented",
            "selected_option": None,
        },
    ])

    updated = apply_semantic_suggestions(snapshot, scan, plan, provider)

    items = {item.field_id: item for item in updated.items}
    assert items["origin"].value == "安徽"
    assert items["origin"].source_path == "location.hukou"
    assert items["origin"].requires_confirmation is True
    assert items["degree"].value == "大学本科"
    assert items["degree"].source_path == "collections.education[0].degree"
    assert items["degree"].requires_confirmation is True
    assert "emergency" not in items
    assert {item.field_id for item in updated.unmatched} == {"emergency"}
    assert updated.token != "plan-old"

    assert provider.seen_candidates == {
        "identity.name": "赵新悦",
        "location.hukou": "安徽",
        "collections.education[0].degree": "本科",
    }


def test_ai_semantic_mapping_rejects_option_not_present_on_page():
    snapshot = ConfirmedProfileSnapshot(
        scalars={},
        collections={"education": [{"degree": "本科"}]},
    )
    scan = FormScan(
        url="https://ats.example.com/apply",
        title="网申",
        fields=[descriptor("degree", "学历层次", input_type="select", options=["大学本科", "硕士研究生"])],
    )
    plan = FillPlan(
        token="plan-old",
        session_id="agent-1",
        page_url=scan.url,
        unmatched=[PlanFieldSummary("degree", "学历层次", "select")],
    )
    provider = FakeSemanticProvider([
        {
            "field_id": "degree",
            "source_path": "collections.education[0].degree",
            "confidence": 0.99,
            "reason": "学历映射",
            "selected_option": "博士研究生",
        },
    ])

    updated = apply_semantic_suggestions(snapshot, scan, plan, provider)
    assert updated.items == []
    assert [item.field_id for item in updated.unmatched] == ["degree"]


def test_ai_semantic_mapping_treats_custom_combobox_and_radio_group_as_option_controls():
    snapshot = ConfirmedProfileSnapshot(
        scalars={"location.hukou": "安徽"},
        collections={"education": [{"degree": "本科"}]},
    )
    scan = FormScan(
        url="https://ats.example.com/apply",
        title="网申",
        fields=[
            descriptor("degree", "学历层次", input_type="combobox", options=["大学本科", "硕士研究生"]),
            descriptor("hukou", "户籍所在地", input_type="radio_group", options=["安徽", "江苏"]),
        ],
    )
    plan = FillPlan(
        token="plan-old",
        session_id="agent-1",
        page_url=scan.url,
        unmatched=[
            PlanFieldSummary("degree", "学历层次", "combobox"),
            PlanFieldSummary("hukou", "户籍所在地", "radio_group"),
        ],
    )
    provider = FakeSemanticProvider([
        {
            "field_id": "degree",
            "source_path": "collections.education[0].degree",
            "confidence": 0.98,
            "reason": "学历映射",
            "selected_option": "大学本科",
        },
        {
            "field_id": "hukou",
            "source_path": "location.hukou",
            "confidence": 0.99,
            "reason": "户籍映射",
            "selected_option": "安徽",
        },
    ])

    updated = apply_semantic_suggestions(snapshot, scan, plan, provider)
    mapped = {item.field_id: item for item in updated.items}
    assert mapped["degree"].value == "大学本科"
    assert mapped["degree"].requires_confirmation is True
    assert mapped["hukou"].value == "安徽"
    assert mapped["hukou"].requires_confirmation is True


def test_semantic_provider_candidates_exclude_sensitive_profile_values():
    from app.browser_agent.semantic_mapping import flatten_confirmed_snapshot

    snapshot = ConfirmedProfileSnapshot(
        scalars={
            "identity.name": "测试用户",
            "identity.id_number": "TESTDOC-ABC1234",
        },
        collections={},
    )
    candidates = flatten_confirmed_snapshot(snapshot)
    assert candidates["identity.name"] == "测试用户"
    assert "identity.id_number" not in candidates
    assert "TESTDOC-ABC1234" not in str(candidates)


def test_semantic_provider_candidates_exclude_political_status_as_sensitive():
    from app.browser_agent.semantic_mapping import flatten_confirmed_snapshot

    snapshot = ConfirmedProfileSnapshot(
        scalars={
            "identity.name": "测试用户",
            "identity.political_status": "测试敏感值",
        },
        collections={},
    )
    candidates = flatten_confirmed_snapshot(snapshot)
    assert candidates == {"identity.name": "测试用户"}
    assert "测试敏感值" not in str(candidates)
