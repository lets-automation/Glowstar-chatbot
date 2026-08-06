"""
router.py
---------
Picks the FEW tables relevant to a question, so the agent's prompt only
contains those tables' columns instead of every table in the database. This
cuts tokens-per-question dramatically (the biggest lever for staying inside
the LLM budget).

It is pure Python keyword matching - it uses ZERO LLM tokens.

WHY THE CANDIDATE SET IS NOW EVERY TABLE
----------------------------------------
This used to score ONLY the ~29 tables in context.KEY_TABLES, out of the ~239
business tables in AasthaErp. That was the single biggest cause of thin and
wrong answers: an audit cross-referencing every table the RULES and glossary
tell the model to use found 84 such tables, of which 55 could NEVER be surfaced
by this router. The prompt named them; the schema block could not show them.

Concretely, the rules instructed the model to use tblPctChecker for "employee-
wise" packet results, tblRepairCommentVision for the quality section of an
employee report, tblPacketSell for sales, tblLeaveReport for workforce presence
and tblPacketParameters for stone proportions - and not one of them was a
routing candidate. The model's only escape was find_tables + get_table_columns,
which costs 2-3 of its 8 tool rounds and which the same rules discourage
("keep tool calls LOW").

So the candidate set is now every non-trap business table. KEY_TABLES is kept,
but demoted from "the only tables that exist" to "a curated relevance boost" -
that hand-picked list is real signal about what people actually ask, it just
should never have been a hard gate.

Widening the net means the SCORING has to carry more weight, since ~239
candidates offer far more chances to match noise than 29 did. Hence the
weak-token filter, the column-hit cap, the size tier and the relative floor
below. See select_tables().
"""

import re
from functools import lru_cache

from app.config import settings
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
    # The sales tables are spelled SELL (tblPacketSell, SellDollar, SellDate),
    # but nobody asks "how much did we sell-s" - they say "sales". Without this
    # the sales table was unreachable even after the candidate set widened, and
    # the rules explicitly require naming it ("sales ARE structurally supported
    # via tblPacketSell, that table is just empty").
    "sale": "sell", "selling": "sell", "sold": "sell", "revenue": "sell",
    # The trade says clarity; this schema says purity (see the RULES: "Purity
    # (clarity)").
    "clarity": "purity",
    "dept": "department", "depart": "department",
    # Verb forms of the PROCESS words. _norm only strips a plural "s", so
    # "polished" never matched the column PolishEmpId (-> token "polish") and the
    # maker/polisher attribution table stayed unreachable for "who polished
    # packet X" - the exact question its own glossary note is written for.
    # Listed explicitly rather than stemming generally: a blunt -ed/-ing stripper
    # would also fold unrelated words together.
    "polished": "polish", "polishing": "polish", "polisher": "polish",
    "checked": "check", "checking": "check",
    "planned": "plan", "planning": "plan",
    "issued": "issue", "issuing": "issue",
    "damaged": "damage",
    "received": "recive", "receive": "recive",   # DB spells it ReciveTime
    "manufactured": "mfg", "manufacturer": "mfg", "manufacturing": "mfg",
}

# Fallback if a question matches nothing recognisable. This is what an
# unrecognised question is answered from, so every table here must be LIVE.
#
# It used to list tblTimeAttendance and tblLabourResult - both DEAD, per the
# glossary's own measured notes:
#   tblLabourResult   last row 2023-04-12; the live labour table is
#                     tblPointRateLabour. The note is blunt about why this keeps
#                     happening: "the dead one has the more obvious name, so
#                     name-based table choice is wrong every time" - which is
#                     exactly what a keyword router does unless told otherwise.
#   tblTimeAttendance last punch 2025-04-05, and its EmpId is 100% NULL across
#                     all 393,882 rows, so a punch can never be attributed to a
#                     named employee. tblLeaveReport (live to 2026-07-27) is the
#                     only remaining workforce-presence feed.
# So two of the six tables handed to every unmatched question could not produce
# a correct answer at all.
_DEFAULT = [
    "tblPacket", "tblPacketHistory", "tblFinalPacket",
    "tblJangadPackets", "tblPointRateLabour", "tblLeaveReport", "tblEmployee",
]

