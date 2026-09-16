import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("XIAOYUE_DATA_DIR", str(tmp_path))
    return TestClient(create_app())
