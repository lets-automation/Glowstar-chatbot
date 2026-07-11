"""
test_regression_audit.py
------------------------
REGRESSION LOCK for the 2026-07-11 full-codebase truncation/data-loss audit.

A 143-agent audit hunted every place data could be silently capped, sliced,
sampled, or lost between SQL Server and the client's screen/download. Each
confirmed defect was fixed; this file pins the fixes so they cannot silently
reopen. Like the other regression locks, it tests each fix at the layer it
operates - pure logic and prompt/source contracts, no LLM calls.

Run: python -m pytest tests/test_regression_audit.py -q
"""

from pathlib import Path

import pytest

from app.agent import tools
from app.agent.postprocess import fallback_chart
from app.agent.widget import WIDGET_SYSTEM_PROMPT, build_dashboard_html
from app.core.sql_guard import DEFAULT_ROW_CAP, ensure_row_cap

ROOT = Path(__file__).resolve().parents[1]


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Truncation DETECTION actually works (the dead-warning bug).
#    ensure_row_cap must inject TOP cap+1 so the runner's fetch-one-extra
#    truncation check can ever fire; an exact-cap TOP made result["truncated"]
#    permanently False and capped reports were presented as complete.
# ---------------------------------------------------------------------------
def test_row_cap_injects_cap_plus_one():
    out = ensure_row_cap("SELECT KapanName FROM tblKapan", cap=5000)
    assert out.upper().startswith("SELECT TOP 5001 ")


def test_row_cap_distinct_injects_cap_plus_one():
    out = ensure_row_cap("SELECT DISTINCT Shape FROM tblPacket", cap=100)
    assert out.upper().startswith("SELECT DISTINCT TOP 101 ")


def test_row_cap_leaves_explicit_top_alone():
    # An explicit top-N is the model/user's own intent (e.g. "top 5 earners").
    sql = "SELECT TOP 5 EmpName FROM tblEmployee"
    assert ensure_row_cap(sql, cap=5000) == sql


def test_default_cap_unchanged():
    # The model-facing default cap stays 1000; only exports use EXPORT_ROW_CAP.
    assert DEFAULT_ROW_CAP == 1000
    assert tools.EXPORT_ROW_CAP == 5000


# ---------------------------------------------------------------------------
# 2. A truncated result is NEVER described to the model as "the COMPLETE data"
#    (ordering bug: the >preview-size note used to win over the truncation
#    warning when both applied).
# ---------------------------------------------------------------------------
def _fake_result(row_count: int, truncated: bool):
    rows = [{"KapanName": f"K{i}", "Weight": i} for i in range(row_count)]
    return {
        "ok": True,
        "columns": ["KapanName", "Weight"],
        "rows": rows,
        "row_count": row_count,
        "truncated": truncated,
        "sql": "SELECT ...",
        "error": "",
    }


def test_truncated_result_warns_and_never_says_complete(monkeypatch):
    monkeypatch.setattr(tools, "run_select", lambda q, max_rows=None: _fake_result(5000, True))
    text, *_ = tools.tool_run_sql({"query": "SELECT x FROM y"})
    assert "WARNING" in text and "LARGER" in text
    assert "COMPLETE" not in text.split("WARNING")[1][:40] or "NEVER present" in text


def test_untruncated_big_result_promises_full_download(monkeypatch):
    monkeypatch.setattr(tools, "run_select", lambda q, max_rows=None: _fake_result(200, False))
    text, *_ = tools.tool_run_sql({"query": "SELECT x FROM y"})
    assert "PREVIEW" in text and "download" in text
    assert "WARNING" not in text


# ---------------------------------------------------------------------------
# 3. create_report is no longer offered to the model (it wrote files to a
#    server path no endpoint serves - a download the user could never
#    download). The handler stays for backward compat; the SPEC must not.
# ---------------------------------------------------------------------------
def test_create_report_not_in_tool_specs():
    names = [s["name"] for s in tools.TOOL_SPECS]
    assert "create_report" not in names
    # The real tools are still offered.
    assert {"run_sql", "get_table_columns", "find_tables"} <= set(names)


def test_rules_explain_downloads_without_file_paths():
    assert "Export buttons" in tools.RULES
    assert "NEVER invent a file path" in tools.RULES


def test_widget_prompt_no_longer_mentions_create_report():
    assert "create_report" not in WIDGET_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# 4. Export-capture guard parity: in ALL three backends the LARGEST result
#    wins, so a later small aggregate can't clobber the full detail listing.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "backend",
    ["app/agent/groq_backend.py", "app/agent/gemini_backend.py", "app/agent/anthropic_backend.py"],
)
def test_capture_guard_largest_wins(backend):
    src = _src(backend)
    assert "len(rows_full) > len(data_rows)" in src, f"{backend} lost the largest-wins capture guard"
    assert "len(rows_full) > 1 or not data_rows" not in src, f"{backend} regressed to the clobber-prone guard"


# ---------------------------------------------------------------------------
# 5. Output-length honesty: no backend uses the too-small 1024 cap, and both
#    chat backends handle their provider's "output truncated" stop reason.
# ---------------------------------------------------------------------------
def test_no_backend_uses_1024_max_tokens():
    for rel in ("app/agent/groq_backend.py", "app/agent/anthropic_backend.py"):
        assert "max_tokens=1024" not in _src(rel), f"{rel} regressed to max_tokens=1024"


def test_anthropic_handles_max_tokens_stop():
    src = _src("app/agent/anthropic_backend.py")
    assert '== "max_tokens"' in src
    assert "_MAX_TOKENS = 4096" in src


def test_groq_handles_length_finish_reason():
    src = _src("app/agent/groq_backend.py")
    assert '== "length"' in src
    assert "_MAX_TOKENS = 2048" in src


