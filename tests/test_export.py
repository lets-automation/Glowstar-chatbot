"""
test_export.py
--------------
Phase 6 test: the /export API endpoint turns a read-only query into a
downloadable file. No API key needed.

Run from the project root with:
    python -m tests.test_export
"""

from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)

SAMPLE_QUERY = (
    "SELECT TOP 5 Shape, COUNT(*) AS Cnt FROM tblPacketHistory "
    "WHERE Shape IS NOT NULL AND Shape <> '' GROUP BY Shape ORDER BY COUNT(*) DESC"
)


def test_export_excel():
    r = client.post("/export", json={"query": SAMPLE_QUERY, "format": "excel"})
    assert r.status_code == 200
    assert len(r.content) > 0
    print("Excel export OK, bytes:", len(r.content))


def test_export_pdf():
    r = client.post("/export", json={"query": SAMPLE_QUERY, "format": "pdf",
                                     "title": "Packets by Shape"})
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"  # PDF magic header
    print("PDF export OK, bytes:", len(r.content))


def test_export_chart():
    r = client.post("/export", json={"query": SAMPLE_QUERY, "format": "chart",
                                     "x_col": "Shape", "y_col": "Cnt"})
    assert r.status_code == 200
    assert r.content[:8].startswith(b"\x89PNG")  # PNG magic header
    print("Chart export OK, bytes:", len(r.content))


def test_export_blocks_writes():
    r = client.post("/export", json={"query": "DELETE FROM tblPacket", "format": "excel"})
    assert r.status_code == 400  # rejected by the safe runner
    print("Write query correctly rejected by /export.")


def run_all():
    test_export_excel()
    test_export_pdf()
    test_export_chart()
    test_export_blocks_writes()
    print("SUCCESS - /export produces Excel/PDF/chart and blocks writes.")


if __name__ == "__main__":
    run_all()
