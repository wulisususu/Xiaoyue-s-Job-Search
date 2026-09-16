import pytest

from app.models import Base
from app.profile.registry import FIELD_REGISTRY, get_field_definition, validate_profile_value


def test_registry_exposes_stable_non_sensitive_fields():
    field = get_field_definition("identity.name")
    assert field.label == "姓名"
    assert field.category == "身份信息"
    assert field.value_type == "string"
    assert field.multiple is False

    expected = {
        "identity.name",
        "contact.phone",
        "contact.email",
        "education.school",
        "education.major",
        "education.degree",
        "education.graduation_date",
        "location.hukou",
        "location.current_city",
        "job.target_roles",
        "skills.summary",
        "experience.summary",
        "awards.summary",
    }
    assert expected.issubset(FIELD_REGISTRY)
    assert "identity.political_status" not in FIELD_REGISTRY


def test_registry_validates_contact_and_list_values():
    assert validate_profile_value("contact.phone", "13800138000") == "13800138000"
    assert validate_profile_value("contact.email", "name@example.com") == "name@example.com"
    assert validate_profile_value("job.target_roles", ["视觉设计", "平面设计"]) == ["视觉设计", "平面设计"]

    with pytest.raises(ValueError):
        validate_profile_value("contact.phone", "123")
    with pytest.raises(ValueError):
        validate_profile_value("contact.email", "not-an-email")
    with pytest.raises(ValueError):
        validate_profile_value("job.target_roles", "视觉设计")
    with pytest.raises(KeyError):
        validate_profile_value("unknown.field", "x")


def test_resume_and_profile_tables_have_identity_constraints():
    required = {
        "resume_versions",
        "profile_fields",
        "profile_field_revisions",
        "profile_draft_fields",
    }
    assert required.issubset(Base.metadata.tables)

    resume_table = Base.metadata.tables["resume_versions"]
    profile_table = Base.metadata.tables["profile_fields"]
    assert resume_table.c.sha256.unique is True
    assert profile_table.c.field_key.unique is True
