from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.secrets import CredentialStoreUnavailableError, get_secret_store
from ..models import ProfileCollectionItem, ProfileField
from ..profile.registry import get_field_definition
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
    secret_store = None
    for row in scalar_rows:
        try:
            definition = get_field_definition(row.field_key)
        except KeyError:
            continue
        if definition.sensitive:
            if not row.secret_ref:
                continue
            try:
                if secret_store is None:
                    secret_store = get_secret_store()
                secret = secret_store.get_secret(row.secret_ref)
            except CredentialStoreUnavailableError:
                continue
            if secret:
                scalars[row.field_key] = secret
            continue
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
