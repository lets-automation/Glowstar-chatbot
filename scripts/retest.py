"""
retest.py
---------
Re-run specific question numbers (to confirm fixes).
    python -m scripts.retest 15,28,44,45,51,54,57,58,59 logs/retest.jsonl
"""

import json
import re
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.agent.agent import ask


def parse_questions(path):
    qs = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"^(\d+)\.\s+(.*)", line.strip())
            if m:
                qs[int(m.group(1))] = m.group(2).strip()
    return qs


def main():
    nums = [int(x) for x in sys.argv[1].split(",")]
    out_file = sys.argv[2] if len(sys.argv) > 2 else "logs/retest.jsonl"
    qs = parse_questions("question_claude.md")

    with open(out_file, "w", encoding="utf-8") as out:
        for n in nums:
            q = qs[n]
            try:
                r = ask(q)
                ans, sql = r["answer"], r["sql_used"]
            except Exception as exc:
                ans, sql = f"ERROR: {exc}", []
            out.write(json.dumps({"q": n, "question": q, "answer": ans, "sql": sql}, ensure_ascii=False) + "\n")
            out.flush()
            print(f"Q{n}: {ans[:80]}")
            time.sleep(2)
    print("DONE")


if __name__ == "__main__":
    main()
