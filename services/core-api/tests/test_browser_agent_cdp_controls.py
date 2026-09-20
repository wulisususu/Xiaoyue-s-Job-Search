from __future__ import annotations

from app.browser_agent import cdp
from app.browser_agent.cdp import EdgeBrowserBackend


def test_cdp_scanner_declares_common_chinese_ats_custom_control_patterns():
    script = cdp._SCAN_SCRIPT
    assert ".ant-select" in script
    assert ".el-select" in script
    assert "radio_group" in script
    assert ".ant-picker" in script
    assert ".el-date-editor" in script


def test_cdp_fill_script_handles_combobox_radio_group_and_date_picker(monkeypatch):
    backend = EdgeBrowserBackend()
    captured: dict[str, str] = {}

    def fake_evaluate(handle, expression):
        captured["script"] = expression
        return {
            "filled_count": 3,
            "skipped_count": 0,
            "verified_count": 2,
            "failed_count": 1,
            "uncertain_count": 0,
            "results": [
                {"field_id": "degree-combo", "status": "VERIFIED"},
                {"field_id": "hukou-radio", "status": "VERIFIED"},
                {"field_id": "grad-date", "status": "FAILED"},
            ],
        }

    monkeypatch.setattr(backend, "_evaluate", fake_evaluate)
    result = backend.fill(
        object(),
        {
            "degree-combo": "本科",
            "hukou-radio": "安徽",
            "grad-date": "2027-06",
        },
    )

    assert result == {
        "filled_count": 3,
        "skipped_count": 0,
        "verified_count": 2,
        "failed_count": 1,
        "uncertain_count": 0,
        "results": [
            {"field_id": "degree-combo", "status": "VERIFIED"},
            {"field_id": "hukou-radio", "status": "VERIFIED"},
            {"field_id": "grad-date", "status": "FAILED"},
        ],
    }
    script = captured["script"]
    assert "combobox" in script
    assert "radio_group" in script
    assert "date_picker" in script
    assert "ant-select-item-option" in script
    assert "el-select-dropdown__item" in script
    assert "new MouseEvent('mousedown'" in script
    assert "new KeyboardEvent('keydown'" in script


def test_cdp_fill_script_performs_post_write_readback_and_validation_checks(monkeypatch):
    backend = EdgeBrowserBackend()
    captured: dict[str, str] = {}

    def fake_evaluate(handle, expression):
        captured["script"] = expression
        return {
            "filled_count": 1,
            "skipped_count": 0,
            "verified_count": 1,
            "failed_count": 0,
            "uncertain_count": 0,
            "results": [],
        }

    monkeypatch.setattr(backend, "_evaluate", fake_evaluate)
    backend.fill(object(), {"name": "赵新悦"})

    script = captured["script"]
    assert "READBACK_MATCH" in script
    assert "PAGE_VALIDATION_ERROR" in script
    assert "aria-invalid" in script
    assert "await sleep(180)" in script
