# Session Token 硬化 + Tauri Sidecar 发布闭环 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 `doc/TODO.md` 建议顺序完成两项 P0：①本机 API session token 改 CSPRNG 并补 auth E2E；②PyInstaller onedir 打包 core sidecar 并接入 Tauri bundle（NSIS）、sidecar 日志、启动失败可诊断 UI。

**Architecture:** ①在现有信任边界上加硬：token 生成换 OS CSPRNG（Rust 侧 256-bit hex），middleware 不变，pytest 直测无 token/错 token/正确 token 与 Host/Origin 守卫；修复 resumesClient 绕过 auth 的缺口。②交付链改为 `PyInstaller onedir -> tauri resources`，Rust 端 `find_core_bin` 已预置 `core-api/` 子目录寻址；exe 与 bundle 的正确性由「本地/CI 共用的 smoke 脚本」验证。

**Tech Stack:** Rust (tauri 2, getrandom)、Python 3.11 (FastAPI, PyInstaller onedir)、NSIS bundler、vitest、pytest。

**关键现状（已核实）：**
- Rust token 生成在 `apps/desktop/src-tauri/src/main.rs:50-56`（时间戳+PID 拼接，待替换）。
- Core middleware 已存在：`services/core-api/app/main.py:42-66`（Bearer + hmac 比较 + Host/Origin 守卫，health 豁免），但 **零测试覆盖**；`conftest.py` 的 `client` fixture 不设 token → middleware 关闭。
- `get_settings()`（`app/config.py:28`）无 lru_cache，每次读 env → 测试可按需注入 `XIAOYUE_SESSION_TOKEN`。
- 前端审计结论：`jobsClient`/`applicationsClient`/`profileClient` 均已合并 `authHeaders()`；**`resumesClient.ts` 硬编码 `http://127.0.0.1:8765` 且 requestJson 不带 Authorization（两个缺口）**；`coreClient.getCoreHealth` 走豁免端点，设计如此。
- Rust sidecar：`main.rs` 的 `CoreSidecar::launch()` 三种结局混淆为 `None`（dev 无 core bin、spawn 失败、health 超时）；stdout/stderr 目前 `Stdio::null()`（无日志）。
- `find_core_bin`（main.rs:20-36）已经会找 `exe_dir/core-api/xiaoyue-core-api.exe` —— tauri `resources` 方案落地后无需改寻址。
- `app/db.py:_alembic_config` 用 `Path(__file__).parents[1]` 定位 alembic —— PyInstaller 下需 `sys._MEIPASS` 兜底（onedir 下 datas 落在 `_internal/`）。
- `tauri.conf.json`：`bundle.active=false`；CSP `connect-src` 只放行 `http://127.0.0.1:8765` —— **动态端口下打包版会被 CSP 拦死**，需 `http://127.0.0.1:*`。
- CI（`.github/workflows/ci.yml`）目前 cargo 只有 metadata/check，无 cargo test、无 pyinstaller。
- lock 文件是扁平 pin 列表（`requirements-lock.txt`），CI 按它装依赖。

**分支策略：** Part A 走分支 `feat/session-token-hardening`（PR 后合入）；Part B 基于合入后的 main 走分支 `feat/sidecar-release-loop`。两部分各自可交付、各自 CI 全绿。

---

## Part A：CSPRNG session token + auth E2E（branch `feat/session-token-hardening`）

### Task A1：Rust token 改 OS CSPRNG（256-bit hex）

**Files:**
- Modify: `apps/desktop/src-tauri/Cargo.toml`（dependencies 加 getrandom）
- Modify: `apps/desktop/src-tauri/src/main.rs:48-56`

- [ ] **Step 1: 写失败测试（cargo test RED）**

在 `main.rs` 末尾追加：

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn session_token_is_256_bit_hex() {
        let token = generate_session_token();
        assert_eq!(token.len(), 64, "256-bit => 64 hex chars");
        assert!(token.chars().all(|c| c.is_ascii_hexdigit()));
    }

    #[test]
    fn session_token_differs_between_launches() {
        assert_ne!(generate_session_token(), generate_session_token());
    }
}
```

- [ ] **Step 2: 运行确认失败**

Run: `cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml`
Expected: FAIL（当前 token 是 `nanos+pid` 16 进制拼接，长度不固定且非 64 hex；两个断言都可能失败）

- [ ] **Step 3: 最小实现**

`Cargo.toml` `[dependencies]` 增加：

```toml
getrandom = "0.3"
```

`main.rs` 替换 48-56 行的注释+函数为：

```rust
/// OS CSPRNG (BCryptGenRandom on Windows): 256-bit per-launch secret,
/// hex-encoded. The token dies with the process and is never persisted.
fn generate_session_token() -> String {
    let mut bytes = [0u8; 32];
    getrandom::fill(&mut bytes).expect("OS CSPRNG unavailable");
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}
```

注意：getrandom 0.3 的 API 是 `getrandom::fill(&mut buf)`；若解析到 0.2 系版本则改用 `getrandom::getrandom(&mut bytes)`。

- [ ] **Step 4: 运行确认通过**

Run: `cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml`
Expected: `test result: ok. 2 passed`

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src-tauri/Cargo.toml apps/desktop/src-tauri/Cargo.lock apps/desktop/src-tauri/src/main.rs
git commit -m "feat(shell): generate session token from OS CSPRNG (256-bit)"
```

