"""
test_kapan_report.py
--------------------
THE WHOLE PICTURE FOR ONE KAPAN.

~7 of the 101 uncovered questions in the 2026-09-03 audit: "packet report for
kapan AA", "Kapan Finish Report for NS26", "kapan Estimation report".

THE TRAPS THIS ENCODES, each of which cost a wrong answer once:

  * PIECES HAS THREE DEFENSIBLE ANSWERS and they disagree - NS26 has 792
    packet rows, SUM(Pcs) of 404 and 768 finished rows. Picking one silently
    is how the same kapan gets three different sizes in three conversations.
  * ChapkaLoss is populated on ONE kapan in the whole database. An empty
    column shown as a measurement is worse than saying it is not tracked.
  * `Weight` is AMBIGUOUS - tblJunk and tblKapan both have one. The first run
    of this recipe died on it.
  * sql_guard REJECTS '--' comments inside a query. The second run died on
    that. Notes go in Python, never in the SQL string.
  * There is no cost data, so FinishedValue minus RoughValue is not profit.

No figure is asserted here - row counts move on every restore. What is pinned
is that the three counts are all PRESENT and that the caveats are stated.
"""
import pytest

from app.agent import recipe_router as rr, reports, tools


class TestRouting:

    @pytest.mark.parametrize("q", [
        "show me packet report for kapan AA",
        "Give me the full packet report for kapan NS26",
        "show me the full packet report for kapan AA with a summary",
        "Show the Kapan Finish Report for Kapan NS26.",
        "Provide me kapan Estimation report for kapan OU26",
    ])
    def test_report_phrasings_route(self, q):
        m = rr.match(q)
        assert m and m["recipe"] == "kapan_report", (q, m)

    @pytest.mark.parametrize("q,expected", [
        # A kapan question with its OWN recipe must keep it.
        ("For kapan NS26, show packets where the MFG grade differs from the "
         "GIA grade on cut or clarity", "cut_purity_change"),
        ("kapan OQ26 ma total ketla piece hata?", "quick_fact"),
        ("give me report of department MFG - 1 for July 2026",
         "department_report"),
    ])
    def test_it_does_not_steal_other_kapan_questions(self, q, expected):
        m = rr.match(q)
        assert m and m["recipe"] == expected, (q, m)

    def test_a_damage_question_is_not_the_general_report(self):
        """Damage has its own definition (tblPlanReport.IsDamageReport) and is
        still to be built; the general report must not silently absorb it."""
        m = rr.match("PREPARE DAMAGE REPORT FOR OS26 KAPAN")
        assert not (m and m.get("recipe") == "kapan_report")

    def test_it_is_not_a_tool_spec(self):
        assert "kapan_report" not in {s["name"] for s in tools.TOOL_SPECS}
        assert "kapan_report" in tools.TOOL_HANDLERS


@pytest.mark.integration
class TestTheReport:

    def test_all_three_piece_counts_are_present(self):
        """They disagree by design. Showing one is how the same kapan gets
        three different sizes in three conversations."""
        out = reports.kapan_report("NS26")
        totals = next(s for s in out["sections"] if s["title"] == "Totals")
        row = totals["rows"][0]
        for col in ("PacketRows", "SumOfPcs", "FinishedRows"):
            assert row.get(col) is not None, col
        assert "THREE DEFENSIBLE ANSWERS" in out["text"]

    def test_it_names_the_count_to_prefer(self):
        out = reports.kapan_report("NS26")
        assert "PREFER the tblPacket row count" in out["text"]

    def test_chapka_loss_is_declared_untracked_not_shown_as_zero(self):
        out = reports.kapan_report("NS26")
        if "Boil loss" in out["text"]:
            assert "Chapka loss is NOT tracked" in out["text"]
        cols = {c for s in out["sections"] for c in s["columns"]}
        assert "ChapkaLoss" not in cols

    def test_it_refuses_to_imply_profit(self):
        """RoughValue minus FinishedValue is not margin - there is no cost
        data anywhere in this database."""
        out = reports.kapan_report("NS26")
        assert "call it profit" in out["text"]

    def test_the_stage_ladder_is_there(self):
        out = reports.kapan_report("NS26")
        stages = next(s for s in out["sections"] if s["title"] == "Stage ladder")
        seen = {r["Stage"] for r in stages["rows"]}
        assert {"CLV", "MFG", "PLS"} <= seen, seen

    def test_the_ambiguous_weight_column_does_not_break_it(self):
        """tblJunk.Weight and tblKapan.Weight - unqualified, SQL Server throws
        'Ambiguous column name' and the whole report dies."""
        out = reports.kapan_report("NS26")
        assert not out["text"].startswith("ERROR"), out["text"][:160]

    def test_no_sql_comment_reaches_the_guard(self):
        """sql_guard rejects '--' in a query outright. Notes belong in Python."""
        out = reports.kapan_report("NS26")
        assert "SQL comments are not allowed" not in out["text"]

    def test_a_near_miss_kapan_is_refused_not_guessed(self):
        out = reports.kapan_report("ZZ99")
        assert out["text"].startswith("ERROR")
        assert "do NOT pick the closest one" in out["text"]
