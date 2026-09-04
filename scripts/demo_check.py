"""END-TO-END DEMO CHECK.

Everything this session was verified at the CODE level. This exercises the path
the client actually touches - HTTP -> nginx -> backend -> gates -> router ->
recipe -> rendered answer - and diffs each answer against a direct query.

It is the only check that would have caught the stale container, which is the
failure that has actually reached the client.

    python -m scripts.demo_check            # against localhost:8080
"""
import json
import re
import sys
import urllib.error
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080/api"

from app.database.connection import get_engine   # noqa: E402
from sqlalchemy import text                      # noqa: E402


def truth(sql):
    with get_engine().connect() as c:
        return c.execute(text(sql)).fetchone()[0]


def ask(question, timeout=180):
    body = json.dumps({"question": question}).encode()
    req = urllib.request.Request(
        BASE + "/chat", data=body,
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace")), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.read()[:200].decode('utf-8','replace')}"
    except Exception as e:                                    # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def nums(s):
    """Every number in the answer, commas stripped."""
    return {n.replace(",", "") for n in re.findall(r"[\d,]*\d", s or "")}


# (question, a SQL that gives the number the answer MUST contain, or None)
CASES = [
    ("how many kapans do we have?",
     "SELECT COUNT(*) FROM tblKapan"),
    ("how many packets are on jangad?",
     "SELECT COUNT(*) FROM tblJangadPackets WHERE ISNULL(IsReceived,0)=0"),
    ("how many stones are out on memo right now?",
     "SELECT COUNT(*) FROM tblPacket WHERE IsOnMemo=1"),
    ("atyare ketla diamond hold par che?",
     "SELECT COUNT(p.ID) FROM tblPacket p JOIN tblKapan k ON k.ID=p.Kapan_ID "
     "WHERE k.IsOnHold=1"),
    ("how many employees do we have?",
     "SELECT COUNT(*) FROM tblEmployee WHERE IsActive=1"),
    ("give me polished GIA pending for mfg-1 department of July 2026", None),
    ("For kapan NS26, show packets where the MFG grade differs from the GIA "
     "grade on cut or clarity", None),
    ("For kapan NS26, list the packets that have an approved CLV plan but no "
     "approved PLS plan yet, with clarity IF to VS2 and planned weight "
     "between 0.50 and 1.00 carat", None),
    ("from kapan QA26 give me packets planned by Marker-2 with purity FL to "
     "VVS2 and size 0.3 to 0.8", None),
    ("Give me the full packet report for kapan NS26",
     "SELECT COUNT(*) FROM tblPacket p JOIN tblKapan k ON k.ID=p.Kapan_ID "
     "WHERE k.KapanName='NS26'"),
    ("give me the report of employee M4117 for June 2026", None),
    ("give me daily production from 1 Jun 2026 to 30 Jun 2026", None),
    ("How many packets were made in June 2026?",
     "SELECT COUNT(*) FROM tblFinalPacket "
     "WHERE CreateDate>='2026-06-01' AND CreateDate<'2026-07-01'"),
    ("provide GIA results for May 2026", None),
    ("give me report of department MFG - 1 for July 2026", None),
]

print("END-TO-END DEMO CHECK  ->  " + BASE)
print("=" * 96)
print(f"{'#':<3}{'STATUS':<9}{'ms':>7}  {'rows':>5}  QUESTION")
print("-" * 96)

results = []
for i, (q, sql) in enumerate(CASES, 1):
    out, err = ask(q)
    if err:
        results.append(("TRANSPORT", q, err))
        print(f"{i:<3}{'FAIL':<9}{'-':>7}  {'-':>5}  {q[:60]}")
        print(f"      {err[:110]}")
        continue

    ans = out.get("answer") or ""
    rows = out.get("rows_returned", 0)
    ms = int(out.get("elapsed_ms") or 0)
    sqls = out.get("sql_used") or []
    via = "recipe" if any(str(s).lstrip().startswith("--") for s in sqls) else "model"

    status, note = "OK", ""
    if not ans.strip():
        status, note = "EMPTY", "no answer text"
    elif ans.lower().startswith(("sorry", "i don't have", "i am unable",
                                 "i'm sorry", "error")):
        status, note = "REFUSED", ans[:100]
    elif sql is not None:
        want = str(truth(sql))
        if want not in nums(ans):
            status = "MISMATCH"
            note = f"expected {want} in the answer"
    results.append((status, q, note))
    print(f"{i:<3}{status:<9}{ms:>7}  {rows:>5}  [{via}] {q[:52]}")
    if note:
        print(f"      {note[:110]}")

print("-" * 96)
bad = [r for r in results if r[0] != "OK"]
print(f"{len(results) - len(bad)} of {len(results)} OK")
for st, q, note in bad:
    print(f"   {st:<10}{q[:70]}")
sys.exit(1 if bad else 0)
