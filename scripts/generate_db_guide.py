"""
generate_db_guide.py
--------------------
Generates DATABASE_GUIDE.md - a complete, human/AI-readable data dictionary
of the GlowStar/AasthaErp database: every table, its columns, row counts,
categories, relationships, and the business glossary.

Feed the output file to any AI to have it frame test questions.

Run from the project root:
    python -m scripts.generate_db_guide
"""

import os

from app.schema import extractor
from app.schema.glossary import TABLE_NOTES, TERMS, render_data_notes

# Categories (first matching keyword wins; order matters).
CATEGORIES = [
    ("Packets & Production", ["packet", "kapan", "final", "issue", "tops"]),
    ("Planning & Cutting", ["plan", "marker", "scope"]),
    ("Labour & Payroll", ["labour", "labor", "bonus", "incentive", "salary",
                            "wage", "pointrate", "credit", "debit", "rate"]),
    ("Employees & HR", ["emp", "employee", "attend", "shift", "leave",
                         "family", "education", "grade", "rating", "reference"]),
    ("Quality & Repair", ["repair", "junk", "quality", "report", "reject", "color"]),
    ("Jangad & Transfer", ["jangad", "transfer", "lot", "angadia"]),
    ("Parties & Business", ["party", "supplier", "company", "customer",
                             "dept", "department", "owner", "broker"]),
    ("Masters & Config", ["master", "criteria", "template", "rule", "type",
                           "setting", "config", "code", "machine"]),
]


def categorize(name: str) -> str:
    low = name.lower()
    for cat, kws in CATEGORIES:
        if any(k in low for k in kws):
            return cat
    return "Other"


def main():
    tables = extractor.get_tables()  # [{name, rows}] business tables, sorted by rows
    row_counts = {t["name"]: t["rows"] for t in tables}
    columns = extractor.get_columns()  # {table: [{name, type}]}
    fks = extractor.get_foreign_keys()

    # Group tables by category.
    by_cat: dict[str, list[str]] = {}
    for t in tables:
        by_cat.setdefault(categorize(t["name"]), []).append(t["name"])

    lines: list[str] = []
    add = lines.append

    add("# GlowStar / AasthaErp - Database Guide\n")
    add("Complete data dictionary of the diamond-manufacturing ERP database. "
        "Use this to understand the data and frame questions.\n")
    add(f"- Total business tables: **{len(tables)}**")
    add(f"- Total columns: **{sum(len(c) for c in columns.values())}**")
    add(f"- Foreign-key links: **{len(fks)}**\n")

    # --- Glossary ---
    add("## Business glossary (diamond-industry terms)\n")
    for term, info in TERMS.items():
        add(f"- **{term}**: {info['definition']}")
    add("")

    # --- Data notes + value codes ---
    add("## " + render_data_notes().replace("=== ", "").replace(" ===", "\n").replace("\n- ", "\n- "))
    add("")

    # --- Common join columns ---
    add("## Common ID / join columns (how tables connect)\n")
    add("- **Kapan_ID / KapanName**: the rough-diamond lot. Most production rows carry it.")
    add("- **Packet_ID / PacketNo**: a packet within a Kapan.")
    add("- **Emp_ID / EmpId / EmpName**: the worker. Emp_ID = tblEmployee.ID.")
    add("- **Department_ID / DepartMent_ID**: the process department/stage.")
    add("- To get an employee's city: join tblEmployee.ID = tblEmpDetail.Emp_ID, filter tblEmpDetail.City.")
    add("")

    # --- Tables by category (summary) ---
    add("## Tables by category (with row counts)\n")
    for cat, _ in CATEGORIES + [("Other", [])]:
        names = sorted(by_cat.get(cat, []), key=lambda n: -row_counts.get(n, 0))
        if not names:
            continue
        add(f"### {cat} ({len(names)} tables)\n")
        for n in names:
            note = TABLE_NOTES.get(n, {}).get("note", "")
            note = f" - {note}" if note else ""
            add(f"- `{n}` ({row_counts.get(n, 0):,} rows){note}")
        add("")

    # --- Full data dictionary (all tables + columns) ---
    add("## Full data dictionary (all tables and columns)\n")
    for cat, _ in CATEGORIES + [("Other", [])]:
        names = sorted(by_cat.get(cat, []), key=lambda n: -row_counts.get(n, 0))
        if not names:
            continue
        add(f"### {cat}\n")
        for n in names:
            cols = columns.get(n, [])
            col_text = ", ".join(f"{c['name']} ({c['type']})" for c in cols)
            add(f"**{n}** ({row_counts.get(n, 0):,} rows)")
            note = TABLE_NOTES.get(n, {}).get("note", "")
            if note:
                add(f"_{note}_")
            add(f"Columns: {col_text}\n")

    # --- Foreign keys ---
    add("## Declared foreign-key relationships\n")
    if fks:
        for fk in fks:
            add(f"- {fk['parent_table']}.{fk['parent_column']} -> "
                f"{fk['ref_table']}.{fk['ref_column']}")
    else:
        add("(None declared - tables link by shared ID columns like Kapan_ID, "
            "Packet_ID, Emp_ID.)")
    add("")

    # --- Tips for framing questions ---
    add("## Tips for framing questions\n")
    add("- Counts: 'How many packets / employees / jangad packets ...?'")
    add("- Sums: 'Total labour amount / total weight of junk / total final-packet value ...'")
    add("- Filters: by City, Shape, Process, IsApproved, IsReceived, date ranges.")
    add("- Group-by: 'packets by shape', 'labour amount by employee', 'attendance by month'.")
    add("- Joins: 'employees in Surat', 'labour result per employee with their name'.")
    add("- Note: employee names are split into FirstName / MiddleName / LastName.")

    out_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "DATABASE_GUIDE.md",
    )
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Wrote {out_path}")
    print(f"Tables: {len(tables)} | Columns: {sum(len(c) for c in columns.values())} "
          f"| FKs: {len(fks)} | Lines: {len(lines)}")


if __name__ == "__main__":
    main()
