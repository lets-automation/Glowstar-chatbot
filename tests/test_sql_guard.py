"""
test_sql_guard.py
-----------------
Tests the SQL safety guard - the layer that guarantees the agent can
only READ. No API key or database needed.

Run from the project root with:
    python -m tests.test_sql_guard
"""

from app.core.sql_guard import ensure_row_cap, is_read_only, validate_and_prepare


def test_allows_safe_selects():
    safe = [
        "SELECT COUNT(*) FROM tblPacket",
        "SELECT EmpName FROM tblPacketHistory",
        "SELECT DISTINCT Shape FROM tblPacket",
        "  select top 10 * from tblFinalPacket  ",
    ]
    for s in safe:
        ok, _ = is_read_only(s)
        assert ok, f"Should be allowed: {s}"


def test_blocks_writes_and_commands():
    bad = [
        "DELETE FROM tblPacket",
        "UPDATE tblPacket SET x = 1",
        "INSERT INTO tblPacket VALUES (1)",
        "DROP TABLE tblPacket",
        "TRUNCATE TABLE tblPacket",
        "ALTER TABLE tblPacket ADD x int",
        "SELECT * INTO newtbl FROM tblPacket",
        "EXEC sp_who",
        "SELECT * FROM tblPacket; DROP TABLE tblPacket",  # multi-statement
        "SELECT * FROM tblPacket -- drop everything",      # comment
        "SELECT * FROM tblPacket /* hidden */",            # block comment
        "WAITFOR DELAY '00:00:10'",                        # time-based
        "SELECT * FROM OPENROWSET('x','y','z')",           # external data
        "BACKUP DATABASE AasthaErp TO DISK='c:/x.bak'",    # admin
        "",  # empty
    ]
    for s in bad:
        ok, reason = is_read_only(s)
        assert not ok, f"Should be blocked: {s}"


def test_row_cap_injection():
    capped = ensure_row_cap("SELECT EmpName FROM tblPacketHistory", cap=1000)
    assert "TOP 1000" in capped.upper()

    # DISTINCT keeps its place.
    capped2 = ensure_row_cap("SELECT DISTINCT Shape FROM tblPacket", cap=500)
    assert "DISTINCT TOP 500" in capped2.upper()

    # Existing TOP is left alone.
    already = "SELECT TOP 5 * FROM tblPacket"
    assert ensure_row_cap(already) == already


def test_validate_and_prepare():
    ok, sql = validate_and_prepare("SELECT EmpName FROM tblPacketHistory")
    assert ok and "TOP 1000" in sql.upper()

    ok2, reason = validate_and_prepare("DELETE FROM tblPacket")
    assert not ok2


def run_all():
    test_allows_safe_selects()
    test_blocks_writes_and_commands()
    test_row_cap_injection()
    test_validate_and_prepare()
    print("SUCCESS - all SQL guard tests passed.")
    print("  - safe SELECTs allowed")
    print("  - writes/commands/multi-statements blocked")
    print("  - row cap injected correctly")


if __name__ == "__main__":
    run_all()
