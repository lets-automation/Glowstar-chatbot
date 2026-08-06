"""
test_round_budget.py
--------------------
REGRESSION LOCK for the tool-round / correction-round split (audit finding #2).

THE BUG THIS PREVENTS
---------------------
All three backends ran their agent loop as `for _ in range(MAX_TOOL_ROUNDS)`,
and EVERY corrective nudge — grounding, report-detail, entity-report, dashboard,
bad-tool-call retry — reached the next iteration with `continue`. So each
correction silently consumed one of the query rounds.

With five triggers available, corrections could eat 5 of the 8 rounds and leave
3 for real work. The perverse result: ENTITY_REPORT_NUDGE, which exists to catch
a thin "report of <employee>", made a thin report MORE likely by spending the
budget needed to produce the full one.

Compounding it, the RULES mandate a 7-section entity profile at one query per
section, plus a lookup to resolve the code the user typed — 8 queries, against a
budget of 8 rounds shared with corrections. That answer could not physically fit,
so the loop fell through to the write-up call, which runs WITHOUT tools, and the
unqueried sections simply vanished.

Corrections now draw on their own budget (tools.MAX_CORRECTION_ROUNDS).
"""
import re

import pytest

from app.agent import tools

_BACKENDS = [
    "app/agent/groq_backend.py",
    "app/agent/anthropic_backend.py",
    "app/agent/gemini_backend.py",
]


def _src(rel: str) -> str:
    with open(rel, encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# 1. The budgets exist, are separate, and leave room for the mandated report.
# ---------------------------------------------------------------------------
def test_query_budget_covers_the_mandated_entity_report():
    """The RULES define a 7-section profile for 'report of <entity>', and a code
    lookup is usually needed first. Anything under 8 cannot produce it."""
    assert tools.MAX_TOOL_ROUNDS >= 8


def test_corrections_have_their_own_budget():
    assert tools.MAX_CORRECTION_ROUNDS >= 1
    assert tools.MAX_TOTAL_ROUNDS == tools.MAX_TOOL_ROUNDS + tools.MAX_CORRECTION_ROUNDS


def test_total_is_bounded():
    """A backstop against a pathological loop - not a budget anyone should hit."""
    assert tools.MAX_TOTAL_ROUNDS <= 20


# ---------------------------------------------------------------------------
# 2. No backend may go back to the single shared counter.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("backend", _BACKENDS)
def test_backend_does_not_use_a_single_shared_round_counter(backend):
    src = _src(backend)
    assert "for _ in range(tools.MAX_TOOL_ROUNDS)" not in src, (
        f"{backend} regressed to one counter - corrections would again steal "
        "rounds from the queries they are trying to fix"
    )


@pytest.mark.parametrize("backend", _BACKENDS)
def test_backend_tracks_both_budgets(backend):
    src = _src(backend)
    assert "tool_rounds" in src and "corrections" in src, (
        f"{backend} must track query rounds and correction rounds separately"
    )
    assert "tools.MAX_TOTAL_ROUNDS" in src, f"{backend} has no absolute ceiling"


@pytest.mark.parametrize("backend", _BACKENDS)
def test_only_real_tool_rounds_spend_the_query_budget(backend):
    """`tool_rounds += 1` must appear exactly once, on the path where the model
    actually asked for tools — not in a nudge path."""
    src = _src(backend)
    assert src.count("tool_rounds += 1") == 1, (
        f"{backend} increments the query budget in more than one place"
    )


@pytest.mark.parametrize("backend", _BACKENDS)
def test_every_nudge_path_spends_the_correction_budget(backend):
    """Each corrective `continue` must be preceded by `corrections += 1`,
    otherwise a nudge is free and the loop can spin."""
    src = _src(backend)
    nudge_emits = re.findall(
        r'(corrections \+= 1\n\s*)?emit\("(Running the query|Building the detailed '
        r'report|Building the full profile|Building your dashboard)…"\)\n\s*continue',
        src,
    )
    assert nudge_emits, f"{backend}: no nudge paths found - did the loop change?"
    unbudgeted = [m[1] for m in nudge_emits if not m[0]]
    assert not unbudgeted, (
        f"{backend}: these nudges do not spend the correction budget: {unbudgeted}"
    )


# ---------------------------------------------------------------------------
# 3. The shared policy module must stay the single source of the nudge text.
#    groq_backend used to REASSIGN policy.EXECUTE_NUDGE at import with a
#    byte-identical copy — a provider module mutating shared policy for all
#    three backends, which is exactly what loop_policy.py was extracted to stop.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("backend", _BACKENDS)
def test_no_backend_mutates_shared_policy(backend):
    src = _src(backend)
    assert not re.search(r"^policy\.\w+\s*=", src, re.MULTILINE), (
        f"{backend} assigns to the shared policy module at import time"
    )


# ---------------------------------------------------------------------------
# 4. The one correction path that can REPEAT must bound itself.
#
# Every nudge is one-shot via its own flag (nudged_report_detail, etc.) or a
# small counter (execute_nudges), except the "provider returned no choices"
# round, which can recur indefinitely on a misbehaving provider. Before the
# split it was implicitly capped by the shared MAX_TOOL_ROUNDS; now it needs to
# check the correction budget itself.
# ---------------------------------------------------------------------------
def test_empty_choices_round_is_bounded():
    src = _src("app/agent/groq_backend.py")
    idx = src.find("provider returned no choices")
    assert idx != -1, "the empty-choices guard disappeared"
    window = src[idx:idx + 700]
    assert "corrections >= tools.MAX_CORRECTION_ROUNDS" in window, (
        "the repeatable empty-choices round must stop at the correction budget, "
        "or a flaky provider spins to the absolute ceiling every turn"
    )
    assert "break" in window
