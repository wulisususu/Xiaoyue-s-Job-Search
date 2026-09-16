# Profile SSOT + Immutable Resume Vault Design

Date: 2026-09-16
Branch: `feat/profile-resume-vault`
Status: Design for review

## 1. Goal

Build the local candidate-data foundation that future AI application automation can trust.

The system must distinguish four concepts:

1. **Profile SSOT** — the current confirmed structured facts that application automation is allowed to consume.
2. **Resume Vault** — immutable source documents and versions.
3. **Extraction Drafts** — candidate facts extracted from a resume but not yet trusted.
4. **Profile History** — append-only revisions showing how a confirmed field changed and where the value came from.

The primary invariant is:

> A resume is an import source, not runtime truth. Uploading or parsing a resume must never directly overwrite the Profile SSOT.

## 2. Scope

### In scope for Phase 3A

- Upload PDF and DOCX resumes through the desktop UI.
- Store files in the app-owned local Vault.
- SHA-256 deduplication and immutable resume versions.
- Extract embedded text from PDF and DOCX.
- Mark image-only / unusable PDFs as `OCR_REQUIRED`; OCR itself is deferred.
- Create conservative extraction drafts from deterministic parsers.
- View, edit, confirm, reject, and replace candidate Profile fields.
- Record source, confidence, confirmation state, timestamps, and revision history.
- Resume list/details UI and Profile review UI.
- Stable API contracts for future AI extraction providers.
- Windows CI coverage for backend, frontend, build, and Tauri metadata.

### Explicitly deferred to Phase 3B

- OpenAI-compatible provider settings.
- API-key storage in the Windows credential store.
- LLM extraction of education, experience, skills, awards, etc.
- OCR engine integration.
- Resume tailoring/generation.
- Browser Agent form filling.
- Portfolio/document library beyond PDF/DOCX resume files.

## 3. Domain invariants

### 3.1 Profile is the only application-time source of truth

Future ATS mapping and Browser Agent code may read confirmed Profile fields. It must not read a resume PDF directly to decide what to fill.

A Profile field contains:

- `field_key`
- typed JSON value
- `value_type`
- `source_type`
- `source_ref`
- `confidence`
- `confirmed`
- `updated_at`

Only `confirmed=true` is eligible for trusted automatic filling.

### 3.2 Resume versions are immutable

A resume version is identified by its SHA-256 content hash.

- Same bytes uploaded again: return the existing version; do not create a duplicate.
- Different bytes, even with the same filename: create a new version.
- Existing Vault bytes are never overwritten by a later upload.
- Deleting a logical resume entry is not part of this phase.

### 3.3 Drafts cannot silently become facts

Parsing creates `ProfileDraftField` rows with `PENDING` status.

A draft becomes Profile data only after an explicit user action:

- `ACCEPTED` → upsert confirmed Profile field and append a revision.
- `REJECTED` → keep draft provenance but do not change Profile.

Manual Profile edits bypass the draft queue because the user is directly supplying the value. They are stored as `source_type=manual`, `confidence=1.0`, `confirmed=true` and still append history.

### 3.4 Provenance is never discarded

When a field changes, the system keeps an append-only revision record with old/new values and the source that caused the change.

A future application record can therefore point to both:

- exact Profile state / field revisions used;
- exact resume version/hash uploaded to the employer.

## 4. Local Vault layout

Use the existing application data directory.

```text
<XIAOYUE_DATA_DIR>/
├── xiaoyue.db
└── vault/
    └── resumes/
        └── <sha256>/
            └── original.<ext>
```

Rules:

- Write upload bytes to a temporary file first.
- Compute SHA-256 while/after writing.
- Validate type before committing the file into the hash directory.
- Move into the final path atomically when possible.
- Store only a relative Vault path in SQLite.
- Never trust the uploaded filename as a filesystem path.
- Accepted formats in Phase 3A: `.pdf`, `.docx`.
- Old binary `.doc` files are rejected with a clear unsupported-format error.

Initial per-file limit: **50 MiB**. This is intentionally larger than a normal resume but prevents accidental multi-gigabyte uploads. Portfolio handling will be separate later.

## 5. File validation and parsing

### PDF

Validation:

- extension `.pdf`;
- PDF signature check (`%PDF-`);
- parser must be able to open the document.

Extraction:

