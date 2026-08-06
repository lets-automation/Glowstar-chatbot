"""
refactor_guard.py
-----------------
Before/after snapshot used to prove a REFACTOR changed no behaviour.

Not a correctness test - scripts/cold_test.py does that. This answers a narrower
question: did restructuring the code change what the agent DOES? So it records
structural facts that a refactor must never alter, and deliberately ignores
prose wording, which varies run to run even at temperature 0.

    python -m scripts.refactor_guard --save before
    ...refactor...
    python -m scripts.refactor_guard --save after
    python -m scripts.refactor_guard --diff before after

Non-determinism is real (the same question has produced 2 queries on one run and
6 on the next), so each case runs twice and records the BEST outcome. A drop is
only reported when both runs are worse - otherwise this would cry wolf on every
comparison and quickly get ignored.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_DIR = Path(__file__).resolve().parents[1] / "logs" / "refactor_guard"

# Chosen to cover the distinct paths through the agent, not to be exhaustive:
# a deterministic gate, a simple count, a breakdown, a detail report, the salary
# refusal, and the scope guard.
CASES = [
    ("simple_count",  "how many kapans are there"),
    ("breakdown",     "department wise production for June 2026"),
    ("detail_report", "give me full report of MFG - 1 from 1 Jul 2026 to 31 Jul 2026"),
    ("employee_360",  "give me the report of employee M4117 for June 2026"),
    ("salary_block",  "what is the salary of employee M4117"),
    ("bonus_allowed", "bonus of employee M4117 for June 2026"),
    ("out_of_scope",  "write me a poem about diamonds"),
    ("greeting",      "hello"),
]

_FALSE_DENIALS = (
    "i don't have that information in the database",
    "not tracked in the system",
)


def snapshot_one(question: str) -> dict:
    from app.agent.agent import ask

    try:
        r = ask(question)
    except Exception as exc:  # noqa: BLE001 - a crash IS the finding
        return {"crashed": str(exc)[:200], "score": -1}

    answer = (r.get("answer") or "").strip()
    low = answer.lower()
    queried = len(r.get("sql_used") or [])
    rows = r.get("rows_returned") or 0
    has_rows = bool(r.get("data_rows"))

    # A score so two runs of the same case can be compared. Deliberately coarse:
    # it ranks "answered with data" over "answered" over "blank/denied".
    score = 0
    if answer:
        score += 1
    if queried:
        score += 1
    if has_rows or rows:
        score += 1
    if len(answer) > 300:
        score += 1
    # A denial while holding no query is the wrong-answer class, not a pass.
    if any(d in low for d in _FALSE_DENIALS) and not queried:
        score = 0

    return {
        "crashed": None,
        "answered": bool(answer),
        "answer_len": len(answer),
        "queries": queried,
        "rows": rows,
        "has_data": has_rows,
        "blank": not answer,
        "false_denial": bool(any(d in low for d in _FALSE_DENIALS) and not queried),
        "score": score,
        "head": answer[:120].replace("\n", " "),
    }


def snapshot() -> dict:
    out = {}
    for key, q in CASES:
        runs = [snapshot_one(q) for _ in range(2)]
        best = max(runs, key=lambda d: d.get("score", -1))
        best["runs"] = [r.get("score", -1) for r in runs]
        out[key] = best
        print(f"  {key:15} score={best['score']} runs={best['runs']} "
              f"queries={best.get('queries')} len={best.get('answer_len')}")
    return out


def diff(before: dict, after: dict) -> int:
    print(f"\n{'case':16}{'before':>10}{'after':>10}   verdict")
    print("-" * 58)
    regressions = 0
    for key, _ in CASES:
        b, a = before.get(key, {}), after.get(key, {})
        bs, as_ = b.get("score", -1), a.get("score", -1)
        if a.get("crashed"):
            verdict, regressions = "CRASHED", regressions + 1
        elif as_ < bs:
            verdict, regressions = "REGRESSED", regressions + 1
        elif as_ > bs:
            verdict = "improved"
        else:
            verdict = "same"
        print(f"{key:16}{bs:>10}{as_:>10}   {verdict}")
    print("-" * 58)
    print("REGRESSIONS:", regressions)
    return 1 if regressions else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--save")
    ap.add_argument("--diff", nargs=2, metavar=("BEFORE", "AFTER"))
    a = ap.parse_args()
    _DIR.mkdir(parents=True, exist_ok=True)

    if a.diff:
        b = json.loads((_DIR / f"{a.diff[0]}.json").read_text(encoding="utf-8"))
        c = json.loads((_DIR / f"{a.diff[1]}.json").read_text(encoding="utf-8"))
        return diff(b, c)

    if not a.save:
        ap.error("pass --save NAME or --diff BEFORE AFTER")
    print(f"\nSnapshot '{a.save}' - {len(CASES)} cases x 2 runs\n" + "=" * 58)
    data = snapshot()
    (_DIR / f"{a.save}.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"\nsaved -> logs/refactor_guard/{a.save}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
