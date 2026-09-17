from __future__ import annotations

import pytest

from app.profile.collections import COLLECTION_REGISTRY, get_collection_definition, validate_collection_payload


def test_collection_registry_exposes_exact_supported_kinds():
    assert list(COLLECTION_REGISTRY) == [
        "education",
        "experience",
        "project",
        "award",
        "certificate",
        "language",
        "skill",
    ]


def test_education_payload_is_trimmed_and_keeps_optional_fields():
    payload = validate_collection_payload(
        "education",
        {
            "school": "  三江学院  ",
            "degree": " 本科 ",
            "major": " 视觉传达设计 ",
            "start_date": "2023-09",
            "end_date": "2027-06",
            "gpa": " 3.6/4.0 ",
            "ranking": " 前 20% ",
        },
    )
    assert payload == {
        "school": "三江学院",
        "degree": "本科",
        "major": "视觉传达设计",
        "start_date": "2023-09",
        "end_date": "2027-06",
        "gpa": "3.6/4.0",
        "ranking": "前 20%",
    }


def test_experience_payload_normalizes_bullets_and_rejects_unknown_fields():
    payload = validate_collection_payload(
        "experience",
        {
            "organization": " 教师工作室 ",
            "role": " 视觉设计 ",
            "location": " 南京 ",
            "start_date": "2025-01",
            "end_date": "2025-06",
            "bullets": [" 海报设计 ", "", " 外拍与剪辑 "],
        },
    )
    assert payload["bullets"] == ["海报设计", "外拍与剪辑"]

    with pytest.raises(ValueError, match="unknown fields"):
        validate_collection_payload("experience", {"organization": "A", "role": "B", "oops": "x"})


@pytest.mark.parametrize(
    ("kind", "payload", "required_key"),
    [
        ("education", {"degree": "本科", "major": "视觉传达"}, "school"),
        ("experience", {"role": "设计"}, "organization"),
        ("project", {"role": "负责人"}, "name"),
        ("award", {"issuer": "学校"}, "name"),
        ("certificate", {"issuer": "机构"}, "name"),
        ("language", {"level": "CET-4"}, "name"),
        ("skill", {"level": "熟练"}, "name"),
    ],
)
def test_required_string_fields_are_enforced(kind, payload, required_key):
    with pytest.raises(ValueError, match=required_key):
        validate_collection_payload(kind, payload)


def test_skill_name_cannot_be_blank():
    with pytest.raises(ValueError, match="name"):
        validate_collection_payload("skill", {"name": "   "})


def test_unknown_collection_kind_is_rejected():
    with pytest.raises(KeyError, match="Unknown profile collection kind"):
        get_collection_definition("unknown")


def test_definitions_expose_labels_and_ordered_field_metadata():
    education = get_collection_definition("education")
    assert education.label == "教育经历"
    assert [field.key for field in education.fields][:3] == ["school", "degree", "major"]
    assert education.fields[0].required is True
