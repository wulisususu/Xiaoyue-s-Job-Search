from app.browser_agent.adapters import get_browser_adapter, select_browser_adapter


def test_known_ats_hosts_share_verifier_identity_but_do_not_overclaim_dedicated_support():
    cases = {
        "https://app.mokahr.com/apply/123": ("moka", "Moka"),
        "https://career.beisen.com/apply/123": ("beisen", "北森"),
        "https://jobs.feishu.cn/apply/123": ("feishu", "飞书招聘"),
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
