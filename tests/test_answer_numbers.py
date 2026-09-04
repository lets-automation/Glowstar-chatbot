"""
The numbers in an answer must come from the DATA, never from the model.

Regression for the 2026-08-24 client demo: the query returned 53 rows totalling
3,227 packets, the model was shown the first 30, and it announced "2,403
packets" - a figure matching neither the true total nor the sum of the rows it
had printed. A second provider said 8,653 for the same query.
"""
import pytest

from app.agent import facts


def _rows(pairs):
    return [{"KapanName": k, "Lab": "GIA", "Packets": n} for k, n in pairs]


GROUPED_SQL = (
    "SELECT TOP 5001 k.KapanName, g.RapVer AS Lab, "
    "COUNT(DISTINCT g.Packet_ID) AS Packets FROM tblPlanMaster g GROUP BY k.KapanName"
)


class TestTotals:
    def test_total_is_summed_over_all_rows_not_the_preview(self):
        rows = _rows([(f"K{i}", 100) for i in range(53)])
        f = facts.compute(GROUPED_SQL, ["KapanName", "Lab", "Packets"], rows)
        assert f["row_count"] == 53
        assert f["totals"]["Packets"] == "5,300"   # all 53, not the first 30

    def test_only_aggregate_columns_are_totalled(self):
        # Summing a raw measurement across rows is a business claim we must not
        # make: this schema repeats a packet once per stage, per day, per rate.
        sql = "SELECT PacketNo, RoughWt FROM tblPacket"
        f = facts.compute(sql, ["PacketNo", "RoughWt"], [{"PacketNo": 1, "RoughWt": 2.5}])
        assert f["totals"] == {}

    def test_capped_result_is_flagged_partial(self):
        f = facts.compute(GROUPED_SQL, ["KapanName", "Lab", "Packets"],
                          _rows([("A", 1)]), truncated=True)
        assert f["partial"] is True
        assert "ONLY the captured rows" in facts.as_model_note(f)

    def test_empty_result_produces_no_claims(self):
        f = facts.compute(GROUPED_SQL, ["KapanName"], [])
        assert facts.as_model_note(f) == ""
        assert facts.totals_line(f) == ""


class TestTotalsLineScopeClause:
    """"across all 1 row" UNDER A TWO-PACKET FIGURE.

    Reported by the client 2026-09-03 on the MFG-1 pending summary, which
    rendered

        PNo: 2, PWt: 0.67, PLSAmt: 29.74 - across all 1 row.

    The clause describes a column summed down a table. Every recipe Summary is
    a SINGLE aggregate row, so the totals and the row are the same object and
    the count says nothing - except to a client, to whom it says the answer
    rests on one record. That is the doubt these totals exist to remove.
    """

    def test_a_single_row_aggregate_carries_no_scope_clause(self):
        line = facts.totals_line(
            {"row_count": 1, "partial": False,
             "totals": {"PNo": "2", "PWt": "0.67", "PLSAmt": "29.74"}})
        assert "across all" not in line
        assert "1 row" not in line
        assert "**PNo: 2**" in line

    def test_a_real_table_still_says_how_many_rows(self):
        line = facts.totals_line(
            {"row_count": 39, "partial": False, "totals": {"PLSAmt": "425.26"}})
        assert "across all 39 rows." in line

    def test_a_capped_result_still_warns_however_few_rows(self):
        """The partial wording is load-bearing - never drop it for a low count."""
        for n in (1, 5001):
            line = facts.totals_line(
                {"row_count": n, "partial": True, "totals": {"PNo": "900"}})
            assert "captured rows" in line, n

    def test_no_totals_still_renders_nothing(self):
        assert facts.totals_line({"row_count": 1, "totals": {}}) == ""


class TestTotalCorrection:
    FACTS = {"row_count": 35, "totals": {"Packets": "2,562"}, "partial": False}

    @pytest.mark.parametrize("text", [
        "In total, **2,403 packets** were processed.",
        "That is a total of 2,403 packets for May.",
        "2,403 packets in total.",
        "Overall, 8,653 packets went to the labs.",
    ])
    def test_wrong_total_is_corrected(self, text):
        out, fixed = facts.correct_total_claims(text, self.FACTS)
        assert "2,562" in out and fixed

    def test_correct_total_is_left_alone(self):
        out, fixed = facts.correct_total_claims(
            "In total, **2,562 packets**.", self.FACTS)
        assert not fixed

    def test_row_values_are_never_rewritten(self):
        # "531" is a real row in the table - only explicit TOTAL claims are ours.
        text = "NS26 led with 531 packets and NT26 followed with 223."
        out, fixed = facts.correct_total_claims(text, self.FACTS)
        assert out == text and not fixed

    def test_ambiguous_multi_total_result_is_left_alone(self):
        # Two totalable columns: which one the sentence meant is a guess, and
        # guessing is the thing being removed from this system.
        f = {"row_count": 3, "totals": {"Packets": "10", "Carats": "20"},
             "partial": False}
        text = "In total, 99 packets."
        assert facts.correct_total_claims(text, f) == (text, [])

    def test_partial_result_is_never_corrected(self):
        f = dict(self.FACTS, partial=True)
        text = "In total, 2,403 packets."
        assert facts.correct_total_claims(text, f) == (text, [])

class TestPinnedReportTotals:
    """A pinned recipe reports its call as a COMMENT, so there is no COUNT()/SUM()
    for the parser to find. Measured live on 2026-08-24: the lab report rendered
    all 27 kapan rows with NO total - the one figure the client checks against
    their ERP. A recipe therefore declares its own additive columns."""

    RECIPE_SQL = ("-- lab_results_report('2026-05-01', '2026-06-01', '', '')"
                  " | totals: PNo, PWt, PLSAmt, GIAAmt, DiffAmt")
    COLUMNS = ["Kapan", "PNo", "PWt", "PLSAmt", "GIAAmt", "DiffAmt", "DiffPer"]
    ROWS = [
        {"Kapan": "NS26", "PNo": 551, "PWt": 380.97, "PLSAmt": 29838.81,
         "GIAAmt": 30346.64, "DiffAmt": 507.83, "DiffPer": 1.70},
        {"Kapan": "NT26", "PNo": 229, "PWt": 142.39, "PLSAmt": 6895.33,
         "GIAAmt": 6973.28, "DiffAmt": 77.95, "DiffPer": 1.13},
    ]

    def test_declared_columns_are_totalled(self):
        f = facts.compute(self.RECIPE_SQL, self.COLUMNS, self.ROWS)
        assert f["totals"]["PNo"] == "780"
        assert f["totals"]["GIAAmt"] == "37,319.92"

    def test_a_percentage_is_never_totalled(self):
        """Summing DiffPer would print a meaningless 2.83%."""
        f = facts.compute(self.RECIPE_SQL, self.COLUMNS, self.ROWS)
        assert "DiffPer" not in f["totals"]

    def test_totals_follow_the_result_column_order(self):
        """The client reads this straight across from their ERP total row."""
        f = facts.compute(self.RECIPE_SQL, self.COLUMNS, self.ROWS)
        assert list(f["totals"]) == ["PNo", "PWt", "PLSAmt", "GIAAmt", "DiffAmt"]

    def test_a_recipe_without_a_declaration_totals_nothing(self):
        f = facts.compute("-- department_report('Fency', '2026-07-01', '2026-08-01')",
                          self.COLUMNS, self.ROWS)
        assert f["totals"] == {}