- use the document text layer first;
- normalize whitespace but retain line structure sufficiently for later AI extraction;
- if extracted meaningful text is below a conservative threshold, set `extraction_status=OCR_REQUIRED` rather than inventing data.

### DOCX

Validation:

- extension `.docx`;
- ZIP/OpenXML structure is valid;
- expected Word document members exist.

Extraction:

- paragraphs and table cells are read in document order as far as practical;
- output is normalized plain text for downstream extraction.

### Parser dependencies

Phase 3A may add focused backend dependencies such as `pypdf`, `python-docx`, and `python-multipart`. OCR-heavy dependencies are explicitly excluded.

## 6. Data model

### `resume_versions`

One row per unique file content.

Fields:

- `id` — stable string ID
- `sha256` — unique, indexed
- `original_filename`
- `file_ext`
- `mime_type`
- `size_bytes`
- `vault_relpath`
- `version_number` — monotonically increasing user-visible sequence for unique versions
- `extraction_status` — `PENDING | EXTRACTED | OCR_REQUIRED | FAILED`
- `extracted_text` — nullable text
- `parser_name`
- `parser_version`
- `extraction_error` — nullable
- `created_at`

The version number is display metadata. SHA-256 is the identity anchor.

### `profile_fields`

Current SSOT snapshot, one row per canonical key.

Fields:

- `id`
- `field_key` — unique
- `value_json`
- `value_type`
- `source_type` — e.g. `manual`, `resume`
- `source_ref` — e.g. resume version ID
- `confidence` — nullable float in `[0,1]`
- `confirmed` — boolean
- `created_at`
- `updated_at`

### `profile_field_revisions`

Append-only change history.

Fields:

- `id`
- `field_key`
- `old_value_json` — nullable
- `new_value_json`
- `value_type`
- `source_type`
- `source_ref`
- `confidence`
- `confirmed`
- `changed_at`

No update/delete operation is exposed for revisions.

### `profile_draft_fields`

Untrusted extracted candidates.

Fields:

- `id`
- `resume_version_id`
- `field_key`
- `value_json`
- `value_type`
- `confidence`
- `extractor_name`
- `status` — `PENDING | ACCEPTED | REJECTED`
- `created_at`
- `reviewed_at` — nullable

Draft rows are immutable except for review status/timestamp.

## 7. Canonical Field Registry

Phase 3A uses a code-level registry rather than database columns for every possible SOE application field.

Each definition contains:

- stable `field_key`;
- Chinese label;
- category;
- value type;
- whether multiple values are allowed;
- basic validation rules.

Initial registry covers common non-sensitive fields needed to establish the mechanism, including:

- `identity.name`
- `contact.phone`
- `contact.email`
- `education.school`
- `education.major`
- `education.degree`
- `education.graduation_date`
- `location.hukou`
- `location.current_city`
- `job.target_roles`
- `skills.summary`
- `experience.summary`
- `awards.summary`

The registry is deliberately extensible. Database migrations are not required merely to add a new canonical field key.

Sensitive declarations are **not pre-populated or inferred**. Later RED-class fields such as legal declarations or politically sensitive fields require explicit user input and dedicated handling.

## 8. Deterministic extraction in Phase 3A

Phase 3A must not pretend to understand an entire resume without an LLM.

The built-in extractor is intentionally conservative:

- email candidates from strict email patterns;
- mainland China mobile-number candidates from strict phone patterns;
- optional exact-match extraction only when a value can be tied to an explicit unambiguous label.

It does **not** infer school, degree, job preference, experience summaries, awards, or other semantic fields from free text.

Those richer fields are the job of the Phase 3B `ProfileExtractionProvider`.

## 9. Future extraction provider contract

Define a narrow provider interface now, without implementing network AI in Phase 3A.

Conceptually:

```python
class ProfileExtractionProvider(Protocol):
    def extract(self, text: str, registry: FieldRegistry) -> list[DraftCandidate]: ...
```

All providers return drafts only. No provider is allowed to write to `profile_fields` directly.

This keeps deterministic extraction, future LLM extraction, and possible OCR+LLM pipelines interchangeable.

## 10. API design

### Resume Vault

- `POST /api/resumes/import`
  - multipart file upload;
  - validate → hash → deduplicate → Vault copy → text extraction → deterministic drafts;
  - returns resume metadata plus extraction result.
- `GET /api/resumes`
  - newest version first.
- `GET /api/resumes/{resume_id}`
  - metadata and extraction status; raw Vault filesystem paths are not exposed.