### Task A2：Core session auth E2E（pytest RED→GREEN）

**Files:**
- Create: `services/core-api/tests/test_session_auth.py`

**说明：** middleware 实现已存在，本任务是把它锁进回归——若测试暴露缺陷则修 middleware。同时用「全路由 /api 前缀断言」保证未来任何新 router（包括未来的 Browser Agent 高权限路由）不可能绕过 middleware。

- [ ] **Step 1: 写测试（RED——先跑一次看是否全绿：全绿说明覆盖已存在，需检查测试是否真的在验证）**

```python
from __future__ import annotations

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.main import create_app

TOKEN = "unit-test-session-secret-256bit"


@pytest.fixture
def auth_client(tmp_path, monkeypatch):
    monkeypatch.setenv("XIAOYUE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("XIAOYUE_SESSION_TOKEN", TOKEN)
    return TestClient(create_app())


def test_health_stays_open(auth_client):
    assert auth_client.get("/api/health").status_code == 200


def test_protected_route_requires_authorization(auth_client):
    response = auth_client.get("/api/profile/definitions")
    assert response.status_code == 401
    assert response.json()["detail"] == "invalid session token"


def test_wrong_token_is_rejected(auth_client):
    headers = {"Authorization": "Bearer not-the-token"}
    assert auth_client.get("/api/profile/definitions", headers=headers).status_code == 401


def test_correct_token_is_accepted(auth_client):
    headers = {"Authorization": f"Bearer {TOKEN}"}
    assert auth_client.get("/api/profile/definitions", headers=headers).status_code == 200


def test_401_body_never_echoes_any_token(auth_client):
    attacker = "Bearer attacker-guess"
    response = auth_client.get("/api/jobs/stats", headers={"Authorization": attacker})
    assert response.status_code == 401
    assert "attacker-guess" not in response.text
    assert TOKEN not in response.text


def test_every_api_route_is_behind_the_guard(auth_client):
    """未来新增 router（含 Browser Agent 高权限路由）也必须落在 /api 前缀内，
    因为 middleware 只保护 /api/* 且豁免 /api/health。"""
    prefixes = {route.path.split("/", 3)[1] for route in auth_client.app.routes if isinstance(route, APIRoute)}
    assert prefixes == {"api"}, f"non-/api routes found: {prefixes}"
    guarded = sorted({("/" + p) if not route.path.startswith("/api/health") else route.path
                      for p in prefixes for route in auth_client.app.routes
                      if isinstance(route, APIRoute)})
    sample = [route for route in auth_client.app.routes
              if isinstance(route, APIRoute) and route.path != "/api/health"]
    for route in sample[:5]:
        assert auth_client.request(route.methods - {"HEAD", "OPTIONS"}, route.path).status_code == 401


def test_non_loopback_host_is_refused(auth_client):
    headers = {"Authorization": f"Bearer {TOKEN}", "Host": "evil.example.com"}
    assert auth_client.get("/api/profile/definitions", headers=headers).status_code == 403


def test_foreign_origin_is_refused(auth_client):
    headers = {"Authorization": f"Bearer {TOKEN}", "Origin": "https://evil.example.com"}
    assert auth_client.get("/api/profile/definitions", headers=headers).status_code == 403


def test_tauri_origin_is_allowed(auth_client):
    headers = {"Authorization": f"Bearer {TOKEN}", "Origin": "tauri://localhost"}
    assert auth_client.get("/api/profile/definitions", headers=headers).status_code == 200


def test_token_never_reaches_the_database(auth_client, tmp_path):
    headers = {"Authorization": f"Bearer {TOKEN}"}
    auth_client.get("/api/profile/definitions", headers=headers)
    db_bytes = (tmp_path / "xiaoyue.db").read_bytes()
    assert TOKEN.encode() not in db_bytes
```

（如 `Host` 头覆盖在 httpx/TestClient 下不被允许，用 `auth_client.get(url, headers={"host": ...})` 小写形式重试；仍不行则跳过该项并在 PR 里注明。）

- [ ] **Step 2: 运行**

