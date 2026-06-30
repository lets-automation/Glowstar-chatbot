"""
test_api.py
-----------
Phase 4 test: the REST API works without crashing.

Uses FastAPI's TestClient (no real server needed).
  - /health always returns ok.
  - /chat returns a graceful 503 if no API key, or a structured answer
    if a key is configured.

Run from the project root with:
    python -m tests.test_api
"""

from fastapi.testclient import TestClient

from app.api.main import app
from app.config import settings

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_validation():
    # Empty question should be rejected by Pydantic (422).
    response = client.post("/chat", json={"question": ""})
    assert response.status_code == 422


def test_chat_behaviour():
    response = client.post("/chat", json={"question": "How many packets are in tblPacket?"})

    if not settings.GROQ_API_KEY:
        # No key yet -> must be a clean 503, NOT a crash.
        assert response.status_code == 503
        assert "GROQ_API_KEY" in response.json()["detail"]
        print("No API key -> /chat returned graceful 503 (as expected).")
    else:
        # Key present -> must return a structured answer.
        assert response.status_code == 200
        body = response.json()
        assert "answer" in body
        assert "sql_used" in body
        assert "rows_returned" in body
        print("API key present -> /chat answered:", body["answer"][:120])


def run_all():
    test_health()
    test_chat_validation()
    test_chat_behaviour()
    print("SUCCESS - API tests passed.")
    print("  - GET /health -> ok")
    print("  - POST /chat with empty question -> 422")
    print("  - POST /chat -> graceful response (503 without key, answer with key)")


if __name__ == "__main__":
    run_all()
