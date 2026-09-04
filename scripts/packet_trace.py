"""
packet_trace.py — DERIVE the client's "pending" rule instead of guessing it.

THE PROBLEM THIS EXISTS FOR
---------------------------
The client's screen says 201 packets are pending. Sixty-six readings of
"pending" have been computed against their database and NONE gives 201. Asking
them to *describe* the rule has failed twice: a described rule comes back as
prose that fits several different queries, and we pick the wrong one.

So stop describing and start eliminating. Ask them for FIVE PACKET NUMBERS off
that screen. Every one of those packets is, by their own definition, pending.
Any candidate reading that EXCLUDES even one of them is wrong and can be struck
off. That is a fact about their data, not an opinion about their wording.

USAGE (venv python — the system one lacks pyodbc)
------------------------------------------------
    venv\\Scripts\\python.exe -m scripts.packet_trace NI26/301 NI26/305 OS26/12
    venv\\Scripts\\python.exe -m scripts.packet_trace --id 309224 308894
    venv\\Scripts\\python.exe -m scripts.packet_trace NI26/301 --period 2026-08-01 2026-09-01

A packet is given as KAPAN/NUMBER, because PacketName is only unique WITHIN a
kapan (it is a small integer — 570, 512, 227). A bare number is ambiguous and
is REFUSED rather than guessed: we have already queried the wrong kapan twice
on this project, and both times a wrong number reached the client. Use --id for
a raw Packet_ID.

WHAT IT PRINTS
--------------
1. Every tblPlanMaster row for each packet, in stage order — the raw evidence.
2. A verdict matrix: candidate reading x packet, include or exclude.
3. The surviving readings — those that include EVERY packet given — and, if a
   --period is supplied, what each one counts over that period. A survivor that
   also lands on 201 is the answer.
"""
from __future__ import annotations

import argparse
import sys

from app.database.runner import run_select

if hasattr(sys.stdout, "reconfigure"):          # Windows console is cp1252
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

LABS = ("GIA", "HRD", "IGI")
_LAB_SQL = ", ".join(f"'{lab}'" for lab in LABS)


def _q(sql: str, cap: int = 500):
    r = run_select(sql, max_rows=cap, timeout=180)
    if not r.get("ok"):
        print(f"  ! query failed: {str(r.get('error'))[:200]}")
        return []
    return r.get("rows") or []


# ---------------------------------------------------------------------------
# RESOLVING WHAT THE CLIENT TYPED
# ---------------------------------------------------------------------------
def resolve(token: str) -> list[dict]:
    """KAPAN/NUMBER -> the matching packet(s). Ambiguity is reported, not picked."""
    if "/" not in token:
        print(f"  ! {token!r}: give it as KAPAN/NUMBER (e.g. NI26/301). "
              f"PacketName is only unique within a kapan; a bare number would "
              f"mean guessing which kapan, and that has gone wrong twice.")
        return []
    kapan, _, name = token.partition("/")
    kapan, name = kapan.strip().replace("'", "''"), name.strip().replace("'", "''")
    rows = _q(f"""
SELECT DISTINCT pm.Packet_ID, pm.PacketName, k.KapanName
FROM tblPlanMaster pm WITH (NOLOCK)
JOIN tblKapan k WITH (NOLOCK) ON pm.KapanId = k.ID
WHERE k.KapanName = '{kapan}' AND CAST(pm.PacketName AS varchar(50)) = '{name}'""")
    if not rows:
        print(f"  ! {token!r}: no packet found. Check the kapan name — OS26 and "
              f"OR26, NI26 and NS26 all exist, and we have queried the wrong "
              f"one before.")
    elif len(rows) > 1:
        print(f"  ! {token!r} is ambiguous: {[r['Packet_ID'] for r in rows]}")
    return rows


def by_id(pid: str) -> list[dict]:
    if not str(pid).isdigit():
        print(f"  ! --id {pid!r} is not a number")
        return []
    rows = _q(f"""
SELECT DISTINCT TOP 1 pm.Packet_ID, pm.PacketName, k.KapanName
FROM tblPlanMaster pm WITH (NOLOCK)
JOIN tblKapan k WITH (NOLOCK) ON pm.KapanId = k.ID
WHERE pm.Packet_ID = {int(pid)}""")
    if not rows:
        print(f"  ! Packet_ID {pid}: no plan rows")
    return rows


