from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..integrations.types import ImportSummary
from ..integrations.workfind import import_workfind
from ..integrations.xiaozhao import import_xiaozhao_payload
from ..models import SourceSnapshot
from .store import record_sync_failure, record_sync_success
from .tencent_sheet import fetch_tencent_payload

PayloadLoader = Callable[[], dict]
ByteFetcher = Callable[[str], bytes]

WORKFIND_BASE = "https://gitee.com/zxasoul/workfind/raw/master/"
WORKFIND_PATHS = {"db": "国企数据库.db", "relations": "央企二级子公司.json"}


@dataclass(slots=True)
class SyncResult:
    source_name: str
    status: str
    content_hash: str | None = None
    records_seen: int = 0
    companies_created: int = 0
    jobs_created: int = 0
    sources_created: int = 0
    relations_created: int = 0
    error: str | None = None


def _json_payload_bytes(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _hash_bytes(*parts: bytes) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(len(part).to_bytes(8, "big"))
        digest.update(part)
    return digest.hexdigest()


def _snapshot_exists(session: Session, source_name: str, content_hash: str) -> bool:
    return session.scalar(select(SourceSnapshot.id).where(SourceSnapshot.source_name == source_name, SourceSnapshot.content_hash == content_hash)) is not None


def _result(source_name: str, status: str, content_hash: str | None, summary: ImportSummary | None = None, error: str | None = None) -> SyncResult:
    summary = summary or ImportSummary()
    return SyncResult(source_name=source_name, status=status, content_hash=content_hash, records_seen=summary.records_seen, companies_created=summary.companies_created, jobs_created=summary.jobs_created, sources_created=summary.sources_created, relations_created=summary.relations_created, error=error)


def sync_tencent_source(session: Session, payload_loader: PayloadLoader | None = None) -> SyncResult:
    source_name = "tencent-sheet"
    loader = payload_loader or fetch_tencent_payload
    try:
        payload = loader()
        raw = _json_payload_bytes(payload)
        content_hash = _hash_bytes(raw)
        if _snapshot_exists(session, source_name, content_hash):
            run = record_sync_success(session, source_name, content_hash, raw.decode("utf-8"), remote_version=str(payload.get("updated") or "") or None, items_seen=int(payload.get("count") or 0))
            return _result(source_name, run.status, content_hash)
        summary = import_xiaozhao_payload(session, payload, source_name=source_name)
        run = record_sync_success(session, source_name, content_hash, raw.decode("utf-8"), remote_version=str(payload.get("updated") or "") or None, items_seen=summary.records_seen, items_created=summary.jobs_created)
        return _result(source_name, run.status, content_hash, summary)
    except Exception as exc:
        session.rollback()
        record_sync_failure(session, source_name, str(exc))
        return _result(source_name, "FAILED", None, error=str(exc))


def _default_workfind_fetcher(kind: str) -> bytes:
    path = WORKFIND_PATHS[kind]
    url = WORKFIND_BASE + urllib.parse.quote(path)
    request = urllib.request.Request(url, headers={"User-Agent": "XiaoyueJobSearch/0.1"})
    with urllib.request.urlopen(request, timeout=45) as response:
        return response.read()


def sync_workfind_bundle(session: Session, cache_dir: Path, fetch_bytes: ByteFetcher | None = None) -> SyncResult:
    source_name = "workfind-online"
    fetcher = fetch_bytes or _default_workfind_fetcher
    try:
        db_bytes = fetcher("db")
        relations_bytes = fetcher("relations")
        json.loads(relations_bytes.decode("utf-8"))
        content_hash = _hash_bytes(db_bytes, relations_bytes)
        current = cache_dir / "current"
        current.mkdir(parents=True, exist_ok=True)
        db_path = current / WORKFIND_PATHS["db"]
        relations_path = current / WORKFIND_PATHS["relations"]
        db_path.write_bytes(db_bytes)
        relations_path.write_bytes(relations_bytes)
        payload_text = json.dumps({"db_sha256": hashlib.sha256(db_bytes).hexdigest(), "relations_sha256": hashlib.sha256(relations_bytes).hexdigest()})
        if _snapshot_exists(session, source_name, content_hash):
            run = record_sync_success(session, source_name, content_hash, payload_text=payload_text, local_path=str(current))
            return _result(source_name, run.status, content_hash)
        summary = import_workfind(session, db_path, relations_path)
        run = record_sync_success(session, source_name, content_hash, payload_text=payload_text, items_seen=summary.records_seen, items_created=summary.companies_created, local_path=str(current))
        return _result(source_name, run.status, content_hash, summary)
    except Exception as exc:
        session.rollback()
        record_sync_failure(session, source_name, str(exc))
        return _result(source_name, "FAILED", None, error=str(exc))
