"""
test_blank_reply.py
-------------------
A model can stop with no text at all. The backends' in-loop return passes that
through verbatim, so the user gets an EMPTY chat bubble - with ok=True, which
also puts an export button next to nothing.

Observed live on NVIDIA gpt-oss-20b: the same "give me full report of MFG - 1"
question answered fully (2 queries, 317 rows) on one run and returned nothing at
all on the very next one. The guard lives in postprocess.enrich() because that
is the single point every backend passes through.
"""
from app.agent.postprocess import enrich

_ROWS = [{"KapanName": "GB", "PacketNo": 1}, {"KapanName": "GB", "PacketNo": 2}]


def test_a_blank_answer_never_reaches_the_user():
    out = enrich({"answer": "", "sql_used": [], "rows_returned": 0, "ok": True})
    assert out["answer"].strip(), "an empty chat bubble was returned"


def test_a_blank_answer_with_no_data_is_not_a_false_denial():
    """
    The pre-existing fallback said "I don't have that information in the
    database". When the real cause is our model call producing nothing, that
    tells the client their data is MISSING - a confidently wrong answer about
    their own factory. It must describe the actual failure instead.
    """
    out = enrich({"answer": "", "sql_used": [], "rows_returned": 0, "ok": True})
    assert "don't have that information in the database" not in out["answer"]
    assert out["ok"] is False, "nothing real to show, so export must not be offered"


def test_a_blank_answer_that_still_has_rows_keeps_them():
    # The queries succeeded and only the write-up is missing: the rows are real,
    # so they must still render and stay exportable.
    out = enrich({
        "answer": "", "sql_used": ["SELECT 1"], "rows_returned": 2, "ok": True,
        "data_columns": ["KapanName", "PacketNo"], "data_rows": _ROWS,
    })
    assert "couldn't write the summary" in out["answer"]
    assert out["ok"] is True
    assert out["data_rows"] == _ROWS


def test_whitespace_only_counts_as_blank():
    out = enrich({"answer": "   \n\t  ", "sql_used": [], "rows_returned": 0, "ok": True})
    assert out["answer"].strip()
    assert out["ok"] is False


def test_a_real_answer_is_left_alone():
    out = enrich({
        "answer": "In July 2026 MFG - 1 finished 317 packets.",
        "sql_used": ["SELECT 1"], "rows_returned": 317, "ok": True,
    })
    assert out["answer"].startswith("In July 2026")
    assert out["ok"] is True
