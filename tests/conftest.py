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


# --- Live-LLM guard ---------------------------------------------------------
# Some tests call the real provider. On the free tier that is ~20 requests/DAY
# TOTAL, shared with the client demo — so a routine `pytest tests/` run was
# quietly eating the quota the demo needed (and then the demo failed).
#
# Live tests are now OPT-IN. Run them deliberately when you have quota:
#     RUN_LIVE_LLM_TESTS=true python -m pytest tests/ -q
import os


def pytest_collection_modifyitems(config, items):
    if os.getenv("RUN_LIVE_LLM_TESTS", "").strip().lower() in ("1", "true", "yes"):
        return
    skip = pytest.mark.skip(
        reason="calls the live LLM (costs demo quota) — set RUN_LIVE_LLM_TESTS=true to run"
    )
    for item in items:
        if "live_llm" in item.keywords:
            item.add_marker(skip)
