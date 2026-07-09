"""
test_auth_gate.py
-----------------
Verifies the authentication gate actually protects the API — the one thing the
other tests deliberately bypass. These tests clear the auth override so the REAL
get_current_user runs.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.config import settings
from app.core import auth

client = TestClient(app)


@pytest.fixture(autouse=True)
def no_bypass(monkeypatch):
    """
    Undo conftest's auth bypass AND force AUTH_ENABLED=true, so these tests
    exercise the REAL auth gate (it's off by default in the product, but must
    still work correctly when a deployment turns it on).
    """
    monkeypatch.setattr(settings, "AUTH_ENABLED", True)
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def test_chat_requires_auth():
    r = client.post("/chat", json={"question": "hello"})
    assert r.status_code == 401


def test_export_rows_requires_auth():
    r = client.post("/export_rows", json={"rows": [{"a": 1}], "format": "excel"})
    assert r.status_code == 401


def test_bad_token_rejected():
    r = client.post(
        "/chat",
        json={"question": "hello"},
        headers={"Authorization": "Bearer not.a.real.token"},
    )
    assert r.status_code == 401


def test_health_is_public():
    assert client.get("/health").status_code == 200


def test_login_flow_issues_token():
    # Needs Redis. Create a throwaway user, log in, confirm a token comes back
    # and that it then passes the auth dependency.
    username, password = "pytest_gateuser", "pytest_pass_123"
    try:
        auth.delete_user(username)  # clean slate if a prior run left one
        auth.create_user(username, password, "Pytest Gate User")
    except Exception:
        pytest.skip("Redis not reachable — skipping live login test.")

    r = client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200
    token = r.json()["access_token"]

    # Wrong password is rejected.
    bad = client.post("/auth/login", json={"username": username, "password": "wrong"})
    assert bad.status_code == 401

    # A valid token passes the auth dependency (health needs none, so hit an
    # auth-only endpoint that doesn't require the DB/LLM: export_rows with data).
    ok = client.post(
        "/export_rows",
        json={"columns": ["a"], "rows": [{"a": 1}], "format": "excel"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert ok.status_code == 200

    auth.delete_user(username)
