"""
lab_amount_export.py — localise the PLS/GIA amount gap to the PACKET.

THE PROBLEM
-----------
For July 2026 our PLS-vs-GIA report agrees with the client's on everything that
is easy to agree on and differs on one number:

    packets    3,692        MATCHES exactly
    weight     2,016.478    MATCHES exactly
    PLS amount 146,421.80   theirs is 146,553.80 — exactly 132.00 more

WHAT HAS ALREADY BEEN RULED OUT (2026-09-01, against the live database)
----------------------------------------------------------------------
  * A recomputation. Their own procedures - dbo.GetPLSSUM and
    dbo.GetPLSSUMBYLAB, read out of sys.sql_modules - do a plain
    SUM(pm.Amount) straight off the plan row. There is no rate x weight,
    no discount arithmetic, no lab charge in the figure.
  * Picking the wrong PLS row. Every one of the 3,692 packets has EXACTLY one
    PLS row - no packet is missing one, none has two.
  * The approval and damage flags: filtering on either leaves 146,421.80.
  * Double counting: the period holds 3,692 lab rows for 3,692 packets, so the
    sum cannot be counting a packet twice.
  * Another column: OAmount (2,196,316.67), SecAmount (0), weight x rate
    (6,714,860.84) and Amount+Discount (-69,313.35) are nowhere near.
  * A different date basis: PLS-dated July gives 148,077.40 over 4,533 packets;
    ApproveDate-dated gives 34,647.44 over 1,650.
  * A lab filter: dropping LAB='NONE' packets removes 6,569.53, not 132.00.
  * A single PLS row worth 132.00: there is none in the whole table.

So the formula is not in dispute and the row set is not in dispute. What is
left is per-packet data - most likely a PLS Amount edited between their report
run and the backup we hold. That cannot be settled by another aggregate. It
needs a row-level diff, which is what this produces.

USAGE (venv python — the system one lacks pyodbc)
------------------------------------------------
    venv\\Scripts\\python.exe -m scripts.lab_amount_export
    venv\\Scripts\\python.exe -m scripts.lab_amount_export --period 2026-07-01 2026-08-01
    venv\\Scripts\\python.exe -m scripts.lab_amount_export --out pls_july.csv

Then ask the client to export the same period from their screen and diff on
Kapan+Packet. 132.00 will be sitting on one row, or a handful, and that row
says what their report does differently. One diff settles what six aggregate
comparisons could not.
"""
from __future__ import annotations

import argparse
import csv
import sys

from app.database.runner import run_select

if hasattr(sys.stdout, "reconfigure"):          # Windows console is cp1252
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Deliberately the SAME shape reports.lab_results_report uses, so the export
# and the chat answer cannot disagree. If this query is edited, that recipe is
# the other half and must move with it.
SQL = """
SELECT k.KapanName AS Kapan, g.PacketName AS Packet, g.Packet_ID,
       g.RapVer AS LabStage, LTRIM(RTRIM(g.LAB)) AS LabDest,
       CAST(g.CreatDate AS date) AS LabDate,
       CAST(ISNULL(g.PolishedWt, 0) AS decimal(14,3)) AS PolishedWt,
       CAST(ISNULL(p.Amount, 0) AS decimal(18,4)) AS PLSAmt,
       CAST(ISNULL(g.Amount, 0) AS decimal(18,4)) AS GIAAmt,
       p.PLSDate, p.PLSApproved, p.PLSDamage
FROM tblPlanMaster g WITH (NOLOCK)
JOIN tblKapan k WITH (NOLOCK) ON g.KapanId = k.ID
OUTER APPLY (SELECT TOP 1 pm.Amount,
                    CAST(pm.CreatDate AS date) AS PLSDate,
                    pm.IsApproved AS PLSApproved,
                    ISNULL(pm.IsDamagePlan, 0) AS PLSDamage
             FROM tblPlanMaster pm WITH (NOLOCK)
             WHERE pm.Packet_ID = g.Packet_ID AND pm.RapVer = 'PLS'
             ORDER BY pm.ID DESC) p
WHERE g.RapVer IN ('GIA','HRD','IGI')
  AND g.CreatDate >= '{frm}' AND g.CreatDate < '{to}'
ORDER BY k.KapanName, g.PacketName"""


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Export per-packet PLS and lab amounts so the client's "
                    "report can be diffed against ours row by row.")
    ap.add_argument("--period", nargs=2, metavar=("FROM", "TO"),
                    default=["2026-07-01", "2026-08-01"],
                    help="half-open range; TO is EXCLUSIVE (default July 2026)")
    ap.add_argument("--out", default="lab_amounts.csv",
                    help="CSV path (default lab_amounts.csv)")
    args = ap.parse_args()
    frm, to = args.period

    # The cap must exceed the row count or the export silently truncates - the
    # exact failure that had us report 60 for a question whose answer was 288.
    r = run_select(SQL.format(frm=frm, to=to), max_rows=100000, timeout=300)
    if not r.get("ok"):
        print(f"query failed: {r.get('error')}")
        return 1
    rows = r.get("rows") or []
    if r.get("truncated"):
        print("! TRUNCATED - raise max_rows; do not use this file")
        return 1

    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(r["columns"]))
        w.writeheader()
        w.writerows(rows)

    pls = sum(float(x["PLSAmt"] or 0) for x in rows)
    gia = sum(float(x["GIAAmt"] or 0) for x in rows)
    wt = sum(float(x["PolishedWt"] or 0) for x in rows)
    packets = len({x["Packet_ID"] for x in rows})

    print(f"{frm} to {to} (end exclusive)  ->  {args.out}")
    print(f"  rows            {len(rows):,}")
    print(f"  packets         {packets:,}")
    print(f"  polished weight {wt:,.3f}")
    print(f"  PLS amount      {pls:,.2f}")
    print(f"  lab amount      {gia:,.2f}")
    print("\nAsk the client to export the same period and diff on Kapan+Packet.")
    print("The PLSAmt column is the one in dispute (ours 146,421.80 vs their")
    print("146,553.80 for July 2026 - a difference of exactly 132.00).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
