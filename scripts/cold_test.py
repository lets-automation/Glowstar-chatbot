"""
cold_test.py
------------
Run the COLD TEST: client-realistic questions with NO encoded guidance, each
checked against a ground truth computed from the database in the same run.

This measures preparedness for questions nobody anticipated — the thing that has
actually been failing — as opposed to re-testing the handful we already fixed.

    python -m scripts.cold_test                 # all cases
    python -m scripts.cold_test --limit 8       # first N (quota-aware)
    python -m scripts.cold_test --only COLD-01,COLD-07

Statuses:
  CORRECT   the ground-truth value appears in the answer
  CHECK     an answer was produced but the value is absent - read it yourself
  NO-DATA   the assistant declined / returned nothing (RIGHT for the
            deliberately-unanswerable cases, wrong for the rest)
  BLOCKED   provider quota/outage - NOT verified, never counted as a pass
"""
from __future__ import annotations

import argparse
import re
import sys

from app.agent import access_guard, date_gate
from app.agent.agent import ask
from app.database.runner import run_select
from scripts.cold_cases import COLD_CASES

_BLOCKED = ("busy right now", "usage limit", "couldn't reach", "could not reach",
            "unavailable right now", "not configured")


def truth_of(sql: str):
    r = run_select(sql, max_rows=2)
    if not r.get("ok") or not r["rows"]:
        return None
    return list(r["rows"][0].values())[0]


def answer_contains(answer: str, value) -> bool:
    """Is the ground-truth value present in the answer (comma/format tolerant)?"""
    if value is None:
        return False
    plain = re.sub(r"[,\s]", "", (answer or "")).lower()
    cands = {str(value)}
    try:
        f = float(value)
        cands.add(str(int(f)))
        cands.add(f"{f:.2f}")
        cands.add(f"{round(f):,}".replace(",", ""))
    except (TypeError, ValueError):
        pass
    return any(str(c).replace(",", "").lower() in plain for c in cands)


def run(only: set[str] | None = None, limit: int | None = None) -> int:
    cases = [c for c in COLD_CASES if not only or c["id"] in only]
    if limit:
        cases = cases[:limit]
    print(f"\nCOLD TEST — {len(cases)} questions with NO encoded guidance\n" + "=" * 74)

    tally: dict[str, int] = {}
    for c in cases:
        expected = truth_of(c["truthSql"]) if c.get("truthSql") else None

        # Mirror the app's deterministic gates before spending a model call.
        q = c["question"]
        if access_guard.is_pay_question(q):
            res = access_guard.refusal_response(q)
        elif date_gate.needs_date(q):
            res = date_gate.ask_date_response(q)
        else:
            try:
                res = ask(q)
            except Exception as exc:  # noqa: BLE001
                res = {"answer": f"EXCEPTION: {exc}", "rows_returned": 0}

        answer = res.get("answer") or ""
        if any(b in answer.lower() for b in _BLOCKED):
            status = "BLOCKED"
        elif answer_contains(answer, expected):
            status = "CORRECT"
        elif not res.get("rows_returned") and not (res.get("data_rows") or []):
            status = "NO-DATA"
        else:
            status = "CHECK"

        tally[status] = tally.get(status, 0) + 1
        print(f"\n[{status:8}] {c['id']}")
        print(f"   Q      : {q[:88]}")
        print(f"   truth  : {expected}   (recorded: {c.get('truthValue')})")
        print(f"   answer : {answer[:200].replace(chr(10), ' ')}")

    print("\n" + "=" * 74)
    for k in ("CORRECT", "CHECK", "NO-DATA", "BLOCKED"):
        print(f"  {k:8}: {tally.get(k, 0)}")
    if tally.get("BLOCKED"):
        print("\n!! BLOCKED cases were NOT verified — fix the provider and re-run.")
    print("   NO-DATA is the CORRECT result for the deliberately-unanswerable cases;")
    print("   read those individually rather than trusting the totals.")
    return 1 if (tally.get("CHECK") or tally.get("BLOCKED")) else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated case ids")
    ap.add_argument("--limit", type=int, help="run only the first N cases")
    a = ap.parse_args()
    sys.exit(run(set(a.only.split(",")) if a.only else None, a.limit))
