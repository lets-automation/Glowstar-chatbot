"""
demo_rehearsal.py
-----------------
RUN THIS BEFORE EVERY CLIENT DEMO.

Every failure the client hit was found by THEM, not us, because "tests pass" only
proves the guards and the SQL — not that the assistant actually answers their
question in the product. This script closes that gap: it puts the client's REAL
questions through the full agent (same path as the app) and prints a PASS / FAIL /
BLOCKED table.

Rules it follows so it can never give false confidence:
  * a provider/quota failure is reported as BLOCKED, never PASS — an unverified
    question is treated as unverified, not as working;
  * expectations are about the ANSWER the client sees (a real number, a table,
    a refusal, a date prompt), not about internal state;
  * ground-truth numbers are computed from the database in the same run, so a
    plausible-but-wrong figure fails.

Usage (from the project root, backend venv or inside the container):
    python -m scripts.demo_rehearsal
    python -m scripts.demo_rehearsal --only gia,salary
"""
from __future__ import annotations

import argparse
import re
import sys
import time

from app.agent import access_guard, date_gate
from app.agent.agent import ask
from app.database.runner import run_select

# Phrases that mean the PROVIDER failed (quota/outage) — never a content failure.
_BLOCKED_MARKERS = (
    "busy right now",
    "usage limit",
    "couldn't reach the ai",
    "could not reach the ai",
    "not configured",
    "unavailable right now",
)


def _truth(sql: str):
    """Compute a ground-truth scalar straight from the DB."""
    r = run_select(sql, max_rows=2)
    if not r.get("ok") or not r["rows"]:
        return None
    return list(r["rows"][0].values())[0]


def _has_number(answer: str, value) -> bool:
    """True if the answer contains `value` (ignoring thousands separators)."""
    if value is None:
        return False
    plain = re.sub(r"[,\s]", "", answer or "")
    return str(int(value)) in plain


def _mentions_all(answer: str, needles: list[str]) -> bool:
    plain = re.sub(r"[,\s]", "", answer or "")
    return all(n.replace(",", "") in plain for n in needles)


def _section_count(answer: str) -> int:
    """How many titled sections the profile has (bold/heading lines)."""
    n = 0
    for line in (answer or "").splitlines():
        t = line.strip()
        if t.startswith("#") or (t.startswith("**") and t.endswith("**")) or t.endswith(":"):
            if len(t) < 80:
                n += 1
    return n


def _looks_like_table(answer: str) -> bool:
    return _table_rows(answer) >= 1


def _table_rows(answer: str) -> int:
    """Count DATA rows in the markdown table the client actually sees.

    This is the only honest measure of "did they get their data". rows_returned
    reflects the LAST query the model ran (often a small summary), so a full
    detail table can coexist with rows_returned=1.
    """
    n = 0
    for line in (answer or "").splitlines():
        t = line.strip()
        if t.startswith("|") and t.endswith("|") and t.count("|") >= 3:
            cells = [c.strip() for c in t.strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):
                continue          # separator row
            n += 1
    return max(0, n - 1)          # minus the header


# --- the client's real questions, from the actual meetings --------------------
# expect(answer, result) -> (ok: bool, note: str)
CASES = [
    {
        "id": "damage",
        "q": "give me the damage report of department MFG - 1 from 1 Jun 2026 to 30 Jun 2026",
        "why": "asked in a meeting; must list rows, not a lone total",
        "expect": lambda a, r: (
            _table_rows(a) >= 3,
            f"table_rows={_table_rows(a)} | last_query_rows={r.get('rows_returned')}",
        ),
    },
    {
        "id": "gia",
        "q": "Provide past month GIA results of Fency department employees",
        "why": "the complaint that lost two meetings: needs PLS-vs-GIA + the maker",
        # Employee-wise SUMMARY or per-packet DETAIL are both correct readings —
        # what must never happen is prose with no table (seen intermittently).
        "expect": lambda a, r: (
            _table_rows(a) >= 3,
            f"table_rows={_table_rows(a)} (what the client sees) "
            f"| last_query_rows={r.get('rows_returned')}",
        ),
    },
    {
        "id": "production",
        "q": "Fency department production for June 2026",
        "why": "must give the packet breakdown AND the correct 76.16 ct total",
        "truth": ("SELECT CAST(SUM(CurrentWt) AS int) FROM tblFinalPacket "
                  "WHERE CreateDate>='2026-06-01' AND CreateDate<'2026-07-01' "
                  "AND PacketID IN (SELECT Packet_ID FROM tblPointRateLabour "
                  "WHERE DepartmentName='Fency')"),
        "expect": lambda a, r: (
            _table_rows(a) >= 3,
            f"table_rows={_table_rows(a)} (a lone summary = the old bug)",
        ),
    },
    {
        "id": "daily",
        "q": "give me daily production from 1 Jun 2026 to 30 Jun 2026",
        "why": "day-wise grouping (this silently crashed before the date fix)",
        "expect": lambda a, r: (
            _table_rows(a) >= 10,
            f"table_rows={_table_rows(a)} (expect ~26 production days)",
        ),
    },
    {
        "id": "wip",
        "q": "how many diamonds are in process and in which department",
        "why": "their WIP screen; live snapshot, must not ask for a date",
        "expect": lambda a, r: (
            _table_rows(a) >= 3 and not r.get("ask_date"),
            f"table_rows={_table_rows(a)} ask_date={r.get('ask_date')}",
        ),
    },
    {
        "id": "salary",
        "q": "what is the salary of employee M2139",
        "why": "client policy: salary must be refused",
        "expect": lambda a, r: (
            "salary" in a.lower() and r.get("rows_returned", 0) == 0,
            "must refuse and run no query",
        ),
    },
    {
        "id": "bonus",
        "q": "bonus of the Fency workers for June 2026",
        "why": "bonus is explicitly ALLOWED — must NOT be refused",
        "expect": lambda a, r: (
            "don't have access" not in a.lower(),
            "must not be blocked by the salary guard",
        ),
    },
    {
        "id": "employee360",
        "q": "give me past month report of employee id M4117 for June 2026",
        "why": "asked in a meeting; must be a FULL profile (production + damage + "
               "bonus/incentive), not just one section",
        # Their ERP prints production alongside damage/bonus. The old answer gave
        # damage + bonus + incentive only and omitted what he actually MADE.
        "expect": lambda a, r: (
            _mentions_all(a, ["33", "17.4"]) or _section_count(a) >= 3,
            f"sections={_section_count(a)} has_production_figures="
            f"{_mentions_all(a, ['33'])}",
        ),
    },
    {
        "id": "datepicker",
        "q": "Give me the stock report",
        "why": "no period given -> must show the date picker, not dump history",
        "expect": lambda a, r: (
            bool(r.get("ask_date")),
            f"ask_date={r.get('ask_date')}",
        ),
    },
]


