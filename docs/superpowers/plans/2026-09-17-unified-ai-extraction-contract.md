# Unified AI Extraction Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge the two drifting AI extraction contracts into one formal `ProfileExtractionProvider` chain: `Resume → AIExtractionRun → Draft → 人工 Review → Profile SSOT`, with replay-safe (idempotent) drafts and full provider/model provenance on every candidate.

**Architecture:** The contract lives in `app/profile/extraction.py`: providers return a `ProfileExtractionBundle` (scalar field candidates + structured collection candidates + provider/model/prompt/schema metadata) instead of scalar-only lists. `DeterministicExtractionProvider` (regex contact extraction) and `OpenAICompatibleExtractionProvider` (HTTP, any OpenAI-compatible endpoint) are the only implementations. A new `AIExtractionRun` row records every extraction attempt (provider, model, versions, status, input hash, error); drafts are stamped with `extraction_run_id` + `candidate_fingerprint` and made idempotent via a partial unique index. The dead `ProfileExtractor`/`provider.complete()`/`ExtractionResult` path is deleted.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2, Alembic, SQLite, httpx, pytest.

**Spec:** user P0 directive "统一 AI Provider / Extraction Contract"; `doc/TODO.md` item 3.

## Global Constraints

- AI output can only become `PENDING` drafts; Profile SSOT (fields + collections) is only reachable through human accept.
- Existing scalar Profile, existing draft rows, and current collection APIs stay backward-compatible; existing rows keep NULL `extraction_run_id`.
- Legacy `experience.summary` / `awards.summary` / `skills.summary` are never auto-split into collections.
- Migration chain continues from `0008_head`; new revision is `0009`.
- Providers must reject oversize input/output, enforce timeouts, classify errors (request/timeout/response), drop invalid per-item candidates while keeping valid ones, and reject malformed top-level JSON.
- Switching OpenAI ↔ DeepSeek ↔ Qwen only changes `AIProviderConfig`; no business-layer change.
- TDD is mandatory: RED → GREEN for every task.
- No Browser Agent work.

---

### Task 1: Unified extraction contract + deterministic provider

**Files:**
- Modify: `services/core-api/app/profile/extraction.py`
- Test: `services/core-api/tests/test_unified_extraction_contract.py`

**Interfaces:**
- `ExtractionMetadata(provider, model, prompt_version, schema_version)` frozen dataclass.
- `ProfileExtractionBundle(fields, collections, metadata)`: `fields: list[DraftCandidate]`, `collections: list[CollectionDraftCandidate]` (moved here from `collection_drafts.py`, re-exported there).
- `ProfileExtractionProvider` Protocol: `extract(text: str) -> ProfileExtractionBundle`.
- `DeterministicExtractionProvider` implementing the protocol (email/phone only, provider=`deterministic`, model=`deterministic-contact-v1`).
- `scalar_candidate_fingerprint(candidate)` / `collection_candidate_fingerprint(candidate)`: SHA-256 hex over canonical `{field_key, value}` / `{kind, payload}`, computed after validation so replay of the same normalized candidate is a no-op.
- `extract_deterministic(text)` stays as a backward-compatible shim returning `provider.extract(text).fields`.

- [ ] RED: tests for bundle shape (fields + empty collections + metadata), metadata constants, fingerprint stability, and compat shim.
- [ ] GREEN: implement; re-export `CollectionDraftCandidate` from `collection_drafts.py`.
- [ ] Run focused tests; commit.

### Task 2: OpenAI-compatible provider implements the unified contract

**Files:**
- Create: `services/core-api/app/ai/errors.py` — `ProviderRequestError`, `ProviderTimeoutError`, `ProviderResponseError`, `ProviderInputError`.
- Rewrite: `services/core-api/app/ai/openai_compatible.py`
- Delete dead drift path: `services/core-api/app/ai/extractor.py`, `schemas.py`, `validator.py`, `exceptions.py` (no callers outside themselves).
- Test: rewrite `tests/test_openai_compatible.py`, update `tests/test_ai_collection_contract.py`.

**Interfaces:**
- `OpenAICompatibleExtractionProvider(config: AIProviderConfig, api_key: str, transport: httpx.BaseTransport | None)` with `extract(text) -> ProfileExtractionBundle`; metadata: provider=`openai_compatible`, model=`config.text_model`, `OPENAI_PROMPT_VERSION`, `OPENAI_SCHEMA_VERSION`.
- Boundaries: `MAX_INPUT_CHARS`/`MAX_OUTPUT_CHARS` (200k) → `ProviderInputError`/`ProviderResponseError`; timeout → `ProviderTimeoutError`; network/HTTP >= 400 → `ProviderRequestError`; invalid top-level JSON/shape/empty content → `ProviderResponseError`.
- Partial-validity policy: scalar candidates with unknown `field_key` or non-registry value shapes are dropped; collection candidates with invalid payloads are dropped item-by-item; valid items survive. Legacy scalar-only responses (no `collections` key) still accepted.
- Deleted: `OpenAICompatibleClient`, `extract_candidates()`, `extract_profile_candidates()`, `RawAICandidate`/`RawAICollectionCandidate`/`RawAIExtractionBundle`.