- `GET /api/resumes/{resume_id}/drafts`
  - candidate fields generated from this resume.

### Profile

- `GET /api/profile/fields`
  - current SSOT fields.
- `PUT /api/profile/fields/{field_key}`
  - explicit manual create/update;
  - validate against registry;
  - append revision.
- `GET /api/profile/history?field_key=...`
  - field revision history.

### Draft review

- `GET /api/profile/drafts?status=PENDING`
- `POST /api/profile/drafts/{draft_id}/accept`
  - validates draft;
  - upserts Profile field as confirmed;
  - appends revision;
  - marks draft accepted in the same transaction.
- `POST /api/profile/drafts/{draft_id}/reject`
  - marks draft rejected without changing Profile.

No endpoint in Phase 3A provides automatic bulk acceptance.

## 11. Desktop UX

### 简历库

Replace the empty state with:

- upload control for PDF/DOCX;
- version list showing version number, filename, size, SHA-256 prefix, extraction status, and created time;
- clear duplicate-upload result (`已存在相同版本`);
- visual state for `OCR_REQUIRED` and parsing failures;
- selected resume details with pending draft count.

The UI must never imply that upload means Profile was automatically updated.

### 我的资料

Split into two visible sections:

1. **已确认资料**
   - grouped by registry category;
   - show value, source, confidence where applicable, and last updated time;
   - allow explicit edit/save.
2. **待确认信息**
   - show draft value, source resume/version, confidence, and extractor;
   - explicit `确认写入` / `忽略` actions.

A short explanatory banner states:

> 只有“已确认资料”会被未来的 AI 网申自动填写使用。

## 12. Error handling

- Unsupported file → `415` with actionable message.
- File too large → `413`.
- Invalid/corrupt PDF or DOCX → `422`; no Vault version is committed.
- Duplicate content → `200` with `deduplicated=true` and existing version metadata.
- Parser failure after valid Vault commit → keep the immutable resume row, mark `FAILED`, preserve error for retry/future parser improvements.
- Image-only PDF → `OCR_REQUIRED`, not `FAILED`.
- Invalid Profile value → `422`; Profile remains unchanged.
- Draft accept transaction failure → neither Profile nor draft status changes.

## 13. Security and privacy

- Everything remains local-first under `XIAOYUE_DATA_DIR`.
- Resume bytes are never uploaded to an external service in Phase 3A.
- APIs bind to the existing local core (`127.0.0.1`).
- No API key is stored or introduced in this phase.
- Filenames are sanitized for display and are never used to construct arbitrary paths.
- Backend resolves Vault files from database-owned relative paths only.

## 14. Testing strategy

Backend TDD covers at minimum:

- PDF import and text extraction;
- DOCX import and table/paragraph extraction;
- SHA-256 deduplication;
- unsupported/corrupt file rejection;
- 50 MiB size limit;
- `OCR_REQUIRED` classification;
- conservative email/phone draft creation;
- draft acceptance transaction;
- rejected draft does not modify Profile;
- manual Profile write and append-only revision history;
- registry validation;
- API serialization and error codes.

Frontend TDD covers at minimum:

- Resume Vault list rendering;
- file upload action and duplicate indication;
- extraction state rendering;
- Profile confirmed-field rendering;
- pending draft accept/reject actions;
- explanatory SSOT safety text;
- no automatic conversion of a newly uploaded resume into confirmed Profile data.

Final acceptance uses the existing Windows GitHub Actions workflow:

- Web tests
- Core tests
- Vite production build
- Tauri Cargo metadata

## 15. Acceptance criteria

Phase 3A is complete only when all are true:

1. A PDF or DOCX can be imported from the desktop UI into the local immutable Vault.
2. Same-content re-upload does not create a second resume version.
3. Embedded text is extracted and persisted; unusable text-layer PDFs become `OCR_REQUIRED`.
4. Conservative deterministic drafts may be generated, but Profile remains unchanged after import.
5. A user can explicitly accept a draft into Profile.
6. A user can explicitly reject a draft without changing Profile.
7. A user can manually create/edit a Profile field.
8. Every Profile change appends provenance/history.
9. Profile and Resume Vault are visible in their respective desktop pages.
10. No network AI, OCR, Browser Agent, or credential-store logic is introduced in Phase 3A.
11. The final branch HEAD passes the complete Windows CI workflow.
