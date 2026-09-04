"""
cost_trace.py
-------------
Thin, ALWAYS-SAFE wrapper over AgentCost's trace API (SDK >= 0.2.0).

What it buys us: the dashboard used to show one flat list of LLM calls, so a
question that cost $0.06 was six anonymous calls. Wrapping a turn in workflow()
and each provider round in step() stamps every event with trace_id, step_name
and step_index, which turns that same $0.06 into "5 planning rounds + 1
write-up" - i.e. it shows WHERE a turn got expensive. That matters here because
the tool loop can legitimately burn MAX_TOOL_ROUNDS rounds, and today nothing
distinguishes a question that needed five queries from a model that stalled and
was nudged five times.

WHY THIS FILE EXISTS RATHER THAN CALLING track_costs DIRECTLY:

1. Tracking is OPTIONAL. It is on only when AGENTCOST_API_KEY and
   AGENTCOST_PROJECT_ID are set (see main.py), and the package may not even be
   installed. Every caller would otherwise repeat that check.
2. It must never take a chat turn down. The SDK is a young third party, and
   these context managers run around every provider call in the app - the
   hottest path there is. A trace bug must cost us a dashboard breakdown, not
   an answer. So enter/exit failures are swallowed and the body still runs.
3. track_costs.workflow() is only safe to enter AFTER init() succeeded. The
   SDK's trace close hook funnels into the batcher, which is None until then,
   so an outcome recorded on an uninitialised tracker raises AttributeError -
   from a finally block, during teardown. enable() below is the gate: nothing
   here does anything until main.py has confirmed init() worked.

The swallowing is deliberately one-directional: a failure INSIDE the SDK is
ignored, but an exception raised by the wrapped body is always re-raised
untouched. Silently eating a provider error to protect cost tracking would be
exactly backwards.

Outside a workflow(), step()/tool()/outcome() are no-ops by the SDK's own
design, so instrumenting a helper never depends on how it was reached - the
backends can be called straight from a script or a test with nothing enabled.
"""

from contextlib import contextmanager

from app.core.logging_util import logger

# The agentcost.track_costs module, but ONLY once main.py has confirmed that
# init() succeeded. None means "do nothing" and is the default, so importing
# this module never implies tracking is on.
_tc = None


def enable(track_costs) -> None:
    """Arm the tracing helpers. Called by main.py after a successful init()."""
    global _tc
    _tc = track_costs


def is_enabled() -> bool:
    """True when spans are actually being recorded (useful in tests)."""
    return _tc is not None


def disable() -> None:
    """Drop back to no-ops. Exists for tests; the app never calls it."""
    global _tc
    _tc = None


@contextmanager
def _span(factory, what: str):
    """Run a body inside an SDK context manager that is allowed to fail.

    The SDK context is entered and exited by hand rather than with `with`,
    because a `with` inside a try/except would put the body in the same try -
    and then a swallowed SDK error would swallow the caller's exception too.
    Splitting them keeps the guarantee that the body's exception always wins.
    """
    cm = None
    value = None
    if _tc is not None:
        try:
            cm = factory()
            value = cm.__enter__()
        except Exception as exc:  # noqa: BLE001 - tracing must not break the app
            logger.debug("cost_trace: could not open %s span: %s", what, exc)
            cm = None

    try:
        yield value
    except BaseException as exc:
        if cm is not None:
            try:
                cm.__exit__(type(exc), exc, exc.__traceback__)
            except Exception as close_exc:  # noqa: BLE001
                logger.debug("cost_trace: closing %s span failed: %s", what, close_exc)
        raise
    else:
        if cm is not None:
            try:
                cm.__exit__(None, None, None)
            except Exception as close_exc:  # noqa: BLE001
                logger.debug("cost_trace: closing %s span failed: %s", what, close_exc)


@contextmanager
def workflow(name: str):
    """Group one run - here, one chat turn - under a single trace.

    Yields the trace id (None when tracking is off). Nesting is safe: the SDK
    joins the enclosing trace instead of starting a second one, so wrapping
    ask() covers the API, the CLI and the e2e script without any of them
    needing to know whether an outer workflow already exists.
    """
    with _span(lambda: _tc.workflow(name), "workflow") as trace_id:
        yield trace_id


@contextmanager
def step(name: str):
    """Attribute the LLM calls made inside to one named step of the turn.

    Steps sharing a name are told apart by the step_index the SDK assigns, so
    the five rounds of a tool loop can all be called "plan" and still be
    counted separately. Note that the SDK's **extra kwargs are stored but never
    sent (0.2.0), so anything that must reach the dashboard belongs in `name`.
    """
    with _span(lambda: _tc.step(name), "step") as span_id:
        yield span_id


@contextmanager
def tool(name: str):
    """Like step(), but marks the span as a tool invocation.

    Only worth using around a tool that itself calls an LLM - a span with no
    LLM call inside it emits no event and never reaches the dashboard. Our DB
    tools are pure SQL, which is why run_tool() is not wrapped.
    """
    with _span(lambda: _tc.tool(name), "tool") as span_id:
        yield span_id


def outcome(success: bool, label: str | None = None) -> bool:
    """Record how the enclosing run ended; sent when the workflow closes.

    Lets the dashboard separate "$0.06 well spent" from "$0.06 and the user got
    an error", which is the number worth watching on a free tier that fails by
    running out of quota. Returns False when nothing was recorded.
    """
    if _tc is None:
        return False
    try:
        return bool(_tc.outcome(success, label=label))
    except Exception as exc:  # noqa: BLE001 - never break a turn over telemetry
        logger.debug("cost_trace: recording outcome failed: %s", exc)
        return False