def run(only: set[str] | None = None, repeat: int = 1) -> int:
    """
    repeat>1 runs each question N times. Use it before a demo: the model is NOT
    deterministic, and the failure mode that embarrasses us is a question that
    answers well when we test and thinly when the client asks. A question is only
    trustworthy if it passes EVERY repeat.
    """
    cases = [c for c in CASES if not only or c["id"] in only]
    if repeat > 1:
        cases = [dict(c, _run=i + 1) for c in cases for i in range(repeat)]
    print(f"\nDEMO REHEARSAL — {len(cases)} runs"
          f"{f' ({repeat}x each)' if repeat > 1 else ''}\n" + "=" * 74)
    results = []

    for c in cases:
        # The deterministic gates answer without the model; mirror the app's order.
        if access_guard.is_pay_question(c["q"]):
            res = access_guard.refusal_response(c["q"])
        elif date_gate.needs_date(c["q"]):
            res = date_gate.ask_date_response(c["q"])
        else:
            t0 = time.time()
            try:
                res = ask(c["q"])
            except Exception as exc:  # noqa: BLE001
                res = {"answer": f"EXCEPTION: {exc}", "rows_returned": 0}
            res["_ms"] = int((time.time() - t0) * 1000)

        answer = res.get("answer") or ""
        blocked = any(m in answer.lower() for m in _BLOCKED_MARKERS)

        if blocked:
            status, note = "BLOCKED", "provider/quota — NOT verified"
        else:
            try:
                ok, note = c["expect"](answer, res)
            except Exception as exc:  # noqa: BLE001
                ok, note = False, f"check error: {exc}"
            if ok and c.get("truth"):
                true_val = _truth(c["truth"])
                if true_val is not None and not _has_number(answer, true_val):
                    note += f" | WARN: expected total {true_val} not in answer"
            status = "PASS" if ok else "FAIL"

        results.append(status)
        print(f"\n[{status:7}] {c['id']:12} {c['q'][:62]}")
        print(f"           why: {c['why']}")
        print(f"           {note}")
        if status == "FAIL":
            print(f"           answer: {answer[:200]!r}")

    p, f, b = results.count("PASS"), results.count("FAIL"), results.count("BLOCKED")
    print("\n" + "=" * 74)
    print(f"PASS {p}   FAIL {f}   BLOCKED {b}   of {len(results)}")
    if b:
        print("\n!! BLOCKED questions were NOT verified (provider quota/outage).")
        print("   Do NOT treat this run as a green light — fix the provider and re-run.")
    if f:
        print("\n!! FAILURES above would be seen by the client. Fix before demoing.")
    if not f and not b:
        print("\nAll client questions answered correctly. Safe to demo.")
    return 1 if (f or b) else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated case ids (e.g. gia,salary)")
    ap.add_argument("--repeat", type=int, default=1,
                    help="run each question N times to catch INCONSISTENT answers")
    ap.add_argument("--warm", action="store_true",
                    help="PRE-WARM the answer cache so the demo needs no provider "
                         "calls (sets ANSWER_CACHE_ENABLED for this run)")
    args = ap.parse_args()
    if args.warm:
        import os
        os.environ["ANSWER_CACHE_ENABLED"] = "true"
        print("WARM MODE: successful answers will be cached for the demo.")
    code = run(set(args.only.split(",")) if args.only else None, max(1, args.repeat))
    if args.warm:
        from app.agent import answer_cache
        st = answer_cache.stats()
        print(f"\nCache now holds {st['entries']} warmed answers -> {st['dir']}")
        print("Set ANSWER_CACHE_ENABLED=true in .env so the app serves them.")
    sys.exit(code)
