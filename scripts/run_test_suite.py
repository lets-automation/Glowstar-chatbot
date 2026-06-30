"""
run_test_suite.py
-----------------
Runs the 60 test questions from question_claude.md through the chatbot and
saves each result to logs/test_results.jsonl incrementally (so progress
survives a rate-limit / interruption).

Run from the project root:
    python -m scripts.run_test_suite
"""

import json
import re
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.agent.agent import ask


def parse_questions(path: str):
    qs = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"^(\d+)\.\s+(.*)", line.strip())
            if m:
                qs.append((int(m.group(1)), m.group(2).strip()))
    return qs


def main():
    # Optional range: python -m scripts.run_test_suite [start] [end] [outfile]
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    end = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    out_file = sys.argv[3] if len(sys.argv) > 3 else "logs/test_results.jsonl"

    questions = [
        (n, q) for (n, q) in parse_questions("question_claude.md") if start <= n <= end
    ]
    print(f"Running questions {start}-{end} ({len(questions)} total)...")

    with open(out_file, "w", encoding="utf-8") as out:
        for num, q in questions:
            try:
                r = ask(q)
                answer = r["answer"]
                sql = r["sql_used"]
            except Exception as exc:
                answer = f"ERROR: {exc}"
                sql = []

            rec = {"q": num, "question": q, "answer": answer, "sql": sql}
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
            print(f"Q{num}: {answer[:80]}")
            time.sleep(2)  # gentle pacing to avoid per-minute limits

    print("DONE")


if __name__ == "__main__":
    main()
