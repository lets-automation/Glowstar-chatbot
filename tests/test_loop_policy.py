"""
test_loop_policy.py
-------------------
The tool-loop policy: when to push a stalled model, what counts as ungrounded,
and when a "report" came back as a summary instead of detail rows.

This logic used to live in groq_backend.py, which the other two backends had to
import PRIVATE names from. It is provider-agnostic, so it now lives on its own
and is tested directly rather than through whichever provider happened to run.
"""
import pytest

from app.agent import loop_policy as lp


# --- ungrounded answers ----------------------------------------------------
@pytest.mark.parametrize("text", [
    "SELECT KapanName FROM tblKapan",
    "Here is the query:\nselect * from tblPacket where x = 1",
])
def test_written_out_sql_is_detected(text):
    assert lp.looks_like_unrun_sql(text) is True


@pytest.mark.parametrize("text", [
    "", None,
    "We finished 305 packets in June.",
    # 'select' alone is not a query - a plain-English sentence must not trip it.
    "Please select a department to continue.",
])
def test_ordinary_prose_is_not_mistaken_for_sql(text):
    assert lp.looks_like_unrun_sql(text) is False


def test_charts_and_dashboards_count_as_presenting_data():
    # A chart shows numbers exactly as a table does, so an ungrounded one is
    # just as fabricated.
    assert lp.has_data_visual([{"kind": "chart"}]) is True
    assert lp.has_data_visual([{"kind": "dashboard"}]) is True


def test_a_plain_widget_is_not_a_data_visual():
    # kind='widget' may legitimately need no DB data, so it must not force a
    # query round.
    assert lp.has_data_visual([{"kind": "widget"}]) is False
    assert lp.has_data_visual([]) is False
    assert lp.has_data_visual(None) is False


# --- report-came-back-as-a-summary ----------------------------------------
def test_all_aggregated_is_true_only_when_every_query_grouped():
    assert lp.all_sql_aggregated(["SELECT a, COUNT(*) FROM t GROUP BY a"]) is True


def test_a_detail_query_followed_by_a_total_is_not_flagged():
    # The GOOD pattern: pull the detail rows, then one small total for the
    # headline. Checking only the LAST query would wrongly flag this.
    assert lp.all_sql_aggregated([
        "SELECT KapanName, PacketNo FROM tblFinalPacket",
        "SELECT COUNT(*) FROM tblFinalPacket GROUP BY KapanName",
    ]) is False


def test_no_queries_is_not_aggregated():
    assert lp.all_sql_aggregated([]) is False


# --- intent detection ------------------------------------------------------
@pytest.mark.parametrize("q", ["give me the damage report", "stock reports please"])
def test_report_intent(q):
    assert lp.REPORT_ASKED_RE.search(q)


@pytest.mark.parametrize("q", ["summary of June", "how many packets", "monthly trend"])
def test_summary_intent_exempts_aggregation(q):
    assert lp.SUMMARY_INTENT_RE.search(q)


@pytest.mark.parametrize("q", ["show me a dashboard", "production analytics", "give an overview"])
def test_dashboard_intent(q):
    assert lp.DASHBOARD_ASKED_RE.search(q)


# --- the module's contract -------------------------------------------------
def test_policy_stays_free_of_provider_imports():
    """
    The whole point of this module is that it belongs to no provider. If a
    backend import creeps in, the dependency arrow reverses and we are back to
    'groq_backend is secretly the framework'.
    """
    import ast
    import inspect

    # Parse real import NODES rather than scanning text. The docstring both
    # names the backends in prose AND quotes the old import statement verbatim
    # to show what was wrong - a line-based check flags its own documentation.
    tree = ast.parse(inspect.getsource(lp))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [n.name for n in node.names]
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")

    for mod in imported:
        for backend in ("groq_backend", "gemini_backend", "anthropic_backend"):
            assert backend not in mod, f"loop_policy must not import {backend}"


def test_nudges_are_non_empty():
    # An empty nudge silently disables a guard - the model gets a blank message
    # and carries on exactly as before.
    for nudge in (lp.EXECUTE_NUDGE, lp.DASHBOARD_NUDGE, lp.REPORT_DETAIL_NUDGE):
        assert nudge and len(nudge) > 80


# --- thin entity report ("report of <entity>" = only the WHO row) ----------
WHO_ROW = {"columns": ["FirstName", "LastName", "DepartMentName", "Code"],
           "rows": [{"FirstName": "VEKARIYA", "LastName": "DINESHBHAI",
                     "DepartMentName": "MFG-4", "Code": "M4167"}]}
PRODUCTION = {"columns": ["KapanName", "PacketNo", "Carats"],
              "rows": [{"KapanName": "NS26", "PacketNo": i, "Carats": 1.0}
                       for i in range(40)]}


def test_a_report_that_is_only_the_identity_row_is_flagged():
    # The client's case: "full report of employee code MF4167" produced one row
    # of name/code/department, and the Excel download was that single row.
    assert lp.thin_entity_report("give me full report of employee code M4167",
                                 [WHO_ROW]) is True


def test_a_real_multi_section_report_is_not_flagged():
    assert lp.thin_entity_report("give me full report of employee M4167",
                                 [WHO_ROW, PRODUCTION]) is False


def test_one_big_section_is_not_flagged():
    # A department report that is one long detail listing IS a report.
    assert lp.thin_entity_report("give me full report of MFG - 1", [PRODUCTION]) is False


def test_a_question_that_is_not_a_report_is_left_alone():
    assert lp.thin_entity_report("who is employee M4167", [WHO_ROW]) is False


def test_an_explicit_summary_is_left_alone():
    # "summary"/"how many" legitimately return one small result.
    assert lp.thin_entity_report("summary report of employee M4167", [WHO_ROW]) is False
    assert lp.thin_entity_report("how many packets report", [WHO_ROW]) is False


def test_no_sections_at_all_is_flagged():
    # Nothing came back for a report question - worth one corrective round.
    assert lp.thin_entity_report("full report of employee M4167", []) is True
