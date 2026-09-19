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
  const normalize = (value) => text(value).toLowerCase();
  const ensureId = (el, suffix) => {
    if (!el.dataset.xiaoyueAgentId) {
      el.dataset.xiaoyueAgentId =
        'xy-' + Date.now().toString(36) + '-' + String(suffix) + '-' + Math.random().toString(36).slice(2, 8);
    }
    return el.dataset.xiaoyueAgentId;
  };
  const labelFor = (el) => {
    if (!el) return '';
    if (el.labels && el.labels.length) return text(Array.from(el.labels).map((x) => x.innerText).join(' '));
    const wrapped = el.closest && el.closest('label');
    if (wrapped) return text(wrapped.innerText);
    if (el.id) {
      try {
        const label = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
        if (label) return text(label.innerText);
      } catch (_) {}
    }
    return '';
  };
  const formLabelFor = (el) => {
    if (!el) return '';
    const container = el.closest && el.closest(
      '.ant-form-item,.el-form-item,.form-item,.form-field,.field,[class*="form-item"],[class*="formItem"]'
    );
    if (!container) return labelFor(el);
    const candidates = Array.from(container.querySelectorAll(
      '.ant-form-item-label label,.el-form-item__label,.form-label,[class*="label"],label,dt,th'
    ));
    const candidate = candidates.find((node) => !el.contains(node) && text(node.innerText));
    return candidate ? text(candidate.innerText) : labelFor(el);
  };
  const sectionFor = (el) => {
    if (!el) return '';
    const fieldset = el.closest && el.closest('fieldset');
    if (fieldset) {
      const legend = fieldset.querySelector('legend');
      if (legend) return text(legend.innerText);
    }
    let node = el.parentElement;
    for (let depth = 0; node && depth < 5; depth += 1, node = node.parentElement) {
      const heading = node.querySelector(
        ':scope > h1,:scope > h2,:scope > h3,:scope > h4,:scope > .title,:scope > [class*="title"]'
      );
      if (heading) return text(heading.innerText);
    }
    return '';
  };
  const optionText = (radio) => {
    const labelled = labelFor(radio);
    return labelled || text(radio.value);
  };
  const fields = [];
  const consumed = new Set();

  // Native + Ant Design + Element Plus radio groups are represented as one
  // logical control. Every member receives the same stable agent id.
  const radios = Array.from(document.querySelectorAll('input[type="radio"]'));
  const radioGroups = new Map();
  radios.forEach((radio, index) => {
    const root = radio.closest('[role="radiogroup"],.ant-radio-group,.el-radio-group,fieldset');
    const name = radio.getAttribute('name') || '';
    let key;
    if (root) {
      key = 'root:' + ensureId(root, 'rg-' + index);
    } else if (name) {
      key = 'name:' + name;
    } else {
      key = 'single:' + index;
    }
    if (!radioGroups.has(key)) radioGroups.set(key, { root, radios: [] });
    radioGroups.get(key).radios.push(radio);
  });

  let radioIndex = 0;
  for (const group of radioGroups.values()) {
    const members = group.radios;
    if (!members.length) continue;
    const root = group.root || members[0].parentElement || members[0];
    const fieldId = ensureId(root, 'radio-' + radioIndex++);
    root.dataset.xiaoyueControlType = 'radio_group';
    members.forEach((radio) => {
      radio.dataset.xiaoyueAgentId = fieldId;
      radio.dataset.xiaoyueControlType = 'radio_group';
      consumed.add(radio);
    });
    fields.push({
      field_id: fieldId,
      tag: 'radio_group',
      input_type: 'radio_group',
      label: formLabelFor(root) || formLabelFor(members[0]),
      name: members[0].getAttribute('name') || '',
      placeholder: '',
      aria_label: root.getAttribute('aria-label') || '',
      section: sectionFor(root),
      required: members.some((radio) => Boolean(radio.required || radio.getAttribute('aria-required') === 'true')),
      options: members.map(optionText).filter(Boolean),
      disabled: members.every((radio) => Boolean(radio.disabled)),
      readonly: false,
    });
  }

  const nodes = Array.from(document.querySelectorAll('input,select,textarea,[role="combobox"]'));
  nodes.forEach((el, index) => {
    if (consumed.has(el)) return;
    const tag = el.tagName.toLowerCase();
    const nativeType = tag === 'input' ? (el.getAttribute('type') || 'text').toLowerCase() : tag;

    const frameworkCombo = el.closest && el.closest('.ant-select,.el-select');
    const ariaCombo = el.getAttribute('role') === 'combobox'
      ? el
      : (el.closest && el.closest('[role="combobox"]'));
    const comboRoot = tag !== 'select' ? (frameworkCombo || ariaCombo) : null;
    if (comboRoot) {
      if (consumed.has(comboRoot)) return;
      consumed.add(comboRoot);
      const inner = comboRoot.matches('input') ? comboRoot : comboRoot.querySelector('input,[role="combobox"]');
      if (inner) consumed.add(inner);
      const fieldId = ensureId(comboRoot, 'combo-' + index);
      comboRoot.dataset.xiaoyueControlType = 'combobox';
      if (inner) {
        inner.dataset.xiaoyueAgentId = fieldId;
        inner.dataset.xiaoyueControlType = 'combobox';
      }
      const controlsId = (inner && inner.getAttribute('aria-controls')) || comboRoot.getAttribute('aria-controls');
      const listbox = controlsId ? document.getElementById(controlsId) : null;
      const optionNodes = listbox
        ? Array.from(listbox.querySelectorAll('[role="option"],.ant-select-item-option,.el-select-dropdown__item'))
        : [];
      fields.push({
        field_id: fieldId,
        tag: comboRoot.tagName.toLowerCase(),
        input_type: 'combobox',
        label: formLabelFor(comboRoot) || formLabelFor(inner),
        name: (inner && inner.getAttribute('name')) || comboRoot.getAttribute('name') || '',
        placeholder: (inner && inner.getAttribute('placeholder')) || '',
        aria_label: (inner && inner.getAttribute('aria-label')) || comboRoot.getAttribute('aria-label') || '',
        section: sectionFor(comboRoot),
        required: Boolean(
          (inner && (inner.required || inner.getAttribute('aria-required') === 'true'))
          || comboRoot.getAttribute('aria-required') === 'true'
        ),
        options: optionNodes.map((node) => text(node.innerText || node.textContent)).filter(Boolean),
        disabled: Boolean(
          (inner && inner.disabled)
          || comboRoot.getAttribute('aria-disabled') === 'true'
          || comboRoot.classList.contains('ant-select-disabled')
          || comboRoot.classList.contains('is-disabled')
        ),
        readonly: false,
      });
      return;
    }

    const dateRoot = el.closest && el.closest('.ant-picker,.el-date-editor');
    if (tag === 'input' && dateRoot) {
      const fieldId = ensureId(el, 'date-' + index);
      el.dataset.xiaoyueControlType = 'date_picker';
      fields.push({
        field_id: fieldId,
        tag: 'input',
        input_type: 'date_picker',
        label: formLabelFor(dateRoot) || formLabelFor(el),
        name: el.getAttribute('name') || '',
        placeholder: el.getAttribute('placeholder') || '',
        aria_label: el.getAttribute('aria-label') || '',
        section: sectionFor(dateRoot),
        required: Boolean(el.required || el.getAttribute('aria-required') === 'true'),
        options: [],
        disabled: Boolean(el.disabled || dateRoot.classList.contains('ant-picker-disabled') || dateRoot.classList.contains('is-disabled')),
        readonly: false,
      });
      consumed.add(el);
      return;
    }

    const fieldId = ensureId(el, index);
    el.dataset.xiaoyueControlType = nativeType;
    const options = tag === 'select'
      ? Array.from(el.options || []).map((option) => text(option.textContent || option.value)).filter(Boolean)
      : [];
    fields.push({
      field_id: fieldId,
      tag,
      input_type: nativeType,
      label: formLabelFor(el),
      name: el.getAttribute('name') || '',
      placeholder: el.getAttribute('placeholder') || '',
      aria_label: el.getAttribute('aria-label') || '',
      section: sectionFor(el),
      required: Boolean(el.required || el.getAttribute('aria-required') === 'true'),
      options,
      disabled: Boolean(el.disabled),
      readonly: Boolean(el.readOnly),
    });
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
(async () => {{
  const updates = {encoded};
  let filled = 0;
  let skipped = 0;
  const blocked = new Set(['hidden','password','file','submit','button','reset','image','checkbox']);
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const text = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const normalize = (value) => text(value).toLowerCase();
  const isVisible = (el) => Boolean(el && (el.getClientRects().length || el.offsetParent !== null));
  const labelledText = (el) => {{
    if (!el) return '';
    if (el.labels && el.labels.length) return text(Array.from(el.labels).map((x) => x.innerText).join(' '));
    const wrapped = el.closest && el.closest('label');
    return wrapped ? text(wrapped.innerText) : text(el.value);
  }};
  const setNativeValue = (el, value) => {{
    const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const descriptor = Object.getOwnPropertyDescriptor(proto, 'value');
    if (descriptor && descriptor.set) descriptor.set.call(el, value);
    else el.value = value;
  }};
  const dispatchValueEvents = (el) => {{
    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
    el.dispatchEvent(new Event('blur', {{ bubbles: true }}));
  }};

  for (const [fieldId, rawValue] of Object.entries(updates)) {{
    const nodes = Array.from(document.querySelectorAll('[data-xiaoyue-agent-id]'))
      .filter((node) => node.dataset.xiaoyueAgentId === fieldId);
    if (!nodes.length) {{ skipped += 1; continue; }}

    const el = nodes[0];
    const controlType = (
      el.dataset.xiaoyueControlType
      || (el.tagName.toLowerCase() === 'input' ? (el.getAttribute('type') || 'text') : el.tagName.toLowerCase())
    ).toLowerCase();
    const value = Array.isArray(rawValue) ? rawValue.join('；') : String(rawValue ?? '');

    if (blocked.has(controlType)) {{ skipped += 1; continue; }}

    if (controlType === 'radio_group') {{
      const radios = nodes.filter((node) => node.matches && node.matches('input[type="radio"]'));
      const normalized = normalize(value);
      const target = radios.find((radio) =>
        normalize(radio.value) === normalized || normalize(labelledText(radio)) === normalized
      );
      if (!target || target.disabled) {{ skipped += 1; continue; }}
      const clickable = target.closest('label,.ant-radio-wrapper,.el-radio') || target;
      clickable.click();
      target.dispatchEvent(new Event('input', {{ bubbles: true }}));
      target.dispatchEvent(new Event('change', {{ bubbles: true }}));
      filled += 1;
      continue;
    }}

    if (controlType === 'combobox') {{
      const root = el.closest('.ant-select,.el-select') || el;
      const inner = root.matches('input') ? root : root.querySelector('input,[role="combobox"]');
      if (
        (inner && inner.disabled)
        || root.getAttribute('aria-disabled') === 'true'
        || root.classList.contains('ant-select-disabled')
        || root.classList.contains('is-disabled')
      ) {{
        skipped += 1;
        continue;
      }}
      const trigger = root.querySelector('.ant-select-selector,.el-select__wrapper,[role="combobox"],input') || root;
      trigger.dispatchEvent(new MouseEvent('mousedown', {{ bubbles: true, cancelable: true, view: window }}));
      trigger.click();
      await sleep(120);

      const normalized = normalize(value);
      const options = Array.from(document.querySelectorAll(
        '[role="option"],.ant-select-item-option,.el-select-dropdown__item'
      )).filter((option) =>
        isVisible(option)
        && !option.classList.contains('ant-select-item-option-disabled')
        && !option.classList.contains('is-disabled')
        && option.getAttribute('aria-disabled') !== 'true'
      );
      const option = options.find((candidate) =>
        normalize(candidate.innerText || candidate.textContent) === normalized
        || normalize(candidate.getAttribute('data-value')) === normalized
      );
      if (!option) {{ skipped += 1; continue; }}
      option.dispatchEvent(new MouseEvent('mousedown', {{ bubbles: true, cancelable: true, view: window }}));
      option.click();
      filled += 1;
      continue;
    }}

    if (controlType === 'date_picker') {{
      const input = el.matches('input') ? el : el.querySelector('input');
      if (!input || input.disabled) {{ skipped += 1; continue; }}
      input.focus();
      input.click();
      setNativeValue(input, value);
      input.dispatchEvent(new Event('input', {{ bubbles: true }}));
      input.dispatchEvent(new Event('change', {{ bubbles: true }}));
      input.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', code: 'Enter', bubbles: true }}));
      input.dispatchEvent(new KeyboardEvent('keyup', {{ key: 'Enter', code: 'Enter', bubbles: true }}));
      input.blur();
      filled += 1;
      continue;
    }}

    if (el.disabled || el.readOnly) {{ skipped += 1; continue; }}
    const tag = el.tagName.toLowerCase();
    if (tag === 'select') {{
      const normalized = normalize(value);
      const option = Array.from(el.options || []).find((item) =>
        normalize(item.value) === normalized || normalize(item.textContent) === normalized
      );
      if (!option) {{ skipped += 1; continue; }}
      el.value = option.value;
      dispatchValueEvents(el);
      filled += 1;
      continue;
    }}
    if (tag === 'input' || tag === 'textarea') {{
      setNativeValue(el, value);
      dispatchValueEvents(el);
      filled += 1;
      continue;
    }}
    skipped += 1;
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
