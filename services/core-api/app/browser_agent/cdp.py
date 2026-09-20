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
    target_id: str = ""
    websocket_url: str = ""


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
      dom_id: root.getAttribute('id') || members[0].getAttribute('id') || '',
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
        dom_id: (inner && inner.getAttribute('id')) || comboRoot.getAttribute('id') || '',
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
        dom_id: el.getAttribute('id') || '',
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
      dom_id: el.getAttribute('id') || '',
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
            self._bind_page_target(handle)
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

    def _page_targets(self, handle: EdgeHandle) -> list[dict[str, Any]]:
        targets = self._json(handle, "/json/list")
        if not isinstance(targets, list):
            raise BrowserControlError("DevTools target list is invalid")
        return [
            target for target in targets
            if isinstance(target, dict)
            and target.get("type") == "page"
            and isinstance(target.get("webSocketDebuggerUrl"), str)
            and not str(target.get("url", "")).startswith(("devtools://", "chrome://"))
        ]

    def _bind_page_target(self, handle: EdgeHandle) -> str:
        """Bind the session to one CDP page target exactly once.

        Login/OAuth/help popups may create extra tabs. They must never silently
        steal Browser Agent control from the page that this session opened.
        """
        pages = self._page_targets(handle)
        if not pages:
            raise BrowserControlError("未找到可控制的招聘页面，请确认受控浏览器窗口仍然打开。")
        exact = [page for page in pages if str(page.get("url", "")) == handle.entry_url]
        non_blank = [
            page for page in pages
            if str(page.get("url", "")) not in {"", "about:blank", "edge://newtab/"}
        ]
        target = (exact or non_blank or pages)[-1]
        target_id = str(target.get("id") or "")
        websocket_url = str(target.get("webSocketDebuggerUrl") or "")
        if not target_id or not websocket_url:
            raise BrowserControlError("招聘页面缺少可绑定的 DevTools target。")
        handle.target_id = target_id
        handle.websocket_url = websocket_url
        return websocket_url

    def _page_websocket(self, handle: EdgeHandle) -> str:
        if not handle.target_id:
            return self._bind_page_target(handle)

        for target in self._page_targets(handle):
            if str(target.get("id") or "") != handle.target_id:
                continue
            websocket_url = str(target.get("webSocketDebuggerUrl") or "")
            if not websocket_url:
                break
            handle.websocket_url = websocket_url
            return websocket_url

        raise BrowserControlError(
            "原受控招聘页面已关闭或被替换。为避免误操作其他标签页，请重新启动 Browser Agent 会话。"
        )

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
                    dom_id=str(raw.get("dom_id", "")),
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
            target_id=handle.target_id,
        )

    def upload_file(self, handle: EdgeHandle, field_id: str, file_path: Path) -> dict[str, Any]:
        resolved = file_path.resolve()
        if not resolved.is_file():
            raise BrowserControlError("待上传简历文件不存在")

        encoded_field_id = json.dumps(field_id)
        ws_url = self._page_websocket(handle)
        result = self._call_ws(
            ws_url,
            "Runtime.evaluate",
            {
                "expression": (
                    "(() => {"
                    "const id=" + encoded_field_id + ";"
                    "const el=Array.from(document.querySelectorAll('[data-xiaoyue-agent-id]'))"
                    ".find((node)=>node.dataset.xiaoyueAgentId===id"
                    "&& node.tagName==='INPUT' && (node.getAttribute('type')||'').toLowerCase()==='file');"
                    "return el || null;"
                    "})()"
                ),
                "returnByValue": False,
                "awaitPromise": True,
                "userGesture": True,
            },
        )
        if result.get("exceptionDetails"):
            raise BrowserControlError("定位简历上传控件失败")
        remote = result.get("result") or {}
        object_id = remote.get("objectId")
        if not isinstance(object_id, str) or not object_id:
            raise BrowserControlError("未找到受控简历上传控件")

        try:
            self._call_ws(ws_url, "DOM.enable")
            self._call_ws(
                ws_url,
                "DOM.setFileInputFiles",
                {
                    "files": [str(resolved)],
                    "objectId": object_id,
                },
            )
        finally:
            try:
                self._call_ws(ws_url, "Runtime.releaseObject", {"objectId": object_id})
            except Exception:
                pass

        observed = self._evaluate(
            handle,
            (
                "(() => {"
                "const id=" + encoded_field_id + ";"
                "const el=Array.from(document.querySelectorAll('[data-xiaoyue-agent-id]'))"
                ".find((node)=>node.dataset.xiaoyueAgentId===id"
                "&& node.tagName==='INPUT' && (node.getAttribute('type')||'').toLowerCase()==='file');"
                "if(!el || !el.files || el.files.length!==1) return null;"
                "const file=el.files[0];"
                "return {filename:file.name,size:file.size,type:file.type};"
                "})()"
            ),
        )
        if not isinstance(observed, dict):
            raise BrowserControlError("浏览器未确认简历文件已写入上传控件")
        filename = observed.get("filename")
        if filename != resolved.name:
            raise BrowserControlError("浏览器回读的简历文件名与所选版本不一致")
        return {
            "filename": str(filename),
            "size": int(observed.get("size", 0) or 0),
            "type": str(observed.get("type", "") or ""),
        }

    def fill(self, handle: EdgeHandle, values: dict[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(values, ensure_ascii=False)
        script = r"""
(async () => {
  const updates = __UPDATES__;
  let filled = 0;
  let skipped = 0;
  const actionStates = {};
  const blocked = new Set(['hidden','password','file','submit','button','reset','image','checkbox']);
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const text = (value) => String(value ?? '').replace(/\s+/g, ' ').trim();
  const normalize = (value) => text(value).toLowerCase();
  const isVisible = (el) => Boolean(el && (el.getClientRects().length || el.offsetParent !== null));
  const nodesFor = (fieldId) => Array.from(document.querySelectorAll('[data-xiaoyue-agent-id]'))
    .filter((node) => node.dataset.xiaoyueAgentId === fieldId);
  const controlTypeFor = (el) => (
    el.dataset.xiaoyueControlType
    || (el.tagName.toLowerCase() === 'input' ? (el.getAttribute('type') || 'text') : el.tagName.toLowerCase())
  ).toLowerCase();
  const labelledText = (el) => {
    if (!el) return '';
    if (el.labels && el.labels.length) return text(Array.from(el.labels).map((x) => x.innerText).join(' '));
    const wrapped = el.closest && el.closest('label');
    return wrapped ? text(wrapped.innerText) : text(el.value);
  };
  const setNativeValue = (el, value) => {
    const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const descriptor = Object.getOwnPropertyDescriptor(proto, 'value');
    if (descriptor && descriptor.set) descriptor.set.call(el, value);
    else el.value = value;
  };
  const dispatchValueEvents = (el) => {
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    el.dispatchEvent(new Event('blur', { bubbles: true }));
  };
  const validationMessage = (el) => {
    if (!el) return '';
    const ariaInvalid = el.getAttribute && el.getAttribute('aria-invalid') === 'true';
    const container = el.closest && el.closest(
      '.ant-form-item,.el-form-item,.form-item,.form-field,.field,[class*="form-item"],[class*="formItem"]'
    );
    const errorNode = container && container.querySelector(
      '.ant-form-item-explain-error,.el-form-item__error,[role="alert"]'
    );
    const message = errorNode && isVisible(errorNode) ? text(errorNode.innerText || errorNode.textContent) : '';
    return message || (ariaInvalid ? 'aria-invalid' : '');
  };
  const readObserved = (nodes, controlType) => {
    if (!nodes.length) return null;
    const el = nodes[0];

    if (controlType === 'radio_group') {
      const checked = nodes.find((node) => node.matches && node.matches('input[type="radio"]:checked'));
      return checked ? (labelledText(checked) || text(checked.value)) : '';
    }

    if (controlType === 'combobox') {
      const root = el.closest('.ant-select,.el-select') || el;
      const selected = root.querySelector(
        '.ant-select-selection-item,.el-select__selected-item,.el-select__selection .el-tag'
      );
      if (selected && text(selected.innerText || selected.textContent)) {
        return text(selected.innerText || selected.textContent);
      }
      const inner = root.matches('input') ? root : root.querySelector('input,[role="combobox"]');
      return inner ? text(inner.value) : null;
    }

    if (controlType === 'date_picker') {
      const input = el.matches('input') ? el : el.querySelector('input');
      return input ? text(input.value) : null;
    }

    const tag = el.tagName.toLowerCase();
    if (tag === 'select') {
      const selected = el.options && el.selectedIndex >= 0 ? el.options[el.selectedIndex] : null;
      return selected ? text(selected.textContent || selected.value) : text(el.value);
    }
    if (tag === 'input' || tag === 'textarea') return text(el.value);
    return null;
  };

  for (const [fieldId, rawValue] of Object.entries(updates)) {
    const nodes = nodesFor(fieldId);
    const value = Array.isArray(rawValue) ? rawValue.join('；') : String(rawValue ?? '');
    if (!nodes.length) {
      actionStates[fieldId] = { status: 'SKIPPED', reason: 'FIELD_NOT_FOUND', requested: value };
      skipped += 1;
      continue;
    }

    const el = nodes[0];
    const controlType = controlTypeFor(el);
    if (blocked.has(controlType)) {
      actionStates[fieldId] = { status: 'SKIPPED', reason: 'CONTROL_BLOCKED', requested: value };
      skipped += 1;
      continue;
    }

    if (controlType === 'radio_group') {
      const radios = nodes.filter((node) => node.matches && node.matches('input[type="radio"]'));
      const normalized = normalize(value);
      const target = radios.find((radio) =>
        normalize(radio.value) === normalized || normalize(labelledText(radio)) === normalized
      );
      if (!target || target.disabled) {
        actionStates[fieldId] = { status: 'SKIPPED', reason: 'OPTION_NOT_FOUND', requested: value };
        skipped += 1;
        continue;
      }
      const clickable = target.closest('label,.ant-radio-wrapper,.el-radio') || target;
      clickable.click();
      target.dispatchEvent(new Event('input', { bubbles: true }));
      target.dispatchEvent(new Event('change', { bubbles: true }));
      actionStates[fieldId] = { status: 'ATTEMPTED', requested: value };
      filled += 1;
      continue;
    }

    if (controlType === 'combobox') {
      const root = el.closest('.ant-select,.el-select') || el;
      const inner = root.matches('input') ? root : root.querySelector('input,[role="combobox"]');
      if (
        (inner && inner.disabled)
        || root.getAttribute('aria-disabled') === 'true'
        || root.classList.contains('ant-select-disabled')
        || root.classList.contains('is-disabled')
      ) {
        actionStates[fieldId] = { status: 'SKIPPED', reason: 'CONTROL_DISABLED', requested: value };
        skipped += 1;
        continue;
      }
      const trigger = root.querySelector('.ant-select-selector,.el-select__wrapper,[role="combobox"],input') || root;
      trigger.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
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
      if (!option) {
        actionStates[fieldId] = { status: 'SKIPPED', reason: 'OPTION_NOT_FOUND', requested: value };
        skipped += 1;
        continue;
      }
      option.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
      option.click();
      actionStates[fieldId] = { status: 'ATTEMPTED', requested: value };
      filled += 1;
      continue;
    }

    if (controlType === 'date_picker') {
      const input = el.matches('input') ? el : el.querySelector('input');
      if (!input || input.disabled) {
        actionStates[fieldId] = { status: 'SKIPPED', reason: 'CONTROL_DISABLED', requested: value };
        skipped += 1;
        continue;
      }
      input.focus();
      input.click();
      setNativeValue(input, value);
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));
      input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true }));
      input.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', bubbles: true }));
      input.blur();
      actionStates[fieldId] = { status: 'ATTEMPTED', requested: value };
      filled += 1;
      continue;
    }

    if (el.disabled || el.readOnly) {
      actionStates[fieldId] = { status: 'SKIPPED', reason: 'CONTROL_DISABLED', requested: value };
      skipped += 1;
      continue;
    }
    const tag = el.tagName.toLowerCase();
    if (tag === 'select') {
      const normalized = normalize(value);
      const option = Array.from(el.options || []).find((item) =>
        normalize(item.value) === normalized || normalize(item.textContent) === normalized
      );
      if (!option) {
        actionStates[fieldId] = { status: 'SKIPPED', reason: 'OPTION_NOT_FOUND', requested: value };
        skipped += 1;
        continue;
      }
      el.value = option.value;
      dispatchValueEvents(el);
      actionStates[fieldId] = { status: 'ATTEMPTED', requested: value };
      filled += 1;
      continue;
    }
    if (tag === 'input' || tag === 'textarea') {
      setNativeValue(el, value);
      dispatchValueEvents(el);
      actionStates[fieldId] = { status: 'ATTEMPTED', requested: value };
      filled += 1;
      continue;
    }
    actionStates[fieldId] = { status: 'SKIPPED', reason: 'UNSUPPORTED_CONTROL', requested: value };
    skipped += 1;
  }

  // Give React/Vue/ATS validation handlers a chance to reconcile or reject the
  // value before deciding whether the fill really succeeded.
  await sleep(180);

  const results = [];
  let verified = 0;
  let failed = 0;
  let uncertain = 0;
  for (const [fieldId, rawValue] of Object.entries(updates)) {
    const requested = Array.isArray(rawValue) ? rawValue.join('；') : String(rawValue ?? '');
    const action = actionStates[fieldId];
    if (!action || action.status === 'SKIPPED') {
      results.push({
        field_id: fieldId,
        requested,
        observed: null,
        status: 'SKIPPED',
        reason: action ? action.reason : 'NOT_ATTEMPTED',
      });
      continue;
    }

    const nodes = nodesFor(fieldId);
    if (!nodes.length) {
      failed += 1;
      results.push({
        field_id: fieldId,
        requested,
        observed: null,
        status: 'FAILED',
        reason: 'FIELD_DISAPPEARED',
      });
      continue;
    }

    const el = nodes[0];
    const controlType = controlTypeFor(el);
    const observed = readObserved(nodes, controlType);
    const error = validationMessage(el);
    if (error) {
      failed += 1;
      results.push({
        field_id: fieldId,
        requested,
        observed,
        status: 'FAILED',
        reason: 'PAGE_VALIDATION_ERROR',
      });
      continue;
    }

    if (observed === null) {
      uncertain += 1;
      results.push({
        field_id: fieldId,
        requested,
        observed: null,
        status: 'UNCERTAIN',
        reason: 'READBACK_UNAVAILABLE',
      });
      continue;
    }

    if (normalize(observed) === normalize(requested)) {
      verified += 1;
      results.push({
        field_id: fieldId,
        requested,
        observed,
        status: 'VERIFIED',
        reason: 'READBACK_MATCH',
      });
    } else {
      failed += 1;
      results.push({
        field_id: fieldId,
        requested,
        observed,
        status: 'FAILED',
        reason: observed ? 'VALUE_MISMATCH' : 'VALUE_REVERTED',
      });
    }
  }

  return {
    filled_count: filled,
    skipped_count: skipped,
    verified_count: verified,
    failed_count: failed,
    uncertain_count: uncertain,
    results,
  };
})()
""".replace("__UPDATES__", encoded)
        payload = self._evaluate(handle, script)
        if not isinstance(payload, dict):
            raise BrowserControlError("页面填写结果无效")

        raw_results = payload.get("results")
        results = raw_results if isinstance(raw_results, list) else []
        return {
            "filled_count": int(payload.get("filled_count", 0)),
            "skipped_count": int(payload.get("skipped_count", 0)),
            "verified_count": int(payload.get("verified_count", 0)),
            "failed_count": int(payload.get("failed_count", 0)),
            "uncertain_count": int(payload.get("uncertain_count", 0)),
            "results": [item for item in results if isinstance(item, dict)],
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
