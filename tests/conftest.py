"""
conftest.py
-----------
Shared pytest fixtures.

Every protected endpoint now depends on auth (get_current_user) and, for the
expensive ones, rate limiting (enforce_rate_limit). The feature tests here are
about the endpoints' OWN behaviour (export works, chat answers, etc.), not about
auth — so we bypass auth for them with FastAPI dependency overrides, injecting a
fake logged-in user. The auth gate itself is covered separately in
test_auth_gate.py (which does NOT use this bypass).
"""

import pytest

from app.api.main import app
from app.core.auth import get_current_user
from app.core.rate_limit import enforce_rate_limit

_FAKE_USER = {"username": "tester", "display_name": "Tester"}


@pytest.fixture(autouse=True)
def bypass_auth():
    """Treat every request as an authenticated user for the feature tests."""
    app.dependency_overrides[get_current_user] = lambda: _FAKE_USER
    app.dependency_overrides[enforce_rate_limit] = lambda: _FAKE_USER
    yield
    app.dependency_overrides.clear()
