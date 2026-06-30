"""
glossary.py
-----------
Business glossary for the Aastha diamond-manufacturing ERP.

WHY THIS EXISTS:
The AI agent reads table/column names, but those don't explain the
*business meaning*. This glossary teaches the agent diamond-industry
terms (Packet, Jangad, Point, etc.) and what each key table holds, so
it can turn a plain question into the correct SQL.

STATUS OF DEFINITIONS:
- "confirmed": grounded in industry research (safe to rely on).
- "verify":    inferred from table names - CONFIRM the column-level
               details with the client, then change to "confirmed".

These are easy to edit - just update the text as the client confirms.
"""

# ---------------------------------------------------------------------------
# 1. INDUSTRY TERMS  (term -> {definition, status})
#    Grounded in diamond-manufacturing research.
# ---------------------------------------------------------------------------
TERMS = {
    "Carat": {
        "definition": "Diamond weight unit. 1 carat = 200 milligrams.",
        "status": "confirmed",
    },
    "Point": {
        "definition": (
            "Fine weight unit. 1 carat = 100 points. A 0.25ct stone is a "
            "'25-pointer'. Labour is often paid per point of weight processed."
        ),
        "status": "confirmed",
    },
    "Kapan": {
        "definition": (
            "A lot/parcel of ROUGH diamonds bought and processed together as "
            "one batch. Most records are tagged with a Kapan_ID/KapanName. "
            "A Kapan is split into individual Packets for processing."
        ),
        "status": "confirmed",
    },
    "Lot": {
        "definition": (
            "In this business a 'lot' means a KAPAN (a parcel of rough "
            "diamonds). So 'how many lots' = how many kapans (count distinct "
            "Kapan_ID / use tblKapan). It does NOT mean junk LotNo."
        ),
        "status": "confirmed",
    },
    "Packet": {
        "definition": (
            "A parcel/lot of diamonds tracked as a single unit as it moves "
            "through the factory (planning -> cutting -> polishing -> final). "
            "Packets belong to a Kapan."
        ),
        "status": "confirmed",
    },
    "SubPcs": {
        "definition": "Sub-pieces - a packet split into smaller pieces.",
        "status": "verify",
    },
    "Tantion / Tansion": {
        "definition": (
            "Tension grade of the stone (a quality/clarity attribute used in "
            "rate calculations). Spelled both 'Tantion' and 'Tansion' in the DB."
        ),
        "status": "verify",
    },
    "Jangad": {
        "definition": (
            "An entrustment note - diamonds sent out on approval / "
            "sale-or-return basis, on trust. Tracks goods given out but not "
            "yet sold or returned (common in the Indian diamond trade)."
        ),
        "status": "confirmed",
    },
    "Plan / Planning": {
        "definition": (
            "Mapping how a rough stone will be cut to maximise value. The "
            "first manufacturing stage."
        ),
        "status": "confirmed",
    },
    "Labour Rate": {
        "definition": (
            "Piece-rate paid to a worker for processing a diamond, usually "
            "per point of weight or per process stage."
        ),
        "status": "confirmed",
    },
    "Point Rate Labour": {
        "definition": "The labour rate paid specifically per point of weight.",
        "status": "confirmed",
    },
    "Labour Result": {
        "definition": (
            "The output of a worker's processing - pieces completed and "
            "resulting yield."
        ),
        "status": "verify",
    },
    "Incentive": {
        "definition": "Extra pay earned for meeting yield/quality/output targets.",
        "status": "confirmed",
    },
    "Bonus": {
        "definition": "Additional reward pay, often rate-based.",
        "status": "confirmed",
    },
    "Repair": {
        "definition": "Re-polishing or fixing a stone that did not pass quality.",
        "status": "confirmed",
    },
    "Junk": {
        "definition": "Rejected or scrap diamond material.",
        "status": "verify",
    },
    "Time Attendance": {
        "definition": "Worker attendance records (in/out, present days).",
        "status": "confirmed",
    },
    "Report Rate": {
        "definition": "Rates used for reporting / valuation purposes.",
        "status": "verify",
    },
    "Fluorescence": {
        "definition": (
            "How much a diamond glows under UV. STORED IN A MISSPELLED COLUMN: "
            "'Florecent' (tblPacket, tblPacketHistory, tblPlanMaster, etc.) or "
            "'Florocent' (tblFinalPacket, tblLabourResult, rate tables). There "
            "is NO column spelled 'Fluorescent'."
        ),
        "status": "confirmed",
    },
}


