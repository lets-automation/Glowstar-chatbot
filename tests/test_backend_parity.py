"""
test_backend_parity.py
----------------------
Every provider must carry the SAME safety behaviour.

This file exists because of a measured failure. Fixes for a crash and a false
denial were committed one morning and, three hours later, were present in
groq_backend only - gemini and anthropic still had both bugs. Nothing failed:
the tests were green, because each fix was tested through whichever backend
happened to run.

The root cause was structural. The shared logic lived INSIDE groq_backend and
the other two imported private names out of it, so "shared" was a convention
rather than something enforced. loop_policy.py now owns the policy; these tests
guard the parts that still have to be repeated in each provider's own loop.

Source-level assertions are blunt, and deliberately so: the alternative is
running three live providers, which costs money and quota and cannot run in CI.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKENDS = ["groq", "gemini", "anthropic"]


def _src(name: str) -> str:
    return (ROOT / "app" / "agent" / f"{name}_backend.py").read_text(encoding="utf-8")


@pytest.mark.parametrize("backend", BACKENDS)
def test_shared_policy_comes_from_loop_policy(backend):
    """No backend may define its own copy of the nudges or the grounding checks,
    and none may import them from another backend."""
    src = _src(backend)
    assert "loop_policy" in src, f"{backend} does not use the shared policy module"
    for other in BACKENDS:
        assert f"from app.agent.{other}_backend import" not in src, (
            f"{backend} imports from {other}_backend - policy belongs in loop_policy"
        )


@pytest.mark.parametrize("backend", BACKENDS)
def test_an_empty_answer_does_not_end_the_turn(backend):
    """
    A model that stops calling tools and writes NOTHING must not be returned as
    a blank answer. With data it breaks to the forced write-up; with nothing it
    nudges the model to actually run the query.

    Employee-360 ("report of employee M4117") is the case: 32 rows gathered
    across 2 queries, then no prose at all.
    """
    src = _src(backend)
    assert "if not answer" in src, (
        f"{backend} returns a blank answer instead of forcing the write-up"
    )


@pytest.mark.parametrize("backend", BACKENDS)
def test_no_false_denial_when_nothing_was_queried(backend):
    """
    "I don't have that information in the database" must be reserved for a query
    that genuinely came back empty. Said when NO query ran, it tells the client
    their data is missing - observed about an employee who plainly exists.
    """
    src = _src(backend)
    denial = "I don't have that information in the database."
    if denial not in src:
        return  # this backend never makes that claim at all
    tail = src.split(denial, 1)[1][:300]
    assert "sql_used" in tail, (
        f"{backend} can deny having data without checking whether it ever queried"
    )


@pytest.mark.parametrize("backend", BACKENDS)
def test_capture_uses_the_shared_rule(backend):
    # Which result counts as "the answer" - the lookup-shown-as-report bug.
    assert "result_capture.better(" in _src(backend)
