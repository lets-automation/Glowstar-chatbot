"""
test_quick_facts.py
-------------------
THE ONE-LINE FACTS THAT USED TO GET NO QUERY AT ALL.

Measured on the recorded cold run (cold_qwen3_v2.txt, 28 questions, qwen3-30b):
17 Gujlish business questions asked, 6 answered with NO SQL EXECUTED. The
anti-fabrication guard then refuses to invent a number, so the client sees
"I couldn't pull that" for questions this database answers in one query.

These now answer in code, with no LLM call. Two things are pinned here:

  1. THE NUMBERS ARE RIGHT. Each is checked against the figure the matching
     query_rules entry was verified with, recomputed independently.
  2. THE TRIGGERS DO NOT OVERREACH. A deterministic WRONG answer is worse than
     a refusal - it arrives fast, confident and unqualified. Most of this file
     is about what must NOT match.
"""
from datetime import date

import pytest

from app.agent import quick_facts, recipe_router as rr

TODAY = date(2026, 8, 31)


class TestTheQuestionsThatUsedToFail:
    """Verbatim from cold_qwen3_v2.txt, where each ran zero queries."""

    @pytest.mark.parametrize("q,fact", [
        ("aa varsh ma ketla planning verify thaya che?", "planning_approved"),
        ("kapan OQ26 ma total ketla piece hata?", "kapan_pieces"),
        ("our stock na stone no average depth % ketlo che?", "stock_avg_depth"),
        ("Aapne ketla department chalu chhe? Kitne department active hain abhi?",
         "active_departments"),
        ("Aa mahine ketla nang thaya?", "finished_output"),
    ])
    def test_it_routes_without_the_model(self, q, fact):
        spec = rr.match(q, TODAY)
        assert spec and spec["recipe"] == "quick_fact"
        assert spec["fact"] == fact


class TestScopeMustResolveOrItDeclines:
    """Answering over all of history, or over the wrong kapan, is exactly the
    failure this project keeps having. No scope, no answer."""

    def test_a_period_fact_with_no_period_declines(self):
        assert rr.match("ketla planning verify thaya che?", TODAY) is None

    def test_a_kapan_fact_with_no_kapan_declines(self):
        assert rr.match("kapan ma total ketla piece hata?", TODAY) is None

    def test_a_kapan_fact_with_an_unknown_kapan_declines(self):
        """ZZ99 is not a kapan. Resolution is exact - never the nearest one."""
        assert rr.match("kapan ZZ99 ma ketla piece hata?", TODAY) is None

    def test_a_scopeless_fact_needs_nothing(self):
        spec = rr.match("how many employees are there?", TODAY)
        assert spec and spec["fact"] == "headcount"


class TestItDoesNotHijackTheReportRecipes:
    """The report recipes are the higher-value route and were here first."""

    @pytest.mark.parametrize("q,recipe", [
        ("give me report of department MFG - 1 for july 2026", "department_report"),
        ("provide past month gia results of fency department employees", "lab_results"),
        ("polished GIA pending for mfg-1 department last month", "pending_lab_results"),
        ("give me cut purity change report of NI26", "cut_purity_change"),
    ])
    def test_the_report_still_wins(self, q, recipe):
        spec = rr.match(q, TODAY)
        assert spec and spec["recipe"] == recipe


class TestTheTriggersDoNotOverreach:
    """A confident wrong one-liner is worse than falling through to the model."""

    @pytest.mark.parametrize("q", [
        # Per-department/per-employee breakdowns are REPORTS, not a scalar.
        "how many employees in each department",
        "department wise employee count",
        "give me top 10 employees who get highest bonus",
        "how many employees are in MFG - 1 department",
        # Definition questions.
        "what is a kapan?",
        "what does PLS mean",
        # A different subject that shares the counting words.
        # COVERED SINCE 2026-09-03 by the on_jangad / on_memo facts, which read
        # the verified source (tblJangadPackets not tblJangad, CurrentWt not the
        # empty PolishedWt). Claiming them is now right - see
        # test_live_snapshot_facts. Replaced here by two that must still fall
        # through: a shape needs its whole family, a ranking is not a scalar.
        "how many oval diamonds do we have in stock?",
        "which kapan produced the most junk by weight",
    ])
    def test_it_falls_through_to_the_normal_path(self, q):
        spec = rr.match(q, TODAY)
        assert not (spec and spec["recipe"] == "quick_fact"), \
            f"quick_facts should not claim {q!r}"

    def test_department_wording_beats_headcount(self):
        """'how many departments' and 'how many employees' share the same
        counting words; the department reading must win its own question."""
        spec = rr.match("how many departments do we have", TODAY)
        assert spec and spec["fact"] == "active_departments"


