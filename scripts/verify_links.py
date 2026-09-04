"""
verify_links.py
---------------
RE-MEASURE THE CURATED JOIN MAP after a database refresh.

app/schema/context.py ships LOGICAL_LINKS: the joins the database does not
declare for itself (264 tables, 51 foreign keys, four of them on the six
busiest tables). Each entry carries the share of child rows that actually find
a parent, and that percentage is load-bearing - it is what tells the model an
INNER JOIN would silently drop rows. A stale percentage is worse than none, so
re-run this whenever the client's backup is restored:

    python -m scripts.verify_links

It prints the map as Python, ready to paste back into context.py, and exits
non-zero if any measured value has drifted more than DRIFT_TOLERANCE from what
is currently recorded.
"""
from __future__ import annotations

import sys

from app.database.runner import run_select
from app.schema.context import LOGICAL_LINKS

# Percentage points a link may move before it needs a human's attention.
DRIFT_TOLERANCE = 1.0


def match_rate(table: str, col: str, ref_table: str, ref_col: str):
    """Share of non-null child values that find a parent row, and the count."""
    sql = (
        f"SELECT COUNT(*) AS tot, "
        f"SUM(CASE WHEN r.{ref_col} IS NULL THEN 0 ELSE 1 END) AS matched "
        f"FROM {table} p LEFT JOIN {ref_table} r ON p.{col} = r.{ref_col} "
        f"WHERE p.{col} IS NOT NULL"
    )
    res = run_select(sql, max_rows=2)
    if not res.get("ok") or not res["rows"]:
        return None, 0, res.get("error", "")
    row = res["rows"][0]
    tot = row.get("tot") or 0
    matched = row.get("matched") or 0
    if not tot:
        return None, 0, "no rows"
    return round(100.0 * matched / tot, 1), tot, ""


def main() -> int:
    drifted = []
    print("LOGICAL_LINKS: dict[str, list[tuple]] = {")
    for table, links in LOGICAL_LINKS.items():
        print(f'    "{table}": [')
        for col, ref_table, ref_col, recorded in links:
            pct, tot, err = match_rate(table, col, ref_table, ref_col)
            if pct is None:
                print(f'        # UNMEASURABLE {col} -> {ref_table}.{ref_col}: {err[:60]}')
                drifted.append(f"{table}.{col}: {err[:60]}")
                continue
            flag = ""
            if abs(pct - recorded) > DRIFT_TOLERANCE:
                flag = f"   # WAS {recorded}"
                drifted.append(f"{table}.{col}: {recorded} -> {pct}")
            print(f'        ("{col}", "{ref_table}", "{ref_col}", {pct}),'
                  f'{flag}    # {tot:,} rows')
        print("    ],")
    print("}")

    if drifted:
        print("\nDRIFTED - update context.py.LOGICAL_LINKS:", file=sys.stderr)
        for d in drifted:
            print(f"  {d}", file=sys.stderr)
        return 1
    print("\nAll link match rates still within "
          f"{DRIFT_TOLERANCE} point(s) of what context.py records.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
