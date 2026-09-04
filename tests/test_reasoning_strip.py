"""
test_reasoning_strip.py
-----------------------
Guard the chain-of-thought stripper in postprocess.strip_reasoning().

WHY THIS EXISTS
---------------
Measured on the 2026-08-18 self-hosted GPU bakeoff (Qwen3.5-9B on an RTX 5090
via vLLM): 18 of 26 answers arrived with the model's private monologue in the
message body, because the server was started without a matching
--reasoning-parser. One of those answers printed the ENTIRE SCOPE ruleset back
to the user - the system prompt, including which columns are blocked.

That is an IP leak, so the strip lives in postprocess (every backend, every
provider) rather than depending on a serving flag someone must remember.
"""
from app.agent.postprocess import strip_reasoning, extract_askdate, extract_suggestions


def test_strips_bare_monologue_terminated_by_close_tag():
    """The shape actually observed: the chat template ate the opening tag, so
    the reply is raw deliberation ended by </think>."""
    raw = "All RFID values are NULL. Let me summarise. </think>\n\n## RFID Report\nTotal: 0"
    out = strip_reasoning(raw)
    assert out.startswith("## RFID Report")
    assert "Let me summarise" not in out


def test_strips_well_formed_pair():
    raw = "<think>internal deliberation</think>The answer is 42."
    assert strip_reasoning(raw) == "The answer is 42."


def test_strips_up_to_the_last_close_tag():
    raw = "first thought </think> second thought </think> FINAL"
    assert strip_reasoning(raw) == "FINAL"


def test_never_returns_empty_for_a_non_empty_reply():
    """A blank bubble is worse than a leak - postprocess has its own guard for
    genuinely empty replies, and this must not manufacture one."""
    raw = "purely reasoning with nothing after it </think>"
    assert strip_reasoning(raw).strip()


def test_leaves_ordinary_answers_untouched():
    raw = "Currently 11,835 packets are on hold (37 kapans)."
    assert strip_reasoning(raw) == raw


def test_does_not_leak_the_system_prompt():
    """The exact failure seen live: the model recited its own SCOPE rules."""
    raw = ("I must politely REFUSE everything else, including writing poems. "
           "Looking at my rules: I am ONLY GlowStar's business-DATA assistant. </think>\n"
           "I'm GlowStar's data assistant - what would you like to know from your data?")
    out = strip_reasoning(raw)
    assert "REFUSE" not in out
    assert "business-DATA assistant" not in out
    assert out.startswith("I'm GlowStar's data assistant")


def test_markers_survive_stripping():
    """extract_* run AFTER the strip; the real marker must still be found and
    the monologue must not become the user-visible text."""
    raw = ("They gave no period, so I should use the ASKDATE: marker. </think>\n"
           "Which period would you like?\n\nASKDATE:")
    text, ask = extract_askdate(strip_reasoning(raw))
    assert ask is True
    assert text.startswith("Which period")
    assert "I should use" not in text


def test_suggestions_are_taken_from_the_answer_not_the_monologue():
    raw = ("I will offer SUGGESTIONS: bogus | fake | wrong </think>\n"
           "Here is your report.\n\nSUGGESTIONS: Show stock | Show damage")
    text, sugg = extract_suggestions(strip_reasoning(raw))
    assert sugg == ["Show stock", "Show damage"]
    assert text.startswith("Here is your report")
