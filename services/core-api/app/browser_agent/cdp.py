from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from websockets.sync.client import connect

from .models import FormFieldDescriptor, FormScan


class BrowserUnavailableError(RuntimeError):
    pass


class BrowserControlError(RuntimeError):
    pass


@dataclass(slots=True)
class EdgeHandle:
    process: subprocess.Popen
    port: int
    profile_dir: Path
    entry_url: str


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _browser_candidates() -> list[Path]:
    candidates: list[Path] = []
    configured = os.environ.get("XIAOYUE_BROWSER_BIN")
    if configured:
        candidates.append(Path(configured))

    for env_name in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        root = os.environ.get(env_name)
        if root:
            candidates.append(Path(root) / "Microsoft" / "Edge" / "Application" / "msedge.exe")

    for name in ("msedge", "microsoft-edge", "google-chrome", "chrome", "chromium", "chromium-browser"):
        resolved = shutil.which(name)
        if resolved:
            candidates.append(Path(resolved))

    deduped: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path).lower()
        if key not in seen:
            seen.add(key)
            deduped.append(path)
    return deduped


def find_browser_binary() -> Path:
    for path in _browser_candidates():
        if path.is_file():
            return path
    raise BrowserUnavailableError(
        "未找到 Microsoft Edge/Chromium。可通过 XIAOYUE_BROWSER_BIN 指定浏览器可执行文件。"
    )


_SCAN_SCRIPT = r"""
(() => {
  const text = (value) => (value || '').replace(/\s+/g, ' ').trim();
  const labelFor = (el) => {
    if (el.labels && el.labels.length) return text(Array.from(el.labels).map((x) => x.innerText).join(' '));
    const wrapped = el.closest('label');
    if (wrapped) return text(wrapped.innerText);
    if (el.id) {
      try {
        const label = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
        if (label) return text(label.innerText);
      } catch (_) {}
    }
    const parent = el.parentElement;
    if (parent) {
      const nearby = parent.querySelector('.label,.form-label,[class*="label"],dt,th');
      if (nearby) return text(nearby.innerText);
    }
    return '';
  };
  const sectionFor = (el) => {
    const fieldset = el.closest('fieldset');
    if (fieldset) {
      const legend = fieldset.querySelector('legend');
      if (legend) return text(legend.innerText);
    }
    let node = el.parentElement;
    for (let depth = 0; node && depth < 5; depth += 1, node = node.parentElement) {
      const heading = node.querySelector(':scope > h1,:scope > h2,:scope > h3,:scope > h4,:scope > .title,:scope > [class*="title"]');
      if (heading) return text(heading.innerText);
    }
    return '';
  };
  const nodes = Array.from(document.querySelectorAll('input,select,textarea'));
  const fields = nodes.map((el, index) => {
    if (!el.dataset.xiaoyueAgentId) {
      el.dataset.xiaoyueAgentId = 'xy-' + Date.now().toString(36) + '-' + index.toString(36) + '-' + Math.random().toString(36).slice(2, 8);
    }
    const tag = el.tagName.toLowerCase();
    const inputType = tag === 'input' ? (el.getAttribute('type') || 'text').toLowerCase() : tag;
    const options = tag === 'select'
      ? Array.from(el.options || []).map((option) => text(option.textContent || option.value)).filter(Boolean)
      : [];
    return {
      field_id: el.dataset.xiaoyueAgentId,
      tag,
      input_type: inputType,
      label: labelFor(el),
      name: el.getAttribute('name') || '',
      placeholder: el.getAttribute('placeholder') || '',
      aria_label: el.getAttribute('aria-label') || '',
      section: sectionFor(el),
      required: Boolean(el.required || el.getAttribute('aria-required') === 'true'),
      options,
      disabled: Boolean(el.disabled),
      readonly: Boolean(el.readOnly),
    };
  });
  return { url: location.href, title: document.title || '', fields };
})()
"""


