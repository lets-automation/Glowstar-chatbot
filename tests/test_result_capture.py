"""
test_result_capture.py
----------------------
Locks the rule that decides WHICH query result is the answer when one question
ran several queries. Both scenarios below are bugs we actually shipped, so each
test names the failure it prevents.
"""
from app.agent.result_capture import better, is_lookup


def _apply(results):
    """Feed results through in order, the way a backend's tool loop does."""
    cols: list[str] = []
    rows: list = []
    for c, r in results:
        if better(c, r, cols, rows):
            cols, rows = c, r
    return cols, rows


# --- bug 1: "give me full report of MFG - 1" -------------------------------
# A 10-row, ONE-column department lookup beat the real 8-column report because
# the old rule was "largest wins". The user was shown department names captioned
# as their report.
LOOKUP = (["DepartMentName"], [{"DepartMentName": f"MFG-{i}"} for i in range(10)])
REPORT = (["ActiveStaff", "PacketsFinished", "TotalCarats", "WIPPackets"],
          [{"ActiveStaff": 42, "PacketsFinished": 305, "TotalCarats": 91.2,
            "WIPPackets": 7}])


def test_a_one_column_lookup_never_wins_over_a_real_report():
    cols, _ = _apply([LOOKUP, REPORT])
    assert cols == REPORT[0], "the department lookup was shown as the report"


def test_lookup_loses_even_when_it_runs_last():
    # Query order is not reliable - the model may re-check a spelling after
    # running the report. The rule must not depend on ordering.
    cols, _ = _apply([REPORT, LOOKUP])
    assert cols == REPORT[0]


# --- bug 2: the kapan-report download ------------------------------------
# A detail list, then a 1-row summary the model ran "for the prose". Taking the
# LAST result would clobber the detail and the Excel download would hold one row.
DETAIL = (["KapanName", "PacketNo", "Weight"],
          [{"KapanName": "GB", "PacketNo": i, "Weight": 1.0} for i in range(500)])
SUMMARY = (["TotalPackets", "TotalWeight"], [{"TotalPackets": 500, "TotalWeight": 500.0}])


def test_a_summary_run_afterwards_does_not_clobber_the_detail_list():
    cols, rows = _apply([DETAIL, SUMMARY])
    assert cols == DETAIL[0] and len(rows) == 500, "the export lost the detail rows"


# --- the fallbacks --------------------------------------------------------
def test_a_lookup_is_kept_when_it_is_all_we_have():
    # "list every department" IS a one-column answer. Better to show it than
    # nothing at all.
    cols, rows = _apply([LOOKUP])
    assert cols == LOOKUP[0] and len(rows) == 10


def test_empty_results_are_ignored():
    cols, rows = _apply([REPORT, ([], []), (["X"], [])])
    assert cols == REPORT[0] and rows == REPORT[1]


def test_nothing_captured_stays_empty():
    assert _apply([]) == ([], [])
    assert _apply([([], [])]) == ([], [])


def test_is_lookup_flags_single_and_zero_column_results():
    assert is_lookup(["Name"]) is True
    assert is_lookup([]) is True
    assert is_lookup(["Name", "Count"]) is False
