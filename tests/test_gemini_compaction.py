"""
test_gemini_compaction.py
-------------------------
gemini_backend._compact_contents(): the production provider had NO compaction.

WHY
---
The policy lived inside groq_backend, so it protected the backend we test with
and left the one we SHIP with unguarded. Gemini 2.5 Flash's 1M window hid that;
a self-hosted model would not (see docs/AI-Hosting-Options.md).

The invariant that matters most is structural: Gemini requires a
function_response for every function_call, so compaction may only shorten a
part's text, never drop a part.
"""
from google.genai import types

from app.agent import context_budget
from app.agent.gemini_backend import _compact_contents

_BIG = "x" * 6000
_N = int(context_budget.COMPACT_ABOVE_TOKENS * context_budget.CHARS_PER_TOKEN
         // len(_BIG)) + 1


def _convo(n_tools: int, body: str = _BIG) -> list:
    out = [types.Content(role="user", parts=[types.Part(text="give me the full report")])]
    for i in range(n_tools):
        out.append(types.Content(
            role="model",
            parts=[types.Part.from_function_call(name="run_sql", args={"query": f"q{i}"})],
        ))
        out.append(types.Content(
            role="user",
            parts=[types.Part.from_function_response(
                name="run_sql", response={"result": body})],
        ))
    return out


def _results(contents):
    return [p.function_response.response["result"]
            for c in contents for p in (c.parts or [])
            if getattr(p, "function_response", None) is not None]


def test_a_short_conversation_is_left_alone():
    """Most turns are two or three rounds and lose nothing by staying whole."""
    contents = _convo(1, body="small result")
    _compact_contents(contents)
    assert _results(contents) == ["small result"]


def test_a_long_conversation_is_trimmed():
    contents = _convo(_N)
    before = _results(contents)
    _compact_contents(contents)
    after = _results(contents)
    assert sum(map(len, after)) < sum(map(len, before)), "an over-budget turn must shrink"
    assert any(r.startswith(context_budget.PLACEHOLDER_PREFIX) for r in after)


def test_every_function_response_survives():
    """A function_call with no matching response makes the request malformed."""
    contents = _convo(_N)
    n_before = len(_results(contents))
    roles_before = [c.role for c in contents]
    _compact_contents(contents)
    assert len(_results(contents)) == n_before
    assert [c.role for c in contents] == roles_before


def test_the_most_recent_results_stay_in_full():
    contents = _convo(_N)
    _compact_contents(contents)
    kept = _results(contents)[-context_budget.KEEP_FULL_TOOL_RESULTS:]
    assert all(r == _BIG for r in kept), "recent results must not be trimmed"


def test_user_text_turns_are_never_touched():
    contents = _convo(_N)
    _compact_contents(contents)
    assert contents[0].parts[0].text == "give me the full report"


def test_compaction_is_idempotent():
    """It runs before EVERY round, so a second pass must not re-trim its own
    placeholder into nonsense."""
    contents = _convo(_N)
    _compact_contents(contents)
    once = _results(contents)
    _compact_contents(contents)
    assert _results(contents) == once
