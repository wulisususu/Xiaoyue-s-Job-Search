# AI Profile Extraction + Secure Provider Configuration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add secure OpenAI-compatible provider configuration and explicit resume-to-AI extraction that creates registry-validated pending Profile drafts without modifying Profile SSOT.

**Architecture:** Store only non-secret provider metadata in an additive SQLite table; store the API key behind a `SecretStore` abstraction backed by the OS credential store. Use raw `httpx` against the OpenAI-compatible chat-completions endpoint, validate every returned candidate against the existing Profile registry, deduplicate identical pending AI drafts, and surface the flow through Settings and Resume Vault UI.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2.0, SQLite, httpx, keyring, React, TypeScript, Vitest, Tauri 2.

**Spec:** `docs/superpowers/specs/2026-09-16-ai-profile-extraction-design.md`

## Global Constraints

- AI output must never directly create or update `ProfileField` or `ProfileFieldRevision`.
- Only explicit existing draft acceptance may write AI-proposed values into Profile SSOT.
- API keys must never be stored in SQLite, ordinary files, frontend storage, logs, exceptions, or API responses.
- SQLite stores only `secret_ref` plus non-secret provider metadata.
- Production secret storage uses an OS credential-store abstraction; no plaintext fallback is permitted.
- Phase 3B supports one active/default OpenAI-compatible provider only.
- Vision model configuration is stored but not invoked.
- Only resumes with `extraction_status == EXTRACTED` and non-empty extracted text may use AI text extraction.
- Unknown registry keys and locally invalid values are rejected before draft creation.
- Repeated identical AI extraction must not duplicate an identical `PENDING` draft.
- CI must never contact a real model endpoint or mutate a real credential store.
- Final acceptance runs on the existing Windows GitHub Actions workflow.

---

## File Structure

Backend:

- `services/core-api/app/models.py` — add additive `AIProviderConfig` model.
- `services/core-api/app/ai/__init__.py` — AI subsystem package.
- `services/core-api/app/ai/secrets.py` — `SecretStore`, production keyring adapter, credential errors.
- `services/core-api/app/ai/provider.py` — provider config normalization/validation and endpoint construction.
- `services/core-api/app/ai/openai_compatible.py` — provider-agnostic chat-completions request/response parser.
- `services/core-api/app/profile/ai_extraction.py` — registry validation, draft dedupe, resume extraction orchestration.
- `services/core-api/app/routes/ai.py` — provider + API-key endpoints.
- `services/core-api/app/routes/resumes.py` — add explicit `POST /api/resumes/{resume_id}/ai-extract`.
- `services/core-api/app/main.py` — register AI router.
- `services/core-api/pyproject.toml` — runtime `httpx` + `keyring`.

Backend tests:

- `services/core-api/tests/test_ai_provider.py`
- `services/core-api/tests/test_ai_secrets.py`
- `services/core-api/tests/test_openai_compatible.py`
- `services/core-api/tests/test_ai_profile_extraction.py`
- `services/core-api/tests/test_ai_api.py`

Frontend:

- `apps/desktop/src/api/aiClient.ts` — typed provider/settings API.
- `apps/desktop/src/api/aiClient.test.ts` — provider/secret request contracts.
- `apps/desktop/src/api/resumesClient.ts` — AI-extraction request type/function.
- `apps/desktop/src/api/resumesClient.test.ts` — exact AI-extraction endpoint contract.
- `apps/desktop/src/pages/SettingsPage.tsx` — secure provider configuration UI.
- `apps/desktop/src/pages/SettingsPage.test.tsx` — write-only secret and provider-form behavior.
- `apps/desktop/src/pages/ResumesPage.tsx` — explicit AI extraction action/status.
- `apps/desktop/src/pages/ResumesPage.test.tsx` — AI action does not imply Profile mutation.
- `apps/desktop/src/styles/global.css` — focused settings/extraction layout styles.
- `README.md` — Phase 3B security and data-flow documentation.

---

### Task 1: Provider Persistence and OS Secret Store

**Files:**
- Modify: `services/core-api/app/models.py`
- Modify: `services/core-api/pyproject.toml`
- Create: `services/core-api/app/ai/__init__.py`
- Create: `services/core-api/app/ai/secrets.py`
- Create: `services/core-api/app/ai/provider.py`
- Test: `services/core-api/tests/test_ai_provider.py`
- Test: `services/core-api/tests/test_ai_secrets.py`

