"""
test_cost_trace.py
------------------
The AgentCost trace spans (SDK >= 0.2.0) added in app/core/cost_trace.py.

Two things are under test, and the second matters more than the first:

  1. The spans produce the breakdown we added them for - one trace per turn,
     one numbered step per provider round, an outcome on the end.
  2. They cannot break a chat turn. These context managers sit around EVERY
     provider call in the app, so a bug in third-party telemetry would take the
     product down. A body exception must always win, and a broken or absent SDK
     must degrade to a no-op.

Everything runs in the SDK's local_mode: no network, no dashboard, no key.
"""

from types import SimpleNamespace

import pytest

from agentcost import track_costs
from agentcost.tracker import _tracker

from app.core import cost_trace


@pytest.fixture
def local_tracking():
    """AgentCost in local_mode, armed, and reset again afterwards.

    Autouse is deliberately NOT used: cost_trace must be disabled for the rest
    of the suite, which is also its production default.
    """
    track_costs.init(local_mode=True, debug=False)
    _tracker._batcher.clear_events()
    cost_trace.enable(track_costs)
    yield
    cost_trace.disable()
    track_costs.shutdown()


def _emit_llm_event(model="test-model"):
    """Stand in for an intercepted provider call.

    Goes through _record_event, the single funnel 0.2.0 routes every real
    interceptor through, so what this records is what a real call would record.
    """
    _tracker._record_event({"model": model, "input_tokens": 10, "output_tokens": 5})


def _drain():
    """Stored events. LocalBatcher only keeps them once flushed."""
    track_costs.flush()
    records = _tracker._batcher.get_all_events()
    return (
        [r for r in records if r.get("record_type") != "outcome"],
        [r for r in records if r.get("record_type") == "outcome"],
    )


# --- 1. the breakdown we added the spans for --------------------------------

def test_one_turn_is_one_trace_with_numbered_steps(local_tracking):
    """The whole point: the calls of one question arrive related, not loose."""
    with cost_trace.workflow("erp-chat-turn"):
        with cost_trace.step("plan"):
            _emit_llm_event("round-1")
        with cost_trace.step("plan"):
            _emit_llm_event("round-2")
        with cost_trace.step("write-up"):
            _emit_llm_event("final")
        cost_trace.outcome(True, label="answered")

    events, outcomes = _drain()

    assert len(events) == 3
    assert len({e["trace_id"] for e in events}) == 1, \
        "the calls of ONE question must share ONE trace - that is the feature"
    assert {e["workflow"] for e in events} == {"erp-chat-turn"}
    assert [e["step_name"] for e in events] == ["plan", "plan", "write-up"]
    # Two rounds both named "plan" must still be countable as two. Without
    # distinct step_index values the dashboard cannot tell a question that
    # genuinely needed several queries from one round retried.
    assert [e["step_index"] for e in events] == [0, 1, 2]

    assert len(outcomes) == 1
    assert outcomes[0]["success"] is True and outcomes[0]["label"] == "answered"
    assert outcomes[0]["trace_id"] == events[0]["trace_id"], \
        "the outcome must attach to the trace it describes"


def test_a_failed_turn_is_marked_failed(local_tracking):
    """Rounds that ran before a failure were still paid for; the dashboard has
    to be able to separate that money from money that bought an answer."""
    with cost_trace.workflow("erp-chat-turn"):
        with cost_trace.step("plan"):
            _emit_llm_event()
        cost_trace.outcome(False, label="no_answer")

    events, outcomes = _drain()
    assert len(events) == 1, "the spend is still recorded"
    assert outcomes[0]["success"] is False and outcomes[0]["label"] == "no_answer"


def test_calls_outside_any_workflow_are_still_recorded(local_tracking):
    """Tracing is additive. An untraced call must not become an untracked one."""
    _emit_llm_event("loose")

    events, _ = _drain()
    assert len(events) == 1
    assert "trace_id" not in events[0]


# --- 2. tracing must never cost us a turn -----------------------------------

def test_body_exception_is_never_swallowed(local_tracking):
    """The one thing that would be worse than losing cost data: losing the
    provider error that explains why a turn failed."""
    class Boom(Exception):
        pass

    with pytest.raises(Boom):
        with cost_trace.workflow("erp-chat-turn"):
            with cost_trace.step("plan"):
                raise Boom("provider died")


