# MVP Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first runnable local-first foundation for Xiaoyue's Job Search: a Windows-oriented Tauri 2 + React desktop shell backed by a FastAPI local core, SQLite persistence, a file-vault root, app settings, and a tested navigation/health baseline.

**Architecture:** The desktop UI is a thin local client. A Python FastAPI core owns persistence and future integrations. SQLite is the canonical local database; user files will later live under a dedicated local vault. The first milestone intentionally excludes resume parsing, WorkFind/Xiaozhao ingestion, and browser automation so those subsystems can be added behind stable interfaces.

**Tech Stack:** Tauri 2, React 19, TypeScript, Vite, Python 3.11+, FastAPI, SQLModel/SQLAlchemy, SQLite, pytest, Vitest, React Testing Library.

**Spec:** `doc/央国企 AI 求职工作台——专家级开发方案 V1.md`

## Global Constraints

- Windows desktop is the primary target for V1.
- Local-first only; no cloud account or SaaS backend in this milestone.
- Personal data and API keys must not be hard-coded or committed.
- SQLite is the local persistence layer.
- Tauri 2 is the desktop shell; React + TypeScript is the UI.
- Python 3.11+ FastAPI is the local core.
- Browser automation, WorkFind/Xiaozhao importers, resume parsing, and AI provider calls are explicitly out of scope for this first implementation plan.
- Every implementation task follows test-first development where practical.
- No implementation work is performed directly on `main`; use `feat/mvp-foundation`.

---

## File Structure Locked for This Milestone

```text
Xiaoyue-s-Job-Search/
├─ apps/
│  └─ desktop/
│     ├─ package.json
│     ├─ vite.config.ts
│     ├─ tsconfig.json
│     ├─ index.html
│     ├─ src/
│     │  ├─ main.tsx
│     │  ├─ app/App.tsx
│     │  ├─ app/routes.tsx
│     │  ├─ api/coreClient.ts
│     │  ├─ components/AppShell.tsx
│     │  ├─ pages/DashboardPage.tsx
│     │  ├─ pages/JobsPage.tsx
│     │  ├─ pages/ApplicationsPage.tsx
│     │  ├─ pages/ProfilePage.tsx
│     │  ├─ pages/ResumesPage.tsx
│     │  ├─ pages/SettingsPage.tsx
│     │  ├─ styles/global.css
│     │  └─ test/setup.ts
│     └─ src-tauri/
│        ├─ Cargo.toml
│        ├─ tauri.conf.json
│        └─ src/main.rs
├─ services/
│  └─ core-api/
│     ├─ pyproject.toml
│     ├─ app/
│     │  ├─ __init__.py
│     │  ├─ main.py
│     │  ├─ config.py
│     │  ├─ db.py
│     │  ├─ models.py
│     │  └─ routes/
│     │     ├─ __init__.py
│     │     ├─ health.py
│     │     └─ settings.py
│     └─ tests/
│        ├─ conftest.py
│        ├─ test_health.py
│        └─ test_settings.py
├─ scripts/
│  ├─ dev.ps1
│  └─ test.ps1
├─ .github/workflows/ci.yml
├─ .gitignore
├─ package.json
└─ README.md
```

---

### Task 1: Repository Tooling and Workspace Skeleton

**Files:**
- Create: `.gitignore`
- Create: `package.json`
- Create: `README.md`
- Create: `scripts/dev.ps1`
- Create: `scripts/test.ps1`

**Interfaces:**
- Consumes: none.
- Produces: root npm scripts `dev`, `test`, `test:web`, and `test:core`; a Windows PowerShell entry point for local development.

- [ ] **Step 1: Create the root workspace manifest**

```json
{
  "name": "xiaoyue-job-search",
  "private": true,
  "workspaces": ["apps/desktop"],
  "scripts": {
    "dev": "npm run dev --workspace apps/desktop",
    "test:web": "npm run test --workspace apps/desktop",
    "test:core": "python -m pytest services/core-api/tests -q",
    "test": "npm run test:web && npm run test:core"
  }
}
```

- [ ] **Step 2: Add ignore rules**

`.gitignore` must include at minimum:

```gitignore
node_modules/
dist/
.vite/
__pycache__/
*.py[cod]
.pytest_cache/
.venv/
.env
.env.*
!.env.example
*.db
*.sqlite
*.sqlite3
apps/desktop/src-tauri/target/
.worktrees/
local-data/
```

- [ ] **Step 3: Add Windows development scripts**

`scripts/dev.ps1` starts the core API in one process and the desktop UI in another, with `XIAOYUE_DATA_DIR` defaulting to `$env:LOCALAPPDATA\XiaoyueJobSearch`.

