# Profile SSOT + Immutable Resume Vault Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local immutable PDF/DOCX Resume Vault plus a confirmed Profile SSOT with provenance, conservative extraction drafts, review actions, and desktop UI.

**Architecture:** Resume import is a one-way source pipeline: uploaded bytes are validated, hashed, persisted immutably under the application Vault, text is extracted, and only untrusted draft fields are created. Profile fields are a separate canonical registry-backed SSOT; only explicit manual edits or accepted drafts can change it, and every change appends an immutable revision.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2.0, SQLite, pypdf, python-docx, python-multipart, React, TypeScript, Vitest, Tauri 2.

**Spec:** `docs/superpowers/specs/2026-09-16-profile-resume-vault-design.md`

## Global Constraints

- Accepted resume formats in Phase 3A are `.pdf` and `.docx`; legacy `.doc` is rejected.
- Maximum upload size is exactly 50 MiB.
- Resume identity is SHA-256; same bytes must return the existing version without creating another version number.
- Vault files are immutable and stored under `<data_dir>/vault/resumes/<sha256>/original.<ext>`; SQLite stores only a relative Vault path.
- Resume parsing must never directly create or overwrite `profile_fields`.
- Only `confirmed=true` Profile fields may be considered trusted for future automatic application filling.
- Draft acceptance and Profile update must happen in one database transaction.
- Profile revisions are append-only; no revision update/delete API is introduced.
- Image-only/unusable text-layer PDFs are `OCR_REQUIRED`, not `FAILED`.
- No OCR engine, network AI, credential storage, resume tailoring, Browser Agent, or portfolio/document library is added in Phase 3A.
- All final acceptance checks run on Windows through the existing GitHub Actions workflow.

---

## File Structure

Backend files:

- `services/core-api/app/models.py` — add resume/profile/draft/revision persistence models.
- `services/core-api/app/profile/registry.py` — canonical field definitions and value validation.
- `services/core-api/app/profile/service.py` — Profile upsert/history and draft review transactions.
- `services/core-api/app/profile/extraction.py` — provider protocol and deterministic email/phone extractor.
- `services/core-api/app/resumes/vault.py` — hashing, format validation, immutable Vault writes, dedupe orchestration.
- `services/core-api/app/resumes/parsers.py` — PDF/DOCX text extraction and OCR-required classification.
- `services/core-api/app/routes/resumes.py` — Resume Vault APIs.
- `services/core-api/app/routes/profile.py` — Profile/draft/history APIs.
- `services/core-api/app/main.py` — register the new routers.
- `services/core-api/pyproject.toml` — add `pypdf`, `python-docx`, `python-multipart`.

Backend tests:

- `services/core-api/tests/test_profile_registry.py`
- `services/core-api/tests/test_resume_vault.py`
- `services/core-api/tests/test_resume_parsers.py`
- `services/core-api/tests/test_profile_service.py`
- `services/core-api/tests/test_resume_profile_api.py`

Frontend files:

- `apps/desktop/src/api/profileClient.ts` — typed Resume/Profile APIs.
- `apps/desktop/src/api/profileClient.test.ts` — request contract tests.
- `apps/desktop/src/pages/ResumesPage.tsx` / `ResumesPage.test.tsx` — upload/version/status UI.
- `apps/desktop/src/pages/ProfilePage.tsx` / `ProfilePage.test.tsx` — confirmed fields + draft review UI.
- `apps/desktop/src/styles/global.css` — focused Resume/Profile styles using the existing visual system.

---

### Task 1: Profile Registry and Persistence Models

**Files:**
- Modify: `services/core-api/app/models.py`
- Create: `services/core-api/app/profile/__init__.py`
- Create: `services/core-api/app/profile/registry.py`
- Test: `services/core-api/tests/test_profile_registry.py`

**Interfaces:**
- Produces `FieldDefinition`, `FIELD_REGISTRY`, `get_field_definition(field_key)`, `validate_profile_value(field_key, value)`.
- Produces SQLAlchemy models `ResumeVersion`, `ProfileField`, `ProfileFieldRevision`, `ProfileDraftField`.

- [ ] **Step 1: Write registry/model failing tests**

```python
from app.profile.registry import get_field_definition, validate_profile_value


def test_registry_exposes_stable_name_field():
    field = get_field_definition("identity.name")
    assert field.label == "姓名"
    assert field.value_type == "string"


def test_phone_validation_rejects_invalid_value():
    assert validate_profile_value("contact.phone", "13800138000") == "13800138000"
    with pytest.raises(ValueError):
        validate_profile_value("contact.phone", "123")
```

