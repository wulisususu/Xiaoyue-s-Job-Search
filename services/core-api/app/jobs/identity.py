from __future__ import annotations

import hashlib
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_LEGAL_SUFFIXES = (
    "股份有限公司",
    "有限责任公司",
    "有限公司",
    "公司",
)
_TRACKING_KEY = re.compile(r"^(?:utm_.+|source|from|ref|track)$", re.IGNORECASE)
_PUNCTUATION = re.compile(r"[\s·•・,，。.;；:：'\"“”‘’()（）\[\]【】{}<>《》]+")


def _compact(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "").strip()
    return _PUNCTUATION.sub("", text)


def normalize_company_name(value: str) -> str:
    text = _compact(value)
    for suffix in _LEGAL_SUFFIXES:
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    return text.lower()


def company_alias_candidates(value: str) -> set[str]:
    compact = _compact(value)
    normalized = normalize_company_name(value)
    aliases = {compact, normalized}
    if normalized.endswith("集团") and len(normalized) > len("集团"):
        aliases.add(normalized[: -len("集团")])
    return {item for item in aliases if item}


def normalize_job_url(url: str, provider: str = "") -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    parts = urlsplit(raw)
    if not parts.netloc:
        return raw
    scheme = (parts.scheme or "https").lower()
    host = parts.netloc.lower()
    query = parts.query
    fragment = parts.fragment
    if provider.strip().lower() == "company":
        kept = [
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if not _TRACKING_KEY.match(key)
        ]
        kept.sort()
        query = urlencode(kept)
        fragment = ""
    return urlunsplit((scheme, host, parts.path or "/", query, fragment))


# Portal-level entry points that many different jobs share. They are source
# evidence, never a job identity.
_GENERIC_PATH_SEGMENTS = {
    "campus", "xiaoyuan", "zhaopin", "recruit", "recruitment", "jobs", "job",
    "career", "careers", "xyz", "shezhao", "shetui", "social", "school",
    "yjs", "hr", "rencai", "zhaopinhui", "yingjie", "graduation", "gw",
    "zw", "index", "list", "main", "home", "default",
}


def is_generic_career_url(url: str) -> bool:
    parts = urlsplit((url or "").strip())
    path = parts.path.rstrip("/").lower()
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return True
    if len(segments) == 1 and segments[0] in _GENERIC_PATH_SEGMENTS:
        return True
    return False


def job_identity_url(url: str, provider: str = "company") -> str:
    """Normalized URL usable as job identity, or '' for generic portals.

    Generic career pages (e.g. https://company.com/campus) are shared by many
    real jobs, so they must never merge those jobs into one canonical record.
    """
    normalized = normalize_job_url(url, provider=provider)
    if not normalized or is_generic_career_url(normalized):
        return ""
    return normalized


def _field(value: str) -> str:
    return re.sub(r"\s+", "", (value or "").strip().lower())


def job_fingerprint(company_key: str, title: str, location: str = "", recruitment_batch: str = "") -> str:
    payload = "|".join((_field(company_key), _field(title), _field(location), _field(recruitment_batch)))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
