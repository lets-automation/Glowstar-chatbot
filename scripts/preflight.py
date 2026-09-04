"""
preflight.py
------------
THIRTY SECONDS OF CHECKS BEFORE A CLIENT DEMO.

Run it after `docker compose ... up -d --build backend` and before anyone
walks in:

    python -m scripts.preflight

It answers one question - is this thing ready - and it does it WITHOUT calling
the LLM provider, so it costs nothing and cannot be broken by a slow model, a
rate limit or a dead endpoint. Every check below is either a database read or a
deterministic code path.

Exit code 0 = ready. Non-zero = read the FAIL lines.
"""
from __future__ import annotations

import sys
from datetime import date

OK, BAD = "  OK  ", " FAIL "


def _check(label, fn):
    try:
        ok, detail = fn()
    except Exception as exc:  # noqa: BLE001 - a check must never crash the run
        ok, detail = False, f"{type(exc).__name__}: {exc}"
    print(f"{OK if ok else BAD} {label:<44} {detail}")
    return ok


def _db():
    from app.database.runner import run_select

    r = run_select("SELECT COUNT(*) AS n FROM tblPacket", max_rows=2)
    if not r["ok"]:
        return False, r["error"][:70]
    return r["rows"][0]["n"] > 0, f"{r['rows'][0]['n']:,} packets"


def _recipe(question, expect_recipe, expect_sections):
    def run():
        from app.agent import recipe_router as rr

        hit = rr.match(question)
        if not hit:
            return False, "did not route"
        if hit["recipe"] != expect_recipe:
            return False, f"routed to {hit['recipe']}"
        raw = rr.answer(hit)
        n = len(raw.get("data_sections") or [])
        if n < expect_sections:
            return False, f"only {n} sections"
        # cut_purity_change is scoped by KAPAN and carries no period; every
        # other recipe carries one. Report whichever scope it actually has.
        scope = (f"kapan {hit['kapan']}" if hit.get("kapan")
                 else f"{hit.get('from_date')}..{hit.get('to_date')}")
        return True, f"{hit['recipe']}, {n} sections, {scope}"
    return run


def _guards():
    from app.agent import query_rules as qr

    cases = [
        ("how many oval diamonds do we have in stock?",
         "SELECT COUNT(*) FROM tblPacket WHERE Shape = 'OV'"),
        ("how many packets are on hold",
         "SELECT COUNT(*) FROM tblPacket WHERE IsOnHold = 1"),
        # THE NUMBER THAT ACTUALLY REACHED THE CLIENT. "Has PLS, has no GIA
        # row" answered 12 where they count 2. The recipe no longer writes it;
        # this proves the FREE-SQL path rejects it too.
        ("polished GIA pending for mfg-1 department for july month",
         "SELECT COUNT(DISTINCT p.Packet_ID) FROM tblPlanMaster p "
         "WHERE p.RapVer='PLS' AND p.IsDamagePlan=0 AND p.IsApproved=1 "
         "AND NOT EXISTS (SELECT 1 FROM tblPlanMaster g "
         "WHERE g.Packet_ID=p.Packet_ID AND g.RapVer='GIA' AND g.IsApproved=1)"),
    ]
    missed = [q for q, sql in cases if not qr.violations(q, sql)]
    return not missed, ("wrong-source guards active" if not missed
                        else f"NOT blocking: {missed}")


def _no_fabrication():
    from app.agent import postprocess

    return (postprocess.asserts_a_figure("There are 369 active employees"),
            "ungrounded-figure guard active")


def main() -> int:
    print(f"GlowStar pre-flight - {date.today():%d %b %Y}")
    print("=" * 78)
    results = [
        _check("database reachable", _db),
        _check("report of a department",
               _recipe("report of department MFG - 1 for July 2026",
                       "department_report", 6)),
        _check("report asked in Gujlish",
               _recipe("MFG 1 nu report aapo July 2026 nu",
                       "department_report", 6)),
        _check("lab results, employee wise",
               _recipe("last month GIA results employee wise for fency department",
                       "lab_results", 3)),
        _check("polished but GIA pending",
               _recipe("polished GIA pending for mfg-1 department last month",
                       "pending_lab_results", 2)),
        # The one report the client checks packet-for-packet against their own
        # ERP. It takes a KAPAN and no period, so it also proves the router
        # still answers a question the date picker would otherwise intercept.
        _check("cut-purity change (kapan scoped)",
               _recipe("give me cut purity change report of NI26",
                       "cut_purity_change", 2)),
        _check("wrong-source guards", _guards),
        _check("anti-fabrication guard", _no_fabrication),
    ]
    print("=" * 78)
    if all(results):
        print("READY - the questions above answer from the database with no "
              "LLM call at all.")
        return 0
    print("NOT READY - fix the FAIL lines above before the demo.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
