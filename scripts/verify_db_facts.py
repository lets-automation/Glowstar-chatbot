"""
verify_db_facts.py — re-verify the EMPIRICAL data-model facts encoded in
app/schema/glossary.py against a newly restored client backup.

Why this exists: the bot's accuracy rests on ~23 hand-audited facts about the DATA
(not the schema) — "tblPacketSell is empty", "tblIncentiveAmount.Credit is dead
after 2019", "tblTimeAttendance.EmpId is 100% NULL". A fresher backup can silently
flip any of them, turning correct guidance into a confident WRONG answer. Every
check below prints OLD vs NEW so a flip is impossible to miss.

Usage (venv python — system python lacks pyodbc):
    venv\\Scripts\\python.exe scripts\\verify_db_facts.py
    venv\\Scripts\\python.exe scripts\\verify_db_facts.py --old AasthaErp --new AasthaErp_new
"""
from __future__ import annotations

import argparse
import sys

import pyodbc

if hasattr(sys.stdout, "reconfigure"):  # Windows console is cp1252
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DRIVER = "ODBC Driver 18 for SQL Server"
SERVER = "localhost"

# (label, sql, expectation) — expectation is the fact glossary.py currently asserts.
CHECKS: list[tuple[str, str, str]] = [
    # --- data recency: how fresh is this backup, per subject area ---
    ("recency: tblPacket", "SELECT MAX(CreDate) FROM tblPacket", "latest packet date"),
    ("recency: tblFinalPacket", "SELECT MAX(CreateDate) FROM tblFinalPacket", "latest finished packet"),
    ("recency: tblPacketHistory", "SELECT MAX(ReciveTime) FROM tblPacketHistory", "latest process step"),
    ("recency: tblPointRateLabour", "SELECT MAX(ProcessDate) FROM tblPointRateLabour", "latest labour row"),
    ("recency: tblIncentiveAmount", "SELECT MAX(TransactTime) FROM tblIncentiveAmount", "latest incentive"),
    ("recency: tblPlanMaster", "SELECT MAX(CreatDate) FROM tblPlanMaster", "latest plan"),
    ("recency: tblLeaveReport", "SELECT MAX(LeaveDate_From) FROM tblLeaveReport", "latest leave"),
    ("recency: tblJunk", "SELECT MAX(CreateDate) FROM tblJunk", "latest scrap row"),

    # --- KNOWN-EMPTY tables (glossary tells the bot to say "not recorded") ---
    ("empty? tblPacketSell", "SELECT COUNT(*) FROM tblPacketSell", "0 — sales NOT tracked"),
    ("empty? tblRejection", "SELECT COUNT(*) FROM tblRejection", "0 — QC rejections not captured"),
    ("empty? tblStockInventory", "SELECT COUNT(*) FROM tblStockInventory", "0"),
    ("empty? tblGradingMaster", "SELECT COUNT(*) FROM tblGradingMaster", "0"),
    ("empty? tblInclusionInventory", "SELECT COUNT(*) FROM tblInclusionInventory", "0"),
    ("empty? tblUserMaster", "SELECT COUNT(*) FROM tblUserMaster", "0"),
    ("empty? tblRepairing", "SELECT COUNT(*) FROM tblRepairing", "0"),
    ("empty? tblRepairLoss", "SELECT COUNT(*) FROM tblRepairLoss", "0"),

    # --- DEAD tables/columns: guidance routes AWAY from these ---
    ("dead? tblLabourResult max date", "SELECT MAX(ProcessDate) FROM tblLabourResult",
     "dead ~Feb 2023 — use tblPointRateLabour instead"),
    ("dead? tblRepairLog max date", "SELECT MAX([Time]) FROM tblRepairLog",
     "dead since Feb 2022 (and it's a CRUD log, not repairs)"),
    ("stale? tblLabourResultGIA max date", "SELECT MAX(ProcessDate) FROM tblLabourResultGIA",
     "stale, ends mid-2024 — use tblFinalPacket Lab='GIA'"),
    ("dead? tblEmpGIABonus date range",
     "SELECT CONCAT(MIN(CreateDate), ' .. ', MAX(CreateDate)) FROM tblEmpGIABonus",
     "one-time Apr-Oct 2019 batch, not a live stream"),
    ("dead? tblIncentiveAmount.Credit non-null since 2020",
     "SELECT COUNT(*) FROM tblIncentiveAmount WHERE Credit IS NOT NULL AND TransactTime >= '2020-01-01'",
     "0 — Credit/Debit are legacy; live measure is CreditPoints"),
    ("live? tblIncentiveAmount.CreditPoints non-null 2026",
     "SELECT COUNT(*) FROM tblIncentiveAmount WHERE CreditPoints IS NOT NULL AND TransactTime >= '2026-01-01'",
     ">0 — points ledger is the live measure"),
    ("dead? tblPacket.IsInTempStock true-count",
     "SELECT COUNT(*) FROM tblPacket WHERE IsInTempStock = 1", "0 — column is dead, ignore it"),
    ("dead? tblLabour_MW.Final non-null",
     "SELECT COUNT(*) FROM tblLabour_MW WHERE Final IS NOT NULL",
     "0 — wage cols all NULL; use tblPointRateLabour"),

    # --- NULL-rate facts the guidance depends on ---
    ("null? tblTimeAttendance.EmpId non-null",
     "SELECT COUNT(*) FROM tblTimeAttendance WHERE EmpId IS NOT NULL",
     "0 — attendance per-employee is NOT answerable"),
    ("null? tblJunk.Grede non-null", "SELECT COUNT(*) FROM tblJunk WHERE Grede IS NOT NULL",
     "0 — never report a junk grade"),
    ("null? tblJunk.Value non-null", "SELECT COUNT(*) FROM tblJunk WHERE Value IS NOT NULL",
     "~5% — never report a junk value"),

    # --- identity / counting facts (numbers quoted verbatim in the glossary) ---
    ("identity: tblPacket rows", "SELECT COUNT(*) FROM tblPacket", "glossary says 164,573"),
    ("identity: distinct PacketNo", "SELECT COUNT(DISTINCT PacketNo) FROM tblPacket",
     "glossary says 2,330 — PacketNo is NOT unique"),
    ("identity: tblKapan rows", "SELECT COUNT(*) FROM tblKapan", "glossary says 847"),
    ("identity: tblIncentiveAmount distinct EmpID",
     "SELECT COUNT(DISTINCT EmpID) FROM tblIncentiveAmount", "glossary says 1,946"),
    ("identity: tblRepairCommentVision rows", "SELECT COUNT(*) FROM tblRepairCommentVision",
     "the real repair table"),
    ("identity: tblEmployee rows", "SELECT COUNT(*) FROM tblEmployee", "employee master"),

    # --- trap tables the router must keep blocking ---
    ("trap: tblTimeAttendance_Demo rows", "SELECT COUNT(*) FROM tblTimeAttendance_Demo",
     "~45k FAKE rows — must stay blocked"),
]