# ---------------------------------------------------------------------------
# THE EVIDENCE
# ---------------------------------------------------------------------------
def history(packet_id: int) -> list[dict]:
    return _q(f"""
SELECT pm.ID, pm.RapVer, pm.LAB, pm.CreatDate, pm.ApproveDate,
       pm.IsApproved, ISNULL(pm.IsDamagePlan, 0) AS IsDamagePlan,
       pm.EmpCode, pm.EmpName, pm.Cut, pm.Purity, pm.PolishedWt, pm.Amount
FROM tblPlanMaster pm WITH (NOLOCK)
WHERE pm.Packet_ID = {int(packet_id)}
ORDER BY pm.CreatDate, pm.ID""")


def show_history(label: str, rows: list[dict]) -> None:
    print(f"\n=== {label} — {len(rows)} plan row(s) ===")
    if not rows:
        print("  (none)")
        return
    head = f"  {'ID':>8} {'Stage':<6} {'LAB':<5} {'Created':<17} {'Appr':<4} {'Dmg':<3} {'Emp':<8} {'Wt':>7} {'Amount':>10}"
    print(head)
    print("  " + "-" * (len(head) - 2))
    for r in rows:
        print(f"  {r['ID']:>8} {str(r['RapVer'] or ''):<6} "
              f"{str(r['LAB'] or ''):<5} {str(r['CreatDate'] or '')[:16]:<17} "
              f"{str(r['IsApproved']):<4} {str(r['IsDamagePlan']):<3} "
              f"{str(r['EmpCode'] or ''):<8} "
              f"{(r['PolishedWt'] if r['PolishedWt'] is not None else 0):>7} "
              f"{(r['Amount'] if r['Amount'] is not None else 0):>10}")


# ---------------------------------------------------------------------------
# THE CANDIDATE READINGS
# ---------------------------------------------------------------------------
# Each is a predicate over one packet's plan rows, so it can be evaluated on a
# packet the client has told us IS pending. A reading that says False for such
# a packet is DISPROVED — no further argument needed.
#
# Keep adding readings here as they are proposed. That is the point: a new idea
# costs one function and is tested against the client's own packets in seconds,
# instead of becoming the 67th number we quote at them.
def _approved(rows):
    return [r for r in rows if r["IsApproved"] == 1 and r["IsDamagePlan"] == 0]


def _latest(rows):
    return max(rows, key=lambda r: (str(r["CreatDate"] or ""), r["ID"]), default=None)


def _pls_rows(rows):
    return [r for r in rows if (r["RapVer"] or "") == "PLS"]


def _lab_rows(rows):
    return [r for r in rows if (r["RapVer"] or "") in LABS]


def _lab_of(rows):
    """The destination lab on the packet's latest approved PLS row."""
    pls = _latest(_approved(_pls_rows(rows)))
    return (pls["LAB"] or "").strip().upper() if pls else ""


READINGS = {
    "latest approved row IS PLS":
        lambda rs: (_latest(_approved(rs)) or {}).get("RapVer") == "PLS",

    "latest approved row IS PLS, LAB in GIA/HRD/IGI":
        lambda rs: (_latest(_approved(rs)) or {}).get("RapVer") == "PLS"
                   and _lab_of(rs) in LABS,

    "latest approved row IS PLS, LAB = NONE":
        lambda rs: (_latest(_approved(rs)) or {}).get("RapVer") == "PLS"
                   and _lab_of(rs) == "NONE",

    "latest row IS PLS (ignoring IsApproved)":
        lambda rs: (_latest([r for r in rs if r["IsDamagePlan"] == 0]) or {})
                   .get("RapVer") == "PLS",

    "has approved PLS, no approved GIA row":
        lambda rs: bool(_approved(_pls_rows(rs)))
                   and not [r for r in _approved(_lab_rows(rs))
                            if r["RapVer"] == "GIA"],

    "has approved PLS, no approved lab row at all":
        lambda rs: bool(_approved(_pls_rows(rs))) and not _approved(_lab_rows(rs)),

    "has approved PLS w/ LAB in 3, no approved GIA row":
        lambda rs: bool(_approved(_pls_rows(rs))) and _lab_of(rs) in LABS
                   and not [r for r in _approved(_lab_rows(rs))
                            if r["RapVer"] == "GIA"],

    "has approved PLS w/ LAB in 3, no approved lab row at all":
        lambda rs: bool(_approved(_pls_rows(rs))) and _lab_of(rs) in LABS
                   and not _approved(_lab_rows(rs)),

    "has PLS, no lab row (IsApproved ignored entirely)":
        lambda rs: bool(_pls_rows(rs)) and not _lab_rows(rs),
}