`scripts/test.ps1` runs:

```powershell
npm test
```

and exits non-zero on failure.

- [ ] **Step 4: Add README bootstrap documentation**

README must document exact prerequisites:

```text
Node.js 20+
Python 3.11+
Rust stable
Microsoft Edge WebView2 Runtime
```

and exact local commands:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .\services\core-api[dev]
npm install
.\scripts\test.ps1
.\scripts\dev.ps1
```

- [ ] **Step 5: Verify workspace files parse**

Run:

```bash
node -e "JSON.parse(require('fs').readFileSync('package.json','utf8')); console.log('ok')"
```

Expected: `ok`.

- [ ] **Step 6: Commit**

```bash
git add .gitignore package.json README.md scripts
git commit -m "chore: initialize project workspace"
```

---

### Task 2: FastAPI Core, Configuration, and SQLite Foundation

**Files:**
- Create: `services/core-api/pyproject.toml`
- Create: `services/core-api/app/__init__.py`
- Create: `services/core-api/app/config.py`
- Create: `services/core-api/app/db.py`
- Create: `services/core-api/app/models.py`
- Create: `services/core-api/app/main.py`
- Create: `services/core-api/app/routes/__init__.py`
- Create: `services/core-api/app/routes/health.py`
- Create: `services/core-api/tests/conftest.py`
- Create: `services/core-api/tests/test_health.py`

**Interfaces:**
- Consumes: environment variable `XIAOYUE_DATA_DIR`.
- Produces: `create_app() -> FastAPI`, `get_settings() -> AppSettings`, `get_engine() -> Engine`, and `GET /api/health`.

- [ ] **Step 1: Write the failing health test**

```python
from fastapi.testclient import TestClient
from app.main import create_app


def test_health_returns_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("XIAOYUE_DATA_DIR", str(tmp_path))
    client = TestClient(create_app())

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["database"] == "ok"
```

- [ ] **Step 2: Run the test and verify failure**

Run:

```bash
python -m pytest services/core-api/tests/test_health.py -q
```

Expected: import/module failure because the application does not exist yet.

- [ ] **Step 3: Implement application settings**

`AppSettings` must resolve:

```python
class AppSettings(BaseSettings):
    app_name: str = "Xiaoyue Job Search"
    host: str = "127.0.0.1"
    port: int = 8765
    data_dir: Path

    @property
    def database_path(self) -> Path:
        return self.data_dir / "xiaoyue.db"

    @property
    def vault_dir(self) -> Path:
        return self.data_dir / "vault"
