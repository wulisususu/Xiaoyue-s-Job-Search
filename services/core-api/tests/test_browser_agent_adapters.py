from app.browser_agent.adapters import get_browser_adapter, select_browser_adapter


def test_moka_is_promoted_to_dedicated_path_aware_adapter():
    adapter = select_browser_adapter("https://app.mokahr.com/apply/123")
    assert adapter.id == "moka"
    assert adapter.display_name == "Moka"
    assert adapter.implementation == "moka_dom_v1"
    assert "moka_native_field_paths" in adapter.capabilities
    assert "indexed_repeatable_mapping" in adapter.capabilities
    assert "resume_upload" in adapter.capabilities
    assert "additional_attachments" in adapter.limitations
    assert "moka_custom_fields" in adapter.limitations
    assert "auto_submit" in adapter.limitations


def test_beisen_is_promoted_to_dedicated_path_aware_adapter():
    adapter = select_browser_adapter("https://career.beisen.com/apply/123")
    assert adapter.id == "beisen"
    assert adapter.display_name == "北森"
    assert adapter.implementation == "beisen_dom_v1"
    assert "beisen_standard_resume_paths" in adapter.capabilities
    assert "indexed_repeatable_mapping" in adapter.capabilities
    assert "file_upload" in adapter.limitations
    assert "internship_experience_disambiguation" in adapter.limitations
    assert "high_risk_declarations" in adapter.limitations
    assert "auto_submit" in adapter.limitations


def test_feishu_is_promoted_to_dedicated_path_aware_adapter():
    adapter = select_browser_adapter("https://jobs.feishu.cn/apply/123")
    assert adapter.id == "feishu"
    assert adapter.display_name == "飞书招聘"
    assert adapter.implementation == "feishu_dom_v1"
    assert "feishu_talent_paths" in adapter.capabilities
    assert "indexed_repeatable_mapping" in adapter.capabilities
    assert "file_upload" in adapter.limitations
    assert "high_risk_identity_fields" in adapter.limitations
    assert "feishu_customized_data" in adapter.limitations
    assert "auto_submit" in adapter.limitations


def test_other_known_ats_hosts_remain_honest_generic_dom_adapters():
    cases = {
        "https://company.hotjob.cn/wt/apply": ("hotjob", "Hotjob"),
    }

    for url, (expected_id, expected_name) in cases.items():
        adapter = select_browser_adapter(url)
        assert adapter.id == expected_id
        assert adapter.display_name == expected_name
        assert adapter.implementation == "generic_dom"
        assert "post_fill_readback" in adapter.capabilities
        assert "file_upload" in adapter.limitations
        assert "auto_submit" in adapter.limitations


def test_unknown_site_falls_back_to_generic_adapter():
    adapter = select_browser_adapter("https://careers.example.com/apply")
    assert adapter.id == "generic"
    assert adapter.display_name == "通用招聘表单"
    assert adapter.implementation == "generic_dom"


def test_unknown_adapter_id_cannot_invent_capabilities():
    fallback = get_browser_adapter("future-unknown-adapter")
    assert fallback.id == "generic"
    assert "auto_submit" not in fallback.capabilities
