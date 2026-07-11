"""
Export must obey the client's display rule: raw internal ids (KapanID, PacketID,
ID, UserID) NEVER reach a downloaded report — only names/numbers. Regression lock
for the 'packet report for kapan AA' leak where the Excel dumped ID/KapanID/
PacketID/UserID columns.
"""

from app.agent.postprocess import _is_id_col, enrich, sanitize_export

# The exact column set that leaked in the reported bug (from tblFinalPacket).
_LEAKED_COLS = [
    "ID", "KapanID", "KapanName", "PacketID", "PacketNo", "SubPcs", "Shape",
    "Color", "Purity", "Cut", "Polish", "Symmetry", "Florecent", "RoughWt",
    "CurrentWt", "WeightLoss", "Tops", "Amount", "CreateDate", "UserID",
    "Comment", "Lab",
]


def test_is_id_col_matches_erp_ids_only():
    for col in ("ID", "id", "KapanID", "PacketID", "UserID", "Emp_ID", "PacketId"):
        assert _is_id_col(col), col
    # Ordinary words ending in a lowercase 'id' must NOT be treated as ids.
    for col in ("void", "paid", "grid", "valid", "KapanName", "PacketNo",
                "Purity", "CreateDate", "PolishedWt", "Rate"):
        assert not _is_id_col(col), col


def test_sanitize_export_drops_raw_ids_keeps_the_rest():
    rows = [{c: ("AA" if c == "KapanName" else 1) for c in _LEAKED_COLS}]
    keep, trimmed = sanitize_export(_LEAKED_COLS, rows)
    assert [c for c in _LEAKED_COLS if c not in keep] == [
        "ID", "KapanID", "PacketID", "UserID",
    ]
    assert "KapanName" in keep and "PacketNo" in keep
    # No id key survives in the row dicts either.
    assert all(not _is_id_col(k) for k in trimmed[0])


def test_sanitize_export_never_empties_an_all_id_result():
    cols = ["ID", "KapanID"]
    rows = [{"ID": 1, "KapanID": 2}]
    keep, trimmed = sanitize_export(cols, rows)
    assert keep == cols and trimmed == rows  # keep originals rather than export nothing


def test_enrich_strips_ids_from_export_snapshot():
    raw = {
        "answer": "Here is the packet report.\n\n| KapanName | Packet |\n| --- | --- |\n| AA | 1 |",
        "sql_used": ["SELECT * FROM tblPacket WHERE KapanName='AA'"],
        "rows_returned": 2,
        "ok": True,
        "data_columns": ["ID", "KapanName", "PacketID", "PacketNo", "Shape"],
        "data_rows": [
            {"ID": 206338, "KapanName": "AA", "PacketID": 218508, "PacketNo": 135, "Shape": "RD"},
            {"ID": 206339, "KapanName": "AA", "PacketID": 218483, "PacketNo": 110, "Shape": "RD"},
        ],
    }
    out = enrich(raw)
    assert out["data_columns"] == ["KapanName", "PacketNo", "Shape"]
    assert all("ID" not in r and "PacketID" not in r for r in out["data_rows"])
    assert out["data_rows"][0] == {"KapanName": "AA", "PacketNo": 135, "Shape": "RD"}
