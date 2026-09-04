"""
test_recipe_router.py
---------------------
THE RECIPE IS CHOSEN IN CODE, NOT BY THE MODEL.

Measured 2026-08-31: called directly the recipes are correct
(department_report = 8 sections, lab_results = 4), but the model would not
CALL them - "Provide july month report of department MFG - 1" and "provide me
last month GIA results employee wise for fency department" both came back with
no tool call, so the anti-fabrication guard refused the prose written instead
and the client saw "I couldn't pull that" for questions the system answers
perfectly.

Every period here is resolved against a FIXED today (31 Aug 2026, the day the
client hit these), so the suite cannot drift with the calendar.
"""
from datetime import date

import pytest

from app.agent import recipe_router as rr

TODAY = date(2026, 8, 31)


class TestPeriodResolution:
    """`to` is EXCLUSIVE throughout - an inclusive end silently drops the last
    day, which is the 5% loss query_rules.date_range_exclusive exists to stop."""

    @pytest.mark.parametrize("q,want", [
        ("Provide july month report of department MFG - 1", ("2026-07-01", "2026-08-01")),
        ("report for July 2026", ("2026-07-01", "2026-08-01")),
        ("last month GIA results", ("2026-07-01", "2026-08-01")),
        ("past month report", ("2026-07-01", "2026-08-01")),
        ("this month report", ("2026-08-01", "2026-09-01")),
        ("aa varsh no report", ("2026-01-01", "2027-01-01")),
        ("last year report", ("2025-01-01", "2026-01-01")),
        ("report from 2026-05-01 to 2026-06-01", ("2026-05-01", "2026-06-01")),
    ])
    def test_english(self, q, want):
        assert rr.resolve_period(q, TODAY) == want

    @pytest.mark.parametrize("q,want", [
        ("gaya mahine nu report", ("2026-07-01", "2026-08-01")),
        ("aa mahine no report", ("2026-08-01", "2026-09-01")),
        ("MFG 1 nu report aapo July 2026 nu", ("2026-07-01", "2026-08-01")),
    ])
    def test_gujlish(self, q, want):
        """The client's staff do not write fluent English - this is the whole
        point of matching on the words they actually type."""
        assert rr.resolve_period(q, TODAY) == want

    def test_a_bare_month_takes_the_most_recent_one(self):
        """"december" asked in Aug 2026 means Dec 2025, not a future month."""
        assert rr.resolve_period("report for december", TODAY) == (
            "2025-12-01", "2026-01-01")

    @pytest.mark.parametrize("q", ["give me a report", "hello", ""])
    def test_no_period_is_never_invented(self, q):
        """An unbounded report is the failure date_gate exists to prevent, so
        the router must decline rather than guess."""
        assert rr.resolve_period(q, TODAY) is None


class TestMatching:

    @pytest.mark.parametrize("q,recipe,dept", [
        ("Provide july month report of department MFG - 1", "department_report", "MFG - 1"),
        ("give me report of department MFG - 1 for July 2026", "department_report", "MFG - 1"),
        ("MFG 1 nu report aapo July 2026 nu", "department_report", "MFG - 1"),
        ("provide me last month GIA results employee wise for fency department",
         "lab_results", "Fency"),
        ("last month gia results", "lab_results", ""),
    ])
    def test_it_routes_the_questions_that_were_failing(self, q, recipe, dept):
        hit = rr.match(q, TODAY)
        assert hit and hit["recipe"] == recipe
        assert hit["department"] == dept

    @pytest.mark.parametrize("q,why", [
        # (the pending question moved to TestPendingIsRoutedToItsOwnRecipe
        #  once pending_lab_results existed to answer it)
        ("how many total were pending in last month",
         "names no stage - guessing one is how the completed-work report "
         "came to answer a pending question"),
        ("give me report of department Marketing for July 2026",
         "department does not resolve - the normal path must ask which one"),
        ("provide report of department MFG - 1",
         "no period named - must not be invented"),
        ("how many oval diamonds do we have in stock?", "not a recipe question"),
        ("hello", "not a recipe question"),
    ])
    def test_it_declines_everything_else(self, q, why):
        assert rr.match(q, TODAY) is None, why


