"""
sql_guard.py
------------
Safety checks for any SQL the AI agent wants to run.

This is the most important safety layer: it guarantees the agent can
ONLY read data, never change it. Every SQL string must pass through
here before it ever touches the database.

Two jobs:
  1. is_read_only(sql)  -> reject anything that writes or runs commands
  2. ensure_row_cap(sql) -> inject "TOP 1000" so a query can't return
                            millions of rows by accident
"""

import re

# Default maximum rows a single query may return.
DEFAULT_ROW_CAP = 1000

# Words that mean "this query changes data or runs commands" -> always reject.
# Matched as whole words, case-insensitive.
_FORBIDDEN = [
    # data modification (UPDATETEXT/WRITETEXT are separate keywords - they do NOT
    # contain a word boundary after "UPDATE"/"WRITE", so list them explicitly)
    "INSERT", "UPDATE", "UPDATETEXT", "WRITETEXT", "DELETE", "DROP", "ALTER",
    "TRUNCATE", "MERGE", "CREATE", "INTO",
    # command / privilege execution
    "EXEC", "EXECUTE", "GRANT", "REVOKE", "DENY", "RECONFIGURE", "SHUTDOWN",
    # admin / file / external data access
    "BACKUP", "RESTORE", "DBCC", "BULK", "WAITFOR",
    "OPENROWSET", "OPENQUERY", "OPENDATASOURCE", "OPENJSON",
]

_FORBIDDEN_RE = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in _FORBIDDEN) + r")\b",
    re.IGNORECASE,
)

# Stored-procedure names (sp_executesql, xp_cmdshell, ...). A "\bSP_\b" pattern
# NEVER matches these (there is no word boundary between "_" and the next letter),
# so match the PREFIX followed by name chars instead.
_PROC_RE = re.compile(r"\b(?:sp|xp)_\w+", re.IGNORECASE)


def is_read_only(sql: str) -> tuple[bool, str]:
    """
    Return (ok, reason).
    ok=True  -> the SQL is a safe, single, read-only SELECT.
    ok=False -> reason explains what was rejected.
    """
    if not sql or not sql.strip():
        return False, "Empty SQL."

    text = sql.strip()

    # Block SQL comments - they can hide injected commands.
    if "--" in text or "/*" in text:
        return False, "SQL comments are not allowed."

    # Must be a single statement. Allow one optional trailing semicolon.
    without_trailing = text.rstrip(";").strip()
    if ";" in without_trailing:
        return False, "Multiple SQL statements are not allowed."

    # Must start with SELECT or WITH (a CTE that ends in a SELECT).
    head = without_trailing.lstrip("(").lstrip().upper()
    if not (head.startswith("SELECT") or head.startswith("WITH")):
        return False, "Only SELECT queries are allowed."

    # Must not contain any forbidden (write/command) keyword.
    match = _FORBIDDEN_RE.search(without_trailing)
    if match:
        return False, f"Forbidden keyword found: {match.group(1).upper()}"

    # Must not call a stored procedure (sp_.../xp_...).
    proc = _PROC_RE.search(without_trailing)
    if proc:
        return False, f"Stored-procedure calls are not allowed: {proc.group(0)}"

    return True, "ok"


def ensure_row_cap(sql: str, cap: int = DEFAULT_ROW_CAP) -> str:
    """
    Make sure a SELECT can't return unbounded rows by injecting
    'TOP <cap+1>' right after SELECT (or SELECT DISTINCT).

    Why cap+1, not cap: the runner detects truncation by fetching ONE row
    more than the cap. If the injected TOP were exactly the cap, that extra
    row could never arrive, result["truncated"] could never become True, and
    a silently-capped report would be presented as complete (a real bug this
    fixes). The +1 row is only the truncation signal - the runner still
    returns at most `cap` rows.

    Notes:
    - If the query already has a TOP, we leave it alone (an explicit top-N
      is the model/user's own intent - the rules forbid the model from
      adding one to a plain listing).
    - For CTEs (WITH ...) or anything we can't safely rewrite, we return
      it unchanged - the query runner caps fetched rows as a backstop.
    """
    text = sql.strip().rstrip(";").strip()
    upper = text.upper()

    # Already capped, or not a plain leading SELECT -> leave as-is.
    if upper.startswith("WITH"):
        return text
    if re.match(r"^SELECT\s+TOP\b", upper) or re.match(
        r"^SELECT\s+DISTINCT\s+TOP\b", upper
    ):
        return text

    # Inject TOP after "SELECT DISTINCT" or "SELECT".
    if upper.startswith("SELECT DISTINCT"):
        return re.sub(
            r"^SELECT\s+DISTINCT\s+",
            f"SELECT DISTINCT TOP {cap + 1} ",
            text,
            count=1,
            flags=re.IGNORECASE,
        )
    if upper.startswith("SELECT"):
        return re.sub(
            r"^SELECT\s+",
            f"SELECT TOP {cap + 1} ",
            text,
            count=1,
            flags=re.IGNORECASE,
        )

    return text


