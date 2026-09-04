"""
coverage.py
-----------
THE METRIC THAT DECIDES THIS PRODUCT.

What share of the questions the client actually asks is answered by a RECIPE -
code that cannot get it wrong - rather than by the model writing SQL freely?

Every wrong answer this project has shipped came from the free-SQL slice.
Shrinking it is the whole job. Not model size, not test count.

    python -m scripts.coverage                  # reads the container's log
    python -m scripts.coverage questions.txt    # or a file, one per line

Pull the live corpus first if you want today's picture:

    docker exec glowstar_chatbot-backend-1 sh -c       "grep -h '| INFO | Q: ' /app/logs/agent.log | sed 's/.*| Q: //'"       | sort -u > questions.txt
"""
import collections
import io
import sys

# Gujlish questions contain characters the Windows console codepage
# cannot encode, and an unhandled UnicodeEncodeError took the whole
# report down mid-print. Never let formatting kill a measurement.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from app.agent import recipe_router as rr, date_gate, lab_gate, access_guard

if len(sys.argv) > 1:
    src = io.open(sys.argv[1], encoding="utf-8", errors="replace").read()
else:
    import subprocess
    src = subprocess.run(
        ["docker", "exec", "glowstar_chatbot-backend-1", "sh", "-c",
         "grep -h '| INFO | Q: ' /app/logs/agent.log | sed 's/.*| Q: //'"],
        capture_output=True, text=True, errors="replace").stdout
    if not src.strip():
        sys.exit("no questions found - pass a file, or start the container")
qs = [q.strip().strip('"') for q in src.splitlines()]
qs = [q for q in qs if len(q) > 6]

buckets = collections.Counter()
recipes = collections.Counter()
free = []
for q in qs:
    m = rr.match(q)
    if m:
        name = m.get("recipe")
        name = m.get("fact") if name == "quick_fact" else name
        buckets["recipe"] += 1
        recipes[name] += 1
    elif date_gate.needs_date(q, []) or lab_gate.needs_lab(q, []):
        buckets["asks a clarifying question first"] += 1
    elif access_guard.is_pay_question(q):
        buckets["refused (pay guard)"] += 1
    else:
        buckets["free SQL - model writes it"] += 1
        free.append(q)

total = len(qs)
print("REAL LOGGED QUESTIONS: %d unique\n" % total)
print("%-38s%6s  %s" % ("OUTCOME", "N", "%"))
print("-" * 56)
for k, n in buckets.most_common():
    print("%-38s%6d  %5.1f%%" % (k, n, 100.0 * n / total))
print()
print("Deterministic recipes hit:")
for k, n in recipes.most_common(14):
    print("   %-30s%4d" % (k, n))
print()
print("Still free SQL (%d) - a sample:" % len(free))
for q in free[:18]:
    print("   -", q[:88])