**Interfaces:**
- Produces SQLAlchemy model `AIProviderConfig` with primary key `id="default"` and no API-key value column.
- Produces `normalize_base_url(value: str) -> str`.
- Produces `chat_completions_url(base_url: str) -> str`.
- Produces `SecretStore` Protocol.
- Produces `KeyringSecretStore(service_name="XiaoyueJobSearch")`.
- Produces `get_secret_store() -> SecretStore`.
- Produces `CredentialStoreUnavailableError`.
- Uses deterministic secret ref `ai-provider:default:api-key`.

- [ ] **Step 1: Write provider/model RED tests**

Assert metadata contains `ai_provider_configs`; assert its columns are only non-secret configuration plus `secret_ref`; assert there is no `api_key` column. Assert:

```python
assert normalize_base_url("https://example.com/v1/") == "https://example.com/v1"
assert chat_completions_url("https://example.com/v1") == "https://example.com/v1/chat/completions"
assert chat_completions_url("http://127.0.0.1:8000") == "http://127.0.0.1:8000/v1/chat/completions"
```

Reject `ftp://`, embedded credentials, query strings, fragments, and missing hosts.

- [ ] **Step 2: Write secret-store RED tests**

Use a fake keyring module/object to verify `set_secret`, `get_secret`, and `delete_secret` call the fixed service namespace and exact secret ref. Simulate `keyring.errors.NoKeyringError` and assert it becomes `CredentialStoreUnavailableError`; assert no file/SQLite fallback occurs.

- [ ] **Step 3: Run targeted tests and verify RED**

Run:

```powershell
python -m pytest services/core-api/tests/test_ai_provider.py services/core-api/tests/test_ai_secrets.py -q
```

Expected: missing model/package/functions.

- [ ] **Step 4: Implement minimally**

Add runtime dependencies:

```toml
"httpx>=0.27",
"keyring>=25"
```

`AIProviderConfig` fields: `id`, `provider_name`, `base_url`, `text_model`, `vision_model`, `temperature`, `timeout_seconds`, `supports_json_schema`, `supports_vision`, `secret_ref`, `created_at`, `updated_at`.

`KeyringSecretStore` must never log secret values and must translate unavailable-backend errors to the domain error.

- [ ] **Step 5: Run targeted tests and verify GREEN**

Run the same targeted pytest command; expected all pass.

- [ ] **Step 6: Commit checkpoint**

Commit message: `feat: add secure ai provider foundation`

---

### Task 2: Provider Configuration API

**Files:**
- Create: `services/core-api/app/routes/ai.py`
- Modify: `services/core-api/app/main.py`
- Test: `services/core-api/tests/test_ai_api.py`

**Interfaces:**
- `GET /api/ai/provider`
- `PUT /api/ai/provider`
- `PUT /api/ai/provider/api-key`
- `DELETE /api/ai/provider/api-key`

Provider response fields must exclude `secret_ref` and API-key value, exposing only `has_api_key`.

- [ ] **Step 1: Write provider API RED tests**

Use temporary `XIAOYUE_DATA_DIR` and monkeypatch `app.routes.ai.get_secret_store` with an in-memory fake.

Assert:

- GET before configuration returns a clear not-configured representation.
- PUT saves normalized non-secret settings.
- GET returns settings + `has_api_key=false`.
- PUT API key writes the fake secret store and saves only `secret_ref` in SQLite.
- GET after secret save returns `has_api_key=true` and response JSON contains neither the API-key value nor `secret_ref`.
- DELETE removes the secret and clears `secret_ref`.
- unavailable secret store maps to 503.
- invalid provider config maps to 422.

- [ ] **Step 2: Run API test and verify RED**

Run:

```powershell
python -m pytest services/core-api/tests/test_ai_api.py -q
```

Expected: 404/missing router behavior.

- [ ] **Step 3: Implement minimal router**

Use Pydantic request/response models. Provider PUT must preserve an existing `secret_ref`. API-key write requires an existing provider config. Secret write succeeds before `secret_ref` is committed. Secret deletion clears the DB ref only after the store delete call succeeds.

- [ ] **Step 4: Run targeted API tests and full Core regression**

Run:

```powershell
python -m pytest services/core-api/tests/test_ai_api.py -q
python -m pytest services/core-api/tests -q
```

Expected: all pass.

- [ ] **Step 5: Commit checkpoint**

