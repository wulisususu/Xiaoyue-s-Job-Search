from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ProfileCollectionItem, ProfileField
from .models import ConfirmedProfileSnapshot


def build_confirmed_profile_snapshot(session: Session) -> ConfirmedProfileSnapshot:
    """Materialize the Browser Agent's only profile input.

    Draft rows are intentionally not queried at all.  Even within the formal
    SSOT tables, only confirmed rows are exposed to browser automation.
    """
    scalar_rows = session.scalars(
        select(ProfileField)
        .where(ProfileField.confirmed.is_(True))
        .order_by(ProfileField.field_key)
    ).all()
    scalars: dict[str, object] = {}
    for row in scalar_rows:
        try:
            scalars[row.field_key] = json.loads(row.value_json)
        except (TypeError, json.JSONDecodeError):
            continue

    collection_rows = session.scalars(
        select(ProfileCollectionItem)
        .where(ProfileCollectionItem.confirmed.is_(True))
        .order_by(ProfileCollectionItem.kind, ProfileCollectionItem.position, ProfileCollectionItem.id)
    ).all()
    collections: dict[str, list[dict[str, object]]] = {}
    for row in collection_rows:
        try:
            payload = json.loads(row.payload_json)
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        collections.setdefault(row.kind, []).append(payload)

    return ConfirmedProfileSnapshot(scalars=scalars, collections=collections)
