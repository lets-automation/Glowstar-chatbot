"""
context_budget.py
-----------------
Keep a long multi-round question inside the context window - for EVERY provider.

WHY THIS MODULE EXISTS
----------------------
The compaction logic lived inside groq_backend, so it protected exactly one of
the three backends. gemini_backend and anthropic_backend had none at all - and
`LLM_PROVIDER=gemini` is what production runs. The Gemini path was not failing
only because Gemini 2.5 Flash has a 1M context to hide in; that is luck, not
design, and it evaporates the moment the model is self-hosted (see
docs/AI-Hosting-Options.md, where the plan is a rented 24GB GPU).

WHAT IS SAFE TO DROP
--------------------
Only the CONTENT of older tool results, and only down to a one-line
description. The messages themselves must stay: the OpenAI dialect requires
every tool_call_id to have a matching tool reply, and Gemini requires a
function_response for every function_call - deleting one makes the next request
malformed. Assistant and user turns are never touched; they carry the reasoning
and the question.

The full rows are already captured for export (result_capture), so nothing the
USER receives is lost here - only the model's second look at older rows.

The provider-specific half is just "how do I find the tool results and put text
back", so that stays in each backend. The POLICY - what the budget is, which
results may be trimmed, when to stop - lives here and is shared.
"""
from __future__ import annotations

import json

# Chars per token FOR WHAT THIS ACTUALLY MEASURES.
#
# 4.0 is the rule of thumb for English prose, and it is wrong here by nearly a
# factor of two: almost all of a conversation's bulk is run_sql results, which
# are JSON rows, and JSON is dense in punctuation and short tokens.
#
# Measured 2026-08-25 with tiktoken against the live database, on the result
# shapes that actually drive a report turn:
#     30 rows x 22 cols (tblFinalPacket)  11,654 chars /  5,064 tok = 2.30
#     30 rows x 97 cols (tblPlanMaster)   56,024 chars / 22,080 tok = 2.54
#     30 rows x  1 col  (department name)    714 chars /    231 tok = 3.09
# 2.4 is the centre of the wide-JSON band, which is what overflows a turn; the
# narrow text-heavy end only ever errs further towards safety. An earlier 2.00
# was the FLOOR of that range, so it over-estimated tokens and fired compaction
# at an effective ~19-21k instead of the 24k below.
#
# Raising this trims LATER, so it spends context. Lower it, don't raise it, for
# a small-context model.
CHARS_PER_TOKEN = 2.4

# Start compacting once the CONVERSATION alone passes this. The system prompt is
# a fixed overhead that has to fit ALONGSIDE the conversation, not part of the
# conversation's budget - counting it meant the threshold was exceeded before
# the user's question was even appended, so compaction ran on round one of every
# turn and never stopped. By the write-up call of an eight-round report, five of
# the eight results had been replaced by a placeholder and the model was asked
# for a seven-section profile while it could see the data for three. That is the
# "thin report" the client reported.
#
# The budget it has to fit inside: system prompt ~19.9k mean / 24.3k worst
# (measured over a 59-question corpus) + this 24k + the output allowance
# (LLM_MAX_TOKENS, currently 16,384) = ~65k. Fits the 262k context of
# Qwen3.6-27B and any 128k model with room to spare. NOT comfortable on a 32k
# one, and LM Studio still defaults new models to ~4k - if a provider with a
# small context is ever used, lower this rather than discovering it as a failed
# turn.
COMPACT_ABOVE_TOKENS = 24000

# The model needs the LAST couple of results in full to keep reasoning; older
# ones it has already used and summarised into its own answer-so-far.
KEEP_FULL_TOOL_RESULTS = 2

# Below this a result is not worth the placeholder that would replace it.
MIN_TRIMMABLE_CHARS = 400

PLACEHOLDER_PREFIX = "[earlier result"


def budget_chars() -> float:
    """The conversation size, in characters, above which trimming starts."""
    return COMPACT_ABOVE_TOKENS * CHARS_PER_TOKEN


def trimmed_note(body: str) -> str:
    """A trimmed tool result the model can still NARRATE from.

    The old placeholder kept the first 160 characters of raw JSON and nothing
    else, which is the opening of the column list - so a section the model had
    already queried became unwriteable, and it either dropped the section or
    described it vaguely. Keeping the COLUMN NAMES and the ROW COUNT costs a few
    dozen tokens and lets it still say "Damage: 6 records, columns KapanName,
    PacketNo, Worker, Points, Amount, Date" instead of silently omitting it.

    Deliberately does NOT keep sample rows: a preview the model mistakes for the
    whole result is how "9 packets" got reported where the database held 381.
    """
    try:
        payload = json.loads(body)
        cols = ", ".join(str(c) for c in (payload.get("columns") or [])[:14])
        n = payload.get("row_count", len(payload.get("rows") or []))
        detail = f"{n} rows, columns: {cols}" if cols else f"{n} rows"
    except (json.JSONDecodeError, TypeError, AttributeError):
        detail = body.strip().splitlines()[0][:120] if body.strip() else "no detail"
    return (
        f"{PLACEHOLDER_PREFIX}, trimmed to save room - {detail}. The full rows are "
        "already captured for the user's download, so report this section from "
        "what you already wrote about it; do NOT re-run this query, and do NOT "
        "omit the section.]"
    )


def plan_trims(tool_texts: list[str], other_chars: int) -> dict[int, str]:
    """Decide which tool results to shrink. Returns {index into tool_texts: note}.

    TRIM OLDEST-FIRST, AND STOP AS SOON AS IT FITS.

    An earlier version blanked every tool result except the last two in a single
    pass, however little room was actually needed - so a turn one character over
    the threshold lost as much data as one three times over it. Trimming until
    the conversation fits keeps the most sections the budget allows, which on a
    multi-section report is the difference between narrating six sections and
    narrating two. Same budget, more answer.

    Pure function of sizes, so it is identical on every provider and testable
    without building a single provider-shaped message.
    """
    budget = budget_chars()
    total = other_chars + sum(len(t) for t in tool_texts)
    if total < budget:
        return {}

    out: dict[int, str] = {}
    trimmable = (
        len(tool_texts) - KEEP_FULL_TOOL_RESULTS
        if KEEP_FULL_TOOL_RESULTS else len(tool_texts)
    )
    for i in range(max(0, trimmable)):
        if total < budget:
            break
        body = tool_texts[i]
        if len(body) <= MIN_TRIMMABLE_CHARS or body.startswith(PLACEHOLDER_PREFIX):
            continue
        note = trimmed_note(body)
        if len(note) >= len(body):
            continue
        out[i] = note
        total -= len(body) - len(note)
    return out
