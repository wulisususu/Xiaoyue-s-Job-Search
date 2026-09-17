from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ProfileCollectionItem, ProfileCollectionRevision, utcnow
from .collections import get_collection_definition, validate_collection_payload


class ProfileCollectionItemNotFoundError(LookupError):
    pass


class ProfileCollectionOrderError(ValueError):
    pass


class DuplicateProfileCollectionValueError(RuntimeError):
    pass


def _dump(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _items_for_kind(session: Session, kind: str) -> list[ProfileCollectionItem]:
    get_collection_definition(kind)
    return list(
        session.scalars(
            select(ProfileCollectionItem)
            .where(ProfileCollectionItem.kind == kind)
            .order_by(ProfileCollectionItem.position, ProfileCollectionItem.id)
        ).all()
    )


def list_collection_items(session: Session, kind: str) -> list[ProfileCollectionItem]:
    return _items_for_kind(session, kind)


def _item_for_kind(session: Session, kind: str, item_id: int) -> ProfileCollectionItem:
    get_collection_definition(kind)
    item = session.get(ProfileCollectionItem, item_id)
    if item is None or item.kind != kind:
        raise ProfileCollectionItemNotFoundError(f"Profile collection item {item_id} not found in {kind}")
    return item


def _append_revision(
    session: Session,
    *,
    item_id: int,
    kind: str,
    old_payload_json: str | None,
    new_payload_json: str | None,
    old_position: int | None,
    new_position: int | None,
    source_type: str,
    source_ref: str | None,
    confidence: float | None,
    operation: str,
) -> ProfileCollectionRevision:
    revision = ProfileCollectionRevision(
        item_id=item_id,
        kind=kind,
        old_payload_json=old_payload_json,
        new_payload_json=new_payload_json,
        old_position=old_position,
        new_position=new_position,
        source_type=source_type,
        source_ref=source_ref,
        confidence=confidence,
        operation=operation,
    )
    session.add(revision)
    return revision


def _skill_name(payload_json: str) -> str | None:
    try:
        payload = json.loads(payload_json)
    except (TypeError, json.JSONDecodeError):
        return None
    name = payload.get("name") if isinstance(payload, dict) else None
    return name.casefold() if isinstance(name, str) else None


def _ensure_unique_skill(
    session: Session,
    *,
    kind: str,
    payload: dict,
    excluding_item_id: int | None = None,
) -> None:
    if kind != "skill":
        return
    candidate = payload.get("name")
    if not isinstance(candidate, str):
        return
    normalized = candidate.casefold()
    for item in _items_for_kind(session, "skill"):
        if excluding_item_id is not None and item.id == excluding_item_id:
            continue
        if _skill_name(item.payload_json) == normalized:
            raise DuplicateProfileCollectionValueError(f"Duplicate skill: {candidate}")


def create_collection_item_uncommitted(
    session: Session,
    kind: str,
    payload,
    *,
    source_type: str = "manual",
    source_ref: str | None = None,
    confidence: float | None = 1.0,
    confirmed: bool = True,
) -> ProfileCollectionItem:
    """Create an item and its CREATE revision without committing.

    Higher-level workflows such as AI-draft acceptance use this primitive so
    their review-state transition and the SSOT write share one transaction.
    Callers that own no surrounding transaction should use create_collection_item.
    """
    normalized = validate_collection_payload(kind, payload)
    _ensure_unique_skill(session, kind=kind, payload=normalized)
    existing = _items_for_kind(session, kind)
    item = ProfileCollectionItem(
        kind=kind,
        position=len(existing),
        payload_json=_dump(normalized),
        source_type=source_type,
        source_ref=source_ref,
        confidence=confidence,
        confirmed=confirmed,
    )
    session.add(item)
    session.flush()
    _append_revision(
        session,
        item_id=item.id,
        kind=kind,
        old_payload_json=None,
        new_payload_json=item.payload_json,
        old_position=None,
        new_position=item.position,
        source_type=source_type,
        source_ref=source_ref,
        confidence=confidence,
        operation="CREATE",
    )
    return item


def create_collection_item(
    session: Session,
    kind: str,
    payload,
    *,
    source_type: str = "manual",
    source_ref: str | None = None,
    confidence: float | None = 1.0,
    confirmed: bool = True,
) -> ProfileCollectionItem:
    try:
        item = create_collection_item_uncommitted(
            session,
            kind,
            payload,
            source_type=source_type,
            source_ref=source_ref,
            confidence=confidence,
            confirmed=confirmed,
        )
        session.commit()
        session.refresh(item)
        return item
    except Exception:
        session.rollback()
        raise


def update_collection_item(
    session: Session,
    kind: str,
    item_id: int,
    payload,
    *,
    source_type: str = "manual",
    source_ref: str | None = None,
    confidence: float | None = 1.0,
    confirmed: bool = True,
) -> ProfileCollectionItem:
    try:
        normalized = validate_collection_payload(kind, payload)
        item = _item_for_kind(session, kind, item_id)
        _ensure_unique_skill(session, kind=kind, payload=normalized, excluding_item_id=item.id)
        old_payload_json = item.payload_json
        old_position = item.position
        item.payload_json = _dump(normalized)
        item.source_type = source_type
        item.source_ref = source_ref
        item.confidence = confidence
        item.confirmed = confirmed
        item.updated_at = utcnow()
        _append_revision(
            session,
            item_id=item.id,
            kind=kind,
            old_payload_json=old_payload_json,
            new_payload_json=item.payload_json,
            old_position=old_position,
            new_position=item.position,
            source_type=source_type,
            source_ref=source_ref,
            confidence=confidence,
            operation="UPDATE",
        )
        session.commit()
        session.refresh(item)
        return item
    except Exception:
        session.rollback()
        raise


def reorder_collection_items(
    session: Session,
    kind: str,
    item_ids: list[int],
    *,
    source_type: str = "manual",
    source_ref: str | None = None,
    confidence: float | None = 1.0,
) -> list[ProfileCollectionItem]:
    try:
        items = _items_for_kind(session, kind)
        current_ids = [item.id for item in items]
        if len(item_ids) != len(set(item_ids)):
            raise ProfileCollectionOrderError("item_ids must not contain duplicates")
        if set(item_ids) != set(current_ids) or len(item_ids) != len(current_ids):
            raise ProfileCollectionOrderError("item_ids must contain every item in the collection exactly once")

        by_id = {item.id: item for item in items}
        for position, item_id in enumerate(item_ids):
            item = by_id[item_id]
            if item.position == position:
                continue
            old_position = item.position
            item.position = position
            item.updated_at = utcnow()
            _append_revision(
                session,
                item_id=item.id,
                kind=kind,
                old_payload_json=item.payload_json,
                new_payload_json=item.payload_json,
                old_position=old_position,
                new_position=position,
                source_type=source_type,
                source_ref=source_ref,
                confidence=confidence,
                operation="REORDER",
            )

        session.commit()
        return _items_for_kind(session, kind)
    except Exception:
        session.rollback()
        raise


def delete_collection_item(
    session: Session,
    kind: str,
    item_id: int,
    *,
    source_type: str = "manual",
    source_ref: str | None = None,
    confidence: float | None = 1.0,
) -> int:
    try:
        item = _item_for_kind(session, kind, item_id)
        deleted_id = item.id
        deleted_payload_json = item.payload_json
        deleted_position = item.position
        _append_revision(
            session,
            item_id=item.id,
            kind=kind,
            old_payload_json=deleted_payload_json,
            new_payload_json=None,
            old_position=deleted_position,
            new_position=None,
            source_type=source_type,
            source_ref=source_ref,
            confidence=confidence,
            operation="DELETE",
        )
        # Revisions keep item_id as an immutable audit identifier rather than
        # a live foreign key. Flushing before deleting makes the audit event
        # explicit while preserving the same transaction boundary.
        session.flush()
        session.delete(item)
        session.flush()

        remaining = _items_for_kind(session, kind)
        for position, current in enumerate(remaining):
            if current.position == position:
                continue
            old_position = current.position
            current.position = position
            current.updated_at = utcnow()
            _append_revision(
                session,
                item_id=current.id,
                kind=kind,
                old_payload_json=current.payload_json,
                new_payload_json=current.payload_json,
                old_position=old_position,
                new_position=position,
                source_type=source_type,
                source_ref=source_ref,
                confidence=confidence,
                operation="REORDER",
            )

        session.commit()
        return deleted_id
    except Exception:
        session.rollback()
        raise