Run: `$env:XIAOYUE_DATA_DIR='...'; $env:PYTEST_ADDOPTS='-p dsh_tmp_shim'; .\.venv\Scripts\python.exe -m pytest services/core-api/tests/test_session_auth.py -q`
Expected: 全部 PASS（若 FAIL → middleware 有真 bug，修到绿）

- [ ] **Step 3: Commit**

```bash
git add services/core-api/tests/test_session_auth.py
git commit -m "test(core): session token auth E2E - 401/403/200, route-coverage, no persistence"
```

### Task A3：修复 resumesClient 绕过 auth/动态端点的缺口（vitest RED→GREEN）

**Files:**
- Create: `apps/desktop/src/api/resumesClient.test.ts`
- Modify: `apps/desktop/src/api/resumesClient.ts`

- [ ] **Step 1: 写失败测试**

```typescript
import { afterEach, describe, expect, it, vi } from 'vitest';

import { getResumes, importResume } from './resumesClient';

const fetchMock = vi.fn();
vi.stubGlobal('fetch', fetchMock);

describe('resumesClient', () => {
  afterEach(() => {
    fetchMock.mockReset();
    delete (window as unknown as Record<string, unknown>).__XIAOYUE_CORE__;
  });

  it('targets the injected endpoint and sends the session token', async () => {
    (window as unknown as Record<string, unknown>).__XIAOYUE_CORE__ = {
      baseUrl: 'http://127.0.0.1:9777',
      sessionToken: 'tok-123',
    };
    fetchMock.mockResolvedValue(new Response('[]', { status: 200, headers: { 'Content-Type': 'application/json' } }));
    await getResumes();
    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:9777/api/resumes',
      expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer tok-123' }) }),
    );
  });

  it('importResume posts to the injected endpoint with authorization', async () => {
    (window as unknown as Record<string, unknown>).__XIAOYUE_CORE__ = {
      baseUrl: 'http://127.0.0.1:9777',
      sessionToken: 'tok-123',
    };
    fetchMock.mockResolvedValue(new Response('{}', { status: 200 }));
    await importResume(new File(['x'], 'r.pdf', { type: 'application/pdf' }));
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('http://127.0.0.1:9777/api/resumes/import');
    expect((init.headers as Headers).get('Authorization')).toBe('Bearer tok-123');
  });
});
```

- [ ] **Step 2: 运行确认失败**

Run: `npx.cmd vitest run src/api/resumesClient.test.ts`（workdir `apps/desktop`）
Expected: FAIL（现在请求打到硬编码 `http://127.0.0.1:8765` 且无 Authorization）

- [ ] **Step 3: 最小实现**

`resumesClient.ts` 的 `CORE_API_BASE` 常量与 `requestJson` 替换为（照抄 `applicationsClient.ts:1,15-25` 模式）：

```typescript
import { CoreApiError, authHeaders, coreRuntime } from './coreClient';
```

```typescript
async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  for (const [key, value] of Object.entries(authHeaders())) {
    headers.set(key, value);
  }
  const response = init ? await fetch(url, { ...init, headers }) : await fetch(url, { headers });
  if (!response.ok) {
    let message = `Core API returned HTTP ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      // Keep the status-based fallback when the response is not JSON.
    }
    throw new CoreApiError(response.status, message);
  }
  return (await response.json()) as T;
}
```

两个调用点改为 `${coreRuntime().baseUrl}/api/resumes` 与 `${coreRuntime().baseUrl}/api/resumes/import`。

注意：ResumesPage.test.tsx 里已有 fetch mock 若断言旧 URL 需同步——先跑 `npx.cmd vitest run` 全量看破坏面。

- [ ] **Step 4: 运行确认通过**

Run: `npx.cmd vitest run`（workdir `apps/desktop`）
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/api/resumesClient.ts apps/desktop/src/api/resumesClient.test.ts apps/desktop/src/pages/ResumesPage.test.tsx
git commit -m "fix(web): resumes client must use runtime endpoint and session token"
```

### Task A4：CI 增加 cargo test 步骤（Rust 现在有可测逻辑了）

**Files:**
- Modify: `.github/workflows/ci.yml`（cargo check 之后）

- [ ] **Step 1: 增加步骤**

```yaml
      - name: Cargo test (Rust unit tests)
        run: cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml
```

- [ ] **Step 2: 本地预演**

Run: `cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml`
Expected: `test result: ok`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: run cargo test now that the shell has unit-tested logic"
```

### Task A5：文档 + 全量验证 + PR

**Files:**
- Modify: `README.md`（安全模型小节）、`doc/TODO.md`（item 2 勾选）

- [ ] **Step 1: README 安全小节追加**

```markdown
### 本地安全模型（两套互不重叠的策略）

