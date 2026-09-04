"""
THE PROMPT BUDGET. This test exists to stop the system getting more expensive.

Every model ROUND re-sends the whole system prompt, and a question costs several
rounds, so prompt size multiplies. Measured 2026-08-25 across the real question
corpus (the top 70 questions from the chat logs):

    MIN 13,521 | AVG 18,186 | MAX 20,934 tokens

Gemini's free tier counts REQUESTS, not questions - at ~3 rounds each that is
only 5-7 questions a day - and Groq's free tier refuses anything over 8,000
tokens per minute outright. So prompt size is not a cost detail here, it is what
decides whether a demo survives.

A conditional rule (query_rules) is CHEAP: it is injected only for the question
it matches, and measured at ~279 tokens on average. Prose added to the always-on
RULES block is NOT cheap - it is paid on every round of every question. If this
test fails, that is almost certainly what happened.
"""
import statistics

import pytest

from app.agent import query_rules, tools

# A spread of the real corpus - one per question family, kept small so the test
# stays fast. Ask counts are from the logs.
CORPUS = [
    "provide past month gia results of fency department employees",
    "how many packets are on jangad?",
    "aa varsh ma ketla planning verify thaya che?",
    "compare production report of department mfg - 1 and mfg-2 from 1 jul 2026 to 31 jul 2026",
    "last month ketla stone lab ma send karya?",
    "oq26 kapan ma final point / final polish weight ketlu nikalyu?",
    "how many stones are out on memo right now?",
    "total fluorescent stones broken down by colour.",
    "give me report of department mfg - 1 for july 2026",
    "give me an analytics overview of our production this year",
    "june ma manufacturing ma ketlu value loss thayu?",
    "how many oval diamonds do we have in stock?",
    "give me the damage report of department mfg - 1",
    "give me top 10 employees who get highest bonus",
    "how many repair records exist for this kapan?",
    "aa mahine ketla nang thaya?",
    "junk nu grade-wise report kadho",
    "how many employees are there?",
    "show me a chart of kapan wise production",
    "hello",
]

# Ceilings sit just above the measured baseline - room for a rule or two, not
# for a new paragraph in the always-on block.
#
# RAISED 2026-08-31, 21,500 -> 21,700, for six new conditional rules and the
# curated join map (context.LOGICAL_LINKS). Each one buys a measured wrong
# answer back:
#     kapan_value_snapshot ..... 17,469,238.68 vs a true 226,631.26   (77x)
#     pct_checker_join ......... an inner join drops 46.7% of production
#     rate_card_not_money ...... 64,311,533.58 vs 3,884,709.83 paid  (16.6x)
#     no_rollup_totals ......... -43,309.04 vs a true -11,536.82     (3.75x)
#     weight_via_points_join ... 197.661 carats vs a true 378.458      (48%)
#     shape_family ............. 2,986 oval vs a true 7,591           (61%)
#
# THE AVERAGE IS THE EVIDENCE THIS WAS NOT THE THING THE TEST GUARDS AGAINST.
# MAX_AVERAGE is deliberately NOT raised: the corpus average moved 18,186 ->
# 18,512 and still clears 18,600, which is only possible because every addition
# is conditional. Always-on prose would have moved the average, not one
# question. The single question at the ceiling ("oq26 kapan ma final point /
# final polish weight") sits at the intersection of four separate traps and is
# the most-guarded question in the corpus.
#
# Before raising this again, look for a rule firing on a question it has
# nothing to say about - pct_checker_join was matching the bare word "polish"
# in "final polish weight" and cost 43 tokens on every such question.
#
# PUT BACK to 21,500 the same day. Routing the report/chart bullets out of the
# always-on block (tools._split_rules) returned 1,533 tokens to every question
# that is not a report, and the worst case fell to 21,347 - back under the
# original ceiling without the six new rules being given up.
#
# RAISED AGAIN to 21,700 for the CURATED VIEW CATALOGUE (schema/views.py,
# 287 tok). This is the second raise in a day, so the reasoning is spelled out:
#   * it MUST be always-on - the model cannot prefer a view it is only told
#     about on some questions;
#   * only REPORT questions exceed 21,500, because they are handed the report
#     bullets back in full. Every other question is ~1,250 tokens CHEAPER than
#     this morning;
#   * the corpus AVERAGE went DOWN, 18,512 -> 18,190, which is the evidence
#     this is not general bloat. MAX_AVERAGE is again left alone;
#   * it buys the mechanism that makes the biggest wrong-answer class
#     impossible rather than merely forbidden - v_packet cannot return 2,986
#     ovals, v_lab cannot return 3,492 lab packets.
#
# THE NEXT REDUCTION SHOULD COME FROM THE NOTES, NOT FROM HERE. The worst
# question spends 6,091 tokens on data notes (27 bullets) against 3,766 on
# schema, and much of that prose exists to warn about traps a view now encodes
# structurally. Retire those notes as the views take them over, and this
# ceiling should come back down - do not raise it a third time first.
MAX_ANY_QUESTION = 21_700
MAX_AVERAGE = 18_600


def _tokens(question: str) -> int:
    with query_rules.for_question(question):
        return len(tools.system_prompt_for(question)) // 4 + len(str(tools.TOOL_SPECS)) // 4


@pytest.mark.integration
def test_no_single_question_blows_the_budget():
    sizes = {q: _tokens(q) for q in CORPUS}
    if max(sizes.values()) < 1000:
        pytest.skip("database not reachable - schema context is empty")
    worst = max(sizes, key=sizes.get)
    assert sizes[worst] <= MAX_ANY_QUESTION, (
        f"{worst!r} now costs {sizes[worst]:,} tokens (ceiling {MAX_ANY_QUESTION:,}). "
        "Every round re-sends this. Did something go into the always-on RULES "
        "block instead of a conditional rule?")


@pytest.mark.integration
def test_the_average_question_stays_within_budget():
    sizes = [_tokens(q) for q in CORPUS]
    if max(sizes) < 1000:
        pytest.skip("database not reachable - schema context is empty")
    avg = statistics.mean(sizes)
    assert avg <= MAX_AVERAGE, (
        f"average prompt is now {avg:,.0f} tokens (ceiling {MAX_AVERAGE:,}).")


@pytest.mark.integration
def test_a_rule_is_cheap_and_conditional():
    """A rule must cost almost nothing on questions it does not match."""
    unrelated = "hello"
    assert query_rules.directive(unrelated) == ""
    lab = "provide past month gia results of fency department employees"
    assert len(query_rules.directive(lab)) // 4 < 400, "one rule should be a few hundred tokens"