Also assert SQLAlchemy metadata contains `resume_versions`, `profile_fields`, `profile_field_revisions`, and `profile_draft_fields`, with unique `sha256` and unique `field_key` constraints.

- [ ] **Step 2: Run targeted test and verify RED**

Run: `python -m pytest services/core-api/tests/test_profile_registry.py -q`
Expected: import/model failures because Profile registry and models do not exist.

- [ ] **Step 3: Implement registry and models minimally**

Use code-level definitions for at least:
`identity.name`, `contact.phone`, `contact.email`, `education.school`, `education.major`, `education.degree`, `education.graduation_date`, `location.hukou`, `location.current_city`, `job.target_roles`, `skills.summary`, `experience.summary`, `awards.summary`.

Represent structured values as JSON text in SQLite and validate value types in the registry layer. Use `Float` for confidence and `Boolean` for confirmed. Do not add politically sensitive or legal-declaration fields.

- [ ] **Step 4: Run targeted tests and verify GREEN**

Run: `python -m pytest services/core-api/tests/test_profile_registry.py -q`
Expected: all tests pass.

- [ ] **Step 5: Commit checkpoint**

Commit message: `feat: add profile registry and resume persistence models`

---

### Task 2: Immutable Resume Vault and Text Parsers

**Files:**
- Modify: `services/core-api/pyproject.toml`
- Create: `services/core-api/app/resumes/__init__.py`
- Create: `services/core-api/app/resumes/vault.py`
- Create: `services/core-api/app/resumes/parsers.py`
- Test: `services/core-api/tests/test_resume_vault.py`
- Test: `services/core-api/tests/test_resume_parsers.py`

**Interfaces:**
- Produces `MAX_RESUME_BYTES = 50 * 1024 * 1024`.
- Produces `ResumeParseResult(status, text, parser_name, parser_version, error)`.
- Produces `validate_and_store_resume(session, settings, filename, content_type, data) -> tuple[ResumeVersion, bool]`, where the bool is `deduplicated`.
- Produces `extract_resume_text(path, ext) -> ResumeParseResult`.

- [ ] **Step 1: Write Vault failing tests**

Cover:
- valid PDF signature and valid DOCX import;
- same byte content imported twice returns same ID/version and `deduplicated=True` second time;
- same filename with different bytes creates another monotonically increasing version;
- `.doc` and arbitrary extensions rejected;
- >50 MiB rejected before Vault commit;
- corrupt PDF/DOCX rejected before `ResumeVersion` row creation;
- stored path matches `resumes/<sha256>/original.<ext>` and never contains the uploaded path.

- [ ] **Step 2: Write parser failing tests**

Generate PDF/DOCX fixtures inside tests. For DOCX, include paragraph text and a table cell. For PDF, test text-layer extraction and a valid page with no meaningful text that returns `OCR_REQUIRED`.

- [ ] **Step 3: Run tests and verify RED**

Run: `python -m pytest services/core-api/tests/test_resume_vault.py services/core-api/tests/test_resume_parsers.py -q`
Expected: missing module/functions.

- [ ] **Step 4: Add focused dependencies and minimal implementation**

Add:

```toml
"pypdf>=5.0",
"python-docx>=1.1",
"python-multipart>=0.0.9"
```

Vault flow must be `validate size -> validate extension/signature/container -> SHA-256 -> dedupe lookup -> write temp file -> atomic replace into hash directory -> create row -> parse -> update extraction metadata`.

Meaningful PDF text threshold: at least 20 non-whitespace characters after normalization. Below that: `OCR_REQUIRED` with no invented text.

- [ ] **Step 5: Run tests and verify GREEN**

Run: `python -m pytest services/core-api/tests/test_resume_vault.py services/core-api/tests/test_resume_parsers.py -q`
Expected: all pass and temp invalid files are absent after failures.

- [ ] **Step 6: Commit checkpoint**

Commit message: `feat: add immutable resume vault and parsers`

---

### Task 3: Deterministic Draft Extraction and Profile Review Service

**Files:**
- Create: `services/core-api/app/profile/extraction.py`
- Create: `services/core-api/app/profile/service.py`
- Test: `services/core-api/tests/test_profile_service.py`

