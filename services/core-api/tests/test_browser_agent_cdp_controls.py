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


def test_cdp_resume_upload_targets_exact_file_input_and_verifies_filename(tmp_path, monkeypatch):
    backend = EdgeBrowserBackend()
    resume = tmp_path / "赵新悦-央企简历.pdf"
    resume.write_bytes(b"%PDF-test")

    calls: list[tuple[str, dict | None]] = []

    monkeypatch.setattr(backend, "_page_websocket", lambda handle: "ws://fake")
    def fake_call(ws_url, method, params=None):
        calls.append((method, params))
        if method == "Runtime.evaluate":
            return {"result": {"objectId": "file-input-object"}}
        return {}
    monkeypatch.setattr(backend, "_call_ws", fake_call)
    monkeypatch.setattr(
        backend,
        "_evaluate",
        lambda handle, expression: {
            "filename": resume.name,
            "size": resume.stat().st_size,
            "type": "application/pdf",
        },
    )

    result = backend.upload_file(object(), "resume-file", resume)

    assert result["filename"] == resume.name
    set_file_calls = [params for method, params in calls if method == "DOM.setFileInputFiles"]
    assert set_file_calls == [
        {
            "files": [str(resume.resolve())],
            "objectId": "file-input-object",
        }
    ]
    assert all(method != "Runtime.callFunctionOn" for method, _ in calls)


def test_cdp_resume_upload_fails_when_browser_readback_filename_differs(tmp_path, monkeypatch):
    from app.browser_agent.cdp import BrowserControlError
    import pytest

    backend = EdgeBrowserBackend()
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-test")

    monkeypatch.setattr(backend, "_page_websocket", lambda handle: "ws://fake")
    monkeypatch.setattr(
        backend,
        "_call_ws",
        lambda ws_url, method, params=None: (
            {"result": {"objectId": "file-input-object"}}
            if method == "Runtime.evaluate"
            else {}
        ),
    )
    monkeypatch.setattr(
        backend,
        "_evaluate",
        lambda handle, expression: {
            "filename": "different.pdf",
            "size": 10,
            "type": "application/pdf",
        },
    )

    with pytest.raises(BrowserControlError, match="文件名"):
        backend.upload_file(object(), "resume-file", resume)
