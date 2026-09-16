from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


BLOCKED_SCHEMES = {"file", "ftp", "gopher", "data", "javascript"}


def validate_external_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme.lower() in BLOCKED_SCHEMES:
        raise ValueError("unsupported URL scheme")
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("only http/https URLs are allowed")
    if not parsed.hostname:
        raise ValueError("missing hostname")

    hostname = parsed.hostname
    try:
        addresses = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ValueError("hostname resolution failed") from exc

    for item in addresses:
        address = item[4][0]
        ip = ipaddress.ip_address(address)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise ValueError("private or reserved address is not allowed")