# ---------------------------------------------------------------------------
# VALUE CODES - what the short coded column values mean (grounded in the real
# data). Included in EVERY question's context: small but high-impact accuracy.
# ---------------------------------------------------------------------------
VALUE_CODES = {
    "Shape (column 'Shape')":
        "RD=Round, EM=Emerald, HR=Heart, PS=Pear, OV=Oval, PR=Princess, "
        "MQ=Marquise, CU=Cushion, RAD=Radiant, BG=Baguette, TRI=Trillion, "
        "SQEM=Square Emerald; 'F.xx' = Fancy and 'S.xx' = special variants. "
        "Always filter with the CODE, not the English word.",
    "Color (column 'Color')":
        "Diamond colour grade: D, E, F, G, H, I, J, K, L, M, N "
        "(D = colourless/best, N = most tinted).",
    "Clarity (stored in the 'Purity' column!)":
        "The clarity grade is in a column NAMED 'Purity'. Values best->worst: "
        "FL, IF, VVS1, VVS2, VS1, VS2, SI1, SI2, I1, I2, I3.",
    "Cut / Polish / Symmetry":
        "EX=Excellent, VG=Very Good, GD=Good, FR=Fair.",
    "Fluorescence (column 'Florecent' or 'Florocent')":
        "NON=None, FNT=Faint, MED=Medium, STG=Strong, VST=Very Strong. "
        "A 'fluorescent stone' = value is NOT 'NON'. No column is spelled "
        "'Fluorescent'.",
    "Process (column 'Process')":
        "The manufacturing stage, e.g. IN Stock, Weight Scale, Marker, Laser, "
        "Galaxy, Blocking, Vision 360, Polish Checker, MFG-1, MFG-2, OUT Stock.",
}

# General data-quality advice (misspellings, misleading names).
DATA_NOTES = [
    "Some columns are misspelled (e.g. fluorescence is 'Florecent'/'Florocent'). "
    "If an expected column name isn't found, call get_table_columns to find the "
    "real/misspelled variant before concluding the data is missing.",
    "Column names can be misleading: the 'Purity' column actually holds the "
    "CLARITY grade.",
    "When filtering a coded column, use the CODES below (e.g. Color='D', "
    "Florecent<>'NON'), not the full English word.",
    "KNOWN-EMPTY TABLES (verified 0 rows): tblPacketSell, tblUserMaster, "
    "tblStockInventory, tblGradingMaster, tblInclusionInventory, tblRejection. "
    "If a question maps to one of these, the data is NOT recorded in this system - "
    "say so plainly. Do NOT silently substitute a different table's numbers, and "
    "NEVER invent rows.",
    "SALES / SOLD / REVENUE are NOT tracked: the only sales table (tblPacketSell) "
    "is empty. If asked how many diamonds/packets were 'sold' or about sales/"
    "revenue, state that sales are not recorded here. CRITICAL: a jangad return "
    "(tblJangadPackets.IsReceived = 1) is goods coming BACK from a sub-contractor, "
    "NOT a sale - never report returned-jangad counts as 'sold'.",
    "KAPAN COUNT: count kapans from the kapan master table tblKapan (847 rows = "
    "one row per kapan). Do NOT use COUNT(DISTINCT Kapan_ID) on tblPacket (that "
    "misses kapans with no packets), and avoid the decoys tblKapan_BKP (backup) "
    "and tblKapanValue (valuation rows, not kapans).",
    "TENSION / TANSION GRADE: the authoritative tension grade is column 'Tantion' "
    "on tblPacketCode (note that spelling). To count packets by tension grade use "
    "tblPacketCode WHERE Tantion = N. (tblPacket also has a 'Tension' column, but "
    "tblPacketCode.Tantion is the canonical packet-code grade - be consistent.)",
]