# The same readings as SQL, so a SURVIVOR can immediately be counted over the
# period and compared against the client's number. Every reading above has a
# form here - a survivor that cannot be counted is only half an answer, and the
# whole point is to land on their figure.
_APPROVED = " AND pls.IsApproved = 1"
_LAB_IN_3 = f" AND LTRIM(RTRIM(pls.LAB)) IN ({_LAB_SQL})"
_LAB_NONE = " AND LTRIM(RTRIM(pls.LAB)) = 'NONE'"

# "Nothing came after this PLS row" - the positional reading, in its approved
# and its IsApproved-blind forms.
_LATEST_APPROVED = """
  AND NOT EXISTS (SELECT 1 FROM tblPlanMaster nx WITH (NOLOCK)
                  WHERE nx.Packet_ID = pls.Packet_ID
                    AND ISNULL(nx.IsDamagePlan, 0) = 0 AND nx.IsApproved = 1
                    AND (nx.CreatDate > pls.CreatDate
                         OR (nx.CreatDate = pls.CreatDate AND nx.ID > pls.ID)))"""
_LATEST_ANY = """
  AND NOT EXISTS (SELECT 1 FROM tblPlanMaster nx WITH (NOLOCK)
                  WHERE nx.Packet_ID = pls.Packet_ID
                    AND ISNULL(nx.IsDamagePlan, 0) = 0
                    AND (nx.CreatDate > pls.CreatDate
                         OR (nx.CreatDate = pls.CreatDate AND nx.ID > pls.ID)))"""

# "The packet has no such row anywhere" - the anti-join readings.
_NO_GIA = """
  AND NOT EXISTS (SELECT 1 FROM tblPlanMaster g WITH (NOLOCK)
                  WHERE g.Packet_ID = pls.Packet_ID AND g.RapVer = 'GIA'
                    AND ISNULL(g.IsDamagePlan, 0) = 0 AND g.IsApproved = 1)"""
_NO_LAB = f"""
  AND NOT EXISTS (SELECT 1 FROM tblPlanMaster g WITH (NOLOCK)
                  WHERE g.Packet_ID = pls.Packet_ID AND g.RapVer IN ({_LAB_SQL})
                    AND ISNULL(g.IsDamagePlan, 0) = 0 AND g.IsApproved = 1)"""
_NO_LAB_ANY = f"""
  AND NOT EXISTS (SELECT 1 FROM tblPlanMaster g WITH (NOLOCK)
                  WHERE g.Packet_ID = pls.Packet_ID AND g.RapVer IN ({_LAB_SQL}))"""

COUNT_SQL = {
    "latest approved row IS PLS": _APPROVED + _LATEST_APPROVED,
    "latest approved row IS PLS, LAB in GIA/HRD/IGI":
        _APPROVED + _LAB_IN_3 + _LATEST_APPROVED,
    "latest approved row IS PLS, LAB = NONE":
        _APPROVED + _LAB_NONE + _LATEST_APPROVED,
    "latest row IS PLS (ignoring IsApproved)": _LATEST_ANY,
    "has approved PLS, no approved GIA row": _APPROVED + _NO_GIA,
    "has approved PLS, no approved lab row at all": _APPROVED + _NO_LAB,
    "has approved PLS w/ LAB in 3, no approved GIA row":
        _APPROVED + _LAB_IN_3 + _NO_GIA,
    "has approved PLS w/ LAB in 3, no approved lab row at all":
        _APPROVED + _LAB_IN_3 + _NO_LAB,
    "has PLS, no lab row (IsApproved ignored entirely)": _NO_LAB_ANY,
}


