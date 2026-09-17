import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture(autouse=True)
def _bypass_url_guard_dns(monkeypatch):
    """Default for HTTP-transport tests: fake transports use fake hosts
    (example.com subdomains) whose DNS does not resolve in CI, and the SSRF
    guard would refuse them before the transport runs. SSRF/guard coverage
    lives in test_verification_hardening.py, which calls the real
    validate_external_url directly and is NOT affected by this patch.
    Never weaken the production guard to make tests pass."""
    monkeypatch.setattr(
        "app.verification.verifier.validate_external_url",
        lambda url: None,
    )


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("XIAOYUE_DATA_DIR", str(tmp_path))
    return TestClient(create_app())