# Main transactional tables (where real stones/records live). Preferred over
# rate/config lookup tables (tblBonusRate, tblReportRate, ...) on score ties.
#
# tblPointRateLabour was missing while the superseded tblLabourResult was
# present - the exact inversion the glossary warns about ("labour/bonus/earnings
# -> tblPointRateLabour for CURRENT/recent; tblLabourResult only for pre-2022
# history, it dies ~Feb 2023"). So a labour question ranked the dead table above
# the live one. Both stay candidates; the live one now outranks on a tie.
_PRIMARY = {
    "tblPacketHistory", "tblFinalPacket", "tblPacket", "tblPacketIssue",
    "tblPointRateLabour", "tblLabourResult", "tblPlanMaster", "tblPlanReport",
    "tblJangadPackets", "tblPacketPoint", "tblEmployee", "tblEmpDetail",
    "tblKapan", "tblIncentiveAmount",
}

# One-row-per-entity MASTER tables. On a score tie they should beat their own
# derived/history siblings (e.g. tblPacket over tblPacketHistory/tblFinalPacket,
# tblKapan over packet tables) so a plain "packets/kapans …" question always
# includes the master and doesn't get it bumped out of the top-k (Layer-2 Q33).
#
# tblDepartMent belongs here for the same reason: "department wise" questions
# must join it to turn DepartMentId into a name, but it is a small 92-row lookup
# with no distinguishing columns, so on a bare name match it lost to config
# siblings that merely share the word (tblDeptConfig, tblDeptCompareRate,
# tblEmpConnDept). Measured: rank 11 of 58 on "which department has the most
# work in process" - just outside the prompt.
_MASTER = {"tblPacket", "tblKapan", "tblEmployee", "tblDepartMent"}

# ---------------------------------------------------------------------------
# Scoring weights. These only started to matter once the candidate set grew from
# 29 tables to ~239: with 29 hand-picked tables almost any match was a good
# match, so a raw hit count worked. Across the whole database it does not.
# ---------------------------------------------------------------------------

# Column-name fragments that appear in most tables and therefore carry NO
# routing signal. Without this, one common word in the question ("date", "name",
# "code") matches nearly every table and buries the real answer under noise.
# The meaningful half of a compound column still counts: KapanName splits to
# {kapan, name}, "name" is dropped, "kapan" survives and does the work.
_WEAK_COLUMN_TOKENS = {
    "id", "date", "time", "name", "no", "code", "type", "status", "user",
    "create", "creat", "created", "update", "updated", "modify", "modified",
    "is", "flag", "detail", "master", "value", "remark", "note", "entry",
    "active", "delete", "deleted", "by", "on", "at", "new", "old", "temp",
}

# A wide table (200 columns) would otherwise out-score a precisely-named one
# purely by surface area. Column matches are corroboration, not evidence.
_MAX_COLUMN_HITS = 3

# The glossary notes are long PROSE (some run 400+ words), so they collide with
# ordinary question words by chance. Capped and weighted well below a name hit:
# tblLeaveReport having "leave" in its NAME is strong evidence; tblFinalPacket's
# essay mentioning "employee" in passing is not. Scoring them the same is what
# kept genuinely-named tables out of the prompt.
_MAX_NOTE_HITS = 2

# Signal weights, strongest first.
_NAME_WEIGHT = 4.0       # the question's word is in the TABLE NAME - strongest
_NOTE_WEIGHT = 1.0       # ...merely somewhere in its glossary prose - weak
_COLUMN_WEIGHT = 1.0     # ...in one of its column names - corroboration

# Boosts. A table only reaches this point if it already matched something, so
# these BREAK TIES between plausible tables - they must never out-vote real
# evidence. They were +2/+2 (i.e. +4 for a curated primary table), which alone
# outweighed a direct table-name hit and re-created the old "only KEY_TABLES
# wins" behaviour through the back door.
_KEY_TABLE_BOOST = 1.0   # curated in KEY_TABLES = known to be asked about often
_PRIMARY_BOOST = 1.0     # real transactional data, not a rate/config lookup
_MASTER_BOOST = 0.5      # one-row-per-entity master beats its history sibling

# A table the database reports as EMPTY is demoted rather than dropped: it is
# almost never the answer (the glossary keeps a whole KNOWN-EMPTY TABLES note),
# but not always wrong either - tblPacketSell is empty and the rules explicitly
# want it named when someone asks about sales. A multiplier, not a subtraction,
# so it cannot invert the ordering or produce a negative score.
_EMPTY_TABLE_FACTOR = 0.4

# Keep the top-k, but drop anything scoring far below the best match rather than
# padding the prompt to k with noise. Long, mostly-irrelevant context is a known
# reliability killer on the small models this rotation has to survive on - the
# same reason note_router.py filters the data notes.
# 0.45 was too aggressive once the candidate set widened: a table matching the
# question by NAME scored just under half of a heavily-boosted incumbent and got
# cut. k already bounds the width, so this only has to strip obvious noise.
_RELATIVE_FLOOR = 0.30
_MIN_TABLES = 3          # ...but never starve a weak-signal question completely


