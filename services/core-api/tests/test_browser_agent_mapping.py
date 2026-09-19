from __future__ import annotations

from app.browser_agent.mapping import build_fill_plan
from app.browser_agent.models import ConfirmedProfileSnapshot, FormFieldDescriptor, FormScan


def field(field_id: str, label: str, *, input_type: str = "text", name: str = "", placeholder: str = "", section: str = ""):
    return FormFieldDescriptor(
        field_id=field_id,
        tag="input",
        input_type=input_type,
        label=label,
        name=name,
        placeholder=placeholder,
        aria_label="",
        section=section,
        required=False,
        options=[],
    )


def test_deterministic_mapping_prefers_confirmed_structured_profile_values():
    snapshot = ConfirmedProfileSnapshot(
        scalars={
            "identity.name": "赵新悦",
            "contact.phone": "13800138000",
            "contact.email": "zxy@example.com",
            "location.hukou": "安徽",
        },
        collections={
            "education": [{"school": "三江学院", "major": "视觉传达设计", "degree": "本科"}],
        },
    )
    scan = FormScan(
        url="https://ats.example.com/apply",
        title="网申",
        fields=[
            field("f1", "姓名", name="realName"),
            field("f2", "手机号码", input_type="tel"),
            field("f3", "邮箱", input_type="email"),
            field("f4", "毕业院校", section="教育经历"),
            field("f5", "所学专业", section="教育经历"),
            field("f6", "最高学历", section="教育经历"),
            field("f7", "生源地"),
            field("f8", "紧急联系人"),
        ],
    )

    plan = build_fill_plan(snapshot, scan)

    mapped = {item.field_id: item for item in plan.items}
    assert mapped["f1"].value == "赵新悦"
    assert mapped["f1"].source_path == "identity.name"
    assert mapped["f2"].source_path == "contact.phone"
    assert mapped["f3"].source_path == "contact.email"
    assert mapped["f4"].value == "三江学院"
    assert mapped["f4"].source_path == "collections.education[0].school"
    assert mapped["f5"].value == "视觉传达设计"
    assert mapped["f6"].value == "本科"
    assert mapped["f7"].source_path == "location.hukou"
    assert mapped["f7"].requires_confirmation is True
    assert "f8" in {item.field_id for item in plan.unmatched}


def test_sensitive_and_submit_controls_are_never_fillable():
    snapshot = ConfirmedProfileSnapshot(scalars={"identity.name": "赵新悦"}, collections={})
    scan = FormScan(
        url="https://ats.example.com/apply",
        title="网申",
        fields=[
            field("name", "姓名"),
            field("password", "密码", input_type="password"),
            field("file", "上传附件", input_type="file"),
            field("submit", "提交申请", input_type="submit"),
        ],
    )

    plan = build_fill_plan(snapshot, scan)
    assert [item.field_id for item in plan.items] == ["name"]
    assert {item.field_id for item in plan.blocked} == {"password", "file", "submit"}


def test_repeated_collection_fields_advance_by_occurrence_and_never_duplicate_first_record():
    snapshot = ConfirmedProfileSnapshot(
        scalars={
            "education.school": "三江学院",
            "education.major": "视觉传达设计",
        },
        collections={
            "education": [
                {"school": "三江学院", "major": "视觉传达设计"},
                {"school": "南京艺术学院", "major": "数字媒体"},
            ],
        },
    )
    scan = FormScan(
        url="https://ats.example.com/apply",
        title="网申",
        fields=[
            field("school-1", "学校", section="教育经历"),
            field("major-1", "专业", section="教育经历"),
            field("school-2", "学校", section="教育经历"),
            field("major-2", "专业", section="教育经历"),
            field("school-3", "学校", section="教育经历"),
        ],
    )

    plan = build_fill_plan(snapshot, scan)
    mapped = {item.field_id: item for item in plan.items}

    assert (mapped["school-1"].value, mapped["school-1"].source_path) == (
        "三江学院", "collections.education[0].school"
    )
    assert (mapped["major-1"].value, mapped["major-1"].source_path) == (
        "视觉传达设计", "collections.education[0].major"
    )
    assert (mapped["school-2"].value, mapped["school-2"].source_path) == (
        "南京艺术学院", "collections.education[1].school"
    )
    assert (mapped["major-2"].value, mapped["major-2"].source_path) == (
        "数字媒体", "collections.education[1].major"
    )
    assert "school-3" not in mapped
    assert "school-3" in {item.field_id for item in plan.unmatched}


def test_custom_ats_controls_require_confirmation_and_checkboxes_are_blocked():
    snapshot = ConfirmedProfileSnapshot(
        scalars={"location.hukou": "安徽"},
        collections={"education": [{"degree": "本科"}]},
    )
    scan = FormScan(
        url="https://ats.example.com/apply",
        title="网申",
        fields=[
            FormFieldDescriptor(
                field_id="degree-combo", tag="div", input_type="combobox",
                label="最高学历", name="degree", placeholder="请选择",
                aria_label="", section="教育经历", required=True,
                options=["本科", "硕士"],
            ),
            FormFieldDescriptor(
                field_id="hukou-radio", tag="radio_group", input_type="radio_group",
                label="户籍所在地", name="hukou", placeholder="",
                aria_label="", section="基本信息", required=True,
                options=["安徽", "江苏"],
            ),
            FormFieldDescriptor(
                field_id="consent", tag="input", input_type="checkbox",
                label="我已阅读并同意", name="consent", placeholder="",
                aria_label="", section="", required=True, options=[],
            ),
        ],
    )

    plan = build_fill_plan(snapshot, scan)
    mapped = {item.field_id: item for item in plan.items}

    assert mapped["degree-combo"].value == "本科"
    assert mapped["degree-combo"].requires_confirmation is True
    assert mapped["hukou-radio"].value == "安徽"
    assert mapped["hukou-radio"].requires_confirmation is True
    assert "consent" in {item.field_id for item in plan.blocked}
