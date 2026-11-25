"""Test setup: temporary database, uploads folder and retrieval-only mode, set before the app is imported."""
import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="agriassist-test-")
os.environ["LLM_PROVIDER"] = "none"
os.environ["UPLOADS_DIR"] = os.path.join(_TMP, "uploads")
os.environ["DB_PATH"] = os.path.join(_TMP, "test.db")
os.environ["DATAGOV_API_KEY"] = ""
os.environ["AUTH_SECRET"] = "test-secret"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import DOCS_DIR  # noqa: E402
from app.ingest import build_chunks  # noqa: E402
from app.main import app  # noqa: E402
from app.retriever import Retriever  # noqa: E402

PLANTVILLAGE = Path(os.getenv("PLANTVILLAGE_DIR", "/home/claude/data_fetch/pv/raw/color"))


@pytest.fixture(scope="session")
def retriever():
    r = Retriever()
    chunks = []
    for path in sorted(DOCS_DIR.iterdir()):
        chunks.extend(build_chunks(path.name, path.read_bytes(), 120, 20))
    r.add(chunks)
    return r


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def auth_headers(client):
    """Registers one test farmer and returns the bearer header for all authenticated tests."""
    r = client.post("/api/auth/register", json={
        "name": "Test Farmer", "email": "farmer@example.com", "password": "password123", "language": "en"})
    if r.status_code == 409:
        r = client.post("/api/auth/login", json={"email": "farmer@example.com", "password": "password123"})
    return {"Authorization": f"Bearer {r.json()['token']}"}
