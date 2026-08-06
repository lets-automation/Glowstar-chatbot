"""
test_count_guard.py
-------------------
Does a prose ROW-COUNT claim match the data returned? Same family as the
superlative guard: the table can be right while the sentence is wrong.

TIER 1 = LOG ONLY. A noisy log is a useless log, so the silent cases below far
outnumber the firing ones. Carat/unit totals are deliberately NOT checked — a
correctly de-duplicated total legitimately differs from the sum of shown rows.
"""
import pytest

from app.agent.count_guard import count_mismatch

SQL = ["SELECT 1"]
ROWS = [{"KapanName": "A", "Packets": 84}, {"KapanName": "B", "Packets": 69}]


@pytest.mark.parametrize("answer,claim", [
    ("A total of 305 packets were finished.", 305),
    ("There were 1,024 records in the result.", 1024),
    ("The total is Rs 11,537 for 305 packets.", 305),   # money nearby, still a count
])
def test_fires_on_an_unsupported_row_count(answer, claim):
    got = count_mismatch(answer, ROWS, 2, "", SQL)
    assert got and got[0] == claim


@pytest.mark.parametrize("answer,rows,rows_returned,question", [
    ("A total of 2 packets were finished.", ROWS, 2, ""),          # matches len(rows)
    ("A total of 34,078 packets.", [{"Total": 34078}], 1, ""),     # the cell IS the count
    ("Showing the first 50 of 3,200 rows.", ROWS, 2, ""),          # preview wording
    ("Packet no. 175 graded VS1 on 12 June 2026.", ROWS, 2, ""),   # identifier + date
    ("Yield was 42.5%.", ROWS, 2, ""),                             # percentage
    ("Here are the top 5 makers.", ROWS, 2, "top 5 makers"),       # number from the question
    ("approximately 300 packets were finished", ROWS, 2, ""),      # approximation
    ("| Kapan | 305 packets |", ROWS, 2, ""),                      # inside a rendered table
])
def test_stays_silent(answer, rows, rows_returned, question):
    assert count_mismatch(answer, rows, rows_returned, question, SQL) is None, answer


def test_global_gates():
    # no rows / no sql / file-grounded answers are out of scope
    assert count_mismatch("A total of 305 packets.", None, 0, "", SQL) is None
    assert count_mismatch("A total of 305 packets.", ROWS, 2, "", None) is None
    assert count_mismatch("A total of 305 packets.", ROWS, 2, "", SQL,
                          file_grounded=True) is None


def test_truncated_results_are_never_flagged():
    # At the export cap the prose may legitimately cite the TRUE total, which is
    # larger than the rows we hold. Uses the shared cap, never a copied literal.
    from app.agent.tools import EXPORT_ROW_CAP

    big = [{"n": i} for i in range(EXPORT_ROW_CAP)]
    assert count_mismatch("A total of 9,999 packets.", big, EXPORT_ROW_CAP, "", SQL) is None


def test_model_written_top_n_is_treated_as_truncated():
    # Verified live: the model wrote "SELECT TOP (1000) ..." and correctly reported
    # the true total of 1,237. We hold only the 1,000 capped rows, so a naive check
    # flags a RIGHT answer. Any TOP(n) equal to the row count means truncation.
    rows = [{"n": i} for i in range(1000)]
    sql = ["SELECT TOP (1000) KapanName FROM tblFinalPacket WHERE CreateDate>='2026-06-01'"]
    assert count_mismatch("A total of 1,237 packets were finished.", rows, 1, "", sql) is None
    # ...but an unrelated TOP must NOT disable the check
    sql2 = ["SELECT TOP (5) KapanName FROM tblFinalPacket"]
    assert count_mismatch("A total of 1,237 packets.", rows, 1, "", sql2) is not None