def count_over(reading: str, frm: str, to: str) -> str:
    """What a surviving reading counts over a period."""
    if reading not in COUNT_SQL:
        return "(no SQL form wired up — add one alongside the predicate)"
    rows = _q(f"""
SELECT COUNT(DISTINCT pls.Packet_ID) AS n
FROM tblPlanMaster pls WITH (NOLOCK)
WHERE pls.RapVer = 'PLS' AND ISNULL(pls.IsDamagePlan, 0) = 0
  AND pls.CreatDate >= '{frm}' AND pls.CreatDate < '{to}'
  {COUNT_SQL[reading]}""")
    return str(rows[0]["n"]) if rows else "?"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Trace packets the client says are PENDING and eliminate "
                    "every reading of 'pending' that excludes any of them.")
    ap.add_argument("packets", nargs="*", metavar="KAPAN/NUMBER",
                    help="e.g. NI26/301 — kapan is REQUIRED, never guessed")
    ap.add_argument("--id", nargs="*", default=[], metavar="PACKET_ID",
                    help="raw tblPlanMaster.Packet_ID values")
    ap.add_argument("--period", nargs=2, metavar=("FROM", "TO"), default=None,
                    help="half-open range for counting a surviving reading, "
                         "e.g. --period 2026-08-01 2026-09-01 (TO is EXCLUSIVE)")
    ap.add_argument("--target", type=int, default=201,
                    help="the number on the client's screen (default 201)")
    args = ap.parse_args()

    if not args.packets and not args.id:
        ap.error("give at least one KAPAN/NUMBER or --id. Ask the client for "
                 "FIVE packet numbers off the screen showing their 201.")

    print("RESOLVING PACKETS")
    found: list[dict] = []
    for tok in args.packets:
        found += resolve(tok)
    for pid in args.id:
        found += by_id(pid)
    if not found:
        print("\nNothing resolved — nothing to eliminate. Stop here rather "
              "than computing another number to send them.")
        return 1

    # ECHO THE KAPAN BACK. Process mistake #1 on this project, twice over: the
    # client said OS26/NI26, we queried OR26/NS26, and all four exist.
    print("\nCONFIRM THESE ARE THE PACKETS YOU MEANT:")
    for p in found:
        print(f"  kapan {p['KapanName']}, packet {p['PacketName']} "
              f"(Packet_ID {p['Packet_ID']})")

    traces = {}
    for p in found:
        rows = history(p["Packet_ID"])
        traces[p["Packet_ID"]] = rows
        show_history(f"{p['KapanName']}/{p['PacketName']} "
                     f"(Packet_ID {p['Packet_ID']})", rows)

    print("\n\nVERDICT MATRIX — every packet below IS pending, per the client.")
    print("A reading that says NO to any of them is disproved.\n")
    width = max(len(k) for k in READINGS)
    ids = [p["Packet_ID"] for p in found]
    labels = {p["Packet_ID"]: f"{p['KapanName']}/{p['PacketName']}" for p in found}
    print(f"  {'reading':<{width}}  " + "  ".join(f"{labels[i]:>12}" for i in ids))
    print("  " + "-" * (width + 2 + 14 * len(ids)))

    survivors = []
    for name, fn in READINGS.items():
        verdicts = []
        for i in ids:
            try:
                verdicts.append(bool(fn(traces[i])))
            except Exception as exc:                 # a bad predicate must not
                print(f"  ! {name}: {exc}")          # kill the whole matrix
                verdicts.append(False)
        cells = "  ".join(f"{('yes' if v else 'NO'):>12}" for v in verdicts)
        print(f"  {name:<{width}}  {cells}")
        if all(verdicts):
            survivors.append(name)

    print("\n\nSURVIVING READINGS (include every packet given):")
    if not survivors:
        print("  NONE. Every candidate is disproved — which is a real result:\n"
              "  their 'pending' is not any reading we have tried. Look at the\n"
              "  plan rows above for what these packets share, and add a new\n"
              "  entry to READINGS rather than resuming the guessing.")
    for name in survivors:
        line = f"  - {name}"
        if args.period:
            n = count_over(name, args.period[0], args.period[1])
            hit = " <-- MATCHES THE CLIENT'S SCREEN" if n == str(args.target) else ""
            line += f"\n      over {args.period[0]} to {args.period[1]}: {n}{hit}"
        print(line)

    if survivors and not args.period:
        print("\n  Re-run with --period FROM TO to see what each survivor "
              "counts, and whether any lands on the client's number.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
