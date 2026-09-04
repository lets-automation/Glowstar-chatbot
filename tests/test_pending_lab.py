"""
test_pending_lab.py
-------------------
THE LAB DIMENSION OF A PENDING QUESTION.

The client's rule, given 2026-08-31: a pending question counts ALL labs by
default, and the bot must ask which lab rather than assume GIA.

That is only answerable because the destination lab is recorded on the PLS row
itself (tblPlanMaster.LAB), so a stone that has been to NO lab still knows
which lab it is waiting for. The absent stage row cannot tell you - there is no
such row, which is the whole point of the question.

The fourth value of that column is 'NONE': a stone marked as never going to a
lab. Counting those as "pending certification" reports work as waiting that
nobody is waiting for, so they are excluded and that exclusion is pinned here.
"""
from datetime import date

import pytest

from app.agent import recipe_router as rr
from app.agent import reports

TODAY = date(2026, 8, 31)

# August 2026, company-wide - the period with enough pending stones to tell the
# lab breakdown apart. Half-open, as everywhere else.
FROM, TO = "2026-08-01", "2026-09-01"


class TestResolveLab:

    @pytest.mark.parametrize("given,want", [
        ("GIA", "GIA"), ("gia", "GIA"), (" hrd ", "HRD"), ("igi", "IGI"),
    ])
    def test_it_accepts_the_three_labs_in_any_case(self, given, want):
        code, err = reports.resolve_lab(given)
        assert (code, err) == (want, "")

    def test_empty_means_all_labs_and_is_not_an_error(self):
        """The client's default. An empty lab must not be treated as a failure
        to resolve, or every unqualified pending question becomes an error."""
        assert reports.resolve_lab("") == (None, "")
        assert reports.resolve_lab(None) == (None, "")

    def test_an_unknown_lab_explains_itself(self):
        code, err = reports.resolve_lab("SGL")
        assert code is None
        assert "SGL" in err and "GIA" in err


class TestTheRouterOnlyScopesWhenExactlyOneLabIsNamed:
    """Naming two labs falls back to ALL, which is the safe direction: a wider
    count, not a silently narrower one."""

    @pytest.mark.parametrize("q,want", [
        ("gia pending last month", "GIA"),
        ("hrd pending last month", "HRD"),
        ("IGI baki chhe", "IGI"),
        ("how many are pending for the lab", ""),
        ("gia and hrd pending last month", ""),
    ])
    def test_named_lab(self, q, want):
        assert rr.named_lab(q) == want

    def test_the_lab_reaches_the_recipe_spec(self):
        hit = rr.match("gia pending for last month", TODAY)
        assert hit and hit["recipe"] == "pending_lab_results"
        assert hit["lab"] == "GIA"

    def test_an_unqualified_pending_question_carries_no_lab(self):
        hit = rr.match("how many packets are pending for the lab last month",
                       TODAY)
        assert hit and hit["lab"] == ""


@pytest.mark.integration
class TestTheLabFilterIsRealAndExcludesNONE:

    @staticmethod
    def _summary(**kw):
        out = reports.pending_lab_report(FROM, TO, **kw)
        sec = next(s for s in out["sections"] if s["title"] == "Summary")
        return out, sec["rows"][0]

    def test_naming_a_lab_narrows_the_count(self):
        _, all_labs = self._summary()
        _, gia = self._summary(lab="GIA")
        assert 0 < gia["PNo"] <= all_labs["PNo"]

    def test_the_lab_breakdown_only_appears_when_no_lab_was_named(self):
        """With a lab named it would be one row restating the summary."""
        out_all, _ = self._summary()
        out_gia, _ = self._summary(lab="GIA")
        assert "By lab" in [s["title"] for s in out_all["sections"]]
        assert "By lab" not in [s["title"] for s in out_gia["sections"]]

    def test_stones_marked_NONE_are_not_pending_anything(self):
        """LAB='NONE' is not a lab - it is a stone that is not going to one."""
        out, _ = self._summary()
        by_lab = next(s for s in out["sections"] if s["title"] == "By lab")
        labs = {r["Lab"] for r in by_lab["rows"]}
        assert "NONE" not in labs
        assert labs <= {"GIA", "HRD", "IGI"}

    def test_the_lab_rows_add_up_to_the_summary(self):
        """A packet has one PLS row, so the by-lab split must partition the
        total exactly - if it does not, the filter is double-counting."""
        out, summary = self._summary()
        by_lab = next(s for s in out["sections"] if s["title"] == "By lab")
        assert sum(r["PNo"] for r in by_lab["rows"]) == summary["PNo"]

    def test_an_unknown_lab_refuses_rather_than_widening(self):
        out = reports.pending_lab_report(FROM, TO, lab="SGL")
        assert out["text"].startswith("ERROR")
        assert out["sections"] == []

    def test_a_pending_answer_never_carries_a_lab_value(self):
        """THE TELL THAT STARTED THIS - a GIAAmt on an ungraded packet."""
        out, _ = self._summary()
        for sec in out["sections"]:
            assert "GIAAmt" not in sec["columns"], sec["title"]
