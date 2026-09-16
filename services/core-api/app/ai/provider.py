from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit


def normalize_base_url(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        raise ValueError("AI provider Base URL is required")

    parsed = urlsplit(raw)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("AI provider Base URL must use http or https")
    if not parsed.hostname:
        raise ValueError("AI provider Base URL must include a host")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("AI provider Base URL must not include credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("AI provider Base URL must not include query strings or fragments")

    path = parsed.path.rstrip("/")
    normalized = urlunsplit((parsed.scheme.lower(), parsed.netloc, path, "", ""))
    return normalized.rstrip("/")


def chat_completions_url(base_url: str) -> str:
    normalized = normalize_base_url(base_url)
    if normalized.endswith("/v1"):
        return f"{normalized}/chat/completions"
    return f"{normalized}/v1/chat/completions"
