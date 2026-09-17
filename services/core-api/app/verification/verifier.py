from __future__ import annotations

import functools
import hashlib
import http.client
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable

from .ats import detect_ats
from .classifier import classify_page
from .url_guard import resolve_global_addresses, validate_external_url

_HTTPConnection = http.client.HTTPConnection
_HTTPSConnection = http.client.HTTPSConnection


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


def _resolve_pinned_ip(hostname: str) -> str:
    """Anti DNS-rebinding: resolve once, validate, and hand back the exact
    address the socket must connect to."""
    return resolve_global_addresses(hostname)[0]


class _PinnedHTTPConnection(_HTTPConnection):
    """HTTP connection whose socket targets a pre-validated IP address."""

    def __init__(self, *args, pinned_ip: str, **kwargs):
        super().__init__(*args, **kwargs)
        self._pinned_ip = pinned_ip

    def connect(self) -> None:
        self.sock = socket.create_connection(
            (self._pinned_ip, self.port), self.timeout, self.source_address
        )
        if self._tunnel_host:
            self._tunnel()


class _PinnedHTTPSConnection(_HTTPSConnection):
    """HTTPS connection targeting a pre-validated IP while keeping the
    original hostname for the TLS SNI extension and certificate check."""

    def __init__(self, *args, pinned_ip: str, **kwargs):
        super().__init__(*args, **kwargs)
        self._pinned_ip = pinned_ip

    def connect(self) -> None:
        sock = socket.create_connection(
            (self._pinned_ip, self.port), self.timeout, self.source_address
        )
        if self._tunnel_host:
            self.sock = sock
            self._tunnel()
            sock = self.sock
        server_hostname = self.host
        self.sock = self._context.wrap_socket(sock, server_hostname=server_hostname)


class _PinningHTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req):  # noqa: N802 (urllib API)
        hostname = urllib.parse.urlsplit(req.full_url).hostname
        pinned = _resolve_pinned_ip(hostname)
        return self.do_open(
            functools.partial(_PinnedHTTPConnection, pinned_ip=pinned), req
        )


class _PinningHTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):  # noqa: N802 (urllib API)
        hostname = urllib.parse.urlsplit(req.full_url).hostname
        pinned = _resolve_pinned_ip(hostname)
        return self.do_open(
            functools.partial(_PinnedHTTPSConnection, pinned_ip=pinned),
            req,
            context=self._context,
        )


def _default_transport(url: str) -> HttpResponse:
    validate_external_url(url)
    chain = [url]
    recorder = _RedirectRecorder(chain)
    # The pinning handlers resolve-and-validate at connect time, binding the
    # DNS answer to the actual socket target (no TOCTOU between validate and
    # connect). Every redirect hop re-runs both.
    opener = urllib.request.build_opener(recorder, _PinningHTTPHandler, _PinningHTTPSHandler)
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
