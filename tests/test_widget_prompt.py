"""
test_widget_prompt.py
---------------------
Guards the SPLIT of the visual-output prompt, and the rule that the bot draws
a chart only when a chart is actually the better answer.

WHAT WAS WRONG
--------------
widget.WIDGET_SYSTEM_PROMPT was one 2,023-token block merged into the system
prompt on every call, on every provider, on every round of the tool loop - and
one report question spends ~6 rounds. About 70% of it was a design system
(CSS-variable palette, type scale, component specs, Chart.js wiring) that only
ever applies to show_widget. show_chart and show_dashboard never read a word of
it: their HTML comes from build_chart_html() / build_dashboard_html(), so those
decisions are ours, not the model's - and they are the common path.

It is now WIDGET_CORE_PROMPT (always on) + WIDGET_DESIGN_PROMPT (gated by
widget.needs_design_rules, appended dead last).

THE FAILURE MODES THESE TESTS EXIST FOR ARE SILENT
--------------------------------------------------
  * Gate opens on everything -> the split stops paying and nobody notices,
    because every answer is still correct.
  * Gate never opens -> widgets quietly get uglier, not broken.
  * Design block drifts in FRONT of the per-question schema -> it un-caches
    ~20k tokens behind it on every question that mentions a diagram, and the
    only symptom is the bill.
  * The "don't draw" rules get trimmed -> the bot goes back to charting single
    numbers, which costs output tokens on every answer.
"""

from pathlib import Path

import pytest

from app.agent import widget

_ROOT = Path(__file__).resolve().parents[1]
_BACKENDS = (
    "app/agent/groq_backend.py",
    "app/agent/gemini_backend.py",
    "app/agent/anthropic_backend.py",
)


def _src(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. The gate stays SHUT on what this bot is actually asked all day.
#
#    This is the test that decides whether the split pays for itself. The
#    exclusion that makes it work: chart / graph / plot / dashboard / analytics
#    / report are deliberately NOT triggers, because show_chart and
#    show_dashboard serve them from our own templates.
# ---------------------------------------------------------------------------
EVERYDAY_QUESTIONS = [
    "give me full report of MFG - 1 from 1 Jul 2026 to 31 Jul 2026",
    "how many employees do we have",
    "department wise production for June 2026",
    "GIA results of Fency department employees",
    "how many packets are on jangad",
    "report of employee M4167",
    "production analytics for June",
    "give me a dashboard of last month",
    "top 10 kapans by damage count",
    "pie chart of shapes",
    "what is the average polished weight this year",
    "kem cho",
]


@pytest.mark.parametrize("question", EVERYDAY_QUESTIONS)
def test_everyday_questions_do_not_pay_for_the_design_system(question):
    assert not widget.needs_design_rules(question), (
        f"{question!r} loaded ~1k tokens of show_widget design rules it will "
        "never use - the gate has drifted open"
    )
    assert widget.visual_prompt_for(question) == ""


# ---------------------------------------------------------------------------
# 2. ...and OPEN when the question asks for something only show_widget can draw.
# ---------------------------------------------------------------------------
CUSTOM_VISUAL_QUESTIONS = [
    "draw a flowchart of the manufacturing process",
    "show me a stacked bar of MFG vs PLS",
    "build an interactive calculator for bonus points",
    "make a timeline of kapan NS26",
    "give me an org chart of the departments",
    "a scatter of weight against value",
    "sketch the process flow from rough to polished",
    "show the department hierarchy as a diagram",
    "multi-series trend of PLS and GIA grades",
    "an infographic of last quarter",
]


@pytest.mark.parametrize("question", CUSTOM_VISUAL_QUESTIONS)
def test_custom_visual_questions_load_the_design_system(question):
    assert widget.needs_design_rules(question), (
        f"{question!r} will hand-write a widget with no palette, type scale or "
        "Chart.js rules"
    )
    assert widget.visual_prompt_for(question) == widget.WIDGET_DESIGN_PROMPT


def test_a_follow_up_turn_keeps_the_design_rules():
    """
    The backends pass tools.routing_text(question, history) - the previous user
    turn plus this one - so a follow-up on a widget does not lose the rules
    halfway through building it.
    """
    assert widget.needs_design_rules("draw the process flow and add the polishing stage")
    assert not widget.needs_design_rules("and add the polishing stage")  # alone: no trigger
    # The real call site concatenates the two, which is what keeps it loaded.
    assert widget.needs_design_rules("draw the process flow and add the polishing stage")


def test_empty_and_missing_text_never_crash_the_gate():
    for value in ("", None):
        assert widget.needs_design_rules(value) is False
        assert widget.visual_prompt_for(value) == ""


# ---------------------------------------------------------------------------
# 3. Size: the always-on half must stay small, or the split stops paying.
# ---------------------------------------------------------------------------
def test_the_always_on_half_stays_small():
    core = len(widget.WIDGET_CORE_PROMPT) // 4
    assert core < 1_300, (
        f"WIDGET_CORE_PROMPT has grown to ~{core} tokens - it is sent on every "
        "call, on every round; move anything show_widget-only into "
        "WIDGET_DESIGN_PROMPT"
    )


def test_the_gated_half_is_worth_gating():
    design = len(widget.WIDGET_DESIGN_PROMPT) // 4
    assert design > 600, (
        f"WIDGET_DESIGN_PROMPT is only ~{design} tokens - if it shrinks this "
        "far the gate is more machinery than it saves"
    )


# ---------------------------------------------------------------------------
# 4. A gate MISS must cost styling, never a broken render.
#
#    The gate is biased towards firing, but it will still miss sometimes - the
#    model can reach for show_widget on a question with no trigger word. When
#    that happens the fragment must still render, so every rule whose absence
#    produces a BLANK BOX or invisible dark-mode text stays in the always-on
#    half. Only the polish is allowed to be gated.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "rule",
    [
        "localStorage",        # blocked, throws -> dead widget
        "position:fixed",      # collapses the auto-sizing iframe
        "cdn.jsdelivr.net",    # off-allowlist resources fail silently
        "<!doctype>",          # a full document does not render as a fragment
        "var(--text-primary)", # hardcoded colors vanish in dark mode
        "#2a78d6",             # ...and canvas cannot read the CSS vars at all
    ],
)
def test_render_breaking_rules_are_in_the_always_on_half(rule):
    assert rule in widget.WIDGET_CORE_PROMPT, (
        f"{rule!r} is only in the gated design block - a gate miss now produces "
        "a broken widget instead of a plainer one"
    )


