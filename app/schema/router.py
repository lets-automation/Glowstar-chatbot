"""
router.py
---------
Picks the FEW tables relevant to a question, so the agent's prompt only
contains those tables' columns instead of all 20. This cuts tokens-per-
question dramatically (the biggest lever for staying inside the LLM budget).

It is pure Python keyword matching - it uses ZERO LLM tokens. The agent
still sees ALL table names in the glossary directory, and can call the
get_table_columns tool if routing misses a table, so accuracy is preserved.
"""

import re
from functools import lru_cache

from app.schema import extractor
from app.schema.context import KEY_TABLES
from app.schema.glossary import TABLE_NOTES

# Common words to ignore when reading a question.
_STOP = {
    "how", "many", "are", "is", "the", "a", "an", "of", "on", "in", "for", "to",
    "what", "total", "count", "list", "show", "give", "me", "number", "all",
    "much", "there", "and", "by", "with", "which", "do", "does", "records",
    "record", "data", "have", "has", "was", "were", "this", "that", "get",
    # Pronouns carry no routing signal but appear in many questions ("how many
    # do WE have", "who are OUR clients") and would spuriously match any note
    # containing them - so ignore them.
    "we", "our", "us", "my", "your",
}

# Map a few synonyms to the word used in the schema/glossary.
# Includes the DB's misspellings (e.g. fluorescence is column 'Florecent').
_SYN = {
    "labor": "labour", "emp": "employee", "worker": "employee",
    "staff": "employee", "pkt": "packet", "stone": "packet",
    # Gujlish role word for worker/employee (Surat diamond floor) — without this,
    # "karigar" questions fell through to the default table list (Layer-2 Q51).
    "karigar": "employee", "kaarigar": "employee",
    "wt": "weight", "qty": "quantity",
    # All fluorescence spellings (question + the DB's two misspellings) map to
    # one token so they match each other during routing.
    "fluorescent": "fluor", "fluorescence": "fluor",
    "florecent": "fluor", "florocent": "fluor", "floro": "fluor",
    "mflorecent": "fluor",
    "colour": "color",
}

# Fallback if a question matches nothing recognisable.
_DEFAULT = [
    "tblPacket", "tblPacketHistory", "tblFinalPacket",
    "tblJangadPackets", "tblTimeAttendance", "tblLabourResult",
]

# Main transactional tables (where real stones/records live). Preferred over
# rate/config lookup tables (tblBonusRate, tblReportRate, ...) on score ties.
_PRIMARY = {
    "tblPacketHistory", "tblFinalPacket", "tblPacket", "tblPacketIssue",
    "tblLabourResult", "tblPlanMaster", "tblPlanReport", "tblJangadPackets",
    "tblPacketPoint", "tblEmployee", "tblEmpDetail", "tblKapan",
}

# One-row-per-entity MASTER tables. On a score tie they should beat their own
# derived/history siblings (e.g. tblPacket over tblPacketHistory/tblFinalPacket,
# tblKapan over packet tables) so a plain "packets/kapans …" question always
# includes the master and doesn't get it bumped out of the top-k (Layer-2 Q33).
_MASTER = {"tblPacket", "tblKapan", "tblEmployee"}


def _norm(word: str) -> str:
    """Lowercase, map synonyms, and strip a trailing plural 's'."""
    word = _SYN.get(word.lower(), word.lower())
    if word.endswith("s") and len(word) > 3:
        word = word[:-1]
    return word


def _tokenize(text: str) -> set[str]:
    """Turn text into a set of meaningful, normalised words."""
    return {
        _norm(w)
        for w in re.findall(r"[a-zA-Z]+", text)
        if w.lower() not in _STOP
    }


def _split_name(name: str) -> list[str]:
    """tblJangadPackets -> ['jangad', 'packet']  (strip 'tbl', split CamelCase)."""
    if name.lower().startswith("tbl"):
        name = name[3:]
    parts = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)", name)
    return [_norm(p) for p in parts if p]


@lru_cache(maxsize=1)
def _key_columns() -> dict:
    """Columns of the key tables (cached - read from the DB only once)."""
    return extractor.get_columns(KEY_TABLES)


def _table_keywords(table: str) -> set[str]:
    """Keywords from a table's name + its glossary meaning."""
    kw = set(_split_name(table))
    note = TABLE_NOTES.get(table, {}).get("note", "")
    kw |= _tokenize(note)
    return kw


def _column_keywords(cols: list[dict]) -> set[str]:
    kw: set[str] = set()
    for c in cols:
        kw |= set(_split_name(c["name"]))
    return kw


def select_tables(question: str, k: int = 4) -> list[str]:
    """
    Return up to k key tables most relevant to the question.
    Table-name/meaning matches count more than column matches.
    """
    q_words = _tokenize(question)
    cols_by_table = _key_columns()

    scores: dict[str, int] = {}
    for table, cols in cols_by_table.items():
        name_hits = len(q_words & _table_keywords(table))
        col_hits = len(q_words & _column_keywords(cols))
        score = 3 * name_hits + col_hits
        if score:
            # Prefer main transactional tables over rate/config lookup tables.
            if table in _PRIMARY:
                score += 2
            # Break ties toward the one-row-per-entity master (see _MASTER).
            if table in _MASTER:
                score += 1
            scores[table] = score

    ranked = sorted(scores, key=lambda t: scores[t], reverse=True)[:k]
    return ranked or _DEFAULT