# Any tbl-prefixed identifier anywhere in the statement. Deliberately NOT
# anchored to FROM/JOIN: that misses comma joins, APPLY, subqueries and CTE
# bodies, and a backup table name has no legitimate reason to appear anywhere
# else in a query. Validated against 252 real statements recovered from
# logs/agent.log and the in-repo query corpus - zero false positives.
#
# Restricted to the "tbl" prefix on purpose. is_trap_table() also matches a
# leading "temp", and an unanchored scan would then reject a perfectly good
# CTE named `temp`. Every trap table in the live database is tbl-prefixed
# (verified: all 14), so the narrower pattern loses no coverage.
_TBL_REF_RE = re.compile(r"\btbl[A-Za-z0-9_]+\b", re.IGNORECASE)

# Suffix/prefix that marks a copy, and what stripping it should leave.
_COPY_MARKER_RE = re.compile(
    r"(_BKP|_BAK|_Backup|Edit|_Compare|_Demo|_Update|_old|Temp|GIA)$", re.IGNORECASE
)


def _primary_of(table: str) -> str | None:
    """The live table a backup/demo copy was made from, if it really exists.

    Only returned when the stripped name is a genuine business table AND is not
    itself a copy. Both conditions are load-bearing:
      * a guess that does not exist sends the model chasing an invalid-object
        error instead of correcting itself;
      * a guess that is ALSO blocked sends it straight back into this guard.
        Real case: tblLabourResultGIAEdit carries two markers, and stripping
        only the last one suggested tblLabourResultGIA - a trap table. Markers
        are therefore stripped repeatedly until the name is clean.
    """
    stripped = table
    for _ in range(4):  # bounded: no real name carries more than a couple
        nxt = _COPY_MARKER_RE.sub("", stripped).rstrip("_")
        if not nxt or nxt == stripped:
            break
        stripped = nxt
    if not stripped or stripped.lower() == table.lower():
        return None
    try:
        from app.schema import extractor

        if extractor.is_trap_table(stripped):
            return None  # would just be blocked again
        # get_tables() is lru_cached, so this is free after the first question.
        if any(t["name"].lower() == stripped.lower() for t in extractor.get_tables()):
            return stripped
    except Exception:  # noqa: BLE001 - never let the hint break the guard
        return None
    return None


def selects_stale_copy(sql: str) -> str:
    """
    Reject a query that reads a BACKUP / EDIT / DEMO / COMPARE / GIA copy.

    Returns a rejection reason, or "" when the query is clean.

    WHY THIS IS IN CODE AND NOT ONLY IN THE PROMPT. These copies hold stale,
    partial or outright FAKE data, and the numbers they return look completely
    plausible - tblPacket_BKP has 71,715 rows against tblPacket's 168,763, and
    tblTimeAttendance_Demo has 45,636 rows of fabricated attendance against the
    real table's 393,882. An answer built on one is confidently wrong in a way
    no reader can catch.

    extractor.is_trap_table() already hides them from find_tables() and from the
    schema router, so the model cannot DISCOVER one. Nothing stopped it naming
    one from memory: before this, run_select("SELECT COUNT(*) FROM
    tblLabourResultGIA") returned 121,337 rows quite happily. The RULES block
    forbids it in prose, which is a ~80%-reliable guard costing ~230 tokens on
    every model call; this is a 100%-reliable guard costing none.

    The reason text is written FOR THE MODEL: run_select hands the error string
    straight back into the tool loop, and the RULES already tell it to read an
    error and fix its SQL. Naming the primary table turns a dead end into a
    self-correction.
    """
    try:
        from app.schema import extractor

        is_trap = extractor.is_trap_table
    except Exception:  # noqa: BLE001 - degrade to the prompt rule, never break a query
        return ""

    seen: list[str] = []
    for name in _TBL_REF_RE.findall(sql or ""):
        if name.lower() in {s.lower() for s in seen}:
            continue
        if is_trap(name):
            seen.append(name)

    if not seen:
        return ""

    parts = []
    for name in seen:
        primary = _primary_of(name)
        parts.append(
            f"'{name}' is a backup/demo/edit copy holding stale or fake data"
            + (f" - query '{primary}' instead" if primary else "")
        )
    return (
        "Blocked: " + "; ".join(parts) + ". Re-run the query against the primary "
        "table. Never report figures from a backup, demo, edit or compare copy."
    )


def validate_and_prepare(sql: str, cap: int = DEFAULT_ROW_CAP) -> tuple[bool, str]:
    """
    Convenience: validate read-only, then apply the row cap.
    Returns (True, safe_sql) or (False, reason).

    The stale-copy check lives HERE rather than in is_read_only() because the
    two answer different questions: is_read_only() is about safety (can this
    statement change anything?), this is about data quality (would this answer
    be a lie?). runner.run_select() is the only production caller, so every
    query the agent runs passes through both.
    """
    ok, reason = is_read_only(sql)
    if not ok:
        return False, reason
    stale = selects_stale_copy(sql)
    if stale:
        return False, stale
    return True, ensure_row_cap(sql, cap)


# Quick manual check: `python -m app.core.sql_guard`
if __name__ == "__main__":
    samples = [
        "SELECT COUNT(*) FROM tblPacket",
        "SELECT EmpName FROM tblPacketHistory",
        "DELETE FROM tblPacket",
        "SELECT * FROM tblPacket; DROP TABLE tblPacket",
        "UPDATE tblPacket SET x=1",
        "SELECT DISTINCT Shape FROM tblPacket",
    ]
    for s in samples:
        ok, result = validate_and_prepare(s)
        print(f"{'OK ' if ok else 'NO '} | {s}\n      -> {result}\n")