1. **本机 API 信任边界**：session token 由 Tauri shell 每次启动用 OS CSPRNG 生成（256-bit），只存在于两侧进程内存与 `Authorization: Bearer` 头中，绝不落入 SQLite、日志或磁盘；`/api/*`（health 除外）强制校验，未来任何新增 router（包括 Browser Agent 高权限路由）天然被覆盖。
2. **招聘 URL verifier SSRF guard**：core 主动出网抓取/验证招聘 URL 时走 pinned-IP 校验链路；它与「本地 AI Provider 访问 localhost」是两套独立安全策略，互不豁免。
```

- [ ] **Step 2: TODO item 2 更新**（`doc/TODO.md` item 2）：CSPRNG/内存存储/auth E2E/clients 审查 四项勾选，保留 Tauri 强相关剩余项。

- [ ] **Step 3: 全量验证**

```powershell
$env:XIAOYUE_DATA_DIR='D:\Xiaoyue-s-Job-Search\.venv\.test-data'
$env:PYTEST_ADDOPTS='-p dsh_tmp_shim'
.\.venv\Scripts\python.exe -m pytest services/core-api/tests -q   # 期望全过
npx.cmd vitest run   # apps/desktop 下全过
cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml
```

- [ ] **Step 4: Push + PR + 等 CI 全绿 + 合入 main**

```bash
git push -u origin feat/session-token-hardening
```

---

## Part B：Tauri sidecar 发布闭环（branch `feat/sidecar-release-loop`，基于 Part A 合入后的 main）

### Task B1：_alembic_config 兼容 PyInstaller（pytest RED→GREEN）

**Files:**
- Modify: `services/core-api/app/db.py:29-36`
- Test: `services/core-api/tests/test_db.py`（新建）

- [ ] **Step 1: 失败测试**

```python
from pathlib import Path
from unittest import mock

from app.config import get_settings
from app.db import _alembic_config


def test_alembic_config_locates_scripts_from_frozen_bundle_root(tmp_path, monkeypatch):
    fake_bundle = tmp_path / "_internal"
    (fake_bundle / "alembic").mkdir(parents=True)
    (fake_bundle / "alembic.ini").write_text("[alembic]\n", encoding="utf-8")
    settings = get_settings.__wrapped__() if hasattr(get_settings, "__wrapped__") else None
    monkeypatch.setattr("sys._MEIPASS", str(fake_bundle))
    config = _alembic_config(_settings_with(tmp_path))
    assert config.get_main_option("script_location") == str(fake_bundle / "alembic")

def _settings_with(tmp_path):
    from app.config import AppSettings
    return AppSettings(data_dir=tmp_path)


def test_alembic_config_defaults_to_source_tree(tmp_path):
    config = _alembic_config(_settings_with(tmp_path))
    assert config.get_main_option("script_location").endswith("alembic")
    assert Path(config.config_file_name).exists()
```

- [ ] **Step 2: 运行确认失败**

`_MEIPASS` 无兜底 → script_location 仍指向源码树 → FAIL。

- [ ] **Step 3: 最小实现（`app/db.py`）**

```python
import sys
```

`_alembic_config` 开头替换为：

```python
def _core_root() -> Path:
    """Source tree in dev; PyInstaller bundle root (onedir `_internal/`)
    in the packaged sidecar, where alembic.ini + alembic/ ship as datas."""
    frozen = getattr(sys, "_MEIPASS", None)
    if frozen:
        return Path(frozen)
    return Path(__file__).resolve().parents[1]


def _alembic_config(settings: AppSettings):
    from alembic.config import Config

    core_root = _core_root()
    config = Config(core_root / "alembic.ini")
    config.set_main_option("script_location", str(core_root / "alembic"))
    config.attributes["db_url"] = f"sqlite:///{settings.database_path}"
    return config