@pytest.mark.integration
class TestTheAnswerIsRealData:
    """No provider is involved, so these run against the database alone."""

    def test_the_department_report_returns_every_section(self):
        raw = rr.answer(rr.match(
            "Provide july month report of department MFG - 1", TODAY))
        assert raw["rows_returned"] > 0
        titles = [s.get("title") for s in raw["data_sections"]]
        for expected in ("Workforce", "Production summary", "Damage", "Bonus"):
            assert expected in titles, titles

    def test_the_lab_report_carries_the_employee_breakdown(self):
        """"employee wise" must be answered, not offered as a follow-up."""
        raw = rr.answer(rr.match(
            "provide me last month GIA results employee wise for fency department",
            TODAY))
        titles = [s.get("title") for s in raw["data_sections"]]
        assert "By employee" in titles, titles

    def test_the_model_facing_preamble_is_not_shown_to_the_user(self):
        """The recipe text is addressed to the MODEL ("Present ALL of them to
        the user...") - showing that verbatim would print our own instructions."""
        raw = rr.answer(rr.match(
            "Provide july month report of department MFG - 1", TODAY))
        assert "Present ALL of them" not in raw["answer"]
        assert raw["answer"].startswith("Here is the department report")

    def test_the_answer_is_grounded_so_no_guard_can_reject_it(self):
        """sql_used and rows must be populated, or postprocess's
        anti-fabrication guard would replace this with a refusal."""
        raw = rr.answer(rr.match("last month gia results", TODAY))
        assert raw["sql_used"] and raw["rows_returned"] > 0


class TestPendingIsRoutedToItsOwnRecipe:
    """"Pending" was the question that started all of this.

    It was answered from lab_results_report - the COMPLETED comparison - which
    reported 379 packets carrying both a PLSAmt and a GIAAmt. A pending packet
    has not been graded, so it cannot have a GIA amount; the answer contradicted
    itself, and the follow-up said 0 in the same session. Three later attempts
    to write it as SQL produced an inverted anti-join and a filter on the
    packet's CURRENT location, both of which return 0 by construction.
    """

    @pytest.mark.parametrize("q", [
        "give me polished GIA pending for mfg-1 department of past month",
        "give me data whose polish planned is already done but gia "
        "certification is pending for MFG-1 department for july month",
        "gia pending last month",
    ])
    def test_a_lab_pending_question_routes_to_the_pending_recipe(self, q):
        hit = rr.match(q, TODAY)
        assert hit and hit["recipe"] == "pending_lab_results"

    def test_a_bare_pending_question_is_not_guessed(self):
        """"how many total were pending" names no stage. Guessing one is how
        the completed-work report came to answer a pending question."""
        assert rr.match("how many total were pending in last month", TODAY) is None

    def test_pending_wins_over_the_completed_report(self):
        """"GIA pending results" matches BOTH the lab-results words and the
        pending words - pending is the narrower reading and must win."""
        hit = rr.match("gia pending results for last month", TODAY)
        assert hit and hit["recipe"] == "pending_lab_results"