def _norm(word: str) -> str:
    """Lowercase, strip a trailing plural 's', then map synonyms.

    ORDER MATTERS, and it used to be the other way round: synonyms were applied
    to the raw word and only then de-pluralised, so every PLURAL synonym missed.
    "workers" was not a key in _SYN, so it became "worker" and never reached
    "employee"; likewise "stones" -> "stone" (never "packet") and "karigars"
    (never "employee"). People ask in plurals constantly, so this quietly cost
    the router most of its synonym table. De-pluralise first, then translate.
    """
    word = word.lower()
    if word.endswith("s") and len(word) > 3:
        word = word[:-1]
    return _SYN.get(word, word)


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
    """
    Columns of every ROUTABLE table (cached - read from the DB only once).

    Despite the name this is no longer limited to KEY_TABLES; it is the full
    candidate set, minus the backup/demo/edit copies that hold stale or fake
    data. The name is kept because it is the seam the routing regression tests
    monkeypatch to score without a database - renaming it would silently
    disable those locks rather than fail them.

    Served from extractor's cached column map, so widening the candidate set
    from 29 tables to ~239 costs no extra database work.
    """
    return {
        table: cols
        for table, cols in extractor.get_columns().items()
        if not extractor.is_trap_table(table)
    }


def _row_counts() -> dict[str, int]:
    """
    {table: row count} if extractor ALREADY has them cached, else {}.

    Deliberately never triggers a database read of its own.

    extractor.get_tables() is lru_cached on SUCCESS only - an exception is never
    cached - so calling it here unconditionally re-dialled a down or
    still-starting database on EVERY question, each attempt paying the full
    connection timeout (measured: 15.8s per attempt, and it took the DB-less
    test suite from 41s to 139s).

    Piggybacking is enough, because build_schema_context() calls get_tables()
    later in the very same question. So the counts are missing only for the
    first question after boot - which routes on name/note/column evidence alone
    and is still correct, just without the size tie-break - and are present from
    the second question on. Row counts refine RANKING only (see _size_bonus);
    they are never required for a correct answer.
    """
    # getattr, not a direct attribute access: this whole function exists to be
    # unable to break a question, and a decorated/stubbed get_tables without
    # cache_info would otherwise raise AttributeError from inside the guard.
    cache_info = getattr(extractor.get_tables, "cache_info", None)
    if cache_info is None or cache_info().currsize == 0:
        return {}                      # not read yet - don't stall a user's turn
    try:
        return {t["name"]: t["rows"] for t in extractor.get_tables()}
    except Exception:  # noqa: BLE001 - routing must survive a DB blip
        return {}


def clear_cache() -> None:
    """Drop the router's cached reads (pairs with extractor.clear_schema_cache)."""
    _key_columns.cache_clear()
    _table_keywords.cache_clear()
    _name_keywords.cache_clear()
    _note_keywords.cache_clear()
    _curation_order.cache_clear()


def _size_bonus(rows: int | None) -> float:
    """
    Nudge ranking toward tables that actually hold data.

    NEVER negative. An earlier version subtracted 3.0 from empty tables, which
    was unsound: the relative floor in select_tables() compares scores as a
    RATIO, and a uniform subtraction wrecks that (5 and 3 become 2 and 0, so a
    close runner-up looks like noise). Emptiness is handled as a multiplier
    instead - see _EMPTY_TABLE_FACTOR - which cannot distort the ordering or
    push a score below zero.

    `None` means the row counts could not be read at all, so we know nothing and
    add nothing.
    """
    if not rows or rows <= 0:
        return 0.0
    if rows < 10_000:
        return 0.5
    if rows < 1_000_000:
        return 1.0
    return 1.5


@lru_cache(maxsize=512)
def _table_keywords(table: str) -> set[str]:
    """Keywords from a table's name + its glossary meaning.

    Kept as the UNION for callers that just want "is this table about X" (and
    for the routing regression tests). Scoring uses the two halves separately -
    see _name_keywords / _note_keywords - because they are very different
    strengths of evidence.
    """
    return _name_keywords(table) | _note_keywords(table)