# ---------------------------------------------------------------------------
# 6. Anthropic (the demo provider) has the same grounding + dashboard nudges
#    as groq/gemini - it must not be the only backend that can present
#    unqueried data.
# ---------------------------------------------------------------------------
def test_anthropic_has_grounding_and_dashboard_nudges():
    src = _src("app/agent/anthropic_backend.py")
    for token in ("ungrounded_fabrication", "_EXECUTE_NUDGE", "DASHBOARD_NUDGE", "looks_like_data_table"):
        assert token in src, f"anthropic backend lost the {token} guard"


# ---------------------------------------------------------------------------
# 7. /export re-runs with the EXPORT cap (not the 1000 model default), and
#    /chat/stream has the missing-key 503 guard.
# ---------------------------------------------------------------------------
def test_export_endpoint_uses_export_cap():
    src = _src("app/api/main.py")
    assert "run_select(req.query, max_rows=EXPORT_ROW_CAP)" in src


def test_chat_stream_has_provider_key_guard():
    src = _src("app/api/main.py")
    stream_body = src.split('@app.post("/chat/stream")')[1].split('@app.post("/export_rows")')[0]
    assert "_active_provider_key_missing()" in stream_body


# ---------------------------------------------------------------------------
# 8. Fallback chart labels its slice ("first 25 of N"), never presenting a
#    sample as the whole data.
# ---------------------------------------------------------------------------
def test_fallback_chart_labels_top25_slice():
    rows = [{"Dept": f"D{i}", "Total": float(i)} for i in range(40)]
    w = fallback_chart("department wise totals", {"widgets": [], "data_rows": rows, "data_columns": ["Dept", "Total"]})
    assert w is not None
    assert "first 25 of 40" in w["title"]


def test_fallback_chart_small_result_untouched_title():
    rows = [{"Dept": f"D{i}", "Total": float(i)} for i in range(5)]
    w = fallback_chart("department wise totals", {"widgets": [], "data_rows": rows, "data_columns": ["Dept", "Total"]})
    assert w is not None
    assert "first 25" not in w["title"]


# ---------------------------------------------------------------------------
# 9. On-screen dashboard matches the export caps (12 tiles / 6 sections) -
#    the screen must not silently drop sections the download includes.
# ---------------------------------------------------------------------------
def test_dashboard_screen_keeps_six_sections():
    args = {
        "title": "T",
        "tiles": [{"label": f"L{i}", "value": i} for i in range(3)],
        "sections": [
            {"type": "bar", "title": f"SEC{i}", "labels": ["a", "b"], "values": [1, 2]}
            for i in range(8)
        ],
    }
    html = build_dashboard_html(args)
    for i in range(6):
        assert f"SEC{i}" in html
    assert "SEC6" not in html and "SEC7" not in html


# ---------------------------------------------------------------------------
# 10. Frontend contract: the reopened-thread export path exists - the runtime
#     stores exportQuery, the UI honors exportTruncated with a full re-run,
#     and PDF chart temp files are uniquely named.
# ---------------------------------------------------------------------------
def test_runtime_persists_export_query():
    src = _src("frontend/src/runtime/useGlowstarRuntime.js")
    assert "exportQuery: data.export_query" in src


def test_thread_export_honors_truncated_snapshot():
    src = _src("frontend/src/components/Thread.jsx")
    assert "truncated && exportQuery" in src
    assert "exportData(exportQuery, format)" in src


def test_pdf_chart_temp_files_are_unique():
    src = _src("app/artifacts/pdf.py")
    assert 'filename="export_chart.png"' not in src
    assert "uuid.uuid4().hex" in src


# ---------------------------------------------------------------------------
# 11. REPORT = DETAIL guard (client-flagged live bug, 2026-07-11): a
#     "...report..." question answered ONLY with GROUP BY aggregates gets one
#     deterministic corrective round in EVERY backend - so "Damage report kapan
#     wise" can never again come back as a "Top 10 kapans" summary with no
#     joined names.
# ---------------------------------------------------------------------------
from app.agent.groq_backend import (  # noqa: E402
    REPORT_ASKED_RE,
    _SUMMARY_INTENT_RE,
    _all_sql_aggregated,
)


def test_report_regex_matches_the_client_question():
    assert REPORT_ASKED_RE.search("Damage report kapan wise?")
    assert not _SUMMARY_INTENT_RE.search("Damage report kapan wise?")


def test_summary_intent_exempts_explicit_summaries():
    # An explicitly-asked summary MAY aggregate - the guard must not fire.
    assert _SUMMARY_INTENT_RE.search("summary report of damage by department")
    assert _SUMMARY_INTENT_RE.search("total damage count per kapan report")


def test_all_sql_aggregated_logic():
    agg = "SELECT KapanName, COUNT(*) FROM t GROUP BY KapanName"
    detail = "SELECT KapanName, PacketNo, Amount FROM t ORDER BY KapanName"
    assert _all_sql_aggregated([agg]) is True
    assert _all_sql_aggregated([agg, agg]) is True
    # A detail query anywhere in the turn means the report was pulled -> no fire.
    assert _all_sql_aggregated([detail, agg]) is False
    assert _all_sql_aggregated([]) is False


@pytest.mark.parametrize(
    "backend",
    ["app/agent/groq_backend.py", "app/agent/gemini_backend.py", "app/agent/anthropic_backend.py"],
)
def test_report_detail_guard_wired_in_backend(backend):
    src = _src(backend)
    assert "nudged_report_detail" in src, f"{backend} lost the report-detail guard"
    assert "REPORT_DETAIL_NUDGE" in src