# Tricky joins / relationships - how to apply filters that need another table.
JOIN_HINTS = [
    "JANGAD by stone attributes: tblJangadPackets only has PacketId, Carat, "
    "Amount, IsReceived. To filter jangad packets by Shape, Color, Florecent, "
    "Tension or Cut, JOIN tblJangadPackets.PacketId = tblPacket.ID (those "
    "attribute columns live on tblPacket).",
    "PER-POINT LABOUR: tblPointRateLabour holds per-point labour (DepartmentName, "
    "ReportRate = rate per point, Packet_ID, Shape, Tansion) but NOT fluorescence. "
    "For non/fluorescent filtering, JOIN Packet_ID = tblPacket.ID (Florecent).",
    "MANAGERS-ONLY final packets: tblFinalPacket.UserID is who created it. For "
    "'managers only', JOIN UserID = tblEmployee.ID WHERE IsManager = 1.",
    "PRESENT DAYS: tblTimeAttendance has one row per punch (EmpId, Time). A "
    "'present day' = a distinct date CAST(Time AS DATE) an employee has a punch "
    "(many punches same day = one present day).",
    "DEPARTMENTS: there is NO department literally named 'Cutting'. Cutting-stage "
    "departments include Marker, Blocking, Brooter, Dhar, Saw, and MFG stages. If "
    "a question says 'cutting department' with no exact match, ask which one.",
]


# Gujarati / Hinglish phrases employees use (this is a Surat diamond firm).
# These are MEANING words, not data values - translate intent, don't match them
# as names. Critical: "sauthi vadhare" means "the most", NOT a person/kapan name.
GUJLISH_TERMS = {
    "sauthi vadhare / sauthi vadhu": "the MOST / highest (use MAX or ORDER BY ... DESC). NOT a name.",
    "sauthi ochu / sauthi ocha": "the LEAST / lowest (use MIN or ORDER BY ... ASC).",
    "ketla / ketli / ketlo": "how many / how much (a COUNT or SUM question).",
    "karigar": "worker / employee.",
    "maal": "goods / stock / material.",
    "atyare": "right now / currently.",
    "aakha mahina ma": "in the whole month.",
    "kaya / kya": "which.",
    "che": "is / are.",
    "na / ni / no": "of (possessive).",
    "thayu / thaya / thai": "happened / done / made.",
    "malyu": "got / received.",
    "pending": "still out / not returned (for jangad, IsReceived = 0).",
}


