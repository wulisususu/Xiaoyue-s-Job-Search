# AI Profile Extraction + Secure Provider Configuration Design

Date: 2026-09-16
Branch: `feat/ai-profile-extraction`
Status: Approved direction, implementation target

## 1. Goal

Extend the Phase 3A Profile SSOT + Immutable Resume Vault foundation with configurable OpenAI-compatible AI extraction while preserving the same trust boundary:

> AI may propose Profile drafts, but AI may never directly create, overwrite, accept, or confirm Profile SSOT fields.

Phase 3B also introduces secure local AI-provider configuration. Non-secret provider metadata may live in SQLite. API keys must live in the operating-system credential store and must never be returned by the Core API or written to ordinary settings.

## 2. Scope

### In scope

- One active/default OpenAI-compatible provider configuration for the local desktop app.
- Configurable provider name, Base URL, text/reasoning model, vision model, temperature, timeout, and capability flags.
- API key persisted through an OS credential-store abstraction.
- SQLite stores only a non-secret credential reference plus non-secret provider settings.
- Provider configuration API and desktop Settings UI.
- AI extraction from an already extracted resume text layer.
- Registry-constrained structured output.
- AI-created values become `PENDING` `ProfileDraftField` rows only.
- Existing human accept/reject flow remains the only route from AI output into Profile SSOT.
- AI extraction can be triggered explicitly from the Resume Vault UI.
- No real external AI calls in CI; provider HTTP behavior is tested with mocks/transports.
- Windows GitHub Actions acceptance remains authoritative.

### Explicitly deferred

- OCR implementation.
- Vision extraction from scanned/image-only resumes.
- Multiple simultaneously active provider profiles.
- Automatic provider failover/routing.
- Browser Agent use of the provider.
- Resume rewriting/tailoring/generation.
- Automatic acceptance of AI output.
- Sensitive/legal declaration inference.
- Application-form filling.

The vision-model field is stored now so later OCR/vision work does not require redesigning the settings contract. It is not invoked in Phase 3B.

## 3. Trust and privacy invariants

### 3.1 Profile SSOT remains authoritative

Only confirmed Profile fields are trusted runtime facts. AI output is untrusted evidence until explicitly accepted by the user.

Resume import and AI extraction must never call `manual_upsert_profile_field()` or `accept_profile_draft()` automatically.

### 3.2 Secrets never enter SQLite or API responses

The API key must not be stored in:

- `app_settings`;
- provider configuration rows;
- log messages;
- exception messages;
- API responses;
- frontend localStorage/sessionStorage.

SQLite stores only a stable `secret_ref`, for example `ai-provider:default:api-key`.

The Core API exposes only `has_api_key: true|false`.

### 3.3 Resume text is sent only after explicit user action

Configuring a provider does not send resume data anywhere. The first network transmission of resume text occurs only when the user explicitly chooses AI extraction for a particular resume.

### 3.4 Registry is the output boundary

The model can only propose fields present in `FIELD_REGISTRY`.

Unknown field keys are discarded. Values are validated through `validate_profile_value()`. Invalid values are rejected before any draft row is created.

No political, legal, or other sensitive declarations are added to the registry by this phase.

## 4. Architecture

```text
Settings UI
   │
   ├── non-secret config ──> Core API ──> ai_provider_configs (SQLite)
   │
   └── API key ────────────> Core API ──> OS Credential Store

ResumeVersion(EXTRACTED)
   │
   └── explicit "AI 提取" action
            │
            v
      AI Extraction Service
            │
            ├── build registry-constrained prompt
            ├── OpenAI-compatible /chat/completions request
            ├── parse JSON response
            ├── discard unknown/invalid candidates
            └── create PENDING ProfileDraftField rows
                         │
                         v
                 existing Profile Review UI
                         │ explicit accept only
                         v
                     Profile SSOT
```

The HTTP client, credential storage, extraction orchestration, API layer, and UI remain separate units so tests can replace network and secret-store dependencies independently.

## 5. Data model

Use an additive table so existing SQLite databases do not require destructive schema changes.

### `ai_provider_configs`

Single MVP row with primary key `default`.

Fields:

- `id` — string primary key, `default` for Phase 3B.
- `provider_name` — user-visible label, e.g. `OpenAI Compatible`.
- `base_url` — normalized HTTP/HTTPS base URL.
- `text_model` — model used for Profile extraction.
- `vision_model` — optional model reserved for later vision work.
- `temperature` — float, default `0.0`, allowed `[0.0, 2.0]`.
- `timeout_seconds` — integer, default `60`, allowed `[5, 300]`.
- `supports_json_schema` — boolean.
- `supports_vision` — boolean.
- `secret_ref` — nullable credential-store reference only.
- `created_at`.
- `updated_at`.