@pytest.mark.integration
class TestThePendingRecipeUsesTheClientsOwnDefinition:
    """PENDING IS POSITIONAL - the packet's LATEST approved plan row IS its PLS
    row - NOT the plain anti-join "has PLS, has no GIA".

    This class used to assert the anti-join, because that shape was lifted from
    the client's own dbo.GetPLSSUM and looked unimpeachable. It over-counts:
    "no GIA row" also keeps stones that HAVE moved on, graded at another lab or
    re-planned after grading. On the one question the client checked against
    their own screen - MFG - 1, July 2026 - the anti-join says 12 and they say
    2, and the 12 is the number we quoted them.

    Both readings are recomputed here, independently of the recipe, so the test
    fails if the recipe drifts back to the wrong one rather than merely
    reporting a different number.
    """

    _MAKER_JOIN = """
FROM tblPlanMaster pls
OUTER APPLY (SELECT TOP 1 mm.EmpId FROM tblPlanMaster mm
             WHERE mm.Packet_ID = pls.Packet_ID AND mm.RapVer = 'MFG'
             ORDER BY mm.ID DESC) m
LEFT JOIN tblEmployee e ON e.ID = m.EmpId
WHERE pls.RapVer = 'PLS' AND ISNULL(pls.IsDamagePlan,0) = 0
  AND pls.IsApproved = 1
  AND pls.CreatDate >= '2026-07-01' AND pls.CreatDate < '2026-08-01'
  AND e.DepartMentName = 'MFG - 1'
  AND LTRIM(RTRIM(pls.LAB)) IN ('GIA','HRD','IGI')"""

    # The definition the client confirmed: nothing approved came after the PLS
    # row, so the stone is still sitting at polish.
    _LATEST = _MAKER_JOIN + """
  AND NOT EXISTS (SELECT 1 FROM tblPlanMaster nx
                  WHERE nx.Packet_ID = pls.Packet_ID
                    AND ISNULL(nx.IsDamagePlan,0) = 0 AND nx.IsApproved = 1
                    AND (nx.CreatDate > pls.CreatDate
                         OR (nx.CreatDate = pls.CreatDate AND nx.ID > pls.ID)))"""

    # The reading this class used to enforce. Kept so the regression is named.
    _ANTI_JOIN = _MAKER_JOIN + """
  AND NOT EXISTS (SELECT 1 FROM tblPlanMaster g
                  WHERE g.Packet_ID = pls.Packet_ID AND g.RapVer = 'GIA'
                    AND ISNULL(g.IsDamagePlan,0) = 0 AND g.IsApproved = 1)"""

    @staticmethod
    def _count(where_sql):
        from app.database.runner import run_select

        r = run_select("SELECT COUNT(DISTINCT pls.Packet_ID) AS n" + where_sql,
                       max_rows=3)
        assert r["ok"], r.get("error")
        return r["rows"][0]["n"]

    @staticmethod
    def _recipe_pno():
        raw = rr.answer(rr.match(
            "give me polished GIA pending for mfg-1 department of past month",
            TODAY))
        summary = next(s for s in raw["data_sections"] if s["title"] == "Summary")
        return summary["rows"][0]["PNo"]

    def test_it_counts_only_stones_that_have_not_moved_on(self):
        assert self._recipe_pno() == self._count(self._LATEST)

    def test_it_is_not_the_old_anti_join(self):
        """The two readings must actually DISAGREE on this question - otherwise
        the test above would pass for a recipe that never changed."""
        latest, anti = self._count(self._LATEST), self._count(self._ANTI_JOIN)
        assert latest < anti, (
            f"expected the anti-join to over-count here; got {anti} vs {latest}")
        assert self._recipe_pno() != anti

    def test_a_pending_answer_carries_no_lab_value(self):
        """THE TELL THAT STARTED THIS. A GIAAmt on a pending packet is a
        contradiction - the packet has not been graded."""
        raw = rr.answer(rr.match(
            "give me polished GIA pending for mfg-1 department of past month",
            TODAY))
        for sec in raw["data_sections"]:
            assert "GIAAmt" not in sec["columns"], sec["title"]
        assert "GIAAmt" not in raw["answer"]

    def test_it_is_scoped_by_the_maker_not_the_current_location(self):
        """tblPacket.DepartMentId is where the packet is SITTING NOW - a
        polished stone waiting for the lab has left MFG-1, so that filter
        returns 0. The recipe joins the MFG plan row's worker instead."""
        raw = rr.answer(rr.match(
            "give me polished GIA pending for mfg-1 department of past month",
            TODAY))
        summary = next(s for s in raw["data_sections"] if s["title"] == "Summary")
        assert summary["rows"][0]["PNo"] > 0, "the location trap returns 0"