**Interfaces:**
- Produces `DraftCandidate(field_key, value, value_type, confidence, extractor_name)`.
- Produces `ProfileExtractionProvider` Protocol with `extract(text, registry) -> list[DraftCandidate]`.
- Produces `extract_deterministic(text) -> list[DraftCandidate]`.
- Produces `create_resume_drafts(session, resume_version) -> list[ProfileDraftField]`.
- Produces `manual_upsert_profile_field(session, field_key, value) -> ProfileField`.
- Produces `accept_profile_draft(session, draft_id) -> ProfileField`.
- Produces `reject_profile_draft(session, draft_id) -> ProfileDraftField`.

- [ ] **Step 1: Write failing service tests**

Assert strict patterns extract:
- `name@example.com` -> `contact.email`;
- `13800138000` -> `contact.phone`.

Assert semantic items such as school/degree are not inferred from arbitrary free text.

Assert import/draft creation leaves `profile_fields` empty.

Assert draft acceptance:
- validates the registry value;
- upserts a confirmed Profile field with `source_type="resume"` and `source_ref=<resume_id>`;
- appends exactly one revision;
- marks draft `ACCEPTED` in the same transaction.

Assert draft rejection only changes status/reviewed timestamp and never changes Profile.

Assert manual edit uses `source_type="manual"`, `confidence=1.0`, `confirmed=True`, and appends a new revision containing old/new values.

- [ ] **Step 2: Run test and verify RED**

Run: `python -m pytest services/core-api/tests/test_profile_service.py -q`
Expected: missing extraction/service functions.

- [ ] **Step 3: Implement deterministic extractor and transactional service**

Use strict email/mobile regexes, de-duplicate identical candidates, and never create fields outside the registry. Serialize Profile values consistently with `json.dumps(..., ensure_ascii=False)`.

The acceptance service owns the transaction boundary: on validation or persistence failure it rolls back both draft status and Profile mutation.

- [ ] **Step 4: Run test and verify GREEN**

Run: `python -m pytest services/core-api/tests/test_profile_service.py -q`
Expected: all pass.

- [ ] **Step 5: Commit checkpoint**

Commit message: `feat: add profile draft extraction and review service`

---

### Task 4: Resume/Profile Core API

**Files:**
- Create: `services/core-api/app/routes/resumes.py`
- Create: `services/core-api/app/routes/profile.py`
- Modify: `services/core-api/app/main.py`
- Test: `services/core-api/tests/test_resume_profile_api.py`

**Interfaces:**
- `POST /api/resumes/import`
- `GET /api/resumes`
- `GET /api/resumes/{resume_id}`
- `GET /api/resumes/{resume_id}/drafts`
- `GET /api/profile/fields`
- `PUT /api/profile/fields/{field_key}` body `{ "value": ... }`
- `GET /api/profile/history?field_key=...`
- `GET /api/profile/drafts?status=PENDING`
- `POST /api/profile/drafts/{draft_id}/accept`
- `POST /api/profile/drafts/{draft_id}/reject`

- [ ] **Step 1: Write API failing tests**

Use FastAPI `TestClient` with temporary `XIAOYUE_DATA_DIR`. Cover:
- multipart PDF/DOCX import response includes `deduplicated`, version, hash, extraction status, pending draft count;
- duplicate upload returns HTTP 200 and existing resume metadata;
- unsupported format -> 415;
- >50 MiB -> 413;
- corrupt supported file -> 422;
- list/detail APIs never expose absolute Vault path;
- import does not create confirmed Profile fields;
- manual profile PUT validates registry and returns 422 on invalid phone/email;
- accept/reject endpoints have the specified state effects;
- history endpoint is ordered newest-first or explicitly documented oldest-first consistently.

- [ ] **Step 2: Run API test and verify RED**

Run: `python -m pytest services/core-api/tests/test_resume_profile_api.py -q`
Expected: 404/import failures because routers do not exist.

- [ ] **Step 3: Implement routers and register them**

Map domain errors deliberately:
- `ResumeTooLargeError` -> 413;
- `UnsupportedResumeTypeError` -> 415;
- `InvalidResumeError` -> 422;
- registry/value validation -> 422;
- missing resume/draft -> 404;
- already-reviewed draft -> 409.

Call deterministic draft generation only after a successful parse with usable extracted text. `OCR_REQUIRED` and `FAILED` create no drafts.

- [ ] **Step 4: Run backend suite**

Run: `python -m pytest services/core-api/tests -q`
Expected: full Core suite passes.

- [ ] **Step 5: Commit checkpoint**

