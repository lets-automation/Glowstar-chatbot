"""
e2e_check.py
------------
Prove the WHOLE chain works, from HTTP request to real ERP rows.

    python -m scripts.e2e_check              # infrastructure only, no LLM calls
    python -m scripts.e2e_check --ask        # ...plus one real question

Checks, cheapest first, stopping at the first failure that makes later ones
meaningless:

    1. /health                     the API is up
    2. db from the host            the restored database answers
    3. db from the BACKEND         the container can reach it as glowstar_ro
       container                   (a different network path - this is the one
                                   that actually matters, and the one that
                                   silently differs from a host-side test)
    4. the SQL guard               a write is refused at the app layer
    5. /suggest                    a real DB read through the API
    6. the frontend                nginx serves the app and proxies /api
    7. --ask only: /chat/stream    a real question, end to end

WHY --ask IS OPT-IN
-------------------
The provider rotation runs on free tiers - Gemini allows ~20 requests/DAY per
key, and ONE report question costs several. A check you run repeatedly must not
quietly eat the quota the client demo needs, which is the same reason
tests/conftest.py makes live-LLM tests opt-in.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

import os

from dotenv import load_dotenv

load_dotenv()

# Must match docker-compose.e2e.yml's published port. Configurable because 8000
# is often already taken by another stack on the same machine.
API = f"http://127.0.0.1:{os.getenv('E2E_API_PORT', '8000')}"
WEB = f"http://localhost:{os.getenv('E2E_WEB_PORT', '8080')}"

_PASS, _FAIL = "PASS", "FAIL"
_results: list[tuple[str, str, str]] = []


def _record(name: str, ok: bool, detail: str = "") -> bool:
    _results.append((name, _PASS if ok else _FAIL, detail))
    print(f"  [{_PASS if ok else _FAIL}] {name}" + (f" - {detail}" if detail else ""))
    return ok


def _get(url: str, timeout: int = 20):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.status, r.read()


def check_health() -> bool:
    try:
        status, body = _get(f"{API}/health")
        return _record("API /health", status == 200, json.loads(body).get("status", ""))
    except Exception as exc:
        return _record("API /health", False, f"{type(exc).__name__}: {exc}")


def check_db_from_host() -> bool:
    try:
        from app.database.runner import run_select

        res = run_select("SELECT COUNT(*) AS n FROM tblPacket")
        if not res["ok"]:
            return _record("database (from host)", False, res["error"][:120])
        n = res["rows"][0]["n"]
        return _record("database (from host)", n > 0, f"{n:,} packets")
    except Exception as exc:
        return _record("database (from host)", False, f"{type(exc).__name__}: {exc}")


def check_db_from_backend() -> bool:
    """The path that actually matters: container -> db over the compose network."""
    import subprocess

    code = (
        "from app.database.runner import run_select;"
        "r=run_select('SELECT COUNT(*) AS n FROM tblKapan');"
        "print('OK' if r['ok'] else 'ERR '+r['error'], r['rows'][0]['n'] if r['ok'] else '')"
    )
    try:
        out = subprocess.run(
            ["docker", "compose", "-f", "docker-compose.yml", "-f",
             "docker-compose.e2e.yml", "exec", "-T", "backend", "python", "-c", code],
            capture_output=True, text=True, timeout=120,
        )
        text = (out.stdout or out.stderr).strip().splitlines()[-1] if (out.stdout or out.stderr) else ""
        return _record("database (from backend container)", text.startswith("OK"), text[:120])
    except Exception as exc:
        return _record("database (from backend container)", False, f"{type(exc).__name__}: {exc}")


def check_readonly_guard() -> bool:
    """A write must be refused. Belt (app guard) and braces (db permissions)."""
    try:
        from app.core.sql_guard import is_read_only
        from app.database.runner import run_select

        ok_guard, reason = is_read_only("UPDATE tblPacket SET PacketNo = 1")
        if ok_guard:
            return _record("read-only guard", False, "sql_guard ACCEPTED an UPDATE")
        res = run_select("UPDATE tblPacket SET PacketNo = 1")
        return _record("read-only guard", not res["ok"], f"refused: {reason}")
    except Exception as exc:
        return _record("read-only guard", False, f"{type(exc).__name__}: {exc}")


def check_suggest() -> bool:
    """A real DB read THROUGH the API - no LLM involved."""
    try:
        status, body = _get(f"{API}/suggest?q=fenc")
        sug = json.loads(body).get("suggestions", [])
        names = [s["name"] for s in sug]
        return _record("API /suggest (live DB read)", status == 200 and bool(sug),
                       f"{len(sug)} matches: {', '.join(names[:4])}")
    except Exception as exc:
        return _record("API /suggest (live DB read)", False, f"{type(exc).__name__}: {exc}")


def check_frontend() -> bool:
    try:
        status, body = _get(WEB)
        served = status == 200 and b"<div id=\"root\"" in body
        if not _record("frontend served", served, f"HTTP {status}, {len(body)} bytes"):
            return False
        status2, body2 = _get(f"{WEB}/api/health")
        return _record("frontend -> /api proxy", status2 == 200,
                       json.loads(body2).get("status", ""))
    except Exception as exc:
        return _record("frontend served", False, f"{type(exc).__name__}: {exc}")


def _backend_logs() -> str:
    import subprocess

    out = subprocess.run(
        ["docker", "compose", "-f", "docker-compose.yml", "-f",
         "docker-compose.e2e.yml", "logs", "backend"],
        capture_output=True, text=True, timeout=120,
    )
    return out.stdout or ""


def check_agentcost_interceptors() -> bool:
    """The interceptor for the ACTIVE provider must have loaded.

    This is the check that would have caught the 2026-08-06 bug immediately.
    agentcost 0.1.3 shipped no Gemini interceptor at all, so with
    LLM_PROVIDER=gemini nothing was ever tracked - and the only symptom was an
    empty dashboard. The startup banner named exactly which interceptors loaded
    ("LangChain, OpenAI, Anthropic") and Gemini was simply absent from it.
    """
    # provider -> the word the SDK prints in its "Tracking initialized" banner
    needed = {
        "gemini": "Gemini",
        "anthropic": "Anthropic", "claude": "Anthropic",
        "cerebras": "OpenAI", "nvidia": "OpenAI",
        "ollama": "OpenAI", "lmstudio": "OpenAI",
    }
    provider = os.getenv("LLM_PROVIDER", "groq").lower()
    try:
        line = next((l for l in _backend_logs().splitlines()
                     if "Tracking initialized" in l), "")
        if not line:
            return _record("AgentCost interceptors", False,
                           "no init banner - tracking is not enabled at all")
        loaded = line.split("Tracking initialized", 1)[1].strip()
        want = needed.get(provider)
        if want is None:
            # groq: the native SDK is not patched by any version of the SDK.
            return _record("AgentCost interceptors", True,
                           f"loaded {loaded} - NOTE provider={provider} is NOT trackable")
        return _record("AgentCost interceptors", want in line,
                       f"provider={provider} needs {want}; loaded {loaded}")
    except Exception as exc:
        return _record("AgentCost interceptors", False, f"{type(exc).__name__}: {exc}")


def check_agentcost(expect_events: bool = False) -> bool:
    """Are cost events actually being SENT?

    Read from the running backend's LOGS, not by exec'ing python in the
    container. An earlier version of this check did the latter and reported
    "not initialized" against a perfectly healthy backend: `docker compose exec
    python -c ...` starts a BRAND NEW process that never ran track_costs.init(),
    so its counters are always zero and say nothing about the uvicorn process
    actually serving requests.

    Needs AGENTCOST_DEBUG=true to see the send lines.
    """
    try:
        logs = _backend_logs()
        sent = logs.count("events successfully")
        failed = logs.count("Failed to send")
        if failed:
            return _record("AgentCost tracking", False,
                           f"{failed} batch send failures in the logs")
        if expect_events and sent == 0:
            debug_on = os.getenv("AGENTCOST_DEBUG", "").lower() in ("1", "true", "yes")
            return _record(
                "AgentCost tracking", False,
                "a question ran but no events were sent"
                + ("" if debug_on else " (AGENTCOST_DEBUG is off, so this may be "
                                       "a blind spot rather than a failure)"))
        return _record("AgentCost tracking", True,
                       f"{sent} batch(es) delivered to api.agentcost.tech")
    except Exception as exc:
        return _record("AgentCost tracking", False, f"{type(exc).__name__}: {exc}")


def check_ask(question: str) -> bool:
    """One real question, all the way through the agent to real rows."""
    payload = json.dumps({"question": question, "session_id": "e2e-check"}).encode()
    req = urllib.request.Request(
        f"{API}/chat/stream", data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        statuses, result = [], None
        with urllib.request.urlopen(req, timeout=300) as r:
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                evt = json.loads(line[5:].strip())
                if evt.get("type") == "status":
                    statuses.append(evt.get("message", ""))
                elif evt.get("type") == "result":
                    result = evt.get("data")
                elif evt.get("type") == "error":
                    return _record("chat (end to end)", False, evt.get("message", "")[:140])
        if result is None:
            return _record("chat (end to end)", False, "no result event")

        answer = (result.get("answer") or "").strip()
        sql = result.get("sql_used") or []
        rows = result.get("rows_returned", 0)
        print(f"       status events : {' -> '.join(statuses[:6])}")
        print(f"       SQL executed  : {len(sql)} quer{'y' if len(sql)==1 else 'ies'}")
        if sql:
            print(f"       first query   : {sql[0][:150]}")
        print(f"       rows returned : {rows}")
        print(f"       answer ({len(answer)} chars):")
        for ln in answer.splitlines()[:14]:
            print(f"         {ln[:110]}")
        # The bar: real SQL ran AND the answer is grounded in it.
        good = bool(sql) and result.get("ok", False) and len(answer) > 40
        return _record("chat (end to end)", good,
                       f"{len(sql)} queries, {rows} rows, ok={result.get('ok')}")
    except urllib.error.HTTPError as exc:
        return _record("chat (end to end)", False, f"HTTP {exc.code}: {exc.read()[:140]}")
    except Exception as exc:
        return _record("chat (end to end)", False, f"{type(exc).__name__}: {exc}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ask", action="store_true",
                    help="also send ONE real question (costs provider quota)")
    ap.add_argument("--question", default="How many packets are on jangad?")
    args = ap.parse_args()

    print("End-to-end check\n")
    print("infrastructure:")
    check_health()
    check_db_from_host()
    check_db_from_backend()
    check_readonly_guard()
    check_suggest()
    check_frontend()
    check_agentcost_interceptors()
    check_agentcost()

    if args.ask:
        print("\nlive question (uses provider quota):")
        check_ask(args.question)
        # Re-read the counters AFTER the question: this is the only check that
        # proves tracking end to end rather than merely loaded.
        print("\ncost tracking after the question:")
        check_agentcost(expect_events=True)
    else:
        print("\n(skipping the live question - re-run with --ask to include it)")

    failed = [r for r in _results if r[1] == _FAIL]
    print(f"\n{len(_results) - len(failed)}/{len(_results)} passed")
    if failed:
        print("failed: " + ", ".join(n for n, _, _ in failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
