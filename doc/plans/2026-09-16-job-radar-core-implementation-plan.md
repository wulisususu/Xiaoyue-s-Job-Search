# Job Radar Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Import WorkFind company data and Xiaozhao Radar job-feed data into Xiaoyue's own SQLite domain model, resolve company identities, deduplicate jobs, expose read APIs, and render the first usable 岗位雷达 page.

**Architecture:** Upstream snapshots remain read-only inputs. Importers convert source-specific records into neutral DTOs; resolver/deduper services own normalization and identity decisions; SQLAlchemy models persist canonical companies/jobs plus provenance. The UI consumes only Xiaoyue Core API and never reads upstream files directly.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0, SQLite, pytest, React 18, TypeScript, Vitest.

**Spec:** `doc/央国企 AI 求职工作台——专家级开发方案 V1.md`; source audit: `third_party/upstreams/UPSTREAM_AUDIT.md`.

## Global Constraints

- WorkFind and Xiaozhao data are discovery sources, not truth.
- Do not mark a Xiaozhao URL as verified/open merely because it exists.
- Preserve upstream provenance and raw source identifiers.
- One canonical Company may have many aliases and sources.
- Dedup priority: stable source ID / canonical URL / company+title+location+batch fingerprint.
- `_local/` snapshots remain ignored and are never imported by application runtime modules directly.
- UI communicates only through `/api/*` Core endpoints.

---

### Task 1: Canonical company/job schema and identity utilities

**Files:**
- Modify: `services/core-api/app/models.py`
- Create: `services/core-api/app/jobs/identity.py`
- Create: `services/core-api/app/jobs/__init__.py`
- Test: `services/core-api/tests/test_job_identity.py`

**Interfaces:**
- Produces `normalize_company_name()`, `company_alias_candidates()`, `normalize_job_url()`, `job_fingerprint()`.
- Produces SQLAlchemy models `Company`, `CompanyAlias`, `CompanyRelation`, `CompanySource`, `Job`, `JobSource`.

- [ ] Write failing tests for legal-suffix normalization, short aliases, conservative URL normalization, and stable fingerprinting.
- [ ] Run `pytest tests/test_job_identity.py -q` and confirm RED.
- [ ] Implement minimal identity helpers and models.
- [ ] Run tests and full Core suite.

### Task 2: WorkFind importer + Company Resolver

**Files:**
- Create: `services/core-api/app/integrations/workfind.py`
- Create: `services/core-api/app/jobs/company_resolver.py`
- Test: `services/core-api/tests/test_workfind_import.py`

**Interfaces:**
- `import_workfind(session, company_db_path, relations_json_path) -> ImportSummary`
- `resolve_company(session, name, *, create_unknown=True) -> Company`

- [ ] Write fixtures/tests proving company counts, province/ownership mapping, child relations, idempotency, and alias resolution.
- [ ] Verify RED.
- [ ] Implement importer and resolver.
- [ ] Verify GREEN and full Core suite.

### Task 3: Xiaozhao importer + Job Deduper

**Files:**
- Create: `services/core-api/app/integrations/xiaozhao.py`
- Create: `services/core-api/app/jobs/deduper.py`
- Test: `services/core-api/tests/test_xiaozhao_import.py`

**Interfaces:**
- `import_xiaozhao(session, jobs_json_path) -> ImportSummary`
- Job statuses in this phase: `DISCOVERED_NO_URL`, `DISCOVERED_URL_UNVERIFIED`.

- [ ] Write tests for compressed-field mapping, URL/no-URL status, duplicate imports, company reuse, and source provenance.
- [ ] Verify RED.
- [ ] Implement importer/deduper.
- [ ] Verify GREEN and full Core suite.

### Task 4: Development import command

**Files:**
- Create: `scripts/import_job_sources.py`
- Test: `services/core-api/tests/test_import_command.py`

**Interfaces:**
- CLI accepts explicit WorkFind DB, relations JSON, Xiaozhao `jobs.json`, and optional `--data-dir`.

- [ ] Write failing CLI test against temporary fixture files.
- [ ] Verify RED.
- [ ] Implement command without importing from `_local/` implicitly.
- [ ] Verify GREEN.

### Task 5: Job Radar API

**Files:**
- Create: `services/core-api/app/routes/jobs.py`
- Modify: `services/core-api/app/main.py`
- Test: `services/core-api/tests/test_jobs_api.py`

**Interfaces:**
- `GET /api/jobs`
- `GET /api/jobs/stats`
- Query filters: `q`, `ownership`, `status`, `industry`, `location`, `limit`, `offset`.

- [ ] Write failing API tests for filters, pagination, counts, and provenance fields.
- [ ] Verify RED.
- [ ] Implement routes.
- [ ] Verify GREEN and full Core suite.

### Task 6: Jobs page first usable UI

**Files:**
- Modify: `apps/desktop/src/api/coreClient.ts`
- Create: `apps/desktop/src/api/jobsClient.test.ts`
- Modify: `apps/desktop/src/pages/JobsPage.tsx`
- Create: `apps/desktop/src/pages/JobsPage.test.tsx`
- Modify: `apps/desktop/src/styles/global.css`

**Interfaces:**
- `getJobs(params)` and `getJobStats()` consume Core API.
- Jobs page displays filters, source/status badges, and disables “开始申请” unless a later verifier marks an entry verified.

- [ ] Write failing client/UI tests.
- [ ] Verify RED in CI/local npm environment.
- [ ] Implement typed client and page.
- [ ] Verify GREEN, production build, and full CI.

### Task 7: Documentation and milestone verification

**Files:**
- Modify: `README.md`
- Create: `doc/JOB_RADAR_DATA_MODEL.md`

- [ ] Document source-to-domain mapping, statuses, import command, and current limitations.
- [ ] Run full Core tests, Web tests, Web build, and Cargo metadata CI.
- [ ] Record the verified branch SHA and keep the branch unmerged until user chooses integration.