No API-key value column exists.

## 6. Credential store

Add a narrow abstraction:

```python
class SecretStore(Protocol):
    def set_secret(self, ref: str, value: str) -> None: ...
    def get_secret(self, ref: str) -> str | None: ...
    def delete_secret(self, ref: str) -> None: ...
```

Production implementation uses `keyring` with a fixed service namespace such as `XiaoyueJobSearch`.

For the default provider, the reference is deterministic:

```text
ai-provider:default:api-key
```

Tests use an in-memory fake store. Tests must never depend on the runner's Windows Credential Manager state.

If no usable OS credential backend exists, secret write/read operations fail with a dedicated `CredentialStoreUnavailableError`, mapped to HTTP 503. The app must not fall back to plaintext files or SQLite.

## 7. Provider configuration rules

`base_url` must:

- use `http` or `https`;
- contain a host;
- have no username/password embedded;
- have query and fragment stripped/rejected;
- be normalized without a trailing slash.

Local HTTP endpoints are allowed because users may run a local compatible proxy/model server.

Endpoint construction:

- if Base URL ends in `/v1`, append `/chat/completions`;
- otherwise append `/v1/chat/completions`.

Examples:

```text
https://api.openai.com/v1
  -> https://api.openai.com/v1/chat/completions

http://127.0.0.1:8000
  -> http://127.0.0.1:8000/v1/chat/completions
```

## 8. OpenAI-compatible extraction client

Create a focused client that accepts injected transport/client dependencies for deterministic tests.

Request characteristics:

- method: `POST`;
- endpoint: normalized chat-completions endpoint;
- `Authorization: Bearer <secret>`;
- `Content-Type: application/json`;
- model: configured `text_model`;
- temperature: configured value;
- timeout: configured value.

If `supports_json_schema=true`, request structured output with a JSON schema. Otherwise request plain JSON and parse the assistant content.

No API key, complete request headers, or raw resume text is logged.

## 9. Extraction contract

The model receives:

- the resume's extracted text;
- the allowed field registry keys, labels, value types, and multiplicity;
- instructions to extract only explicitly supported facts;
- instructions not to infer missing data;
- instructions to return no unknown fields.

Canonical response shape:

```json
{
  "candidates": [
    {
      "field_key": "education.school",
      "value": "三江学院",
      "confidence": 0.98
    }
  ]
}
```

Each candidate is validated locally. Confidence must be numeric and clamped/rejected outside `[0,1]` rather than trusted blindly.

Draft metadata:

- `resume_version_id` = selected resume;
- `field_key` = validated registry key;
- `value_json` = validated value;
- `value_type` = registry value type;
- `confidence` = validated confidence;
- `extractor_name` = `ai:<provider_name>:<text_model>`;
- `status` = `PENDING`.

The AI service does not write `ProfileField` or `ProfileFieldRevision`.

## 10. Draft deduplication

Repeated AI extraction should not flood the review queue with identical pending candidates.

Before inserting a candidate, compare pending drafts for the same:

- resume version;
- field key;
- normalized JSON value;
- extractor name.

If an identical `PENDING` draft exists, reuse/skip it.

A different value for the same field is allowed as a separate draft because it represents a conflicting extraction candidate that requires review.

Accepted or rejected historical drafts remain preserved and are not rewritten.

## 11. API design

### Provider configuration

`GET /api/ai/provider`

Returns either `null`/not-configured state or:

```json
{
  "id": "default",
  "provider_name": "OpenAI Compatible",
  "base_url": "https://example.com/v1",
  "text_model": "model-name",
  "vision_model": "vision-model-name",
  "temperature": 0.0,
  "timeout_seconds": 60,
  "supports_json_schema": true,
  "supports_vision": false,
  "has_api_key": true,
  "created_at": "...",
  "updated_at": "..."
}
```

`PUT /api/ai/provider`

Writes non-secret provider settings only.

`PUT /api/ai/provider/api-key`

Body:

```json
{ "api_key": "..." }
```

Writes to OS credential store and persists only the secret reference.

`DELETE /api/ai/provider/api-key`

Deletes the OS credential and clears `secret_ref`.

The API never returns the key value.

### AI extraction

`POST /api/resumes/{resume_id}/ai-extract`

Preconditions:

- resume exists;
- `extraction_status == EXTRACTED`;
- extracted text is non-empty;
- provider config exists;
- text model is configured;
- API key can be read from OS credential store.

Response:

```json
{
  "resume_id": "...",
  "provider_name": "...",
  "model": "...",
  "candidates_received": 7,
  "drafts_created": 5,
  "duplicates_skipped": 1,
  "invalid_candidates_rejected": 1,
  "draft_ids": [1, 2, 3, 4, 5]
}
```

No automatic review action occurs.

## 12. Error mapping

- provider not configured -> 409;
- provider has no text model -> 409;
- API key missing -> 409;
- credential backend unavailable -> 503;
- resume missing -> 404;
- resume is `OCR_REQUIRED`, `FAILED`, or otherwise lacks usable extracted text -> 409;
- provider timeout -> 504;
- provider HTTP/auth/upstream error -> 502 without echoing secret-bearing request data;
- invalid/non-JSON model response -> 502;
- all candidates invalid -> 200 with zero drafts and a rejected count, because the upstream call itself succeeded;
- invalid provider configuration -> 422.

## 13. Desktop Settings UX

Replace the Settings placeholder with an AI Provider panel containing:

- Provider Name;
- Base URL;
- Text / Reasoning Model;
- Vision Model;
- Temperature;
- Timeout seconds;
- `supports_json_schema` toggle;
- `supports_vision` toggle;
- API Key password input;
- Save Provider button;
- Save API Key button;
- Clear API Key button when a key exists.

The key input is write-only. The UI only shows `已安全保存` / `未配置`; it never loads the secret value back into the browser runtime.

Copy must state that the key is stored by the OS credential store and not ordinary SQLite.

## 14. Resume Vault UX

For a resume with `EXTRACTED` status:

- show an explicit `AI 提取资料` action;
- action is disabled while request is running;
- after success, show counts of created/skipped/rejected candidates;
- refresh pending-draft count;
- copy explicitly states AI extraction only creates review candidates and does not modify Profile SSOT.

For `OCR_REQUIRED`, the AI text-extraction action remains unavailable in Phase 3B with explanatory copy.

## 15. Testing strategy

### Backend

Test at minimum:

- provider table stores no secret value;
- provider Base URL validation/normalization;
- secret store set/get/delete through a fake store;
- no plaintext fallback when credential store fails;
- GET provider exposes `has_api_key`, never key value;
- AI request uses configured endpoint/model/temperature/timeout;
- JSON-schema capability changes the request shape;
- model output outside registry is rejected;
- registry-invalid values are rejected;
- valid model output creates only `PENDING` drafts;
- AI extraction leaves `profile_fields` and revisions unchanged;
- identical pending AI drafts are deduplicated;
- missing provider/key/resume-text errors map correctly;
- upstream 401/500/timeout/malformed JSON map safely;
- CI tests use mocked HTTP and fake credential stores only.

### Frontend

Test at minimum:

- Settings page loads provider config without receiving API key;
- saving provider sends only non-secret fields;
- saving API key uses the dedicated secret endpoint;
- existing-key state renders without exposing key text;
- Resume Vault triggers AI extraction explicitly;
- successful extraction displays draft counts and refreshes resume/draft metadata;
- copy states AI does not directly update Profile.

## 16. Dependencies

Backend runtime may add:

- `httpx>=0.27` for OpenAI-compatible HTTP calls;
- `keyring>=25` for OS credential-store integration.

No OpenAI vendor SDK is required. Using raw OpenAI-compatible HTTP keeps Base URL and model selection provider-agnostic.

## 17. Acceptance criteria

Phase 3B is complete only when all are true:

1. A user can save non-secret OpenAI-compatible provider settings from the desktop UI.
2. An API key can be saved and removed through the OS credential store abstraction without plaintext SQLite/file fallback.
3. Core/API/frontend never return or persist the API-key value outside the credential store.
4. An `EXTRACTED` resume can be explicitly sent to the configured text model for structured extraction.
5. Model output is constrained to the canonical Profile registry and locally validated.
6. Valid AI candidates create `PENDING` drafts only.
7. AI extraction never creates/updates `ProfileField` or `ProfileFieldRevision` directly.
8. Re-running the same extraction does not create duplicate identical pending drafts.
9. Existing manual accept/reject UI remains the only way AI proposals enter Profile SSOT.
10. `OCR_REQUIRED` resumes are not sent to the text-only AI extraction path.
11. Vision model configuration is stored but no image/vision extraction is introduced.
12. CI performs no real external provider call and no real credential-store mutation.
13. README accurately documents Phase 3B behavior and security boundary.
14. Final branch HEAD passes Web tests, Core tests, Vite production build, and Tauri Cargo metadata on Windows GitHub Actions.