Commit message: `feat: expose resume vault and profile APIs`

---

### Task 5: Desktop API Client and Resume Vault UI

**Files:**
- Create: `apps/desktop/src/api/profileClient.ts`
- Create: `apps/desktop/src/api/profileClient.test.ts`
- Modify: `apps/desktop/src/pages/ResumesPage.tsx`
- Create: `apps/desktop/src/pages/ResumesPage.test.tsx`
- Modify: `apps/desktop/src/styles/global.css`

**Interfaces:**
- Produces frontend types `ResumeVersion`, `ProfileDraft`, `ProfileField`, `ProfileRevision`.
- Produces `getResumes()`, `importResume(file)`, `getResumeDrafts(id)`, plus Profile methods consumed in Task 6.

- [ ] **Step 1: Write frontend RED tests**

`profileClient.test.ts` asserts multipart import uses `POST /api/resumes/import` with `FormData`, and list methods use the exact local-core URLs.

`ResumesPage.test.tsx` asserts:
- page renders returned resume versions;
- upload input accepts `.pdf,.docx`;
- uploading calls import and then refreshes list;
- `deduplicated=true` visibly renders `已存在相同版本`;
- `OCR_REQUIRED` visibly explains that OCR is required and has not been run;
- page copy explicitly says upload does not automatically update Profile.

- [ ] **Step 2: Push RED test checkpoint and verify Windows CI fails for missing UI/client behavior**

Expected failure must be caused by missing `profileClient` / Resume Vault UI, not fixture errors.

- [ ] **Step 3: Implement minimal client and Resume Vault page**

Do not add drag-and-drop, delete, rename, default-resume selection, or portfolio UI. Keep the upload action explicit and show version number, filename, size, SHA-256 prefix, extraction status, created time, and pending draft count.

- [ ] **Step 4: Verify frontend GREEN in Windows CI**

Expected: Web tests pass at this checkpoint.

- [ ] **Step 5: Commit checkpoint**

Commit message: `feat: add resume vault desktop UI`

---

### Task 6: Profile SSOT Review UI and Final Acceptance

**Files:**
- Modify: `apps/desktop/src/api/profileClient.ts`
- Modify: `apps/desktop/src/api/profileClient.test.ts`
- Modify: `apps/desktop/src/pages/ProfilePage.tsx`
- Create: `apps/desktop/src/pages/ProfilePage.test.tsx`
- Modify: `apps/desktop/src/styles/global.css`
- Modify: `README.md`

**Interfaces:**
- Uses `getProfileFields()`, `saveProfileField(fieldKey, value)`, `getPendingDrafts()`, `acceptDraft(id)`, `rejectDraft(id)`, `getProfileHistory(fieldKey?)`.

- [ ] **Step 1: Write Profile page RED tests**

Assert:
- banner text contains `只有“已确认资料”会被未来的 AI 网申自动填写使用`;
- confirmed fields render source/confidence/update information;
- pending drafts render resume version/extractor/confidence;
- `确认写入` posts accept then refreshes both confirmed and draft lists;
- `忽略` posts reject then removes/refreshes pending item;
- manual edit/save calls Profile PUT;
- importing a resume alone cannot make a confirmed field appear in Profile mocks.

- [ ] **Step 2: Verify RED on Windows CI**

Expected failure must be missing Profile UI/client behavior.

- [ ] **Step 3: Implement Profile UI minimally**

Group confirmed data by field registry category supplied by either API labels or a small frontend presentation map. Do not expose a bulk-accept action. Manual editing is explicit per field.

- [ ] **Step 4: Update README**

Document:
- Profile SSOT invariant;
- local Vault location conceptually under `XIAOYUE_DATA_DIR` without exposing user-specific paths;
- supported formats and 50 MiB limit;
- `OCR_REQUIRED` meaning;
- Phase 3A has no external resume upload / AI processing.

- [ ] **Step 5: Run fresh final verification**

Backend: `python -m pytest services/core-api/tests -q`

Windows GitHub Actions final HEAD must report success for:
- Test web
- Test core
- Build web
- Validate Tauri Cargo metadata

- [ ] **Step 6: Review acceptance criteria line by line**

Confirm all 11 spec acceptance criteria have evidence. If any criterion is not covered by a passing test or inspected implementation, report it as incomplete rather than claiming Phase 3A complete.

- [ ] **Step 7: Commit final documentation/checkpoint**

Commit message: `docs: document profile ssot and resume vault`