- [ ] RED: provider tests — bundle + metadata, scalar+collection together, bad JSON, timeout, connection error, HTTP 500, empty completion, dropped invalid collection item while valid survives, dropped unknown scalar key, input/output caps, request goes to configured base_url/model.
- [ ] GREEN: implement provider; update the two legacy test files; commit.

### Task 3: `AIExtractionRun` model + `0009` migration

**Files:**
- Modify: `services/core-api/app/models.py`
- Create: `services/core-api/alembic/versions/0009_ai_extraction_runs.py`
- Modify: `services/core-api/tests/test_migrations.py`
- Run: `.\.venv\Scripts\python.exe -m pytest services/core-api/tests/test_migrations.py -q`

**Interfaces:**
- `AIExtractionRun`: `id`, `resume_version_id` (FK resume_versions CASCADE), `provider` (String 80), `model` (String 240), `prompt_version` (String 40), `schema_version` (String 40), `status` (`RUNNING|SUCCEEDED|FAILED`, indexed), `input_hash` (String 64, nullable), `error` (Text, nullable), `created_at`, `completed_at`.
- `profile_draft_fields` / `profile_collection_drafts`: add nullable `extraction_run_id` (FK `ai_extraction_runs.id` ON DELETE SET NULL) and `candidate_fingerprint` (String 64), partial unique index on `(extraction_run_id, candidate_fingerprint)` (SQLite `WHERE extraction_run_id IS NOT NULL AND candidate_fingerprint IS NOT NULL`),
  plus plain index on `extraction_run_id`.

- [ ] RED: table-list update, 0008→0009 upgrade test (legacy rows keep NULL run id, no data loss), drift guard, FK cascade run→drafts… (SET NULL keeps drafts).
- [ ] GREEN: models + migration; focused migration tests pass; commit.

### Task 4: Extraction run orchestration (service layer)

**Files:**
- Create: `services/core-api/app/profile/extraction_runs.py`
- Modify: `services/core-api/app/profile/service.py` (`create_resume_drafts` delegates to run orchestration, same signature), `collection_drafts.py` (expose no-session row builder for reuse).
- Test: `services/core-api/tests/test_extraction_runs.py`

**Interfaces:**
- `execute_extraction_run(session, resume_version, provider) -> AIExtractionRun`: create RUNNING row (input hash over extracted text) → `provider.extract(text)` → validate/normalize candidates (registry + collection validators, invalid items dropped) → persist drafts stamped `extraction_run_id` + fingerprint, skipping candidates whose `(run_id, fingerprint)` already exists → SUCCEEDED + counts; provider errors → FAILED + error message, no drafts, error re-raised to caller.
- `persist_bundle_drafts(session, resume_version, run, bundle)` is the idempotent core used by `execute_extraction_run`.
- Deterministic import keeps working through the same path (provider = `DeterministicExtractionProvider`).

- [ ] RED: run created for deterministic import; success run links both draft kinds with fingerprints; replay of the same run/bundle inserts nothing; failed provider → FAILED run + error + zero drafts + SSOT untouched; drafts never touch SSOT before accept (existing accept/reject tests must stay green).
- [ ] GREEN: implement; focused tests pass; commit.

### Task 5: `AIExtractionRun` API endpoints

**Files:**
- Modify: `services/core-api/app/routes/ai.py` (+ read models with `extraction_run_id` on draft read models in `routes/profile.py` and `routes/resumes.py`)
- Test: `services/core-api/tests/test_extraction_runs_api.py`

**Interfaces:**
- `POST /api/ai/extraction-runs` body `{resume_version_id}`: 404 unknown resume; 422 resume not EXTRACTED/no text or OCR_REQUIRED; 409 provider not configured / API key missing; 200 returns `AIExtractionRunRead` (run fields + `scalar_draft_count` + `collection_draft_count`). Provider failure still returns 200 with `status=FAILED` + `error` (the run row is the record).
- `GET /api/ai/extraction-runs?resume_version_id=` lists runs (optionally filtered).
- `build_default_provider(session)` reads `AIProviderConfig` + keyring; tests monkeypatch it (factory pattern like `get_secret_store`).

- [ ] RED: HTTP tests for all status codes, success path creates drafts, provider-failure path records FAILED run, list endpoint.
- [ ] GREEN: implement; focused tests pass; commit.

### Task 6: Full verification + docs

- [ ] `.\.venv\Scripts\python.exe -m pytest services/core-api/tests -q` all green.
- [ ] `npm run test:web` green; `npm run build` green.
- [ ] Update `doc/TODO.md` (item 3 → completed, note new chain), README section for the unified chain.
- [ ] Commit; push branch; monitor GitHub Actions (Web / Core / migration / build / cargo check / tauri build).

## Coverage Map (user-required tests)

| Required test | Where |
|---|---|
| unified provider contract | Task 1/2 |
| scalar + collection 同时输出 | Task 1/2 |
| AIExtractionRun 创建/成功/失败 | Task 4/5 |
| bad JSON / timeout / provider error / 空响应 | Task 2 |
| 非法 collection payload 单项拒绝 | Task 2 |
| 同一 run 重放不重复 Draft | Task 4 |
| Draft 不污染 SSOT / accept 后进 SSOT | Task 4 (existing accept tests) |
| provider 切换不影响业务层 | Task 2 + Task 5 (two configs, same orchestration) |
| migration fresh DB / 0008→0009 / drift guard | Task 3 |
