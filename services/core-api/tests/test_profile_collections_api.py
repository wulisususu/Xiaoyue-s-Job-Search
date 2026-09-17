from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_engine
from app.models import ProfileCollectionRevision


def test_collection_definitions_expose_all_repeatable_profile_sections(client):
    response = client.get("/api/profile/collections/definitions")
    assert response.status_code == 200
    body = response.json()
    assert [item["kind"] for item in body] == [
        "education",
        "experience",
        "project",
        "award",
        "certificate",
        "language",
        "skill",
    ]
    education = body[0]
    assert education["label"] == "教育经历"
    assert education["fields"][0] == {
        "key": "school",
        "label": "学校",
        "value_type": "string",
        "required": True,
        "multiple": False,
    }


def test_collection_crud_reorder_and_revisions_are_atomic(client):
    assert client.get("/api/profile/collections/education").json() == []

    first = client.post(
        "/api/profile/collections/education",
        json={"payload": {"school": " 三江学院 ", "major": "视觉传达设计"}},
    )
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["position"] == 0
    assert first_body["payload"] == {"school": "三江学院", "major": "视觉传达设计"}
    assert first_body["source_type"] == "manual"
    assert first_body["confidence"] == 1.0
    assert first_body["confirmed"] is True

    second = client.post(
        "/api/profile/collections/education",
        json={"payload": {"school": "第二学校", "degree": "本科"}},
    )
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["position"] == 1
    assert second_body["id"] != first_body["id"]

    listing = client.get("/api/profile/collections/education")
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()] == [first_body["id"], second_body["id"]]

    updated = client.put(
        f"/api/profile/collections/education/{first_body['id']}",
        json={"payload": {"school": "三江学院", "degree": "本科", "major": "视觉传达设计"}},
    )
    assert updated.status_code == 200
    assert updated.json()["id"] == first_body["id"]
    assert updated.json()["position"] == 0
    assert updated.json()["payload"]["degree"] == "本科"

    reordered = client.put(
        "/api/profile/collections/education/order",
        json={"item_ids": [second_body["id"], first_body["id"]]},
    )
    assert reordered.status_code == 200
    assert [item["id"] for item in reordered.json()] == [second_body["id"], first_body["id"]]
    assert [item["position"] for item in reordered.json()] == [0, 1]

    deleted = client.delete(f"/api/profile/collections/education/{first_body['id']}")
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted_id": first_body["id"]}

    remaining = client.get("/api/profile/collections/education")
    assert [item["id"] for item in remaining.json()] == [second_body["id"]]
    assert remaining.json()[0]["position"] == 0

    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            revisions = session.scalars(
                select(ProfileCollectionRevision).order_by(ProfileCollectionRevision.id)
            ).all()
            assert [row.operation for row in revisions] == [
                "CREATE",
                "CREATE",
                "UPDATE",
                "REORDER",
                "REORDER",
                "DELETE",
                "REORDER",
            ]
    finally:
        engine.dispose()


def test_collection_api_rejects_invalid_kind_payload_order_and_duplicate_skill(client):
    unknown_kind = client.get("/api/profile/collections/not-real")
    assert unknown_kind.status_code == 422

    unknown_field = client.post(
        "/api/profile/collections/education",
        json={"payload": {"school": "三江学院", "oops": "x"}},
    )
    assert unknown_field.status_code == 422
    assert "unknown fields" in unknown_field.json()["detail"]

    missing_required = client.post(
        "/api/profile/collections/experience",
        json={"payload": {"role": "设计"}},
    )
    assert missing_required.status_code == 422
    assert "organization" in missing_required.json()["detail"]

    first_skill = client.post(
        "/api/profile/collections/skill",
        json={"payload": {"name": "Python", "level": "熟练"}},
    )
    assert first_skill.status_code == 200

    duplicate_skill = client.post(
        "/api/profile/collections/skill",
        json={"payload": {"name": " python ", "level": "了解"}},
    )
    assert duplicate_skill.status_code == 409

    missing_item = client.put(
        "/api/profile/collections/education/999999",
        json={"payload": {"school": "不存在"}},
    )
    assert missing_item.status_code == 404

    education = client.post(
        "/api/profile/collections/education",
        json={"payload": {"school": "学校A"}},
    ).json()
    bad_order = client.put(
        "/api/profile/collections/education/order",
        json={"item_ids": [education["id"], education["id"]]},
    )
    assert bad_order.status_code == 422


def test_scalar_profile_api_remains_compatible_after_collection_crud(client):
    saved = client.put("/api/profile/fields/identity.name", json={"value": "赵新悦"})
    assert saved.status_code == 200

    created = client.post(
        "/api/profile/collections/education",
        json={"payload": {"school": "三江学院"}},
    )
    assert created.status_code == 200

    fields = client.get("/api/profile/fields")
    assert fields.status_code == 200
    assert fields.json()[0]["field_key"] == "identity.name"
    assert fields.json()[0]["value"] == "赵新悦"
