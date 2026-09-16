from __future__ import annotations

from app.resumes.vault import MAX_RESUME_BYTES
from tests.test_resume_parsers import build_pdf


def upload_pdf(client, text: str = "name@example.com 13800138000 resume text"):
    return client.post(
        "/api/resumes/import",
        files={"file": ("resume.pdf", build_pdf(text), "application/pdf")},
    )


def test_resume_import_lists_metadata_without_vault_path_and_deduplicates(client):
    first = upload_pdf(client)
    assert first.status_code == 200
    body = first.json()
    assert body["deduplicated"] is False
    assert body["version_number"] == 1
    assert len(body["sha256"]) == 64
    assert body["extraction_status"] == "EXTRACTED"
    assert body["pending_draft_count"] == 2
    assert "vault_relpath" not in body

    duplicate = client.post(
        "/api/resumes/import",
        files={"file": ("renamed.pdf", build_pdf("name@example.com 13800138000 resume text"), "application/pdf")},
    )
    assert duplicate.status_code == 200
    duplicate_body = duplicate.json()
    assert duplicate_body["deduplicated"] is True
    assert duplicate_body["id"] == body["id"]
    assert duplicate_body["version_number"] == 1

    listing = client.get("/api/resumes")
    assert listing.status_code == 200
    assert len(listing.json()) == 1
    assert "vault_relpath" not in listing.text

    detail = client.get(f"/api/resumes/{body['id']}")
    assert detail.status_code == 200
    assert "vault_relpath" not in detail.text
    assert detail.json()["pending_draft_count"] == 2


def test_resume_import_http_error_mapping_and_ocr_required(client):
    unsupported = client.post(
        "/api/resumes/import",
        files={"file": ("resume.txt", b"hello", "text/plain")},
    )
    assert unsupported.status_code == 415

    corrupt = client.post(
        "/api/resumes/import",
        files={"file": ("resume.pdf", b"%PDF-not-real", "application/pdf")},
    )
    assert corrupt.status_code == 422

    huge = b"%PDF-" + (b"x" * (MAX_RESUME_BYTES - 4))
    assert len(huge) > MAX_RESUME_BYTES
    too_large = client.post(
        "/api/resumes/import",
        files={"file": ("resume.pdf", huge, "application/pdf")},
    )
    assert too_large.status_code == 413

    blank = client.post(
        "/api/resumes/import",
        files={"file": ("scan.pdf", build_pdf(""), "application/pdf")},
    )
    assert blank.status_code == 200
    assert blank.json()["extraction_status"] == "OCR_REQUIRED"
    assert blank.json()["pending_draft_count"] == 0


def test_import_never_creates_confirmed_profile_until_draft_is_accepted(client):
    imported = upload_pdf(client)
    resume_id = imported.json()["id"]

    fields = client.get("/api/profile/fields")
    assert fields.status_code == 200
    assert fields.json() == []

    resume_drafts = client.get(f"/api/resumes/{resume_id}/drafts")
    assert resume_drafts.status_code == 200
    drafts = resume_drafts.json()
    assert len(drafts) == 2
    assert all(item["status"] == "PENDING" for item in drafts)

    accepted = client.post(f"/api/profile/drafts/{drafts[0]['id']}/accept")
    assert accepted.status_code == 200
    assert accepted.json()["confirmed"] is True
    assert accepted.json()["source_type"] == "resume"
    assert accepted.json()["source_ref"] == resume_id

    rejected = client.post(f"/api/profile/drafts/{drafts[1]['id']}/reject")
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "REJECTED"

    reviewed_again = client.post(f"/api/profile/drafts/{drafts[0]['id']}/accept")
    assert reviewed_again.status_code == 409

    missing = client.post("/api/profile/drafts/999999/accept")
    assert missing.status_code == 404


def test_manual_profile_validation_and_history_are_exposed(client):
    saved = client.put("/api/profile/fields/identity.name", json={"value": "赵新悦"})
    assert saved.status_code == 200
    assert saved.json()["value"] == "赵新悦"
    assert saved.json()["confirmed"] is True
    assert saved.json()["source_type"] == "manual"
    assert saved.json()["confidence"] == 1.0

    updated = client.put("/api/profile/fields/identity.name", json={"value": "赵新悦（更新）"})
    assert updated.status_code == 200

    bad_phone = client.put("/api/profile/fields/contact.phone", json={"value": "123"})
    assert bad_phone.status_code == 422

    unknown = client.put("/api/profile/fields/not.real", json={"value": "x"})
    assert unknown.status_code == 422

    history = client.get("/api/profile/history", params={"field_key": "identity.name"})
    assert history.status_code == 200
    entries = history.json()
    assert len(entries) == 2
    assert entries[0]["new_value"] == "赵新悦（更新）"
    assert entries[0]["old_value"] == "赵新悦"
    assert entries[1]["new_value"] == "赵新悦"


def test_pending_profile_drafts_endpoint_filters_by_status(client):
    upload_pdf(client)
    pending = client.get("/api/profile/drafts", params={"status": "PENDING"})
    assert pending.status_code == 200
    assert len(pending.json()) == 2
    assert all(item["status"] == "PENDING" for item in pending.json())
