"""
test_period_phrasings.py
------------------------
A PERIOD ONE LAYER ACCEPTS MUST BE ONE THE NEXT CAN RESOLVE.

Audit 2026-09-05. date_gate._PERIOD_RE already matched "week", "quarter",
"fortnight", "last N days", "mtd", "ytd" and "q1".."q4" - so the date picker
stayed QUIET for those questions. But recipe_router.resolve_period returned
None for every one of them, so match() declined and the question fell silently
to free SQL WITH NO PERIOD AT ALL - the path that produced every wrong answer
this project has shipped.

Six phrasings were in that state: "last week", "this quarter", "Q1",
"last 7 days", "last 30 days", "fortnight".

The invariant this file pins is the AGREEMENT between the two layers, not the
dates themselves: if the picker does not ask, the router must resolve.
"""
from datetime import date

import pytest

from app.agent import date_gate, recipe_router as rr

# A Thursday, so weekday arithmetic is actually exercised.
TODAY = date(2026, 9, 3)


class TestTheTwoLayersAgree:
    """THE core property. Everything else here is detail."""

    @pytest.mark.parametrize("q", [
        "production last week", "production this week",
        "production this quarter", "production last quarter",
        "production in Q1", "production Q3 2026",
        "production last 7 days", "production last 30 days",
        "production last 2 months", "production in the last fortnight",
        "production mtd", "production ytd",
        "production for July 2026", "production in 2025",
        "production today", "production yesterday",
        "production last month", "production this year",
    ])
    def test_a_period_the_picker_accepts_is_one_the_router_resolves(self, q):
        asks = date_gate.needs_date(q, [])
        resolved = rr.resolve_period(q, TODAY)
        assert asks or resolved is not None, (
            f"{q!r}: the picker stays quiet AND the router cannot resolve it, "
            "so it falls to free SQL with no period at all")


class TestTheBoundariesAreRight:
    """A week is the CALENDAR week; "last 7 days" is the rolling one. The
    client means different things by the two, so they are not aliases."""

    def test_last_week_is_the_previous_monday_to_monday(self):
        # 2026-09-03 is a Thursday -> last week is Mon 24 to Mon 31 Aug.
        assert rr.resolve_period("last week", TODAY) == ("2026-08-24", "2026-08-31")

    def test_this_week_starts_on_monday(self):
        assert rr.resolve_period("this week", TODAY) == ("2026-08-31", "2026-09-07")

    def test_last_7_days_is_rolling_not_calendar(self):
        assert rr.resolve_period("last 7 days", TODAY) == ("2026-08-27", "2026-09-03")

    def test_a_quarter_spans_three_months_end_exclusive(self):
        assert rr.resolve_period("Q1", TODAY) == ("2026-01-01", "2026-04-01")
        assert rr.resolve_period("Q4 2025", TODAY) == ("2025-10-01", "2026-01-01")

    def test_this_and_last_quarter_are_relative_to_today(self):
        # September is Q3.
        assert rr.resolve_period("this quarter", TODAY) == ("2026-07-01", "2026-10-01")
        assert rr.resolve_period("last quarter", TODAY) == ("2026-04-01", "2026-07-01")

    def test_last_quarter_wraps_the_year(self):
        jan = date(2026, 1, 15)
        assert rr.resolve_period("last quarter", jan) == ("2025-10-01", "2026-01-01")

    def test_mtd_and_ytd_run_to_today_inclusive(self):
        # to_date is EXCLUSIVE everywhere, so "to today inclusive" is tomorrow.
        assert rr.resolve_period("mtd", TODAY) == ("2026-09-01", "2026-09-04")
        assert rr.resolve_period("ytd", TODAY) == ("2026-01-01", "2026-09-04")

    def test_fortnight_is_fourteen_days(self):
        assert rr.resolve_period("last fortnight", TODAY) == ("2026-08-20", "2026-09-03")


class TestTheMoreSpecificPhrasingWins:
    """A bare year is the LAST resort - an explicit month or quarter that
    happens to contain a year must not be swallowed by it."""

    def test_a_quarter_with_a_year_is_not_read_as_the_whole_year(self):
        assert rr.resolve_period("Q3 2026", TODAY) == ("2026-07-01", "2026-10-01")

    def test_a_month_with_a_year_still_wins(self):
        assert rr.resolve_period("July 2026", TODAY) == ("2026-07-01", "2026-08-01")

    def test_an_iso_range_still_wins(self):
        assert rr.resolve_period("from 2026-06-01 to 2026-07-01", TODAY) == (
            "2026-06-01", "2026-07-01")

    def test_a_bare_year_still_works(self):
        assert rr.resolve_period("production in 2025", TODAY) == (
            "2025-01-01", "2026-01-01")


class TestNothingIsInvented:

    @pytest.mark.parametrize("q", ["hello", "what is a kapan?",
                                   "how many employees do we have?"])
    def test_a_question_with_no_period_resolves_to_none(self, q):
        assert rr.resolve_period(q, TODAY) is None

    def test_an_absurd_count_is_not_accepted(self):
        """"last 9999 days" is not a period anyone means."""
        assert rr.resolve_period("last 9999 days", TODAY) is None

    def test_the_patterns_carry_no_eaten_backslash(self):
        """A literal word-boundary in this file has become a 0x08 BACKSPACE
        byte twice. Assert the bytes, not the intent."""
        for name in ("_LAST_WEEK_RE", "_THIS_WEEK_RE", "_LAST_N_RE",
                     "_FORTNIGHT_RE", "_QUARTER_RE", "_MTD_RE", "_YTD_RE"):
            pat = getattr(rr, name).pattern
            assert chr(8) not in pat, name
