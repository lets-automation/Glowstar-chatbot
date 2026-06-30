"""
test_artifacts.py
-----------------
Phase 6 test: generate Excel, PDF, and a chart from REAL database data.
No API key needed - this uses the read-only runner directly.

Run from the project root with:
    python -m tests.test_artifacts
"""

import os

from app.artifacts.charts import to_chart
from app.artifacts.excel import to_excel
from app.artifacts.pdf import to_pdf
from app.database.runner import run_select


def _get_sample_data():
    """Real grouped data: top shapes by count in tblPacketHistory."""
    result = run_select(
        "SELECT TOP 8 Shape, COUNT(*) AS Cnt "
        "FROM tblPacketHistory "
        "WHERE Shape IS NOT NULL AND Shape <> '' "
        "GROUP BY Shape ORDER BY COUNT(*) DESC"
    )
    assert result["ok"], f"Query failed: {result['error']}"
    return result["columns"], result["rows"]


def run_all():
    columns, rows = _get_sample_data()
    print(f"Pulled {len(rows)} rows: {columns}")
    for r in rows:
        print("   ", r)

    # 1. Excel
    xlsx = to_excel(columns, rows, "test_shapes.xlsx")
    assert os.path.exists(xlsx) and os.path.getsize(xlsx) > 0
    print("Excel  ->", xlsx)

    # 2. PDF
    pdf = to_pdf(columns, rows, "test_shapes.pdf", title="Packets by Shape")
    assert os.path.exists(pdf) and os.path.getsize(pdf) > 0
    print("PDF    ->", pdf)

    # 3. Chart
    png = to_chart(rows, "Shape", "Cnt", "test_shapes.png", kind="bar",
                   title="Packets by Shape")
    assert os.path.exists(png) and os.path.getsize(png) > 0
    print("Chart  ->", png)

    print("\nSUCCESS - Excel, PDF, and chart generated from live data.")


if __name__ == "__main__":
    run_all()