def render_data_notes() -> str:
    """Return data notes + value codes + gujlish terms as a text block."""
    lines = ["=== DATA NOTES (column spellings & how to filter) ==="]
    for note in DATA_NOTES:
        lines.append(f"- {note}")
    lines.append("\n=== VALUE CODES (what coded column values mean) ===")
    for name, meaning in VALUE_CODES.items():
        lines.append(f"- {name}: {meaning}")
    lines.append("\n=== GUJARATI/HINGLISH PHRASES (translate intent, don't match as names) ===")
    for phrase, meaning in GUJLISH_TERMS.items():
        lines.append(f"- {phrase}: {meaning}")
    lines.append("\n=== TRICKY JOINS (how to apply filters that need another table) ===")
    for hint in JOIN_HINTS:
        lines.append(f"- {hint}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 2. TABLE NOTES  (table name -> {note, status})
#    Business meaning of the key tables. Inferred from names + research;
#    confirm column-level specifics with the client.
# ---------------------------------------------------------------------------
TABLE_NOTES = {
    "tblPacket": {
        "note": "Master list of packets (the central packet record other tables link to).",
        "status": "verify",
    },
    "tblPacketHistory": {
        "note": "Movement/history of each packet as it passes through process stages.",
        "status": "verify",
    },
    "tblPacketIssue": {
        "note": "Records of packets issued out to workers/processes.",
        "status": "verify",
    },
    "tblPacketDetail": {
        "note": "Detailed line items for a packet.",
        "status": "verify",
    },
    "tblPacketPoint": {
        "note": "Weight (in points) of packets.",
        "status": "verify",
    },
    "tblFinalPacket": {
        "note": "Finished/completed packets.",
        "status": "verify",
    },
    "tblIssuedPacketDetail": {
        "note": "Detail lines for issued packets.",
        "status": "verify",
    },
    "tblJangadPackets": {
        "note": (
            "Packets sent out on jangad (approval / sale-or-return). "
            "IsReceived=0 means still OUT ('currently on jangad'); "
            "IsReceived=1 means returned/received. To count packets CURRENTLY "
            "on jangad, filter WHERE IsReceived = 0."
        ),
        "status": "verify",
    },
    "tblPlanMaster": {
        "note": "The cutting plan for each rough stone (planning stage).",
        "status": "verify",
    },
    "tblPlanMasterOptional": {
        "note": "Optional/alternative cutting plans for a stone.",
        "status": "verify",
    },
    "tblLabourRate": {
        "note": "Piece-rates paid to labour per process/stage.",
        "status": "verify",
    },
    "tblPointRateLabour": {
        "note": "Labour rate paid per point of weight.",
        "status": "verify",
    },
    "tblLabourResult": {
        "note": "Output/results of labour processing per worker.",
        "status": "verify",
    },
    "tblIncentiveAmount": {
        "note": "Incentive payment amounts earned by workers.",
        "status": "verify",
    },
    "tblBonusRate": {
        "note": "Bonus rate definitions used to calculate bonus pay.",
        "status": "verify",
    },
    "tblReportRate": {
        "note": "Rates used for reporting/valuation.",
        "status": "verify",
    },
    "tblRepairLog": {
        "note": "Records of stones sent for repair/re-polish.",
        "status": "verify",
    },
    "tblRepairLogNew": {
        "note": "Newer repair/re-polish log (possibly replaces tblRepairLog).",
        "status": "verify",
    },
    "tblTimeAttendance": {
        "note": "Worker attendance records.",
        "status": "verify",
    },
    "tblJunk": {
        "note": "Rejected/scrap diamond material.",
        "status": "verify",
    },
    "tblEmployee": {
        "note": (
            "Master employee records: FirstName, MiddleName, LastName, Code, "
            "department, join date, active status. The employee ID is its ID "
            "column (referenced elsewhere as Emp_ID / EmpId)."
        ),
        "status": "verify",
    },
    "tblEmpDetail": {
        "note": (
            "Employee personal details: address (City, State, Country, "
            "Address1/2), phone, mobile, email. Links to tblEmployee via "
            "Emp_ID. To find employees by city, join tblEmployee.ID = "
            "tblEmpDetail.Emp_ID and filter on City."
        ),
        "status": "verify",
    },
}


# ---------------------------------------------------------------------------
# 3. RENDERING  - turn the glossary into text the LLM can read.
#    The Phase 2 context builder will append this to the schema context.
# ---------------------------------------------------------------------------
def render_glossary_text() -> str:
    """Return the full glossary as a compact, LLM-friendly text block."""
    lines = ["=== BUSINESS GLOSSARY (diamond manufacturing) ==="]

    lines.append("\n-- Industry terms --")
    for term, info in TERMS.items():
        lines.append(f"- {term}: {info['definition']}")

    lines.append("\n-- Key tables (business meaning) --")
    for table, info in TABLE_NOTES.items():
        lines.append(f"- {table}: {info['note']}")

    return "\n".join(lines)


def table_note(table_name: str) -> str:
    """Return the business note for a table, or '' if we don't have one."""
    info = TABLE_NOTES.get(table_name)
    return info["note"] if info else ""


# Quick manual check: `python -m app.schema.glossary`
if __name__ == "__main__":
    print(render_glossary_text())