@lru_cache(maxsize=512)
def _name_keywords(table: str) -> set[str]:
    """Tokens from the TABLE NAME, plus any glossary ALIASES.

    An alias counts as a NAME match (full weight), because that is what it is:
    the word people actually use for this table. Some table names share no word
    at all with how anyone asks for them, and no amount of scoring tuning fixes
    that - it is a vocabulary gap, so it is closed with vocabulary.

    The case that forced this: tblPctChecker holds the maker/polisher
    attribution the RULES call the "CLASSIC TRAP" for employee-wise packet and
    GIA results. Its name tokenises to {pct, checker}. Against "who polished
    packet AA-1" it scored zero on name and lost to the eight tables literally
    called tblPacket* - measured rank 43 of 87. With aliases it is reachable by
    the words in the question.

    Add aliases to a table's TABLE_NOTES entry:  "aliases": "maker polisher ..."
    """
    kw = set(_split_name(table))
    aliases = TABLE_NOTES.get(table, {}).get("aliases", "")
    if aliases:
        kw |= _tokenize(aliases)
    return kw


@lru_cache(maxsize=512)
def _note_keywords(table: str) -> set[str]:
    """Tokens from the table's glossary note (long prose - weak signal)."""
    return _tokenize(TABLE_NOTES.get(table, {}).get("note", ""))


def _column_keywords(cols: list[dict]) -> set[str]:
    """Meaningful tokens from a table's column names.

    Tokens shared by most tables ("id", "date", "name") are dropped - see
    _WEAK_COLUMN_TOKENS for why they actively hurt once every table competes.
    """
    kw: set[str] = set()
    for c in cols:
        kw |= set(_split_name(c["name"]))
    return kw - _WEAK_COLUMN_TOKENS


@lru_cache(maxsize=1)
def _curation_order() -> dict[str, int]:
    """KEY_TABLES position per table - the hand-curated 'most asked' ordering."""
    return {t: i for i, t in enumerate(KEY_TABLES)}


def _curation_rank(table: str) -> int:
    """Sort key: curated tables first in their listed order, everything else after."""
    return _curation_order().get(table, len(KEY_TABLES))


def score_tables(question: str) -> dict[str, float]:
    """Relevance score per candidate table. Exposed for tuning and tests."""
    q_words = _tokenize(question)
    cols_by_table = _key_columns()
    rows_by_table = _row_counts()

    scores: dict[str, float] = {}
    for table, cols in cols_by_table.items():
        name_hits = len(q_words & _name_keywords(table))
        note_hits = min(len(q_words & _note_keywords(table)), _MAX_NOTE_HITS)
        col_hits = min(len(q_words & _column_keywords(cols)), _MAX_COLUMN_HITS)
        if not (name_hits or note_hits or col_hits):
            continue  # no evidence at all - a boost must never create relevance

        score = (
            _NAME_WEIGHT * name_hits
            + _NOTE_WEIGHT * note_hits
            + _COLUMN_WEIGHT * col_hits
        )
        if table in KEY_TABLES:
            score += _KEY_TABLE_BOOST
        if table in _PRIMARY:
            score += _PRIMARY_BOOST
        if table in _MASTER:
            score += _MASTER_BOOST

        # `None` = row counts unavailable (no DB). Demote a table we KNOW is
        # empty, but never one we simply couldn't measure.
        rows = rows_by_table.get(table)
        score += _size_bonus(rows)
        if rows == 0:
            score *= _EMPTY_TABLE_FACTOR

        scores[table] = score
    return scores


def select_tables(question: str, k: int | None = None) -> list[str]:
    """
    Return the tables most relevant to the question, best first.

    Returns AT MOST k (default settings.SCHEMA_MAX_TABLES), and fewer when the
    question simply doesn't have that many plausible tables - padding the prompt
    to a fixed k with weak matches costs tokens and degrades instruction
    following on exactly the small models this has to work on.
    """
    k = settings.SCHEMA_MAX_TABLES if k is None else k
    scores = score_tables(question)
    if not scores:
        return _DEFAULT

    # Tie-break by the curated KEY_TABLES order (it encodes which tables people
    # actually ask about), then alphabetically so the result is deterministic.
    # Ties are common - a one-keyword question matches several tables equally -
    # and this used to fall through to dict insertion order, which meant routing
    # quietly depended on how KEY_TABLES happened to be typed.
    ranked = sorted(scores, key=lambda t: (-scores[t], _curation_rank(t), t))
    cutoff = scores[ranked[0]] * _RELATIVE_FLOOR
    strong = [t for t in ranked if scores[t] >= cutoff]

    # Below the floor we still keep a few, so a vaguely-worded question gets
    # some context instead of one table and a guess.
    return (strong if len(strong) >= _MIN_TABLES else ranked[:_MIN_TABLES])[:k]
