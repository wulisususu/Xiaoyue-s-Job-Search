from __future__ import annotations

import ipaddress
import re
import time
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

import httpx

from .errors import ProviderRequestError, ProviderResponseError, ProviderTimeoutError


def _is_loopback_provider_host(hostname: str) -> bool:
    host = hostname.strip().lower().rstrip(".")
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def normalize_base_url(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        raise ValueError("AI provider Base URL is required")

    parsed = urlsplit(raw)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise ValueError("AI provider Base URL must use http or https")
    if not parsed.hostname:
        raise ValueError("AI provider Base URL must include a host")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("AI provider Base URL must not include credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("AI provider Base URL must not include query strings or fragments")
    if scheme == "http" and not _is_loopback_provider_host(parsed.hostname):
        raise ValueError(
            "Remote AI provider Base URL must use HTTPS; HTTP is only allowed "
            "for localhost or loopback addresses"
        )

    path = parsed.path.rstrip("/")
    normalized = urlunsplit((scheme, parsed.netloc, path, "", ""))
    return normalized.rstrip("/")


def chat_completions_url(base_url: str) -> str:
    """Build the OpenAI-compatible chat-completions endpoint.

    Provider roots are not uniform: OpenAI/xAI/Mistral end in /v1, Doubao
    ends in /v3, GLM ends in /v4, Gemini ends in /v1beta/openai, while
    DeepSeek commonly documents a host-only root.  Treat an explicit API
    version (or Gemini's /openai shim) as authoritative; otherwise retain the
    conventional /v1 fallback used by local/custom OpenAI-compatible servers.
    """
    normalized = normalize_base_url(base_url)
    path = urlsplit(normalized).path.rstrip("/")
    last_segment = path.rsplit("/", 1)[-1].lower() if path else ""
    explicit_api_root = bool(re.fullmatch(r"v\d+(?:beta\d*)?", last_segment)) or last_segment == "openai"
    if explicit_api_root:
        return f"{normalized}/chat/completions"
    return f"{normalized}/v1/chat/completions"


@dataclass(frozen=True)
class ProviderProbeResult:
    status_code: int
    latency_ms: int


def probe_provider(
    *,
    base_url: str,
    api_key: str,
    model: str,
    timeout_seconds: int,
    transport: httpx.BaseTransport | None = None,
) -> ProviderProbeResult:
    """Perform a tiny compatibility probe without running resume extraction."""
    secret = (api_key or "").strip()
    if not secret:
        raise ValueError("AI provider API key is required")
    model_id = (model or "").strip()
    if not model_id:
        raise ValueError("AI provider model is required")

    try:
        endpoint = chat_completions_url(base_url)
    except ValueError as exc:
        raise ProviderRequestError(str(exc)) from exc

    started = time.perf_counter()
    try:
        with httpx.Client(
            transport=transport,
            timeout=float(timeout_seconds),
            headers={
                "Authorization": f"Bearer {secret}",
                "Content-Type": "application/json",
            },
        ) as client:
            response = client.post(
                endpoint,
                json={
                    "model": model_id,
                    "messages": [{"role": "user", "content": "Reply with OK."}],
                },
            )
    except httpx.TimeoutException as exc:
        raise ProviderTimeoutError("AI provider connection test timed out") from exc
    except httpx.RequestError as exc:
        raise ProviderRequestError("AI provider connection test failed") from exc

    if response.status_code >= 400:
        raise ProviderRequestError(f"AI provider returned HTTP {response.status_code}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise ProviderResponseError("AI provider returned invalid JSON") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("choices"), list):
        raise ProviderResponseError("AI provider response is not OpenAI-compatible")

    return ProviderProbeResult(
        status_code=response.status_code,
        latency_ms=max(0, round((time.perf_counter() - started) * 1000)),
    )