@pytest.mark.integration
class TestTheNumbersAreRight:
    """Each checked against the figure its query_rules entry was verified with,
    recomputed here independently of quick_facts."""

    @staticmethod
    def _one(sql):
        from app.database.runner import run_select

        r = run_select(sql, max_rows=5)
        assert r["ok"], r.get("error")
        return r["rows"][0]

    def test_planning_approved_matches_the_rule(self):
        out = quick_facts.answer("planning_approved",
                                 ("2026-01-01", "2027-01-01"), "2026")
        truth = self._one("SELECT COUNT(DISTINCT Packet_ID) AS n FROM tblPlanMaster "
                          "WITH (NOLOCK) WHERE IsApproved = 1 "
                          "AND CreatDate >= '2026-01-01' AND CreatDate < '2027-01-01'")
        assert f"{truth['n']:,}" in out["text"]
        assert truth["n"] == 31_317, "the rule's verified figure moved"

    def test_headcount_matches_the_rule(self):
        out = quick_facts.answer("headcount", None, "")
        truth = self._one("SELECT COUNT(*) AS n FROM tblEmployee WITH (NOLOCK) "
                          "WHERE IsActive = 1")
        assert f"{truth['n']:,}" in out["text"]
        assert truth["n"] == 369, "the rule's verified figure moved"

    def test_kapan_pieces_matches_the_rule(self):
        """OQ26 = 839 packets / 585 Pcs / 682 finished - three defensible
        readings, and the answer must state all three rather than pick one
        silently."""
        out = quick_facts.answer("kapan_pieces", "OQ26", "OQ26")
        for figure in ("839", "585", "682"):
            assert figure in out["text"], f"{figure} missing from the answer"

    def test_every_answer_states_its_basis(self):
        """Several of these questions have more than one defensible reading;
        the rules require naming the one used."""
        for key, scope, label in (("headcount", None, ""),
                                  ("active_departments", None, ""),
                                  ("stock_avg_depth", None, ""),
                                  ("kapan_pieces", "OQ26", "OQ26"),
                                  ("finished_output",
                                   ("2026-08-01", "2026-09-01"), "August 2026")):
            text = quick_facts.answer(key, scope, label)["text"]
            assert "\n\n" in text, f"{key} has no basis note"
            assert len(text.split("\n\n", 1)[1]) > 40, f"{key} basis note is thin"

    def test_an_unknown_fact_errors_rather_than_guessing(self):
        assert quick_facts.answer("no_such_fact").get("text", "").startswith("ERROR")


class TestItCostsNoPromptTokens:

    def test_the_handler_exists_but_no_tool_spec_does(self):
        """Same argument as cut_purity_change: TOOL_SPECS is re-sent on every
        round of every question and the corpus worst case has ~60 tokens of
        headroom. The router reaches this in code, for nothing."""
        from app.agent import tools

        assert "quick_fact" in tools.TOOL_HANDLERS
        assert "quick_fact" not in {s["name"] for s in tools.TOOL_SPECS}


@pytest.mark.integration
class TestNoFalseScopeBanner:
    """A CORRECT number under a banner saying it is unscoped is worse than no
    banner - it teaches the client to distrust a right answer.

    period_guard exempts recipes by looking for ISO dates INSIDE the marker's
    parentheses (_RECIPE_PERIOD_RE). Putting the period after a pipe instead
    made "Aa mahine ketla nang thaya?" return the right August figure (3,214)
    under "covers all available history". Caught live 2026-09-03.
    """

    def test_a_period_fact_marker_carries_the_iso_dates(self):
        from app.agent import period_guard

        out = quick_facts.answer("finished_output",
                                 ("2026-08-01", "2026-09-01"), "August 2026")
        assert "2026-08-01" in out["sql"] and "2026-09-01" in out["sql"]
        assert period_guard._RECIPE_PERIOD_RE.search(out["sql"]), \
            "period_guard will not recognise this marker as period-scoped"

    def test_the_banner_does_not_fire_on_a_scoped_fact(self):
        from app.agent import period_guard

        out = quick_facts.answer("finished_output",
                                 ("2026-08-01", "2026-09-01"), "August 2026")
        assert period_guard.unfiltered_period(
            "Aa mahine ketla nang thaya?", [out["sql"]], out["rows"]) is False

    def test_a_kapan_fact_marker_names_the_kapan(self):
        out = quick_facts.answer("kapan_pieces", "OQ26", "OQ26")
        assert "OQ26" in out["sql"]


@pytest.mark.integration
class TestAZeroExplainsItself:
    """The database is a RESTORED BACKUP that ends before today - tblFinalPacket
    stops 2026-08-20. Asked "Aa mahine ketla nang thaya?" in September, the
    honest answer is 0, which is correct and indistinguishable from a broken
    system. A zero over a period says where the data actually stops."""

    def test_a_period_past_the_data_explains_the_zero(self):
        out = quick_facts.answer("finished_output",
                                 ("2026-09-01", "2026-10-01"), "September 2026")
        assert "data stops before that period" in out["text"]
        assert "tblFinalPacket" in out["text"]

    def test_a_period_inside_the_data_gets_no_such_note(self):
        out = quick_facts.answer("finished_output",
                                 ("2026-08-01", "2026-09-01"), "August 2026")
        assert "data stops before" not in out["text"]
        assert "3,214" in out["text"]

    def test_a_scopeless_fact_never_gets_the_note(self):
        assert "data stops before" not in quick_facts.answer("headcount")["text"]
