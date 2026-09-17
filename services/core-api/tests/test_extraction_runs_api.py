from __future__ import annotations

import itertools
import json
import uuid

import httpx
from sqlalchemy.orm import Session

from app.ai.openai_compatible import OpenAICompatibleExtractionProvider
from app.config import get_settings
from app.db import get_engine
from app.models import AIProviderConfig, ResumeVersion
from app.routes import ai as ai_routes
from test_ai_api import MemorySecretStore

_version_counter = itertools.count(1)

PROVIDER_PAYLOAD = {
    "provider_name": "OpenAI Compatible",
    "base_url": "https://example.com/v1/",
    "text_model": "reasoning-model",
    "temperature": 0.0,
    "timeout_seconds": 60,
    "supports_json_schema": True,
    "supports_vision": False,
}


def seed_resume(status: str = "EXTRACTED", text: str | None = "name@example.com 学校：三江学院") -> ResumeVersion:
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            resume = ResumeVersion(
                id=uuid.uuid4().hex,
                sha256=uuid.uuid4().hex * 2,
                original_filename="resume.pdf",
                file_ext=".pdf",
                mime_type="application/pdf",
                size_bytes=len((text or "").encode()),
                vault_relpath=f"resumes/{uuid.uuid4().hex}/original.pdf",
                version_number=next(_version_counter),
                extraction_status=status,
                extracted_text=text if status == "EXTRACTED" else None,
                parser_name="test",
                parser_version="1",
            )
            session.add(resume)
            session.commit()
            session.refresh(resume)
            return resume
    finally:
        engine.dispose()


def bundle_content() -> str:
    return json.dumps(
        {
            "candidates": [
                {"field_key": "contact.email", "value": "name@example.com", "confidence": 0.99},
            ],
            "collections": [
                {
                    "kind": "education",
                    "payload": {"school": "三江学院", "major": "视觉传达设计"},
                    "confidence": 0.96,
                }
            ],
        },
        ensure_ascii=False,
    )


def completion(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def configure_provider(client, monkeypatch) -> None:
    store = MemorySecretStore()
    monkeypatch.setattr(ai_routes, "get_secret_store", lambda: store)
    assert client.put("/api/ai/provider", json=PROVIDER_PAYLOAD).status_code == 200


def patch_provider(monkeypatch, handler) -> None:
    def build(session) -> OpenAICompatibleExtractionProvider:
        config = session.get(AIProviderConfig, "default")
        assert config is not None
        return OpenAICompatibleExtractionProvider(
            config, "sk-test", transport=httpx.MockTransport(handler)
        )

    monkeypatch.setattr(ai_routes, "build_default_provider", build)


def test_extraction_run_requires_an_api_key(client, monkeypatch):
    resume = seed_resume()
    configure_provider(client, monkeypatch)

    response = client.post("/api/ai/extraction-runs", json={"resume_version_id": resume.id})
    assert response.status_code == 409


def test_extraction_run_rejects_unknown_or_unextractable_resumes(client, monkeypatch):
    configure_provider(client, monkeypatch)

    unknown = client.post("/api/ai/extraction-runs", json={"resume_version_id": "missing"})
    assert unknown.status_code == 404

    ocr = seed_resume(status="OCR_REQUIRED")
    unextractable = client.post("/api/ai/extraction-runs", json={"resume_version_id": ocr.id})
    assert unextractable.status_code == 422


def test_extraction_run_success_creates_pending_drafts_with_provenance(client, monkeypatch):
    resume = seed_resume()
    captured: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.content.decode("utf-8"))
        return completion(bundle_content())

    configure_provider(client, monkeypatch)
    patch_provider(monkeypatch, handler)

    response = client.post("/api/ai/extraction-runs", json={"resume_version_id": resume.id})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "SUCCEEDED"
    assert payload["provider"] == "openai_compatible"
    assert payload["model"] == "reasoning-model"
    assert payload["prompt_version"]
    assert payload["schema_version"]
    assert payload["input_hash"]
    assert payload["completed_at"]
    assert payload["error"] is None
    assert payload["scalar_draft_count"] == 1
    assert payload["collection_draft_count"] == 1
    assert len(captured) == 1
    assert "三江学院" in captured[0]

    drafts = client.get("/api/profile/drafts").json()
    assert len(drafts) == 1
    assert drafts[0]["extraction_run_id"] == payload["id"]
    assert drafts[0]["status"] == "PENDING"

    collection_drafts = client.get("/api/profile/collection-drafts").json()
    assert len(collection_drafts) == 1
    assert collection_drafts[0]["extraction_run_id"] == payload["id"]

    # No SSOT mutation without human accept.
    assert client.get("/api/profile/fields").json() == []
    assert client.get("/api/profile/collections/education").json() == []


def test_provider_failure_returns_the_failed_run_record(client, monkeypatch):
    resume = seed_resume()

    def handler(request: httpx.Request) -> httpx.Response:
        return completion("not json at all")

    configure_provider(client, monkeypatch)
    patch_provider(monkeypatch, handler)

    response = client.post("/api/ai/extraction-runs", json={"resume_version_id": resume.id})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "FAILED"
    assert "not valid JSON" in payload["error"]
    assert payload["completed_at"]
    assert payload["scalar_draft_count"] == 0
    assert payload["collection_draft_count"] == 0
    assert client.get("/api/profile/drafts").json() == []
    assert client.get("/api/profile/collection-drafts").json() == []

    listing = client.get(f"/api/ai/extraction-runs?resume_version_id={resume.id}").json()
    assert [run["id"] for run in listing] == [payload["id"]]
    assert listing[0]["status"] == "FAILED"


def test_extraction_runs_listing_filters_by_resume(client, monkeypatch):
    first = seed_resume()
    second = seed_resume()
    configure_provider(client, monkeypatch)
    patch_provider(monkeypatch, lambda request: completion(bundle_content()))

    assert client.post("/api/ai/extraction-runs", json={"resume_version_id": first.id}).status_code == 200
    assert client.post("/api/ai/extraction-runs", json={"resume_version_id": second.id}).status_code == 200

    all_runs = client.get("/api/ai/extraction-runs").json()
    assert len(all_runs) == 2
    only_first = client.get(f"/api/ai/extraction-runs?resume_version_id={first.id}").json()
    assert [run["resume_version_id"] for run in only_first] == [first.id]
    assert len(only_first) == 1
