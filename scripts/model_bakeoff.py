"""
model_bakeoff.py
-----------------
Compare several FREE-TIER models on a handful of real, client-realistic
questions, side by side.

Reuses two hard-won patterns from the existing test scripts rather than
reinventing them:
  - provider_probe.py's subprocess-per-run isolation. Switching LLM_PROVIDER
    in-process leaves a stale client pointed at the previous provider's
    base_url (see that file's `probe()` docstring) - a fresh subprocess has
    no state to leak.
  - cold_test.py's grading: ground truth is computed from the live DB at run
    time (a restore/refresh updates the expectation automatically), and a
    provider that errors out is BLOCKED, never silently scored as wrong.

    python -m scripts.model_bakeoff                  # default 5 questions x 6 models
    python -m scripts.model_bakeoff --only groq/gpt-oss-20b,openrouter/gemma-4-31b-it
    python -m scripts.model_bakeoff --cases COLD-05,COLD-01
    python -m scripts.model_bakeoff --compare        # saved runs, no LLM calls

SELF-HOSTED (rented GPU) RUNS
-----------------------------
vLLM serves ONE model per process, so comparing two of them is two invocations
with a server restart in between - possibly hours apart, on a pod that gets
stopped to save money. Every run therefore writes its rows to /artifacts, and
--compare rebuilds the side-by-side table from disk without touching a GPU:

    OPENROUTER_BASE_URL=https://<pod-id>-8888.proxy.runpod.net/v1   # in .env
    python -m scripts.model_bakeoff --only vllm/qwen3-coder-30b
    ...restart vLLM on the other model...
    python -m scripts.model_bakeoff --only vllm/qwen3.5-9b
    python -m scripts.model_bakeoff --compare

The tools% column is the one that matters there: it is the share of questions
where run_sql actually fired. A model that guesses a plausible number without
querying can still score CORRECT, and on a GPU-purchase decision that is
exactly the failure you must not mistake for success.

CANDIDATES are all zero-cost as of the date this was written: two are on
Groq's free tier (shared 200K-tokens/day cap across whatever runs there),
four are on OpenRouter's free tier (each with its own separate limit, not
counted against Groq's). Free-tier line-ups change fast - if a candidate
comes back BLOCKED, it may have been pulled; check
https://console.groq.com/docs/models and the OpenRouter /models API before
assuming the harness is broken.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

from app.database.runner import run_select  # noqa: E402
from scripts.cold_cases import COLD_CASES, grade_expectation  # noqa: E402

# label -> (LLM_PROVIDER value, model id to pass to ask())
#
# Verified by hand on 2026-08-11 with a direct httpx probe before wiring these
# into the harness - free-tier availability moves fast, recheck before trusting
# this list on a later date:
#   groq/gpt-oss-20b            EXCLUDED - HTTP 403, "blocked at the organization
#                                level" (console.groq.com/settings/limits). Not
#                                a harness bug - needs an org admin to unblock.
#   openrouter/gemma-4-31b-it   EXCLUDED - failed 2/2 attempts just now with
#                                "Provider returned error" (OpenRouter free-tier
#                                upstream for this model looks currently down,
#                                not merely rate-limited). Worth retrying later.
#   openrouter/gpt-oss-20b      KEPT but flaky - failed 1/2 attempts with the
#                                same "Provider returned error", succeeded on
#                                retry. Expect occasional BLOCKED rows below.
CANDIDATES: dict[str, tuple[str, str]] = {
    "groq/qwen3.6-27b":                  ("groq", "qwen/qwen3.6-27b"),
    "openrouter/gpt-oss-20b":            ("openrouter", "openai/gpt-oss-20b:free"),
    "openrouter/gemma-4-26b-a4b":        ("openrouter", "google/gemma-4-26b-a4b-it:free"),
    "openrouter/nemotron-nano-9b-v2":    ("openrouter", "nvidia/nemotron-nano-9b-v2:free"),
    # PAID - a few rupees per run, not free-tier. Confirmed live on OpenRouter
    # (SiliconFlow/DeepInfra/Venice endpoints, status 0) on 2026-08-11.
    "openrouter/qwen3.5-9b":             ("openrouter", "qwen/qwen3.5-9b"),
    # PAID - $0.08/$0.18 per 1M, cheaper than qwen3.5-9b. 1M-token context.
    "openrouter/deepseek-v4-flash":      ("openrouter", "deepseek/deepseek-v4-flash-0731"),

    # SELF-HOSTED on a rented GPU (RunPod / JarvisLabs), served by vLLM behind
    # its OpenAI-compatible endpoint. These reuse the `openrouter` slot because
    # groq_backend._OPENAI_COMPATIBLE already drives it through the OpenAI SDK
    # with a configurable base_url - serving a vLLM box needs NO change in app/.
    #
    # Point .env at the box ONCE and both rows work:
    #   OPENROUTER_BASE_URL=https://<pod-id>-8888.proxy.runpod.net/v1
    #   OPENROUTER_API_KEY=glowstar-key
    #
    # The id on the right must match what vLLM reports in /v1/models EXACTLY
    # (it defaults to the repo path you passed to `vllm serve`), otherwise the
    # server 404s the request and the row comes back BLOCKED.
    #
    # Only ONE of these can be live at a time - vLLM serves a single model per
    # process - so run them as separate invocations and compare with --compare.
    "vllm/qwen3-coder-30b":  ("openrouter", "cpatonn/Qwen3-Coder-30B-A3B-Instruct-AWQ-4bit"),
    "vllm/qwen3.5-9b":       ("openrouter", "QuantTrio/Qwen3.5-9B-AWQ"),
}

# A small, deliberately mixed default slate: 2 plain English, 3 Gujlish/Hindi
# mixed, 1 that is honestly unanswerable (tblPacketSell has 0 rows) so we can
# see whether a model fabricates a number instead of saying "not recorded".
DEFAULT_CASES = {"COLD-05", "COLD-01", "CT-05", "EDA-2", "COLD-08"}

_BLOCKED = ("busy right now", "usage limit", "couldn't reach", "could not reach",
            "unavailable right now", "not configured")


def truth_of(sql: str):
    r = run_select(sql, max_rows=2)
    if not r.get("ok") or not r["rows"]:
        return None
    return list(r["rows"][0].values())[0]


def answer_contains(answer: str, value) -> bool:
    """Same tolerant match cold_test.py uses (comma/format-insensitive)."""
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


def run_one(label: str, provider: str, model: str, question: str) -> dict:
    """One (model, question) pair in a FRESH SUBPROCESS - see module docstring."""
    code = (
        "import os,json,time;"
        "from dotenv import load_dotenv;load_dotenv();"
        f"os.environ['LLM_PROVIDER']={provider!r};"
        "from app.agent.agent import ask;"
        "t0=time.monotonic();"
        f"r=ask({question!r}, model={model!r});"
        "dt=time.monotonic()-t0;"
        "print('@@'+json.dumps({'answer':r.get('answer') or '',"
        "'ok':bool(r.get('ok')),'rows':r.get('rows_returned',0),"
        "'sql':len(r.get('sql_used') or []),'sql_text':(r.get('sql_used') or []),"
        "'latency':round(dt,1)}))"
    )
    env = dict(os.environ, LLM_PROVIDER=provider, PYTHONIOENCODING="utf-8")
    try:
        out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                             text=True, timeout=180, env=env,
                             encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return {"status": "BLOCKED", "answer": "timed out after 180s",
                "latency": None, "sql": 0}

    line = next((l for l in (out.stdout or "").splitlines() if l.startswith("@@")), None)
    if not line:
        tail = (out.stderr or out.stdout or "no output").strip().splitlines()
        return {"status": "BLOCKED", "answer": (tail[-1] if tail else "?")[:150],
                "latency": None, "sql": 0}

    d = json.loads(line[2:])
    if not d.get("ok"):
        return {"status": "BLOCKED", "answer": d["answer"][:150],
                "latency": d["latency"], "sql": d.get("sql", 0)}
    return {"status": None, "answer": d["answer"], "rows": d["rows"],
            "latency": d["latency"], "sql": d.get("sql", 0),
            "sql_text": d.get("sql_text", [])}


def grade(answer: str, expected, rows: int, case: dict | None = None,
          sql_used: list[str] | None = None) -> str:
    if any(b in answer.lower() for b in _BLOCKED):
        return "BLOCKED"
    # ADV-* probes have no ground-truth value: the right answer is a refusal or
    # an avoidance. One grader, shared with cold_test.py — see cold_cases.py.
    if case and case.get("expect"):
        return grade_expectation(case, answer, sql_used)[0]
    if answer_contains(answer, expected):
        return "CORRECT"
    if not rows:
        return "NO-DATA"
    return "CHECK"


# Results land in /artifacts (gitignored at the repo root), ONE FILE PER
# CANDIDATE. vLLM serves a single model per process, so comparing two
# self-hosted models means two separate invocations minutes or hours apart -
# and without this, the first model's numbers live only in a terminal buffer
# that a closed tab or a stopped pod destroys. Save each run, then:
#
#     python -m scripts.model_bakeoff --only vllm/qwen3-coder-30b
#     ...restart vLLM on the other model...
#     python -m scripts.model_bakeoff --only vllm/qwen3.5-9b
#     python -m scripts.model_bakeoff --compare        # both, side by side
#
_OUT = os.path.join("artifacts", "bakeoff")


def _save(label: str, provider: str, model: str, rows: list[dict]) -> None:
    os.makedirs(_OUT, exist_ok=True)
    path = os.path.join(_OUT, label.replace("/", "_") + ".json")
    payload = {"label": label, "provider": provider, "model": model,
               "when": datetime.now().isoformat(timespec="seconds"), "rows": rows}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"  -> saved {path}")


def _load_all() -> dict[str, list[dict]]:
    """Every previously saved run, newest wins on a repeated label."""
    if not os.path.isdir(_OUT):
        return {}
    out = {}
    for name in sorted(os.listdir(_OUT)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(_OUT, name), encoding="utf-8") as f:
            d = json.load(f)
        out[d["label"]] = d["rows"]
    return out


def _matrix(labels: list[str], results: dict[str, list[dict]]) -> None:
    """Status per case, plus the two columns that decide a GPU purchase.

    tools% is the share of questions where run_sql actually fired. A model can
    score CORRECT while never touching the database - it guessed - so accuracy
    alone cannot tell a working agent from a lucky one.
    """
    # Case ids come from the rows, not the caller: a --compare across runs that
    # used different --cases must not silently misalign the columns.
    ids: list[str] = []
    for label in labels:
        for r in results.get(label, []):
            if r["id"] not in ids:
                ids.append(r["id"])

    print("\n" + "=" * 86)
    print(f"{'model':28}" + "".join(f"{i:>10}" for i in ids) + f"{'avg s':>8}{'tools%':>8}")
    for label in labels:
        row = {r["id"]: r for r in results.get(label, [])}
        lats = [r["latency"] for r in row.values() if r.get("latency") is not None]
        avg = f"{sum(lats) / len(lats):.1f}" if lats else "-"
        ran = [r for r in row.values() if r["status"] != "BLOCKED"]
        tools = f"{100 * sum(1 for r in ran if r.get('sql', 0)) / len(ran):.0f}" if ran else "-"
        cells = "".join(f"{row[i]['status'][:9]:>10}" if i in row else f"{'-':>10}" for i in ids)
        print(f"{label:28}" + cells + f"{avg:>8}{tools:>8}")


def main() -> int:
    # Answers can contain non-cp1252 characters (rupee sign, Gujarati) and the
    # Windows console defaults to cp1252 - a raw print() then crashes the whole
    # run mid-summary. Force UTF-8, falling back to a replacing writer if the
    # platform won't reconfigure.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated candidate labels (see CANDIDATES)")
    ap.add_argument("--cases", help="comma-separated cold_cases ids")
    ap.add_argument("--all", action="store_true",
                    help="every case in cold_cases.py, not the 5-question default. "
                         "Use this when the result decides a purchase - five "
                         "questions is a smoke test, not evidence")
    ap.add_argument("--compare", action="store_true",
                    help="print previously saved runs side by side; no LLM calls, "
                         "no GPU needed - use it after serving each model in turn")
    a = ap.parse_args()

    # --compare is deliberately free: it reads /artifacts only. That is what
    # makes a two-model bakeoff survive a stopped pod, a closed terminal, or a
    # gap of hours between the two halves of the run.
    if a.compare:
        saved = _load_all()
        if not saved:
            print(f"No saved runs in {_OUT}. Run a bakeoff first.")
            return 2
        _matrix(list(saved), saved)
        return 0

    labels = a.only.split(",") if a.only else list(CANDIDATES)
    unknown = [l for l in labels if l not in CANDIDATES]
    if unknown:
        print(f"Unknown candidate(s): {unknown}\nKnown: {list(CANDIDATES)}")
        return 2

    if a.all:
        wanted_ids = {c["id"] for c in COLD_CASES}
    else:
        wanted_ids = set(a.cases.split(",")) if a.cases else DEFAULT_CASES
    cases = [c for c in COLD_CASES if c["id"] in wanted_ids]

    print(f"\nMODEL BAKEOFF - {len(labels)} models x {len(cases)} questions")
    print("=" * 78)

    results: dict[str, list[dict]] = {}
    for label in labels:
        provider, model = CANDIDATES[label]
        print(f"\n--- {label} ({provider} / {model}) ---")
        results[label] = []
        for c in cases:
            expected = truth_of(c["truthSql"]) if c.get("truthSql") else None
            r = run_one(label, provider, model, c["question"])
            status = r.get("status") or grade(
                r["answer"], expected, r.get("rows", 0), case=c,
                sql_used=r.get("sql_text", []))
            # The answer text is persisted too: CHECK means "answered but the
            # ground-truth value was not found in the text", and that verdict is
            # only resolvable by READING it. Without this the saved file can tell
            # you a run went badly but never why, and re-running to find out
            # costs another full GPU session.
            results[label].append({"id": c["id"], "status": status,
                                   "latency": r["latency"], "sql": r.get("sql", 0),
                                   "answer": (r.get("answer") or "")[:1200]})
            lat = f"{r['latency']}s" if r["latency"] is not None else "-"
            # sql=0 is the tell that the model ANSWERED WITHOUT CALLING A TOOL -
            # the weak-model failure groq_backend's grounding guard exists for. It
            # can still land on CORRECT by guessing a plausible number, so it has
            # to be visible SEPARATELY from the status column.
            print(f"  [{status:8}] {c['id']:8} {lat:>6}  sql={r.get('sql', 0)}"
                  f"  {r['answer'][:90]!r}")
        _save(label, provider, model, results[label])

    _matrix(labels, results)

    print("\nCORRECT = ground-truth value found in the answer. CHECK = answered but")
    print("value absent, read it yourself. NO-DATA = declined (right for CT-05).")
    print("BLOCKED = provider/rate-limit error, NOT a model failure - rerun later.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