class EdgeBrowserBackend:
    """Small CDP client for a user-visible, isolated Edge/Chromium session."""

    browser_name = "Microsoft Edge / Chromium"

    def __init__(self, *, startup_timeout: float = 15.0, command_timeout: float = 10.0) -> None:
        self.startup_timeout = startup_timeout
        self.command_timeout = command_timeout

    def start(self, url: str, profile_dir: Path) -> EdgeHandle:
        browser = find_browser_binary()
        profile_dir.mkdir(parents=True, exist_ok=True)
        port = _pick_free_port()
        args = [
            str(browser),
            f"--remote-debugging-port={port}",
            "--remote-debugging-address=127.0.0.1",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--new-window",
            url,
        ]
        process = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
        handle = EdgeHandle(process=process, port=port, profile_dir=profile_dir, entry_url=url)
        try:
            self._wait_ready(handle)
        except Exception:
            self.close(handle)
            raise
        return handle

    def _wait_ready(self, handle: EdgeHandle) -> None:
        deadline = time.monotonic() + self.startup_timeout
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            if handle.process.poll() is not None:
                raise BrowserUnavailableError("受控浏览器启动后立即退出。")
            try:
                with httpx.Client(timeout=1.0, trust_env=False) as client:
                    response = client.get(f"http://127.0.0.1:{handle.port}/json/version")
                    if response.status_code == 200:
                        return
            except Exception as exc:
                last_error = exc
            time.sleep(0.2)
        raise BrowserUnavailableError(f"受控浏览器未在规定时间内启动: {last_error or 'timeout'}")

    def _json(self, handle: EdgeHandle, path: str) -> Any:
        with httpx.Client(timeout=3.0, trust_env=False) as client:
            response = client.get(f"http://127.0.0.1:{handle.port}{path}")
            response.raise_for_status()
            return response.json()

    def _page_websocket(self, handle: EdgeHandle) -> str:
        targets = self._json(handle, "/json/list")
        if not isinstance(targets, list):
            raise BrowserControlError("DevTools target list is invalid")
        pages = [
            target for target in targets
            if isinstance(target, dict)
            and target.get("type") == "page"
            and isinstance(target.get("webSocketDebuggerUrl"), str)
            and not str(target.get("url", "")).startswith(("devtools://", "chrome://"))
        ]
        if not pages:
            raise BrowserControlError("未找到可控制的招聘页面，请确认受控浏览器窗口仍然打开。")
        non_blank = [page for page in pages if str(page.get("url", "")) not in {"", "about:blank", "edge://newtab/"}]
        target = (non_blank or pages)[-1]
        return str(target["webSocketDebuggerUrl"])

    def _call_ws(self, ws_url: str, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        command_id = 1
        with connect(ws_url, open_timeout=3, close_timeout=1) as websocket:
            websocket.send(json.dumps({"id": command_id, "method": method, "params": params or {}}))
            deadline = time.monotonic() + self.command_timeout
            while time.monotonic() < deadline:
                remaining = max(0.1, deadline - time.monotonic())
                raw = websocket.recv(timeout=remaining)
                payload = json.loads(raw)
                if payload.get("id") != command_id:
                    continue
                if "error" in payload:
                    raise BrowserControlError(str(payload["error"]))
                return payload.get("result") or {}
        raise BrowserControlError(f"CDP command timed out: {method}")

    def _evaluate(self, handle: EdgeHandle, expression: str) -> Any:
        result = self._call_ws(
            self._page_websocket(handle),
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
                "userGesture": True,
            },
        )
        if result.get("exceptionDetails"):
            raise BrowserControlError("页面脚本执行失败")
        remote = result.get("result") or {}
        return remote.get("value")

    def scan(self, handle: EdgeHandle) -> FormScan:
        payload = self._evaluate(handle, _SCAN_SCRIPT)
        if not isinstance(payload, dict) or not isinstance(payload.get("fields"), list):
            raise BrowserControlError("页面表单扫描结果无效")
        fields: list[FormFieldDescriptor] = []
        for raw in payload["fields"]:
            if not isinstance(raw, dict) or not raw.get("field_id"):
                continue
            fields.append(
                FormFieldDescriptor(
                    field_id=str(raw.get("field_id", "")),
                    tag=str(raw.get("tag", "")),
                    input_type=str(raw.get("input_type", "")),
                    label=str(raw.get("label", "")),
                    name=str(raw.get("name", "")),
                    placeholder=str(raw.get("placeholder", "")),
                    aria_label=str(raw.get("aria_label", "")),
                    section=str(raw.get("section", "")),
                    required=bool(raw.get("required", False)),
                    options=[str(item) for item in (raw.get("options") or []) if isinstance(item, str)],
                    disabled=bool(raw.get("disabled", False)),
                    readonly=bool(raw.get("readonly", False)),
                )
            )
        return FormScan(
            url=str(payload.get("url", "")),
            title=str(payload.get("title", "")),
            fields=fields,
        )

    def fill(self, handle: EdgeHandle, values: dict[str, Any]) -> dict[str, int]:
        encoded = json.dumps(values, ensure_ascii=False)
        script = f"""
(() => {{
  const updates = {encoded};
  let filled = 0;
  let skipped = 0;
  const blocked = new Set(['hidden','password','file','submit','button','reset','image']);
  const setNativeValue = (el, value) => {{
    const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const descriptor = Object.getOwnPropertyDescriptor(proto, 'value');
    if (descriptor && descriptor.set) descriptor.set.call(el, value);
    else el.value = value;
  }};
  for (const [fieldId, rawValue] of Object.entries(updates)) {{
    const el = Array.from(document.querySelectorAll('[data-xiaoyue-agent-id]'))
      .find((node) => node.dataset.xiaoyueAgentId === fieldId);
    if (!el || el.disabled || el.readOnly) {{ skipped += 1; continue; }}
    const tag = el.tagName.toLowerCase();
    const type = tag === 'input' ? (el.getAttribute('type') || 'text').toLowerCase() : tag;
    if (blocked.has(type) || type === 'checkbox' || type === 'radio') {{ skipped += 1; continue; }}
    const value = Array.isArray(rawValue) ? rawValue.join('；') : String(rawValue ?? '');
    if (tag === 'select') {{
      const normalized = value.trim().toLowerCase();
      const option = Array.from(el.options || []).find((item) =>
        String(item.value).trim().toLowerCase() === normalized ||
        String(item.textContent || '').trim().toLowerCase() === normalized
      );
      if (!option) {{ skipped += 1; continue; }}
      el.value = option.value;
    }} else if (tag === 'input' || tag === 'textarea') {{
      setNativeValue(el, value);
    }} else {{
      skipped += 1; continue;
    }}
    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
    el.dispatchEvent(new Event('blur', {{ bubbles: true }}));
    filled += 1;
  }}
  return {{ filled_count: filled, skipped_count: skipped }};
}})()
"""
        payload = self._evaluate(handle, script)
        if not isinstance(payload, dict):
            raise BrowserControlError("页面填写结果无效")
        return {
            "filled_count": int(payload.get("filled_count", 0)),
            "skipped_count": int(payload.get("skipped_count", 0)),
        }

    def close(self, handle: EdgeHandle) -> None:
        try:
            version = self._json(handle, "/json/version")
            ws_url = version.get("webSocketDebuggerUrl") if isinstance(version, dict) else None
            if isinstance(ws_url, str):
                self._call_ws(ws_url, "Browser.close")
        except Exception:
            pass
        if handle.process.poll() is None:
            try:
                handle.process.terminate()
                handle.process.wait(timeout=3)
            except Exception:
                try:
                    handle.process.kill()
                except Exception:
                    pass