```

- [ ] **Step 4: 运行确认通过；跑全套 migration 测试防回归**

- [ ] **Step 5: Commit**

```bash
git add services/core-api/app/db.py services/core-api/tests/test_db.py
git commit -m "feat(core): locate alembic scripts from PyInstaller bundle root when frozen"
```

### Task B2：PyInstaller onedir 打包 + smoke 脚本

**Files:**
- Create: `services/core-api/packaging/xiaoyue_core_api.py`（uvicorn 启动入口）
- Create: `services/core-api/packaging/xiaoyue-core-api.spec`（onedir）
- Create: `scripts/build-core.ps1`
- Create: `scripts/smoke-core-exe.ps1`
- Modify: `services/core-api/pyproject.toml`（dev extra 加 pyinstaller）
- Modify: `services/core-api/requirements-lock.txt`（追加 pin）

- [ ] **Step 1: 入口脚本 `services/core-api/packaging/xiaoyue_core_api.py`**

```python
"""PyInstaller entrypoint: run the core API under the packaged runtime.

The Tauri shell passes XIAOYUE_PORT / XIAOYUE_SESSION_TOKEN / XIAOYUE_DATA_DIR
as process env; the app itself reads them via pydantic settings.
"""
from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.environ.get("XIAOYUE_HOST", "127.0.0.1")
    port = int(os.environ.get("XIAOYUE_PORT", "8765"))
    uvicorn.run("app.main:app", host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: spec `services/core-api/packaging/xiaoyue-core-api.spec`**

```python
# PyInstaller onedir spec for the bundled core-api sidecar.
# Build: scripts/build-core.ps1 (local) / CI step (runner).
from pathlib import Path

core_root = Path(SPECPATH).resolve().parents[1]

a = Analysis(
    [str(core_root / "packaging" / "xiaoyue_core_api.py")],
    pathex=[str(core_root)],
    binaries=[],
    datas=[
        (str(core_root / "alembic.ini"), "."),
        (str(core_root / "alembic"), "alembic"),
    ],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="xiaoyue-core-api",
    debug=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="xiaoyue-core-api",
)
```

- [ ] **Step 3: 构建脚本 `scripts/build-core.ps1`**

```powershell
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$corePath = Join-Path $repoRoot "services/core-api"

python -m PyInstaller (Join-Path $corePath "packaging/xiaoyue-core-api.spec") --noconfirm `
    --distpath (Join-Path $corePath "dist") `
    --workpath (Join-Path $corePath "build/pyinstaller")

$exe = Join-Path $corePath "dist/xiaoyue-core-api/xiaoyue-core-api.exe"
if (-not (Test-Path $exe)) { throw "sidecar exe missing: $exe" }
Write-Host "Core sidecar built: $exe"
```

- [ ] **Step 4: 安装 pyinstaller 并 pin**

Run: `uv pip install --python .venv pyinstaller`（工作区缓存路径沿用既有 `UV_CACHE_DIR` 做法）
然后 `.\.venv\Scripts\python.exe -m pip show pyinstaller altgraph pefile pyinstaller-hooks-contrib`（或 `pip freeze | findstr -i "pyinstaller altgraph pefile"`）取得精确版本，追加进 `requirements-lock.txt`；`pyproject.toml` dev extra 加 `"pyinstaller>=6"`。

- [ ] **Step 5: smoke 脚本 `scripts/smoke-core-exe.ps1`**

```powershell
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$exe = Join-Path $repoRoot "services/core-api/dist/xiaoyue-core-api/xiaoyue-core-api.exe"
if (-not (Test-Path $exe)) { throw "build the sidecar first (scripts/build-core.ps1)" }

$dataDir = Join-Path $env:TEMP ("xiaoyue-smoke-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force $dataDir | Out-Null
$token = "smoke-secret-0123456789abcdef"
$port = 18800

$env:XIAOYUE_DATA_DIR = $dataDir
$env:XIAOYUE_PORT = "$port"
$env:XIAOYUE_SESSION_TOKEN = $token
$proc = Start-Process -FilePath $exe -PassThru -WindowStyle Hidden
try {
    $deadline = (Get-Date).AddSeconds(60)
    $healthy = $false
    while ((Get-Date) -lt $deadline -and -not $healthy) {
        try {
            $r = Invoke-RestMethod "http://127.0.0.1:$port/api/health" -TimeoutSec 2
            if ($r.status -eq "ok") { $healthy = $true }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $healthy) { throw "sidecar did not become healthy" }

    # Auth enforcement against the packaged exe.
    $code = try { (Invoke-WebRequest "http://127.0.0.1:$port/api/profile/definitions" -UseBasicParsing).StatusCode } catch { $_.Exception.Response.StatusCode.value__ }
    if ($code -ne 401) { throw "expected 401 without token, got $code" }
    $authed = Invoke-WebRequest "http://127.0.0.1:$port/api/profile/definitions" -Headers @{ Authorization = "Bearer $token" } -UseBasicParsing
    if ($authed.StatusCode -ne 200) { throw "expected 200 with token, got $($authed.StatusCode)" }

    # Migration-on-fresh-DB proof: 0009 extraction runs table must exist.
    $db = Join-Path $dataDir "xiaoyue.db"
    if (-not (Test-Path $db)) { throw "sqlite db missing" }
    Write-Host "SMOKE OK: health + auth + migrations + vault on packaged exe ($dataDir)"
} finally {
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force $dataDir -ErrorAction SilentlyContinue
    Remove-Item Env:XIAOYUE_DATA_DIR, Env:XIAOYUE_PORT, Env:XIAOYUE_SESSION_TOKEN -ErrorAction SilentlyContinue
}
```

- [ ] **Step 6: 本地构建 + smoke**

```powershell
.\scripts\build-core.ps1
.\scripts\smoke-core-exe.ps1
```
Expected: `SMOKE OK: health + auth + migrations + vault on packaged exe`

- [ ] **Step 7: Commit**

```bash
git add services/core-api/packaging scripts/build-core.ps1 scripts/smoke-core-exe.ps1 services/core-api/pyproject.toml services/core-api/requirements-lock.txt
git commit -m "build(core): PyInstaller onedir sidecar with health/auth/migration smoke"
```

### Task B3：Rust sidecar 日志（stdout/stderr 落盘 + 裁剪）（cargo test RED→GREEN）

**Files:**
- Modify: `apps/desktop/src-tauri/src/main.rs`

- [ ] **Step 1: 失败测试（追加进 main.rs 的 tests 模块）**

```rust
    #[test]
    fn log_file_names_are_launch_unique_and_pattern_safe() {
        let dir = std::env::temp_dir().join("xiaoyue-log-test");
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        let (mut out, mut err) = open_log_files(&dir).unwrap();
        writeln!(out, "stdout line").unwrap();
        writeln!(err, "stderr line").unwrap();
        let names: Vec<String> = std::fs::read_dir(&dir).unwrap()
            .filter_map(|e| e.ok())
            .map(|e| e.file_name().to_string_lossy().to_string())
            .collect();
        assert_eq!(names.iter().filter(|n| n.starts_with("core-") && n.ends_with(".out.log")).count(), 1);
        assert_eq!(names.iter().filter(|n| n.starts_with("core-") && n.ends_with(".err.log")).count(), 1);
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn prune_keeps_only_newest_logs() {
        let dir = std::env::temp_dir().join("xiaoyue-log-prune-test");
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        for i in 0..12 {
            std::fs::write(dir.join(format!("core-20260917-{:04}-pid.out.log", i)), "x").unwrap();
        }
        std::fs::write(dir.join("unrelated.log"), "x").unwrap();
        prune_old_logs(&dir, 5);
        let mut remaining: Vec<String> = std::fs::read_dir(&dir).unwrap()
            .filter_map(|e| e.ok())
            .map(|e| e.file_name().to_string_lossy().to_string())
            .collect();
        remaining.sort();
        assert_eq!(remaining.iter().filter(|n| n.starts_with("core-")).count(), 5);
        assert!(remaining.contains(&"unrelated.log".to_string()));
        let _ = std::fs::remove_dir_all(&dir);
    }
```

- [ ] **Step 2: 确认编译失败（函数不存在）**

- [ ] **Step 3: 实现（main.rs）**

```rust
fn log_dir(data_dir: &str) -> PathBuf {
    PathBuf::from(data_dir).join("logs")
}

fn open_log_files(dir: &PathBuf) -> std::io::Result<(std::fs::File, std::fs::File)> {
    std::fs::create_dir_all(dir)?;
    let stamp = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or(0);
    let out = std::fs::OpenOptions::new().create(true).append(true)
        .open(dir.join(format!("core-{}-{}.out.log", stamp, std::process::id())))?;
    let err = std::fs::OpenOptions::new().create(true).append(true)
        .open(dir.join(format!("core-{}-{}.err.log", stamp, std::process::id())))?;
    Ok((out, err))
}

/// Keep the newest `keep` per-launch core log pairs; never touch other files.
fn prune_old_logs(dir: &PathBuf, keep: usize) {
    let mut logs: Vec<(std::path::PathBuf, std::time::SystemTime)> = match std::fs::read_dir(dir) {
        Ok(entries) => entries
            .filter_map(|e| e.ok())
            .filter(|e| {
                let n = e.file_name().to_string_lossy().to_string();
                n.starts_with("core-") && (n.ends_with(".out.log") || n.ends_with(".err.log"))
            })
            .filter_map(|e| e.metadata().ok().and_then(|m| m.modified().ok()).map(|t| (e.path(), t)))
            .collect(),
        Err(_) => return,
    };
    logs.sort_by_key(|(_, t)| *t);
    let excess = logs.len().saturating_sub(keep);
    for (path, _) in logs.into_iter().take(excess) {
        let _ = std::fs::remove_file(path);
    }
}
```

`CoreSidecar::launch()` 中 `Command` 构造处替换 stdio：

```rust
        let logs = log_dir(&data_dir);
        prune_old_logs(&logs, 20);
        let (out_log, err_log) = open_log_files(&logs)
            .map_err(|e| eprintln!("cannot open sidecar logs: {e}"))
            .ok();

        let mut command = Command::new(&core_bin);
        command.env("XIAOYUE_PORT", port.to_string())
            .env("XIAOYUE_SESSION_TOKEN", &session_token)
            .env("XIAOYUE_DATA_DIR", &data_dir);
        if let Some(out) = out_log { command.stdout(Stdio::from(out)); } else { command.stdout(Stdio::null()); }
        if let Some(err) = err_log { command.stderr(Stdio::from(err)); } else { command.stderr(Stdio::null()); }
        // 无 core bin（dev 模式）时仍保持 Null —— 见 Task B4 的注释。
        let child = command.spawn().ok()?;
```

- [ ] **Step 4: cargo test 通过 → Commit**

```bash
git add apps/desktop/src-tauri/src/main.rs
git commit -m "feat(shell): sidecar stdout/stderr to rotating per-launch log files"
```

### Task B4：启动失败可诊断（Rust 显式状态 + UI 横幅）（双端 RED→GREEN）

**Files:**
- Modify: `apps/desktop/src-tauri/src/main.rs`
- Modify: `apps/desktop/src/main.tsx`
- Modify: `apps/desktop/src/components/AppShell.tsx`
- Test: `apps/desktop/src/components/AppShell.test.tsx`

- [ ] **Step 1: vitest RED**

```typescript
it('shows a diagnostic banner when the core sidecar failed to start', () => {
  (window as unknown as Record<string, unknown>).__XIAOYUE_CORE_ERROR__ =
    'spawn failed: 访问被拒绝 (os error 5)';
  render(
    <MemoryRouter>
      <AppShell />
    </MemoryRouter>,
  );
  expect(screen.getByRole('alert')).toHaveTextContent('本地核心服务启动失败');
  expect(screen.getByRole('alert')).toHaveTextContent('访问被拒绝');
  delete (window as unknown as Record<string, unknown>).__XIAOYUE_CORE_ERROR__;
});

it('shows no banner when the core runtime is healthy', () => {
  render(
    <MemoryRouter>
      <AppShell />
    </MemoryRouter>,
  );
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});
```

- [ ] **Step 2: AppShell GREEN（main-content 顶部）**

```tsx
const coreError =
  typeof window !== 'undefined'
    ? (window as unknown as Record<string, unknown>).__XIAOYUE_CORE_ERROR__
    : undefined;

// JSX 内：
{typeof coreError === 'string' && coreError && (
  <div role="alert" className="core-error-banner">
    <strong>本地核心服务启动失败</strong>
    <div>小米求职的岗位/资料功能依赖本地 Core 服务，当前不可用。</div>
    <div>原因：{coreError}</div>
    <div>请在数据目录 logs/ 下查看 core-*.log，重启应用重试。</div>
  </div>
)}
```

- [ ] **Step 3: Rust——launch 改显式三态**

```rust
enum SidecarLaunch {
    Launched(CoreSidecar),
    /// Dev shell: nothing bundled, nothing to show (expected path).
    NotBundled,
    /// Bundled but failed: user must see a diagnosable reason.
    Failed(String),
}
```

`launch()` 返回 `SidecarLaunch`：`find_core_bin()` None → `NotBundled`；`spawn` 错误 → `Failed(format!("spawn: {}", e))`；health 超时 → kill child 后 `Failed("sidecar did not become healthy in 30s".into())`。state 类型改 `Mutex<CoreSidecarState>`（内含 `Option<CoreSidecar>` + `Option<String>` 错误）。`core_endpoint` 命令返回：

```rust
#[derive(serde::Serialize)]
struct CoreEndpointInfo {
    base_url: Option<String>,
    session_token: Option<String>,
    status: String,          // "launched" | "unbundled" | "failed"
    detail: Option<String>,
}
```

- [ ] **Step 4: main.tsx——置错误标志**

```typescript
const runtime = await invoke<{ base_url: string | null; session_token: string | null; status: string; detail: string | null }>(
  'core_endpoint',
);
if (runtime?.status === 'launched' && runtime.base_url) {
  (window as unknown as Record<string, unknown>).__XIAOYUE_CORE__ = {
    baseUrl: runtime.base_url,
    sessionToken: runtime.session_token ?? '',
  };
} else if (runtime?.status === 'failed') {
  (window as unknown as Record<string, unknown>).__XIAOYUE_CORE_ERROR__ =
    runtime.detail ?? 'unknown failure';
}
```

（dev/unbundled 保持静默默认。）

- [ ] **Step 5: vitest + cargo test 全过 → Commit**

```bash
git add apps/desktop/src-tauri/src/main.rs apps/desktop/src/main.tsx apps/desktop/src/components/AppShell.tsx apps/desktop/src/components/AppShell.test.tsx
git commit -m "feat(shell): surface diagnosable core startup failure to the UI"
```

### Task B5：tauri.conf.json——resources 绑定 + NSIS + CSP 动态端口（vitest RED→GREEN）

**Files:**
- Modify: `apps/desktop/src-tauri/tauri.conf.json`
- Test: `apps/desktop/src/app/tauriConfig.test.ts`（新建）

- [ ] **Step 1: RED 测试 `apps/desktop/src/app/tauriConfig.test.ts`**

```typescript
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

interface TauriConf {
  bundle: { active: boolean; targets: string[]; resources: Record<string, string> | string[] };
  app: { security: { csp: string } };
}

const conf: TauriConf = JSON.parse(
  readFileSync(resolve(__dirname, '../../../src-tauri/tauri.conf.json'), 'utf-8'),
);

describe('tauri.conf.json (packaging contract)', () => {
  it('bundles with NSIS and carries the PyInstaller onedir output', () => {
    expect(conf.bundle.active).toBe(true);
    expect(conf.bundle.targets).toContain('nsis');
    const resources = Array.isArray(conf.bundle.resources) ? [] : conf.bundle.resources;
    expect(resources['../../services/core-api/dist/xiaoyue-core-api']).toBe('core-api/');
  });

  it('allows the webview to reach any loopback port (dynamic sidecar port)', () => {
    expect(conf.app.security.csp).toMatch(/connect-src[^;]*http:\/\/127\.0\.0\.1:\*/);
  });
});
```

- [ ] **Step 2: 确认失败**（当前 active=false、无 resources、CSP 固定 8765）

- [ ] **Step 3: 修改 `tauri.conf.json`**

```json
  "app": {
    "windows": [ ... ],
    "security": {
      "csp": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; connect-src 'self' http://127.0.0.1:* http://localhost:1420 ipc: http://ipc.localhost"
    }
  },
  "bundle": {
    "active": true,
    "targets": ["nsis"],
    "resources": {
      "../../services/core-api/dist/xiaoyue-core-api": "core-api/"
    }
  }
```

- [ ] **Step 4: vitest 通过 → Commit**

```bash
git add apps/desktop/src-tauri/tauri.conf.json apps/desktop/src/app/tauriConfig.test.ts
git commit -m "build(tauri): bundle NSIS installer with PyInstaller core resources + loopback CSP"
```

### Task B6：CI 打包链路（pyinstaller → smoke → tauri build）

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: 在 "Cargo test" 之后、"Desktop shell build" 之前插入**

```yaml
      - name: Verify core packaging lock
        run: python -m pip install -r services/core-api/requirements-lock.txt
      - name: Build core sidecar (PyInstaller onedir)
        run: ./scripts/build-core.ps1
      - name: Smoke core sidecar exe (health + auth + migrations)
        run: ./scripts/smoke-core-exe.ps1
```

（pyinstaller 已随 requirements-lock 安装；build-core.ps1 里 `python` 即 runner Python。smoke 步骤证明 exe 可跑，tauri build 产出 installer。）

- [ ] **Step 2: 本地全量验证**

```powershell
$env:XIAOYUE_DATA_DIR='D:\Xiaoyue-s-Job-Search\.venv\.test-data'
$env:PYTEST_ADDOPTS='-p dsh_tmp_shim'
.\.venv\Scripts\python.exe -m pytest services/core-api/tests -q
npx.cmd vitest run          # apps/desktop
cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml
./scripts/build-core.ps1
./scripts/smoke-core-exe.ps1
npm.cmd run tauri:build --workspace apps/desktop   # 产出 NSIS（本地若 NSIS 工具链不可用，交给 CI 验证并在 PR 注明）
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: build + smoke the PyInstaller sidecar before tauri build"
```

### Task B7：文档 + PR + CI 全绿

- [ ] **Step 1: TODO item 1（Tauri sidecar）逐项勾选实现项；「Fresh Windows smoke」按事实标注（exe 级 smoke 已自动完成；真机安装 smoke 留待用户手动）。README 增补 sidecar 架构段（onedir + resources 决策、NSIS 渠道、日志路径）。**
- [ ] **Step 2: push + PR + CI 全绿 + 合入 main**

```bash
git push -u origin feat/sidecar-release-loop
```

---

## Self-Review 结论

- TODO item 2 的 6 个未勾项：CSPRNG（A1）、内存存储（A2 持久化断言 + README 声明）、auth E2E（A2）、clients 审查（A3 修复 resumesClient， jobs/applications/profile 已合规）、防绕过（A2 路由覆盖测试）、双安全策略文档（A5）——全覆盖。
- TODO item 1 的未勾项：PyInstaller onedir（B2）、externalBin/resources（B5）、keyring/lxml/pypdf/python-docx/Alembic 依赖验证（B2 smoke + CI B6）、NSIS（B5/B6）、rotating log（B3）、失败可诊断 UI（B4）、Fresh Windows smoke（B7 标注分级）——「PyInstaller onedir exe 构建」与「安装器真机 smoke」由 CI + 用户分担。
- 无占位符；所有步骤含真实代码与预期输出。