```

`get_settings()` creates `data_dir` and `vault_dir` if needed.

- [ ] **Step 4: Implement SQLite initialization**

Create SQLModel entities:

```python
class AppSetting(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: str
```

`get_engine()` returns a SQLite engine using `settings.database_path`; `init_db()` runs `SQLModel.metadata.create_all(engine)`.

- [ ] **Step 5: Implement `/api/health`**

Response schema:

```json
{
  "status": "ok",
  "database": "ok",
  "version": "0.1.0"
}
```

The route must execute `SELECT 1` through the configured engine before returning `database: ok`.

- [ ] **Step 6: Run test and verify pass**

Run:

```bash
python -m pytest services/core-api/tests/test_health.py -q
```

Expected: `1 passed`.

- [ ] **Step 7: Commit**

```bash
git add services/core-api
git commit -m "feat: add local FastAPI core and SQLite foundation"
```

---

### Task 3: Persistent Local Application Settings API

**Files:**
- Create: `services/core-api/app/routes/settings.py`
- Create: `services/core-api/tests/test_settings.py`
- Modify: `services/core-api/app/main.py`

**Interfaces:**
- Consumes: `AppSetting` table and `get_engine()`.
- Produces: `GET /api/settings` and `PUT /api/settings/{key}`.

- [ ] **Step 1: Write failing settings tests**

```python
def test_setting_round_trip(client):
    response = client.put("/api/settings/theme", json={"value": "system"})
    assert response.status_code == 200
    assert response.json() == {"key": "theme", "value": "system"}

    response = client.get("/api/settings")
    assert response.status_code == 200
    assert response.json()["theme"] == "system"
```

`tests/conftest.py` must expose a `client` fixture using a temporary data directory.

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
python -m pytest services/core-api/tests/test_settings.py -q
```

Expected: 404 for settings routes.

- [ ] **Step 3: Implement the routes**

Define request/response types:

```python
class SettingWrite(BaseModel):
    value: str

class SettingRead(BaseModel):
    key: str
    value: str
```

Behavior:
- `PUT /api/settings/{key}` upserts a string value.
- `GET /api/settings` returns a flat JSON object `{key: value}`.
- API keys or secrets must never be stored through this generic endpoint; keys matching `api_key`, `token`, `secret`, or `password` return HTTP 400.

- [ ] **Step 4: Add a secret-rejection test**

```python
def test_settings_reject_secret_keys(client):
    response = client.put("/api/settings/openai_api_key", json={"value": "secret"})
    assert response.status_code == 400
```

- [ ] **Step 5: Run all core tests**

Run:

```bash
python -m pytest services/core-api/tests -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add services/core-api
git commit -m "feat: add local settings persistence API"
```

---

### Task 4: React Desktop UI Shell and Navigation

**Files:**
- Create: `apps/desktop/package.json`
- Create: `apps/desktop/vite.config.ts`
- Create: `apps/desktop/tsconfig.json`
- Create: `apps/desktop/index.html`
- Create: `apps/desktop/src/main.tsx`
- Create: `apps/desktop/src/app/App.tsx`
- Create: `apps/desktop/src/app/routes.tsx`
- Create: `apps/desktop/src/components/AppShell.tsx`
- Create: `apps/desktop/src/pages/DashboardPage.tsx`
- Create: `apps/desktop/src/pages/JobsPage.tsx`
- Create: `apps/desktop/src/pages/ApplicationsPage.tsx`
- Create: `apps/desktop/src/pages/ProfilePage.tsx`
- Create: `apps/desktop/src/pages/ResumesPage.tsx`
- Create: `apps/desktop/src/pages/SettingsPage.tsx`
- Create: `apps/desktop/src/styles/global.css`
- Create: `apps/desktop/src/test/setup.ts`
- Create: `apps/desktop/src/components/AppShell.test.tsx`

**Interfaces:**
- Consumes: none from backend yet.
- Produces: stable navigation routes `/`, `/jobs`, `/applications`, `/profile`, `/resumes`, `/settings`.

- [ ] **Step 1: Write failing shell test**

```tsx
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppShell } from './AppShell';

it('shows all primary navigation items', () => {
  render(
    <MemoryRouter>
      <AppShell />
    </MemoryRouter>
  );

  for (const label of ['首页', '岗位雷达', '投递中心', '我的资料', '简历库', '设置']) {
    expect(screen.getByText(label)).toBeInTheDocument();
  }
});
```

- [ ] **Step 2: Run and verify failure**

Run:

```bash
npm install
npm run test:web
```

Expected: fail because `AppShell` does not exist.

- [ ] **Step 3: Implement UI shell**

Requirements:
- Fixed left navigation on desktop.
- Main content region with React Router outlet.
- Product name shown as `小悦求职`.
- No mock business data beyond explicit zero-state text.
- Pages use the exact top-level labels defined in the spec.

- [ ] **Step 4: Implement initial zero-state pages**

Dashboard cards:

```text
今日新增岗位 0
可申请岗位 0
已收藏 0
填写中 0
已投递 0
笔试 0
面试 0
Offer 0
```

Other pages render explanatory empty states, not fabricated jobs or resumes.

- [ ] **Step 5: Run web tests**

Run:

```bash
npm run test:web
```

Expected: all tests pass.

- [ ] **Step 6: Build web bundle**

Run:

```bash
npm run build --workspace apps/desktop
```

Expected: Vite build succeeds.

- [ ] **Step 7: Commit**

```bash
git add apps/desktop package-lock.json
git commit -m "feat: add desktop navigation shell"
```

---

### Task 5: Core API Client and Health Status in UI

**Files:**
- Create: `apps/desktop/src/api/coreClient.ts`
- Create: `apps/desktop/src/api/coreClient.test.ts`
- Modify: `apps/desktop/src/pages/DashboardPage.tsx`

**Interfaces:**
- Consumes: `GET http://127.0.0.1:8765/api/health`.
- Produces: `getCoreHealth(): Promise<CoreHealth>`.

- [ ] **Step 1: Write failing API client test**

Mock `fetch` and assert:

```ts
await expect(getCoreHealth()).resolves.toEqual({
  status: 'ok',
  database: 'ok',
  version: '0.1.0',
});
```

- [ ] **Step 2: Run and verify failure**

Run:

```bash
npm run test:web
```

Expected: missing `getCoreHealth` implementation.

- [ ] **Step 3: Implement typed client**

```ts
export interface CoreHealth {
  status: 'ok';
  database: 'ok';
  version: string;
}

export async function getCoreHealth(baseUrl = 'http://127.0.0.1:8765'): Promise<CoreHealth>
```

Non-2xx responses must throw `CoreApiError` containing the HTTP status.

- [ ] **Step 4: Show local-core status on dashboard**

Dashboard displays one of:

```text
本地核心：已连接
本地核心：未连接
```

No retry loop in this milestone; a manual refresh/re-render is enough.

- [ ] **Step 5: Run web tests and build**

Run:

```bash
npm run test:web
npm run build --workspace apps/desktop
```

Expected: both pass.

- [ ] **Step 6: Commit**

```bash
git add apps/desktop
git commit -m "feat: connect desktop shell to local core health API"
```

---

### Task 6: Tauri 2 Desktop Wrapper

**Files:**
- Create: `apps/desktop/src-tauri/Cargo.toml`
- Create: `apps/desktop/src-tauri/tauri.conf.json`
- Create: `apps/desktop/src-tauri/src/main.rs`
- Modify: `apps/desktop/package.json`

**Interfaces:**
- Consumes: Vite dev server on `http://localhost:1420` and `apps/desktop/dist` for production.
- Produces: `npm run tauri:dev` and `npm run tauri:build`.

- [ ] **Step 1: Add Tauri dependencies and scripts**

`apps/desktop/package.json` adds:

```json
{
  "scripts": {
    "tauri:dev": "tauri dev",
    "tauri:build": "tauri build"
  },
  "devDependencies": {
    "@tauri-apps/cli": "^2.0.0"
  }
}
```

- [ ] **Step 2: Add minimal Tauri Rust entry point**

`main.rs` starts a single application window titled `小悦求职` and uses no privileged plugins in this milestone.

- [ ] **Step 3: Configure build paths**

`tauri.conf.json` must define:

```json
{
  "build": {
    "beforeDevCommand": "npm run dev",
    "beforeBuildCommand": "npm run build",
    "devUrl": "http://localhost:1420",
    "frontendDist": "../dist"
  }
}
```

- [ ] **Step 4: Verify Rust metadata**

Run:

```bash
cargo metadata --manifest-path apps/desktop/src-tauri/Cargo.toml --no-deps
```

Expected: exits 0.

- [ ] **Step 5: Verify frontend build still passes**

Run:

```bash
npm run build --workspace apps/desktop
```

Expected: exits 0.

- [ ] **Step 6: Commit**

```bash
git add apps/desktop/src-tauri apps/desktop/package.json package-lock.json
git commit -m "feat: wrap desktop UI with Tauri 2"
```

---

### Task 7: Continuous Integration and Foundation Acceptance

**Files:**
- Create: `.github/workflows/ci.yml`
- Modify: `README.md`

**Interfaces:**
- Consumes: root npm and Python test commands.
- Produces: CI verification on push and pull request.

- [ ] **Step 1: Add CI workflow**

Workflow runs on Windows and performs:

```text
checkout
setup-node 20
setup-python 3.11
npm ci
pip install -e ./services/core-api[dev]
npm run test:web
python -m pytest services/core-api/tests -q
npm run build --workspace apps/desktop
cargo metadata --manifest-path apps/desktop/src-tauri/Cargo.toml --no-deps
```

- [ ] **Step 2: Add foundation acceptance checklist to README**

Document exactly:

```text
[ ] Local API responds at /api/health
[ ] SQLite database is created under XIAOYUE_DATA_DIR
[ ] Local vault directory is created
[ ] Desktop UI exposes six primary sections
[ ] UI reports local-core connection state
[ ] Web tests pass
[ ] Core tests pass
[ ] Frontend production build passes
[ ] Tauri Cargo metadata resolves
```

- [ ] **Step 3: Run complete local verification**

Run:

```bash
npm run test:web
python -m pytest services/core-api/tests -q
npm run build --workspace apps/desktop
cargo metadata --manifest-path apps/desktop/src-tauri/Cargo.toml --no-deps
```

Expected: every command exits 0.

- [ ] **Step 4: Commit**

```bash
git add .github README.md
git commit -m "ci: verify MVP foundation"
```

---

## Self-Review Result

- Spec coverage for this sub-project: desktop shell, FastAPI local core, SQLite, local file-vault root, settings foundation, top-level navigation, and test baseline are covered.
- Intentionally deferred to separate implementation plans: resume ingestion/profile SSOT, WorkFind/Xiaozhao data ingestion, apply URL verification, Offer Harvester browser integration, file upload automation, vision fallback, and application CRM state machine.
- No placeholder implementation steps are permitted in this plan.
- Interface names used across tasks are consistent: `create_app`, `get_settings`, `get_engine`, `getCoreHealth`.
