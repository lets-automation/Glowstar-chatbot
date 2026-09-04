"""
test_provider_error_classification.py
-------------------------------------
A WRONG DIAGNOSIS SENDS WHOEVER IS ON CALL TO THE WRONG FILE.

Measured live 2026-09-03. The RunPod pod serving qwen3-30b stopped responding
and its proxy returned the "Waiting for service to respond" HTML page. The
backend reported:

    PROVIDER CALL FAILED | provider=ollama model=qwen3-30b category=auth
       -> CONFIG problem: check LLM_PROVIDER, the model id, and the API key in
          .env (the model may have been renamed/retired by the provider).

The config was perfect. The pod was down. The cause: that HTML page contains
the digits "401" inside an SVG path coordinate, "401" is a bare substring
needle for the `auth` category, and `auth` is ordered BEFORE `connection` - so
three digits of vector art outranked the actual 502.

Two fixes, both pinned here:
  1. An HTML body means a GATEWAY answered, not the API. Never run provider
     needles against markup - classify it as unreachable.
  2. A bare three-digit needle matches any three digits anywhere. Status codes
     count only when they read like a status.
"""
import pytest

from app.core.logging_util import classify_provider_error

# The distinguishing fragment of the real RunPod page, SVG coordinate included.
RUNPOD_502 = """<!DOCTYPE html>
<html lang="en"><head><title>Waiting for service to respond - RunPod</title></head>
<body><svg><path d="M401.5 129.54C393 144.32 381.56 150.71 368.64 150.71Z"/></svg>
<p>Waiting for service to respond</p></body></html>"""


class TestAGatewayPageIsNotAnAuthFailure:

    def test_the_runpod_page_is_unreachable_not_auth(self):
        assert classify_provider_error(Exception(RUNPOD_502)).category == "unreachable"

    def test_any_html_body_is_unreachable(self):
        for body in ("<!doctype html><html><body>502 Bad Gateway</body></html>",
                     "<html>\n<head><title>504 Gateway Time-out</title></head>"):
            assert classify_provider_error(Exception(body)).category == "unreachable"

    def test_the_user_message_does_not_blame_the_config(self):
        """'misconfigured, contact support' for a stopped pod is a wrong
        instruction, not just an imprecise one."""
        msg = classify_provider_error(Exception(RUNPOD_502)).user_message.lower()
        assert "misconfigur" not in msg
        assert "reach" in msg or "try again" in msg


class TestRealFailuresStillClassifyCorrectly:
    """The fix must not blunt the categories that were working."""

    @pytest.mark.parametrize("text,want", [
        ('Error code: 401 - {"error":"Invalid API key"}', "auth"),
        ("Unauthorized", "auth"),
        ("invalid api key provided", "auth"),
        ("The model qwen3-30b does not exist", "model_not_found"),
        ("Error code: 429 - rate limit exceeded", "rate_limit"),
        ("Error code: 413 - request too large", "context_too_large"),
        ("Connection refused", "connection"),
        ("Error code: 502 - Bad Gateway", "connection"),
        ("read operation timed out", "connection"),
    ])
    def test_category(self, text, want):
        assert classify_provider_error(Exception(text)).category == want


class TestBareDigitsAreNotStatusCodes:
    """Three digits in an id, a coordinate or a timestamp are not a status."""

    @pytest.mark.parametrize("text", [
        "request id 401f3a90 completed",
        "path d=M401.5 129.54 L504.2 88.1",
        "packet 429 of kapan NI26 was updated",
    ])
    def test_they_do_not_trigger_a_category(self, text):
        assert classify_provider_error(Exception(text)).category == "unknown"

    def test_a_status_shaped_code_still_counts(self):
        for text in ("http 401", "status: 429", "error code: 503"):
            assert classify_provider_error(Exception(text)).category != "unknown"
