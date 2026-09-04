"""
test_unit_guard.py
------------------
A CARAT FIGURE THAT NO WEIGHT COLUMN PRODUCED.

Seen live in the 2026-08-31 cold run:

    Q: "OQ26 kapan ma final point / final polish weight ketlu nikalyu?"
    A: "OQ26 has 6,107.39 points earned in final-polish work and a total of
        6,107.39 carats polished in that kapan."

The same number under two units. The points half was right - SUM(FMFGPoint) is
6,107.39, exactly what query_rules.final_points requires - and the carat half
was that number re-labelled. The true weight is 378.458.

It is the other half of query_rules.weight_via_points_join: that rule refuses
the one query which would compute both (tblPacketPoint covers 398 of the
kapan's 839 packets), and this catches the model asserting the weight anyway
instead of running the second query it was told to run.
"""
import pytest

from app.agent import unit_guard


class TestTheLiveFailureIsCaught:

    ANSWER = ("OQ26 has **6,107.39 points** earned in final-polish work and a "
              "total of **6,107.39 carats** polished in that kapan.")
    COLUMNS = ["FinalPoints"]
    ROWS = [{"FinalPoints": 6107.39}]

    def test_the_relabelled_number_is_flagged(self):
        assert unit_guard.unsourced_carat_claim(
            self.ANSWER, self.COLUMNS, self.ROWS) == "6,107.39"

    def test_the_caution_names_the_figure(self):
        note = unit_guard.caution("6,107.39")
        assert "6,107.39" in note and "no weight column" in note


class TestItStaysSilentWhenItShould:
    """A false positive here puts a warning on top of a correct answer, so the
    silent cases outnumber the firing one."""

    def test_a_real_weight_column_is_left_alone(self):
        assert unit_guard.unsourced_carat_claim(
            "Total 378.458 ct polished.",
            ["PolishedCarats"], [{"PolishedCarats": 378.458}]) is None

    @pytest.mark.parametrize("col", ["CurrentWt", "TotalWeight", "Carats", "cts"])
    def test_any_weight_shaped_column_disarms_it(self, col):
        assert unit_guard.unsourced_carat_claim(
            "We polished 12.5 carats.", [col], [{col: 12.5}]) is None

    def test_a_points_answer_with_no_carat_claim_passes(self):
        assert unit_guard.unsourced_carat_claim(
            "There are 6,107.39 points.",
            ["FinalPoints"], [{"FinalPoints": 6107.39}]) is None

    def test_a_carat_number_absent_from_the_data_is_not_our_business(self):
        """Only a number that came OUT of the result and was re-labelled is the
        signature. A figure quoted from elsewhere is a different problem and
        belongs to the anti-fabrication guard, not this one."""
        assert unit_guard.unsourced_carat_claim(
            "About 12.5 carats were lost.",
            ["FinalPoints"], [{"FinalPoints": 6107.39}]) is None

    @pytest.mark.parametrize("answer,columns,rows", [
        ("", ["FinalPoints"], [{"FinalPoints": 1.0}]),
        ("5 carats", [], []),
        ("5 carats", ["FinalPoints"], []),
    ])
    def test_empty_inputs_never_fire(self, answer, columns, rows):
        assert unit_guard.unsourced_carat_claim(answer, columns, rows) is None


class TestItIsWiredIntoTheAnswer:

    def test_postprocess_prepends_the_caution(self):
        """The warning goes ABOVE the answer - a note under a figure is not
        read - and the answer itself is left intact, because the points half is
        real and destroying it on a false positive is the worse bug."""
        import inspect

        from app.agent import postprocess

        src = inspect.getsource(postprocess)
        assert "unit_guard" in src
        assert "UNSOURCED-CARAT" in src
