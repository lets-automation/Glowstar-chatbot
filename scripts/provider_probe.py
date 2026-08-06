"""
provider_probe.py
-----------------
Answers one question: is our ERP knowledge PROVIDER-INDEPENDENT?

The client's own report reads tblPlanMaster and separates the PLS (in-house)
grade from the GIA (lab) grade using the RapVer stage column. If the chatbot
only reproduces that mapping on one specific model, the knowledge isn't really
encoded - we are just getting lucky with a strong model, and the next provider
switch silently breaks the client's headline report.

So: ask the SAME question on EVERY configured provider and inspect the SQL each
one generates. Grading is STRUCTURAL, not textual - did the SQL reach the right
table, use the stage column, and separate the two grade sources?

    python -m scripts.provider_probe                 # every configured provider
    python -m scripts.provider_probe --only nvidia,groq

Deliberately does NOT include 'anthropic': it is a PAID API. Pass it by name if
you actually want to spend money on it.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

# The keys live in .env, which is only read when app.config is imported. Load it
# up front so the "is this provider configured?" check can see them.
from dotenv import load_dotenv

load_dotenv()

QUESTION = "Provide GIA results of Fency department employees for June 2026"

# Structural checks - each one is something the client's own query does.
CHECKS = {
    "tblPlanMaster":   lambda s: "tblplanmaster" in s,
    "RapVer stage":    lambda s: "rapver" in s,
    "GIA stage":       lambda s: "'gia'" in s,
    "PLS (in-house)":  lambda s: "'pls'" in s,
    "MFG (the maker)": lambda s: "'mfg'" in s,
    "employee join":   lambda s: "tblemployee" in s or "tblempdetail" in s,
}

# Free / already-paid-for providers. anthropic is excluded on purpose.
CANDIDATES = ["nvidia", "groq", "cerebras", "kimi", "gemini"]


def configured(p: str) -> bool:
    """Gemini keys live in a rotation POOL (GEMINI_API_KEYS, plural) because the
    free tier is only ~20 requests/day/key. Checking the singular name alone
    silently skipped the demo provider entirely."""
    return any(os.getenv(n, "").strip() for n in (
        f"{p.upper()}_API_KEY", f"{p.upper()}_API_KEYS",
        f"{p.upper()}_API_KEY_2", f"{p.upper()}_API_KEY_3"))


def probe(provider: str) -> dict:
    """
    Run ONE provider in a FRESH SUBPROCESS.

    An earlier version reloaded app.config in-process. That is not enough: the
    backend caches a client built from the previous provider's base_url, so
    switching to groq sent groq's model name to NVIDIA's endpoint and came back
    "404 page not found" - which read exactly like the model failing the test.
    A separate process has no state to leak.
    """
    code = (
        "import os,json;"
        "from dotenv import load_dotenv;load_dotenv();"
        f"os.environ['LLM_PROVIDER']={provider!r};"
        "from app.agent.agent import ask;"
        f"r=ask({QUESTION!r});"
        "s=r.get('sql_used') or [];"
        "print('@@'+json.dumps({'sql':' '.join(map(str,s)),"
        "'rows':r.get('rows_returned',0),'ok':bool(r.get('ok')),"
        "'answer':(r.get('answer') or '')[:150]}))"
    )
    env = dict(os.environ, LLM_PROVIDER=provider, PYTHONIOENCODING="utf-8")
    try:
        out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                             text=True, timeout=300, env=env,
                             encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return {"provider": provider, "error": "timed out after 300s"}

    line = next((l for l in (out.stdout or "").splitlines() if l.startswith("@@")), None)
    if not line:
        tail = (out.stderr or out.stdout or "no output").strip().splitlines()
        return {"provider": provider, "error": (tail[-1] if tail else "?")[:150]}

    d = json.loads(line[2:])

    # A provider that never ran is NOT a failed mapping. ask() swallows provider
    # errors into a friendly ok=False answer, so without this check groq hitting
    # its 12k token-per-minute cap scored a clean 0/6 - indistinguishable from a
    # model that reached for the wrong tables. That is the exact confidently-
    # wrong result this harness exists to catch.
    if not d.get("ok") or not d["sql"].strip():
        return {"provider": provider, "error": f"provider did not run: {d['answer']}"}

    blob = d["sql"].lower()
    return {
        "provider": provider,
        "model": os.getenv(f"{provider.upper()}_MODEL", "?"),
        "sql": re.sub(r"\s+", " ", d["sql"])[:400],
        "rows": d["rows"],
        "hits": {k: fn(blob) for k, fn in CHECKS.items()},
        "answer": d["answer"],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated providers")
    a = ap.parse_args()

    want = [p.strip() for p in a.only.split(",")] if a.only else CANDIDATES
    todo = [p for p in want if configured(p)]
    skipped = [p for p in want if p not in todo]

    print(f"\nPROVIDER PROBE - same question, {len(todo)} providers")
    print(f"Q: {QUESTION}")
    if skipped:
        print(f"(no API key, skipped: {', '.join(skipped)})")
    print("=" * 78)

    results = []
    for p in todo:
        r = probe(p)
        results.append(r)
        if r.get("error"):
            print(f"\n[{p:9}] ERROR: {r['error']}")
            continue
        score = sum(r["hits"].values())
        print(f"\n[{p:9}] {r['model']} - {score}/{len(CHECKS)} structural marks, "
              f"{r['rows']} rows")
        for k, ok in r["hits"].items():
            print(f"      {'OK  ' if ok else 'MISS'}  {k}")
        print(f"      SQL: {r['sql'][:220]}")

    print("\n" + "=" * 78)
    print(f"{'provider':10}" + "".join(f"{k[:9]:>11}" for k in CHECKS))
    for r in results:
        if r.get("error"):
            print(f"{r['provider']:10}  ERROR - not verified")
            continue
        print(f"{r['provider']:10}" +
              "".join(f"{('YES' if r['hits'][k] else 'no'):>11}" for k in CHECKS))
    print("\nA provider that ERRORs is NOT a failed mapping - fix it and re-run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
