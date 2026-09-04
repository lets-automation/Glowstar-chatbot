"""
test_production_report.py
-------------------------
PRODUCTION HAS TWO DEFENSIBLE BASES AND THEY DISAGREE.

Measured on the 2026-08-21 backup:

    May 2026   finished 3,227   MFG stage 2,777   -13.9%
    Jun 2026   finished 4,007   MFG stage 3,993    -0.3%
    Jul 2026   finished 4,476   MFG stage 4,517    +0.9%

They count different EVENTS, not the same thing twice - only about
three-quarters of each month's sets overlap. An unlabelled number that moves
14% between two reasonable readings is exactly how trust was lost on this
project, so the recipe computes BOTH and always states which it used.

  FINISHED  tblFinalPacket.CreateDate - the stone was completed.
  MFG       the maker's stage row. tblFinalPacket has NO department, so any
            per-worker or per-department question must use this basis.

No figure is asserted - they move on every restore. What is pinned is that
both bases are reported and the basis is always named.
"""
from datetime import date

import pytest

from app.agent import recipe_router as rr, reports, tools

TODAY = date(2026, 9, 3)


class TestRouting:

    @pytest.mark.parametrize("q,bucket", [
        ("give me daily production from 1 Jun 2026 to 30 Jun 2026", "day"),
        ("How many packets were made in June 2026?", "total"),
        ("Show today's production summary", "total"),
        ("give me month wise production for 2026", "month"),
    ])
    def test_the_bucket_is_read_from_the_question(self, q, bucket):
        m = rr.match(q, TODAY)
        assert m and m["recipe"] == "production_report"
        assert m["bucket"] == bucket, (q, m)

    def test_a_maker_question_uses_the_mfg_basis(self):
        """tblFinalPacket has no department, so anything per-worker must come
        off the maker's stage row."""
        m = rr.match("how many packets did the karigars manufacture in June 2026",
                     TODAY)
        assert m and m["basis"] == "mfg", m

    def test_a_department_question_goes_to_the_department_report(self):
        """It already breaks production down by worker. The router's
        _REPORT_RE does not contain "production", so this matched NOTHING and
        fell to free SQL until 2026-09-03."""
        m = rr.match("Fency department production for June 2026", TODAY)
        assert m and m["recipe"] == "department_report"
        assert m["department"] == "Fency"

    def test_today_resolves_to_a_day(self):
        """date_gate's _PERIOD_RE already accepted "today", but
        resolve_period could not turn it into dates - so the picker stayed
        quiet AND the router declined, and the question fell to free SQL. A
        period the gate accepts must be one the router can resolve."""
        assert rr.resolve_period("show today's production", TODAY) == (
            "2026-09-03", "2026-09-04")
        assert rr.resolve_period("yesterday's production", TODAY) == (
            "2026-09-02", "2026-09-03")

    def test_it_is_not_a_tool_spec(self):
        assert "production_report" not in {s["name"] for s in tools.TOOL_SPECS}
        assert "production_report" in tools.TOOL_HANDLERS


@pytest.mark.integration
class TestBothBasesAreAlwaysReported:

    def test_the_basis_used_is_named(self):
        out = reports.production_report("2026-05-01", "2026-06-01",
                                        bucket="total")
        assert "Basis: stones FINISHED" in out["text"]
        assert "SAY WHICH BASIS YOU USED" in out["text"]

    def test_the_other_basis_is_reported_alongside(self):
        """The gap was 13.9% in May. Quoting one figure without the other is
        how it gets challenged."""
        out = reports.production_report("2026-05-01", "2026-06-01",
                                        bucket="total")
        assert "The other basis (mfg) gives" in out["text"]

    def test_the_mfg_basis_reports_finished_as_its_counter(self):
        out = reports.production_report("2026-05-01", "2026-06-01",
                                        basis="mfg", bucket="total")
        assert "MFG stage" in out["text"]
        assert "The other basis (finished) gives" in out["text"]

    def test_the_two_bases_actually_differ(self):
        """A RELATIONSHIP, not a figure - it survives a restore. If these ever
        become identical, one of the two readings has broken."""
        fin = reports.production_report("2026-05-01", "2026-06-01",
                                        bucket="total")["sections"][0]["rows"][0]
        mfg = reports.production_report("2026-05-01", "2026-06-01", basis="mfg",
                                        bucket="total")["sections"][0]["rows"][0]
        assert fin["Packets"] != mfg["Packets"]

    @pytest.mark.parametrize("bucket,least", [("day", 15), ("month", 6)])
    def test_the_buckets_actually_bucket(self, bucket, least):
        out = reports.production_report(
            "2026-01-01", "2027-01-01" if bucket == "month" else "2026-02-01",
            bucket=bucket)
        assert len(out["sections"][0]["rows"]) >= least

    def test_a_total_needs_no_group_by(self):
        """"GROUP BY 'a literal'" is invalid in T-SQL - "Each GROUP BY
        expression must contain at least one column". The first run of this
        recipe died on exactly that."""
        out = reports.production_report("2026-05-01", "2026-06-01",
                                        bucket="total")
        assert not out["text"].startswith("ERROR"), out["text"][:160]
        assert len(out["sections"][0]["rows"]) == 1

    def test_an_unknown_basis_is_refused_not_guessed(self):
        out = reports.production_report("2026-05-01", "2026-06-01",
                                        basis="vibes")
        assert out["text"].startswith("ERROR")
        assert "14%" in out["text"]
