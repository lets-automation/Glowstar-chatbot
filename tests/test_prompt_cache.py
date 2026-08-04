"""
test_prompt_cache.py
--------------------
Guards the CACHEABLE PREFIX of the system prompt.

Prompt caching bills the repeated head of a prompt at a fraction of the normal
rate - but only up to the first byte that differs. One question costs several
model calls (a tool round each, plus the write-up) and the whole system prompt
is resent every time, so the prefix is most of the bill: measured at 28,015
tokens x ~6 calls for one report question, of which ~23.6k never varies.

The failure mode these tests exist for is SILENT. Putting one per-question value
(a date, a table name, the question itself) into the static block still produces
a correct answer - it just quietly stops caching and the bill goes back up with
nothing in the logs to say so.
"""


from app.agent import tools

QUESTIONS = [
    "give me full report of MFG - 1 from 1 Jul 2026 to 31 Jul 2026",
    "how many employees do we have",
    "department wise production for June 2026",
    "GIA results of Fency department employees",
    "hello",
]


def test_the_prefix_is_byte_identical_across_questions():
    prefixes = {tools.system_prompt_for(q)[: len(tools.STATIC_PROMPT)] for q in QUESTIONS}
    assert len(prefixes) == 1, "the cacheable prefix differs per question - nothing will cache"


def test_every_prompt_actually_starts_with_the_static_block():
    for q in QUESTIONS:
        assert tools.system_prompt_for(q).startswith(tools.STATIC_PROMPT), q


def test_the_static_block_carries_no_moving_date():
    """
    TODAY'S date must stay out of the static block - it would re-cache the whole
    prefix every midnight, and mid-demo if the process crosses a day boundary.

    Note this checks for a MOVING date, not for any year: the block legitimately
    cites fixed data boundaries ("tblPointRateLabour covers mid-2022->now",
    "tblLabourResult dies ~Feb 2023") and those never change. An earlier version
    of this test banned every 4-digit year and failed on exactly that prose.
    """
    from datetime import date

    today = date.today()
    assert "TODAY'S DATE" not in tools.STATIC_PROMPT
    for stamp in (f"{today:%d %b %Y}", f"{today:%Y-%m-%d}"):
        assert stamp not in tools.STATIC_PROMPT, f"{stamp!r} un-caches the prefix daily"


def test_todays_date_is_still_given_to_the_model():
    # It must be in the per-question tail, not simply dropped: without it the
    # model labels grounded numbers with its training-era year.
    from datetime import date

    prompt = tools.system_prompt_for("production this year")
    assert f"{date.today():%d %b %Y}" in prompt
    assert "TODAY'S DATE" in prompt


def test_the_static_block_is_worth_caching():
    # If this ever collapses, the split has silently stopped paying for itself.
    assert len(tools.STATIC_PROMPT) // 4 > 15_000, "static block unexpectedly small"


def test_the_static_block_is_most_of_the_prompt():
    q = QUESTIONS[0]
    total = len(tools.system_prompt_for(q))
    assert len(tools.STATIC_PROMPT) / total > 0.7, \
        "the per-question tail has grown - most of the prompt is no longer cacheable"


# --- the guidance must not have been LOST in the move -----------------------
# The data notes were relocated out of build_schema_context and into
# STATIC_PROMPT. If that wiring breaks, answers get quietly worse (wrong colour
# codes, the 'Florecent' misspelling) with every test still green.
def test_the_data_notes_still_reach_the_model():
    prompt = tools.system_prompt_for("how many stones have strong fluorescence")
    assert "Florecent" in prompt, "data notes lost - the misspelled column is unexplained"


def test_data_notes_are_in_the_cached_part_not_the_tail():
    assert "Florecent" in tools.STATIC_PROMPT


def test_rules_are_in_the_cached_part():
    assert tools.RULES in tools.STATIC_PROMPT
