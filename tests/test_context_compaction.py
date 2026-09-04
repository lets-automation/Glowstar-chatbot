"""
test_context_compaction.py
--------------------------
_compact_history() in groq_backend: keep a long multi-round question inside the
context window.

WHY
---
Nothing trimmed the conversation. A report question runs 9-11 rounds and every
tool result stayed in full, so the context grew until the provider refused the
whole turn: "That request was too large for the current AI model" - after
minutes of waiting, with no partial answer. Recipes (app/agent/reports.py) fix
the reports we anticipated; this is the safety net for the ones we did not.

The invariant that matters most is structural: an OpenAI-dialect request is
MALFORMED if a tool_call_id has no matching tool reply, so compaction may only
shorten content, never remove a message.
"""
from app.agent.groq_backend import (
    _COMPACT_ABOVE_TOKENS,
    _CHARS_PER_TOKEN,
    _KEEP_FULL_TOOL_RESULTS,
    _compact_history,
)

_BIG = "x" * 6000

# How many results it takes to be genuinely over budget, DERIVED from the
# constants rather than hardcoded.
#
# This was a bare _convo(9): 9 x 6,000 = 54,000 chars, which cleared the old
# 48,000-char budget by luck, not by construction. When _CHARS_PER_TOKEN was
# corrected 2->2.4 on 2026-08-25 the budget moved to 57,600 and the fixture
# quietly fell UNDER it, so "a long conversation is compacted" was testing a
# conversation that no longer needed compacting. The tests caught it (the
# fixture guard below), but only because that guard existed - so size it from
# the constants and it cannot rot again.
_OVER_BUDGET_TOOLS = int(_COMPACT_ABOVE_TOKENS * _CHARS_PER_TOKEN // len(_BIG)) + 1


def _convo(n_tools: int, body: str = _BIG) -> list[dict]:
    msgs: list[dict] = [
        {"role": "system", "content": "RULES..."},
        {"role": "user", "content": "give me the full report"},
    ]
    for i in range(n_tools):
        msgs.append({"role": "assistant", "content": None,
                     "tool_calls": [{"id": f"call_{i}"}]})
        msgs.append({"role": "tool", "tool_call_id": f"call_{i}", "content": body})
    return msgs


def _size(msgs) -> int:
    return sum(len(str(m.get("content") or "")) for m in msgs)


def test_a_short_conversation_is_left_alone():
    """Compaction must not fire on ordinary questions - most turns are two or
    three rounds and lose nothing by staying whole."""
    msgs = _convo(1, body="small result")
    before = [dict(m) for m in msgs]
    _compact_history(msgs)
    assert msgs == before


def test_a_long_conversation_is_compacted_to_fit_AND_NO_FURTHER():
    """The contract changed on 2026-08-21, and the change is the point.

    This used to assert the conversation shrank by more than half, which encoded
    the old behaviour: blank EVERY tool result except the last two, however
    little room was actually needed. A turn one character over the threshold
    lost as much data as one three times over it - and on a multi-section report
    that is the difference between narrating six sections and narrating two.

    Trimming stops as soon as the conversation fits, so the invariant is now
    'it fits' plus 'no more than necessary was spent to get there'.
    """
    budget = _COMPACT_ABOVE_TOKENS * _CHARS_PER_TOKEN
    msgs = _convo(_OVER_BUDGET_TOOLS)
    before = _size(msgs)
    assert before > budget, "fixture must actually be over budget"

    _compact_history(msgs)

    assert _size(msgs) < before, "an over-budget conversation must shrink"
    assert _size(msgs) <= budget, "compaction must bring it inside the budget"

    trimmed = sum(1 for m in msgs
                  if m.get("role") == "tool"
                  and str(m.get("content") or "").startswith("[earlier result"))
    kept = sum(1 for m in msgs if m.get("role") == "tool") - trimmed
    assert trimmed >= 1, "something had to give"
    assert kept > _KEEP_FULL_TOOL_RESULTS, (
        f"only {kept} results kept - that is the old blanket-trim behaviour, "
        "which is what made reports thin"
    )


def test_the_system_prompt_is_not_counted_against_the_conversation_budget():
    """The bug this guards was worth five sections of a report.

    _compact_history summed EVERY message, and messages[0] is the system prompt -
    73,518 characters against a 48,000-character trigger. So the threshold was
    already exceeded before the user's question was appended: compaction ran on
    round one of every turn and never stopped, and by the write-up call of an
    eight-round report five of the eight results had been replaced by a
    placeholder. The model was asked for a seven-section profile while it could
    see the data for three.
    """
    huge_system = "S" * 200_000
    msgs = [
        {"role": "system", "content": huge_system},
        {"role": "user", "content": "give me the full report"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "c0"}]},
        {"role": "tool", "tool_call_id": "c0", "content": "x" * 5000},
    ]
    before = [dict(m) for m in msgs]
    _compact_history(msgs)
    assert msgs == before, (
        "a single small result was trimmed because the SYSTEM PROMPT was counted "
        "as conversation"
    )


def test_every_tool_message_survives():
    """THE structural invariant: the request is malformed if a tool_call_id has
    no matching reply, so content may shrink but messages may not disappear."""
    msgs = _convo(_OVER_BUDGET_TOOLS)
    ids_before = [m.get("tool_call_id") for m in msgs if m.get("role") == "tool"]
    roles_before = [m["role"] for m in msgs]
    _compact_history(msgs)
    assert [m["role"] for m in msgs] == roles_before
    assert [m.get("tool_call_id") for m in msgs if m.get("role") == "tool"] == ids_before


def test_the_most_recent_results_stay_in_full():
    """The model still needs the rows it is actively working from; older ones it
    has already folded into its answer-so-far."""
    msgs = _convo(_OVER_BUDGET_TOOLS)
    _compact_history(msgs)
    tools_ = [m for m in msgs if m["role"] == "tool"]
    for m in tools_[-_KEEP_FULL_TOOL_RESULTS:]:
        assert m["content"] == _BIG, "recent results must not be trimmed"


def test_user_and_assistant_turns_are_never_touched():
    """They carry the question and the reasoning - losing either changes the
    answer, which trimming must never do."""
    msgs = _convo(_OVER_BUDGET_TOOLS)
    keep = [m["content"] for m in msgs if m["role"] in ("user", "system")]
    _compact_history(msgs)
    assert [m["content"] for m in msgs if m["role"] in ("user", "system")] == keep


def test_a_trimmed_result_says_what_it_was_and_forbids_a_rerun():
    """A bare truncation invites the model to re-run the query, which costs the
    round the trim just saved."""
    msgs = _convo(_OVER_BUDGET_TOOLS)
    _compact_history(msgs)
    trimmed = [m for m in msgs if m["role"] == "tool"
               and str(m["content"]).startswith("[earlier result")]
    assert trimmed
    assert all("do NOT re-run" in m["content"] for m in trimmed)


def test_compaction_is_idempotent():
    """It runs before EVERY round, so a second pass must not re-trim its own
    placeholder into nonsense."""
    msgs = _convo(_OVER_BUDGET_TOOLS)
    _compact_history(msgs)
    once = [m["content"] for m in msgs]
    _compact_history(msgs)
    assert [m["content"] for m in msgs] == once


def test_threshold_leaves_room_for_prompt_and_output():
    """The system prompt (~19k tokens) and the output budget (up to 16k) both
    sit OUTSIDE this number, so it has to stay well under any context limit."""
    assert _COMPACT_ABOVE_TOKENS * _CHARS_PER_TOKEN < 60_000