Commit message: `feat: expose secure ai provider api`

---

### Task 3: OpenAI-Compatible HTTP Client

**Files:**
- Create: `services/core-api/app/ai/openai_compatible.py`
- Test: `services/core-api/tests/test_openai_compatible.py`

**Interfaces:**
- Produces `ProviderRequestError`, `ProviderTimeoutError`, `ProviderResponseError`.
- Produces `OpenAICompatibleClient.extract_candidates(config, api_key, resume_text, registry=FIELD_REGISTRY) -> list[RawAICandidate]`.
- Produces immutable `RawAICandidate(field_key: str, value: object, confidence: float)`.
- Constructor accepts optional `transport: httpx.BaseTransport | None` for tests.

- [ ] **Step 1: Write HTTP-client RED tests with `httpx.MockTransport`**

Assert request URL, Authorization header, model, temperature and timeout configuration. For `supports_json_schema=true`, assert `response_format.type == "json_schema"`; when false, assert no JSON-schema response format is required.

Return mocked OpenAI-compatible responses and assert parser accepts:

```json
{"choices":[{"message":{"content":"{\"candidates\":[{\"field_key\":\"education.school\",\"value\":\"三江学院\",\"confidence\":0.98}]}"}}]}
```

Also test markdown-fenced JSON, upstream 401/500, timeout, missing choices/content, malformed JSON, wrong candidate shape, and ensure exception strings never contain the API key.

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
python -m pytest services/core-api/tests/test_openai_compatible.py -q
```

Expected: missing client module.

- [ ] **Step 3: Implement prompt/schema builder and client**

System instructions must enumerate allowed registry keys/labels/types, state that missing facts must not be inferred, and request only explicit resume-supported values. The JSON schema allows `value` as string or array of strings and confidence in `[0,1]`.

Do not log request headers or resume text.

- [ ] **Step 4: Run targeted test and verify GREEN**

Run the same pytest command; expected all pass.

- [ ] **Step 5: Commit checkpoint**

Commit message: `feat: add openai compatible extraction client`

---

### Task 4: Registry-Validated AI Draft Orchestration and Resume API

**Files:**
- Create: `services/core-api/app/profile/ai_extraction.py`
- Modify: `services/core-api/app/routes/resumes.py`
- Test: `services/core-api/tests/test_ai_profile_extraction.py`
- Modify/Test: `services/core-api/tests/test_ai_api.py`

**Interfaces:**
- Produces `AIExtractionResult(resume_id, provider_name, model, candidates_received, drafts_created, duplicates_skipped, invalid_candidates_rejected, draft_ids)`.
- Produces `extract_resume_with_ai(session, resume, config, api_key, client) -> AIExtractionResult`.
- Adds `POST /api/resumes/{resume_id}/ai-extract`.

- [ ] **Step 1: Write orchestration RED tests**

Mock the provider client to return a mix of:

- valid `education.school="三江学院"`;
- valid `job.target_roles=["平面设计"]`;
- unknown field key;
- invalid phone value;
- duplicate identical candidate.

Assert only locally valid registry candidates become `PENDING` drafts. Assert `ProfileField` and `ProfileFieldRevision` tables remain empty.

Run extraction twice and assert identical pending drafts are skipped the second time while rejected/accepted history is not rewritten.

- [ ] **Step 2: Write endpoint RED tests**

Cover:

- missing resume -> 404;
- `OCR_REQUIRED` or empty text -> 409;
- missing provider -> 409;
- missing key -> 409;
- credential backend unavailable -> 503;
- upstream/provider request errors -> 502/504 as designed;
- successful call returns counts and pending draft IDs;
- response contains no secret.

Patch the provider client/secret store; never use real network/keyring.

- [ ] **Step 3: Run targeted tests and verify RED**

Run:

```powershell
python -m pytest services/core-api/tests/test_ai_profile_extraction.py services/core-api/tests/test_ai_api.py -q
```

Expected: missing service/endpoint behavior.

- [ ] **Step 4: Implement validation + dedupe**

For each raw candidate:

1. confirm `field_key` exists in `FIELD_REGISTRY`;
2. ensure confidence is numeric within `[0,1]`;
3. call `validate_profile_value(field_key, value)`;
4. serialize normalized value with `json.dumps(..., ensure_ascii=False, separators=(",", ":"))`;
5. query identical `PENDING` draft by resume ID + field key + value JSON + extractor name;
6. create only missing pending drafts;
7. commit drafts only; never touch Profile tables.

- [ ] **Step 5: Run targeted and full Core suites**

Run:

```powershell
python -m pytest services/core-api/tests/test_ai_profile_extraction.py services/core-api/tests/test_ai_api.py -q
python -m pytest services/core-api/tests -q
```

Expected: all pass.

- [ ] **Step 6: Commit checkpoint**

Commit message: `feat: add ai resume draft extraction`

---

### Task 5: Desktop Provider Settings UI

**Files:**
- Create: `apps/desktop/src/api/aiClient.ts`
- Create: `apps/desktop/src/api/aiClient.test.ts`
- Modify: `apps/desktop/src/pages/SettingsPage.tsx`
- Create: `apps/desktop/src/pages/SettingsPage.test.tsx`
- Modify: `apps/desktop/src/styles/global.css`

**Interfaces:**
- Produces `AIProviderConfig` frontend type.
- Produces `getAIProvider()`, `saveAIProvider(config)`, `saveAIApiKey(apiKey)`, `deleteAIApiKey()`.

- [ ] **Step 1: Write frontend RED tests**

Client tests assert exact local-core URLs and methods. Verify provider save body contains no API key. Verify API-key save uses only `/api/ai/provider/api-key` and sends the key only in that request.

Settings page tests assert:

- returned provider values populate inputs;
- `has_api_key=true` renders `已安全保存` without rendering secret text;
- provider save and key save are separate actions;
- password input is write-only and clears after successful save;
- deleting a key changes state to `未配置`;
- copy states secret is stored in the OS credential store, not SQLite.

- [ ] **Step 2: Push RED checkpoint and verify Windows Web tests fail for missing client/UI**

Expected failure must be missing `aiClient`/Settings behavior, not test setup.

- [ ] **Step 3: Implement minimal client and Settings UI**

Do not add provider presets, multi-provider lists, model discovery, or automatic connection testing. Use one explicit provider form.

- [ ] **Step 4: Verify Windows Web tests GREEN**

Expected: Web tests pass after implementation.

- [ ] **Step 5: Commit checkpoint**

Commit message: `feat: add secure ai provider settings ui`

---

### Task 6: Resume Vault AI Extraction UI + Final Acceptance

**Files:**
- Modify: `apps/desktop/src/api/resumesClient.ts`
- Modify: `apps/desktop/src/api/resumesClient.test.ts`
- Modify: `apps/desktop/src/pages/ResumesPage.tsx`
- Modify: `apps/desktop/src/pages/ResumesPage.test.tsx`
- Modify: `apps/desktop/src/styles/global.css`
- Modify: `README.md`

**Interfaces:**
- Adds frontend `AIExtractionResult` type.
- Adds `extractResumeWithAI(resumeId: string) -> Promise<AIExtractionResult>`.

- [ ] **Step 1: Write frontend RED tests**

Assert `extractResumeWithAI("resume-1")` sends `POST http://127.0.0.1:8765/api/resumes/resume-1/ai-extract`.

