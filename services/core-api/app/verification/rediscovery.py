from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from .ats import detect_ats


@dataclass(slots=True)
class RediscoveryLink:
    url: str
    source_kind: str
    score: int
    reason: str


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a": return
        self._href = next((value for key, value in attrs if key.lower() == "href" and value), None)
        self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None: self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href is not None:
            self.links.append((self._href, " ".join(self._text).strip()))
            self._href = None; self._text = []


def extract_rediscovery_candidates(base_url: str, html: str) -> list[RediscoveryLink]:
    parser = _AnchorParser(); parser.feed(html or "")
    base_host = urlparse(base_url).netloc.lower(); best: dict[str, RediscoveryLink] = {}
    for href, label in parser.links:
        if not href or href.startswith(("javascript:", "mailto:", "tel:")): continue
        url = urljoin(base_url, href); parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}: continue
        combined = f"{label} {parsed.path}".lower(); ats = detect_ats(url, ""); same_domain = parsed.netloc.lower() == base_host
        has_career = any(token in combined for token in ("招聘", "校园", "career", "campus", "jobs", "job"))
        has_apply = any(token in combined for token in ("申请", "投递", "apply", "resume"))
        if not ats and not (same_domain and (has_career or has_apply)): continue
        score = 0; reason: list[str] = []; source_kind = "same_domain"
        if ats: score += 60; source_kind = "ats_link"; reason.append(f"ATS:{ats}")
        if has_apply: score += 30; reason.append("apply keyword")
        if has_career: score += 20; reason.append("career keyword")
        if same_domain: score += 10; reason.append("same domain")
        normalized = parsed._replace(fragment="").geturl(); candidate = RediscoveryLink(normalized, source_kind, score, ", ".join(reason))
        existing = best.get(normalized)
        if existing is None or candidate.score > existing.score: best[normalized] = candidate
    return sorted(best.values(), key=lambda item: (-item.score, item.url))


def persist_rediscovery_candidates(session, job_id: str, candidates: list[RediscoveryLink]) -> int:
    from sqlalchemy import select
    from ..models import RediscoveryCandidate
    created = 0
    for candidate in candidates:
        existing = session.scalar(select(RediscoveryCandidate).where(RediscoveryCandidate.job_id == job_id, RediscoveryCandidate.url == candidate.url))
        if existing is None:
            session.add(RediscoveryCandidate(job_id=job_id, url=candidate.url, source_kind=candidate.source_kind, score=candidate.score, reason=candidate.reason)); created += 1
        elif candidate.score > existing.score:
            existing.score = candidate.score; existing.reason = candidate.reason; existing.source_kind = candidate.source_kind
    session.flush(); return created
