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
import time
import re
import sys

from app.agent import access_guard, date_gate, smalltalk_gate
from app.agent.agent import ask
from app.database.runner import run_select
from scripts.cold_cases import COLD_CASES, grade_expectation

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


def run(only: set[str] | None = None, limit: int | None = None,
        full: bool = False) -> int:
    # Answers carry Gujarati, the rupee sign and narrow no-break
    # spaces. The Windows console defaults to cp1252, so a raw print()
    # crashes the whole run mid-suite - and redirecting to a file makes
    # it certain. Same guard model_bakeoff already carries.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    cases = [c for c in COLD_CASES if not only or c["id"] in only]
    if limit:
        cases = cases[:limit]
    print(f"\nCOLD TEST — {len(cases)} questions with NO encoded guidance\n" + "=" * 74)

    tally: dict[str, int] = {}
    timings: list[tuple[str, float]] = []
    for c in cases:
        _t0 = time.monotonic()
        expected = truth_of(c["truthSql"]) if c.get("truthSql") else None

        # Mirror the app's deterministic gates before spending a model call.
        #
        # KEEP THIS IN STEP WITH app/api/main.py. The SQL-request gate was added
        # to both /chat and /chat/stream on 2026-08-26 but not mirrored here, so
        # ADV-03 kept grading WRONG in the suite while real users were correctly
        # refused. A harness that does not mirror a gate measures a system
        # nobody runs.
        q = c["question"]
        if smalltalk_gate.is_smalltalk(q):
            res = smalltalk_gate.smalltalk_response(q)
        elif smalltalk_gate.asks_for_sql(q):
            res = smalltalk_gate.sql_refusal_response()
        elif access_guard.is_pay_question(q):
            res = access_guard.refusal_response(q)
        elif date_gate.needs_date(q):
            res = date_gate.ask_date_response(q)
        else:
            try:
                res = ask(q)
            except Exception as exc:  # noqa: BLE001
                res = {"answer": f"EXCEPTION: {exc}", "rows_returned": 0}

        answer = res.get("answer") or ""
        why = ""
        if any(b in answer.lower() for b in _BLOCKED):
            status = "BLOCKED"
        elif c.get("expect"):
            # ADV-* cases: the right answer is a refusal or an avoidance, which
            # has no ground-truth value to match. See cold_cases.grade_expectation.
            status, why = grade_expectation(c, answer, res.get("sql_used"))
        elif answer_contains(answer, expected):
            status = "CORRECT"
        elif any(answer_contains(answer, truth_of(alt))
                 for alt in c.get("alsoAcceptSql") or []):
            # SOME QUESTIONS HAVE MORE THAN ONE CORRECT NUMBER.
            # query_rules keeps kapan_pieces_points advisory precisely because
            # "how many pieces" and "what weight came out" each have several
            # defensible readings, none of them wrong. Grading such a case
            # against ONE of them marks the other two failures for ever, which
            # is how COLD-07 stayed CHECK while answering correctly. A case may
            # therefore list alternative ground-truth SQL; each is still a real
            # query run against the live database, not a hardcoded number.
            status = "CORRECT"
            why = "matched an alternative ground truth"
        elif not res.get("rows_returned") and not (res.get("data_rows") or []):
            status = "NO-DATA"
        else:
            status = "CHECK"

        tally[status] = tally.get(status, 0) + 1
        _dt = time.monotonic() - _t0
        timings.append((c["id"], _dt))
        print(f"\n[{status:8}] {c['id']}  ({_dt:.1f}s)")
        print(f"   Q      : {q[:88]}")
        if c.get("expect"):
            print(f"   expect : {c['expect']} - {c.get('note', '')[:76]}")
            print(f"   verdict: {why}")
        else:
            print(f"   truth  : {expected}   (recorded: {c.get('truthValue')})")
        if full:
            print("   answer :")
            for _ln in (answer or "").splitlines():
                print(f"      {_ln}")
        else:
            print(f"   answer : {answer[:200].replace(chr(10), ' ')}")

    print("\n" + "=" * 74)
    if timings:
        _s = [t for _, t in timings]
        _slow = sorted(timings, key=lambda x: -x[1])[:3]
        print(f"  timing  : avg {sum(_s)/len(_s):.1f}s | slowest " +
              ", ".join(f"{i_} {t:.0f}s" for i_, t in _slow))
    for k in ("CORRECT", "CHECK", "WRONG", "NO-DATA", "BLOCKED"):
        print(f"  {k:8}: {tally.get(k, 0)}")
    if tally.get("BLOCKED"):
        print("\n!! BLOCKED cases were NOT verified — fix the provider and re-run.")
    if tally.get("WRONG"):
        print("\n!! WRONG means a rule was BROKEN, not merely unmatched: the answer")
        print("   contained text that can only appear if the guard failed. Treat any")
        print("   WRONG on an ADV-* case as a release blocker.")
    print("   NO-DATA is the CORRECT result for the deliberately-unanswerable cases;")
    print("   read those individually rather than trusting the totals.")
    return 1 if (tally.get("CHECK") or tally.get("BLOCKED") or tally.get("WRONG")) else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated case ids")
    ap.add_argument("--limit", type=int, help="run only the first N cases")
    ap.add_argument("--full", action="store_true",
                    help="print the COMPLETE answer, not a 200-char preview "
                         "- needed to review a multi-section report")
    ap.add_argument("--adversarial", action="store_true",
                    help="only the ADV-* rule-breaking probes (scope, injection, "
                         "backup tables, employee identity, salary)")
    ap.add_argument("--data", action="store_true",
                    help="only the original ground-truth data questions")
    a = ap.parse_args()
    picked = set(a.only.split(",")) if a.only else None
    if a.adversarial:
        picked = {c["id"] for c in COLD_CASES if c.get("expect")}
    elif a.data:
        picked = {c["id"] for c in COLD_CASES if not c.get("expect")}
    sys.exit(run(picked, a.limit, a.full))
