from __future__ import annotations

import hashlib
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

from .ats import detect_ats
from .classifier import classify_page
from .url_guard import validate_external_url


@dataclass(slots=True)
class HttpResponse:
    status_code: int
    final_url: str
    body: str
    redirect_chain: list[str]


@dataclass(slots=True)
class VerificationResult:
    checked_url: str
    final_url: str
    redirect_chain: list[str]
    http_status: int | None
    health: str
    ats: str | None
    page_type: str
    apply_evidence: list[str]
    content_fingerprint: str | None
    error: str | None = None
    body: str = ""


Transport = Callable[[str], HttpResponse]


class _RedirectRecorder(urllib.request.HTTPRedirectHandler):
    """HTTPRedirectHandler that records every hop and re-validates it.

    Each redirect target is parsed, resolved against the previous URL and
    passed through the SSRF guard BEFORE following it, so a redirect into
    127.0.0.1 / 169.254.169.254 / file: etc. is refused instead of fetched.
    """

    def __init__(self, chain: list[str]) -> None:
        self.chain = chain

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: N802 (urllib API)
        self.chain.append(newurl)
        validate_external_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _default_transport(url: str) -> HttpResponse:
    validate_external_url(url)
    chain = [url]
    recorder = _RedirectRecorder(chain)
    opener = urllib.request.build_opener(recorder)
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 XiaoyueJobSearch/0.1"})
    try:
        with opener.open(request, timeout=20) as response:
            final_url = response.geturl()
            validate_external_url(final_url)
            body = response.read(2_000_000).decode(response.headers.get_content_charset() or "utf-8", "ignore")
            if final_url != chain[-1]:
                chain.append(final_url)
            return HttpResponse(int(response.status), final_url, body, chain)
    except urllib.error.HTTPError as exc:
        final_url = exc.geturl() or url
        body = ""
        try:
            body = exc.read(512_000).decode(exc.headers.get_content_charset() or "utf-8", "ignore")
        except Exception:
            pass
        if final_url != chain[-1]:
            chain.append(final_url)
        return HttpResponse(int(exc.code), final_url, body, chain)


def _fingerprint(body: str) -> str | None:
    if not body:
        return None
    normalized = " ".join(body.split())[:500_000]
    return hashlib.sha256(normalized.encode("utf-8", "ignore")).hexdigest()


def verify_url(url: str, transport: Transport | None = None) -> VerificationResult:
    try:
        validate_external_url(url)
        response = (transport or _default_transport)(url)
    except Exception as exc:
        return VerificationResult(checked_url=url, final_url="", redirect_chain=[url], http_status=None, health="BROKEN", ats=None, page_type="unknown", apply_evidence=[], content_fingerprint=None, error=str(exc), body="")

    ats = detect_ats(response.final_url, response.body)
    classification = classify_page(response.body)
    status = response.status_code
    if status in (401, 403, 429):
        health = "ACCESS_BLOCKED"
    elif status >= 400:
        health = "BROKEN"
    elif classification.page_type == "closed":
        health = "STALE"
    elif classification.page_type == "login":
        health = "LOGIN_REQUIRED"
    elif classification.page_type == "spa_shell":
        # JS-rendered page: static HTML carries no trustworthy evidence, so
        # neither verify nor fail it — defer to the browser agent.
        health = "REQUIRES_BROWSER"
    elif classification.page_type == "job_detail" and classification.apply_evidence:
        health = "VERIFIED_APPLY"
    elif response.final_url and response.final_url != url:
        health = "REDIRECTED"
    else:
        health = "HEALTHY"
    return VerificationResult(checked_url=url, final_url=response.final_url, redirect_chain=response.redirect_chain, http_status=status, health=health, ats=ats, page_type=classification.page_type, apply_evidence=classification.apply_evidence, content_fingerprint=_fingerprint(response.body), body=response.body)