def connect(db: str) -> pyodbc.Connection:
    return pyodbc.connect(
        f"DRIVER={{{DRIVER}}};SERVER={SERVER};DATABASE={db};"
        "Trusted_Connection=yes;TrustServerCertificate=yes;",
        timeout=60,
    )


def scalar(conn: pyodbc.Connection, sql: str):
    try:
        cur = conn.cursor()
        cur.execute(sql)
        row = cur.fetchone()
        return row[0] if row else None
    except Exception as exc:  # noqa: BLE001 — a broken check must not kill the report
        msg = str(exc).split("]")[-1].strip()
        return f"ERROR: {msg[:70]}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", default="AasthaErp")
    ap.add_argument("--new", default="AasthaErp_new")
    args = ap.parse_args()

    old_conn, new_conn = connect(args.old), connect(args.new)
    print(f"OLD = {args.old}    NEW = {args.new}\n")
    print(f"{'CHECK':<46} {'OLD':>22} {'NEW':>22}  FLAG")
    print("-" * 120)

    changed = 0
    for label, sql, expectation in CHECKS:
        o, n = scalar(old_conn, sql), scalar(new_conn, sql)
        os_, ns_ = str(o), str(n)
        flag = ""
        if os_ != ns_:
            changed += 1
            # A zero that stopped being zero is the dangerous kind of change:
            # it means guidance saying "not recorded / dead" is now WRONG.
            if os_ == "0" and ns_ != "0":
                flag = "*** WAS-EMPTY, NOW HAS DATA — GLOSSARY IS NOW WRONG"
            elif label.startswith(("recency", "identity")):
                flag = "changed (expected — newer data)"
            else:
                flag = "CHANGED — review"
        print(f"{label:<46} {os_:>22} {ns_:>22}  {flag}")
        if flag.startswith("***"):
            print(f"{'':<46} {'':>22} {'':>22}  expected: {expectation}")

    print("-" * 120)
    print(f"{changed} of {len(CHECKS)} checks differ between OLD and NEW.")
    print("Anything marked '***' or 'CHANGED — review' needs a glossary.py edit before the bot is trusted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