# ---------------------------------------------------------------------------
# 5. The bot must draw only when a drawing is the better answer.
#
#    Client-visible waste, not a crash: a chart that restates the single number
#    already in the sentence costs output tokens on every answer and adds
#    nothing. The old prompt only said when to draw; it never said when not to.
# ---------------------------------------------------------------------------
def test_the_core_says_when_to_draw_nothing_at_all():
    core = widget.WIDGET_CORE_PROMPT.lower()
    assert "do not draw anything" in core
    for case in ("single number", "yes/no", "lookup", "definition"):
        assert case in core, f"the no-visual rule no longer covers {case!r}"
    # ...and a report is a table, not a chart - the client-flagged shape.
    assert "a report is a table of detail rows, never a chart" in core


def test_unasked_charts_are_capped_at_one_and_need_a_real_shape():
    core = widget.WIDGET_CORE_PROMPT.lower()
    assert "one chart per answer, never two" in core
    # The threshold that keeps 2-3 point answers in prose.
    assert "4 or more comparable categories" in core


def test_the_placeholder_failure_is_still_banned():
    # "[Chart image: ...]" instead of a tool call was a real reported failure.
    assert "[Chart image: ...]" in widget.WIDGET_CORE_PROMPT


def test_grounding_survived_the_split():
    # Every tile/label/value must come from run_sql in this conversation. This
    # rule can never be gated - an invented dashboard is the worst outcome.
    assert "run_sql" in widget.WIDGET_CORE_PROMPT
    assert "invented numbers" in widget.WIDGET_CORE_PROMPT


def test_the_dashboard_procedure_survived_the_split():
    # show_dashboard is the common analytics path, so its how-to stays always-on
    # - loop_policy.DASHBOARD_NUDGE pushes the model here on every analytics
    # question, and the nudge is useless if the procedure was gated away.
    core = widget.WIDGET_CORE_PROMPT
    assert "show_dashboard ONCE" in core
    assert "3-6 KPI tiles" in core


# ---------------------------------------------------------------------------
# 6. Placement: the gated block goes DEAD LAST, behind the per-question schema.
#
#    Prompt caching matches a PREFIX. In front of the schema, a block that
#    switches on and off would flip the cache key of the largest part of the
#    prompt (~20k tokens) on every question that happened to say "diagram" -
#    the same trap documented at the top of tools.dynamic_schema_for().
#    Correctness would be untouched; only the bill would move.
# ---------------------------------------------------------------------------
_SCHEMA_CALL = {
    "app/agent/groq_backend.py": "tools.system_prompt_for(routing_text)",
    "app/agent/gemini_backend.py": "tools.system_prompt_for(routing)",
    "app/agent/anthropic_backend.py": "tools.dynamic_schema_for(question)",
}


@pytest.mark.parametrize("backend", _BACKENDS)
def test_every_backend_uses_the_split_prompt(backend):
    src = _src(backend)
    assert "WIDGET_CORE_PROMPT" in src, f"{backend} does not send the core visual rules"
    assert "visual_prompt_for(" in src, f"{backend} never sends the design rules"
    assert "WIDGET_SYSTEM_PROMPT" not in src, (
        f"{backend} still merges the old undivided 2k block"
    )


@pytest.mark.parametrize("backend", _BACKENDS)
def test_the_design_block_is_appended_after_the_schema(backend):
    src = _src(backend)
    core = src.index("WIDGET_CORE_PROMPT")
    schema = src.index(_SCHEMA_CALL[backend])
    design = src.index("visual_prompt_for(")
    assert core < schema, f"{backend}: the byte-stable core must come first"
    assert design > schema, (
        f"{backend}: the gated design block sits IN FRONT of the per-question "
        "schema - it will un-cache ~20k tokens whenever it toggles"
    )


def test_anthropic_stays_within_its_four_cache_breakpoints():
    """
    Anthropic allows at most 4 cache_control breakpoints. The design block is
    appended INSIDE the schema block rather than added as a fourth one, which
    keeps a spare - hoisting it into its own block would spend the last slot.
    """
    src = _src("app/agent/anthropic_backend.py")
    assert src.count('"cache_control"') <= 4
