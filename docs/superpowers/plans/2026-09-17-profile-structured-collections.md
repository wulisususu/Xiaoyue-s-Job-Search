# Profile Structured Collections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade Profile SSOT from scalar-only fields plus summary text into ordered structured collections that can represent multiple education, experience, project, award, certificate, language, and skill records without breaking existing scalar fields.

**Architecture:** Keep `ProfileField` as the scalar SSOT. Add a generic typed `ProfileCollectionItem` table for repeatable records and a matching revision table so each item can be created, edited, reordered, or deleted independently. Collection schemas live in a registry with per-field validation. REST endpoints expose definitions and CRUD; the desktop profile page renders section editors from those definitions. AI extraction remains draft-first: this phase defines the collection draft contract and storage hooks, while provider unification remains the next TODO phase.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2, Alembic, SQLite, Pydantic, React 19, TypeScript, Vitest.

**Spec:** `doc/TODO.md` — P0 "Profile SSOT 升级为结构化集合".

## Global Constraints

- Existing scalar `ProfileField` APIs and saved data remain backward-compatible.
- No Browser Agent work in this phase.
- Collection kinds are exactly: `education`, `experience`, `project`, `award`, `certificate`, `language`, `skill`.
- Each collection item has a stable integer id, `kind`, `position`, JSON payload, provenance, confirmation state, and timestamps.
- Manual edits are immediately confirmed and must append a revision row.
- Reordering must be deterministic and preserve stable item ids.
- All schema changes go through Alembic; current head is `0006`, so this phase starts at `0007_profile_structured_collections`.
- API validation rejects unknown kinds, unknown payload fields, empty required strings, invalid positions, and duplicate skill values where applicable.
- Tests are written before implementation for each behavior slice.

---

### Task 1: Collection registry and validation

**Files:**
- Create: `services/core-api/app/profile/collections.py`
- Create: `services/core-api/tests/test_profile_collections.py`

**Interfaces:**
- Produces `COLLECTION_REGISTRY`, `CollectionDefinition`, `get_collection_definition(kind)`, and `validate_collection_payload(kind, payload)`.
- Payloads are normalized JSON-serializable dicts.

- [ ] Write failing tests for all seven kinds, required fields, unknown fields, trimming, bullet/list normalization, and invalid kind rejection.
- [ ] Run `python -m pytest services/core-api/tests/test_profile_collections.py -q` and confirm RED because the module does not exist.
- [ ] Implement the registry and validators with explicit field definitions; reject unknown keys instead of silently dropping them.
- [ ] Re-run the focused tests and confirm GREEN.

### Task 2: Persistence model and migration

**Files:**
- Modify: `services/core-api/app/models.py`
- Create: `services/core-api/alembic/versions/0007_profile_structured_collections.py`
- Modify: `services/core-api/tests/test_migrations.py`
- Extend: `services/core-api/tests/test_profile_collections.py`

**Interfaces:**
- Produces ORM models `ProfileCollectionItem` and `ProfileCollectionRevision`.
- `ProfileCollectionItem`: `id`, `kind`, `position`, `payload_json`, `source_type`, `source_ref`, `confidence`, `confirmed`, `created_at`, `updated_at`.
- `ProfileCollectionRevision`: item identity, kind, old/new payload and position, source metadata, operation (`CREATE|UPDATE|REORDER|DELETE`), timestamp.

- [ ] Add failing persistence tests proving two education rows can coexist and have stable ids/order.
- [ ] Add migration expectations for both new tables and upgrade-from-`0006`.
- [ ] Implement ORM models and `0007` migration with indexes on `(kind, position)` and revision `item_id`.
- [ ] Run focused migration/collection tests to GREEN.

### Task 3: Collection service and API

**Files:**
- Create: `services/core-api/app/profile/collection_service.py`
- Modify: `services/core-api/app/routes/profile.py`
- Create: `services/core-api/tests/test_profile_collections_api.py`

**Interfaces:**
- Service: `create_collection_item`, `update_collection_item`, `delete_collection_item`, `reorder_collection_items`.
- API:
  - `GET /api/profile/collections/definitions`
  - `GET /api/profile/collections/{kind}`
  - `POST /api/profile/collections/{kind}`
  - `PUT /api/profile/collections/{kind}/{item_id}`
  - `DELETE /api/profile/collections/{kind}/{item_id}`
  - `PUT /api/profile/collections/{kind}/order`

- [ ] Write failing API tests for list/create/update/delete/reorder and validation failures.
- [ ] Verify RED with 404/missing service.
- [ ] Implement transaction-safe service methods; every mutation appends a revision.
- [ ] Implement Pydantic request/response models and routes.
- [ ] Run focused API tests to GREEN.

### Task 4: Desktop client and structured section editor

**Files:**
- Modify: `apps/desktop/src/api/profileClient.ts`
- Modify: `apps/desktop/src/pages/ProfilePage.tsx`
- Modify: `apps/desktop/src/styles/profile.css`
- Modify: `apps/desktop/src/api/profileClient.test.ts`
- Modify: `apps/desktop/src/pages/ProfilePage.test.tsx`

**Interfaces:**
- Adds typed `ProfileCollectionDefinition`, `ProfileCollectionItem`, CRUD and reorder client functions.
- Profile page keeps scalar sections and adds repeatable cards for the seven collection kinds.

- [ ] Add failing client tests for collection endpoint URL/body behavior.
- [ ] Add failing UI tests proving two education records render independently, a record can be added, edited, deleted, and order is stable.
- [ ] Implement typed client methods through the same Core API request path.
- [ ] Add reusable structured collection editor UI without duplicating seven components.
- [ ] Run `npm run test:web` and confirm GREEN.

### Task 5: Collection draft contract and compatibility cleanup

**Files:**
- Modify: `services/core-api/app/profile/extraction.py`
- Modify: `services/core-api/app/profile/service.py`
- Extend: `services/core-api/tests/test_profile_service.py`
- Modify: `doc/TODO.md`

**Interfaces:**
- Adds a typed collection candidate shape that provider unification can emit next phase.
- Existing deterministic contact extraction continues producing scalar drafts unchanged.
- No automatic write to confirmed collections without explicit review.

- [ ] Add failing tests proving scalar extraction is unchanged and collection candidates can be represented without mutating SSOT.
- [ ] Introduce collection candidate types/storage boundary only; do not duplicate the OpenAI provider contract in this phase.
- [ ] Mark completed Profile Structured Collections work in TODO and move AI population/review wiring under the next AI-contract phase.
- [ ] Run core profile tests, migration tests, web tests, then full CI.

### Task 6: Integration verification and merge

**Files:** none unless failures reveal a scoped defect.

- [ ] Run branch CI and require Web tests, Core tests, migration tests, web build, cargo metadata, cargo check, and full Tauri build to succeed.
- [ ] Compare `main...feat/profile-structured-collections` and review for unrelated changes.
- [ ] Fast-forward `main` only after the branch CI is green.