def test_a_broken_sdk_degrades_to_noops():
    """cost_trace wraps every provider call in the app. If the third-party SDK
    raises on entry or exit, the turn still has to complete."""
    class Exploding:
        def workflow(self, *a, **k):
            raise RuntimeError("SDK is broken")

        def step(self, *a, **k):
            raise RuntimeError("SDK is broken")

        def tool(self, *a, **k):
            raise RuntimeError("SDK is broken")

        def outcome(self, *a, **k):
            raise RuntimeError("SDK is broken")

    cost_trace.enable(Exploding())
    try:
        with cost_trace.workflow("erp-chat-turn") as trace_id:
            with cost_trace.step("plan") as span_id:
                answered = True
            assert cost_trace.outcome(True) is False
    finally:
        cost_trace.disable()

    assert answered
    assert trace_id is None and span_id is None


def test_disabled_is_the_default_and_is_a_pure_noop():
    """Nothing traces until main.py confirms init() succeeded - entering a
    workflow on a half-initialised tracker raises out of a finally block."""
    assert not cost_trace.is_enabled()

    with cost_trace.workflow("erp-chat-turn") as trace_id:
        with cost_trace.step("plan") as span_id:
            pass
        with cost_trace.tool("run_sql") as tool_id:
            pass
    assert (trace_id, span_id, tool_id) == (None, None, None)
    assert cost_trace.outcome(True) is False


# --- 3. end to end, through the real agent loop -----------------------------

def _fake_openai_client(script):
    """An OpenAI-dialect client that replays `script` and records an event per
    call, which is what the real interceptor does around the same method."""
    calls = {"n": 0}

    def create(**_kwargs):
        i = calls["n"]
        calls["n"] += 1
        _emit_llm_event(f"call-{i}")
        return script[min(i, len(script) - 1)]

    return SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )


def _tool_call_response(name, arguments):
    msg = SimpleNamespace(
        content="",
        tool_calls=[
            SimpleNamespace(
                id="call_1",
                function=SimpleNamespace(name=name, arguments=arguments),
            )
        ],
    )
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


def _text_response(text):
    msg = SimpleNamespace(content=text, tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


def test_a_real_turn_produces_plan_and_write_up_steps(local_tracking, monkeypatch):
    """The spans are placed inside the backend loop, so only running the loop
    proves they wrap what they claim to. Budget is squeezed to one tool round
    so the turn falls through to the write-up instead of answering early."""
    from app.agent import agent, groq_backend, tools

    monkeypatch.setattr(tools, "MAX_TOOL_ROUNDS", 1)
    monkeypatch.setattr(tools, "MAX_TOTAL_ROUNDS", 1)
    # 6-tuple: run_tool gained a `sections` slot so a report recipe can return
    # several NAMED results from one call (see tools.run_tool). Ad-hoc run_sql
    # has no sections, hence the trailing [].
    monkeypatch.setattr(
        tools, "run_tool",
        lambda name, args: ("2 rows", "SELECT 1", 2, ["a"], [{"a": 1}], []),
    )
    monkeypatch.setattr(
        groq_backend, "_client",
        lambda: _fake_openai_client([
            _tool_call_response("run_sql", '{"query": "SELECT 1"}'),
            _text_response("Two packets."),
        ]),
    )
    monkeypatch.setattr(agent.settings, "LLM_PROVIDER", "groq")
    # A cache hit would answer with no provider call at all.
    monkeypatch.setattr(agent.answer_cache, "get", lambda _q: None)
    monkeypatch.setattr(agent.answer_cache, "put", lambda *a, **k: None)

    # DELIBERATELY A QUESTION WITH NO RECIPE. This used to be "how many
    # packets are on jangad?", which became a quick_fact on 2026-09-03 -
    # answered before the backend loop runs, so no spans were emitted and
    # this test failed for a reason that was an IMPROVEMENT. It needs a
    # question that genuinely reaches the model.
    out = agent.ask("List each employee with their native district.")
    assert out["answer"]

    events, outcomes = _drain()
    assert len({e["trace_id"] for e in events}) == 1, \
        "every call of one turn belongs to one trace"
    assert [e["step_name"] for e in events] == ["plan", "write-up"]
    assert len(outcomes) == 1 and outcomes[0]["success"] is True


def test_a_cache_hit_reports_nothing(local_tracking, monkeypatch):
    """A pre-warmed answer makes no provider call. Reporting an outcome for it
    would put free turns on a cost dashboard."""
    from app.agent import agent

    monkeypatch.setattr(
        agent.answer_cache, "get",
        lambda _q: {"answer": "warmed", "_cached_at": "yesterday"},
    )

    out = agent.ask("how many packets are on jangad?")
    assert out == {"answer": "warmed"}

    events, outcomes = _drain()
    assert events == [] and outcomes == [], "a free turn must cost the dashboard nothing"
