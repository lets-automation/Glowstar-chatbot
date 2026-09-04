"""
The prompt must not tell the model a date the database disagrees with.

Found 2026-08-24, right after the 21-Aug backup replaced the 27-Jul one. The
glossary said "CAP any tblPointRateLabour query at 2026-06-30" because July held
206 rows in the OLD backup. In the new one July holds 25,619 - a complete month -
so obeying that cap would have discarded all of July and reported a production
collapse that never happened.

Dates in the notes rot every time a backup is restored. Two rules keep them
honest, and this file enforces both:

  1. a DEAD feed may be named with a literal date - it cannot move; this test
     proves it really is still dead.
  2. a LIVE or LAGGING feed must use the {FEED_END:Table.Column} placeholder,
     which is filled from the database when the prompt is built.
"""
import re

import pytest

from app.schema import glossary

pytestmark = pytest.mark.integration

# Feeds documented as dead, with the column the note means. If one of these
# starts moving again, the note is wrong and the model will under-report it.
KNOWN_DEAD = {
    ("tblLabourResult", "ProcessDate"): "2023-04-12",
    ("tblTimeAttendance", "Time"): "2025-04-05",
    ("tblEmployeeCount", "Date"): "2021-07-23",
    ("tblCompanySchedule", "FromDate"): "2022-06-30",
    ("tblRepairLog", "Time"): "2022-02-19",
    ("tblKtdPacket", "CreDate"): "2019-12-09",
}

# How far past a documented end date we tolerate before calling the note stale.
DRIFT_DAYS = 0


def _measure(table, column):
    from app.database.runner import run_select

    r = run_select(f"SELECT MAX([{column}]) AS d FROM [{table}] WITH (NOLOCK)", max_rows=1)
    if not r.get("ok") or not r.get("rows"):
        return None
    v = list(r["rows"][0].values())[0]
    if not v:
        return None
    return v.strftime("%Y-%m-%d") if hasattr(v, "strftime") else str(v)[:10]


@pytest.mark.parametrize(("table", "column"), sorted(KNOWN_DEAD))
def test_a_feed_documented_as_dead_really_is_dead(table, column):
    measured = _measure(table, column)
    if measured is None:
        pytest.skip("database not reachable")
    claimed = KNOWN_DEAD[(table, column)]
    assert measured == claimed, (
        f"{table}.{column} now ends {measured}, but the glossary still says "
        f"{claimed}. The feed restarted or the backup changed - update the note, "
        f"or switch it to {{FEED_END:{table}.{column}}} if it is live again."
    )


def test_live_feeds_are_not_documented_with_a_literal_date():
    """A date next to a table name is only safe when that feed is dead.

    A START date is fine and stays put - tblRepairCommentVision genuinely
    begins 2025-04-08, and saying so is what stops the model inventing an
    earlier repair trend. Only END-of-feed claims rot.
    """
    source = glossary.render_data_notes("")
    pattern = r"(.{0,45}?)(tbl\\w+)([^.]{0,60}?)(\\d{4}-\\d{2}-\\d{2})"
    dead_tables = {t for t, _c in KNOWN_DEAD}
    offenders = []
    for before, table, between, claimed in re.findall(pattern, source):
        if table in dead_tables:
            continue
        if "START" in (before + between).upper():
            continue                      # a start date cannot go stale
        measured = None
        for col in ("ProcessDate", "CreatedDate", "CreatDate", "CreateDate",
                    "CreDate", "Date", "Time"):
            measured = _measure(table, col)
            if measured:
                break
        if measured and measured > claimed:
            offenders.append(f"{table}: note says {claimed}, data runs to {measured}")
    assert not offenders, (
        "These notes name a date the database has moved past - use "
        "{FEED_END:Table.Column} instead: " + "; ".join(offenders))


def test_the_arrears_note_is_dynamic():
    """The cap that discarded a whole month must never be a literal again."""
    rendered = glossary.render_data_notes("")
    assert "CAP any tblPointRateLabour query at" not in rendered
    assert "tblPointRateLabour is posted IN ARREARS and currently ends" in rendered
    # and the placeholder must be FILLED, not printed
    assert "{FEED_END" not in rendered


def io_read():
    import io as _io
    import app.schema.glossary as g

    return _io.open(g.__file__, encoding="utf-8").read()
