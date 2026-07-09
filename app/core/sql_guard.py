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
    Make sure a SELECT can't return more than `cap` rows by injecting
    'TOP <cap>' right after SELECT (or SELECT DISTINCT).

    Notes:
    - If the query already has a TOP, we leave it alone.
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
            f"SELECT DISTINCT TOP {cap} ",
            text,
            count=1,
            flags=re.IGNORECASE,
        )
    if upper.startswith("SELECT"):
        return re.sub(
            r"^SELECT\s+",
            f"SELECT TOP {cap} ",
            text,
            count=1,
            flags=re.IGNORECASE,
        )

    return text


def validate_and_prepare(sql: str, cap: int = DEFAULT_ROW_CAP) -> tuple[bool, str]:
    """
    Convenience: validate read-only, then apply the row cap.
    Returns (True, safe_sql) or (False, reason).
    """
    ok, reason = is_read_only(sql)
    if not ok:
        return False, reason
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