Page tests assert:

- `EXTRACTED` resume shows `AI 提取资料`;
- `OCR_REQUIRED` does not expose the action and explains text-only AI extraction is unavailable;
- clicking AI extraction shows created/skipped/rejected counts;
- resume list/detail refreshes after success so pending draft count updates;
- copy explicitly says AI only creates pending review candidates and never directly modifies Profile SSOT.

- [ ] **Step 2: Push RED checkpoint and verify failure is feature-specific**

Expected: current Resume Vault lacks AI action/client function.

- [ ] **Step 3: Implement minimal UI and update README**

README must document:

```text
Resume text -> explicit AI extraction -> registry validation -> PENDING draft -> human review -> Profile SSOT
```

Also document API-key storage boundary and that vision/OCR are deferred.

- [ ] **Step 4: Run final acceptance on Windows CI**

Required final HEAD evidence:

- Web tests: success;
- Core tests: success;
- Vite production build: success;
- Tauri Cargo metadata: success.

- [ ] **Step 5: Audit branch diff against Phase 3B boundary**

Verify no OCR engine, Browser Agent integration, resume generation/tailoring, plaintext secret fallback, or automatic draft acceptance was added.

- [ ] **Step 6: Record final branch HEAD and CI run/job IDs**

Do not merge to `main` unless explicitly requested.
