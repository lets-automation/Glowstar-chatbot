"""
test_router_recall.py
---------------------
REGRESSION LOCK for the schema-router widening (audit finding #1).

THE BUG THIS PREVENTS
---------------------
app/schema/router.py used to score ONLY the ~29 tables listed in
context.KEY_TABLES, out of the ~239 business tables in AasthaErp. Cross-
referencing every table the RULES and glossary instruct the model to use found
84 of them, of which 55 could NEVER be surfaced by the router — including
tblPctChecker (named in the "CLASSIC TRAP" rule for employee-wise results),
tblRepairCommentVision (the quality section of the mandated employee report),
tblPacketSell (sales), tblLeaveReport and tblPacketParameters.

The prompt named those tables; the schema block could not show them. That was
the single biggest cause of thin and wrong answers, and no amount of prompt
tuning could fix it.

These tests run WITHOUT a database (the _key_columns seam is mocked, exactly as
the Layer-1/Layer-2 routing tests do), so they lock the mechanism rather than any
particular model's behaviour.
"""
import pytest

from app.config import settings
from app.schema import extractor, router
from app.schema.context import KEY_TABLES

# A table that is REAL and referenced by the rules/glossary, but was never a
# routing candidate because it is not in KEY_TABLES.
_NON_KEY_TABLE = "tblLeaveReport"


@pytest.fixture()
def wide_universe(monkeypatch):
    """Score against a realistic candidate set: KEY_TABLES + non-key + traps."""
    universe = [
        *KEY_TABLES,
        "tblLeaveReport", "tblPacketSell", "tblRepairCommentVision",
        "tblStockInventory", "tblRoughOriginMaster", "tblJangadDetail",
        # trap copies that must never be selected
        "tblPacket_BKP", "tblTimeAttendance_Demo", "tblLabourResultGIA",
        "tblKapan_BKP", "tblTestKapanPricePlanMaster",
    ]
    monkeypatch.setattr(
        router, "_key_columns",
        lambda: {t: [] for t in universe if not extractor.is_trap_table(t)},
    )
    return universe


# ---------------------------------------------------------------------------
# 1. The candidate set is no longer gated on KEY_TABLES.
# ---------------------------------------------------------------------------
def test_a_non_key_table_can_be_selected(wide_universe):
    picked = router.select_tables("how many workers took leave last month")
    assert _NON_KEY_TABLE in picked, (
        f"{_NON_KEY_TABLE} is not in KEY_TABLES and must still be routable - "
        "this is the whole point of the widening"
    )


@pytest.mark.parametrize("question,expected", [
    ("what are our sales this year", "tblPacketSell"),
    ("quality repair comments for kapan AA", "tblRepairCommentVision"),
    ("rough origin wise production", "tblRoughOriginMaster"),
    ("department wise stock inventory", "tblStockInventory"),
])
def test_previously_unreachable_tables_are_surfaced(wide_universe, question, expected):
    assert expected in router.select_tables(question), (
        f"{expected} was unreachable before the widening and must now route"
    )


def test_key_tables_is_a_boost_not_a_gate():
    """KEY_TABLES must still HELP (it encodes what people actually ask about),
    but it must not be the only way in."""
    assert router._KEY_TABLE_BOOST > 0
    # ...and it must not outweigh a direct table-name match, or the old
    # "only KEY_TABLES wins" behaviour returns through the back door.
    assert router._KEY_TABLE_BOOST + router._PRIMARY_BOOST < router._NAME_WEIGHT


# ---------------------------------------------------------------------------
# 2. Widening must NOT let backup/demo/edit copies into the prompt.
#    The router previously had no trap filter at all - it did not need one while
#    its candidate set was a curated list.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("q", [
    "packet report for kapan AA",
    "attendance last month",
    "labour result by employee",
    "kapan wise production",
])
def test_trap_tables_are_never_selected(wide_universe, q):
    picked = router.select_tables(q)
    traps = [t for t in picked if extractor.is_trap_table(t)]
    assert not traps, f"routed to stale/fake data: {traps}"


# ---------------------------------------------------------------------------
# 3. Evidence strength: a NAME match beats a glossary-prose match.
#    The notes are long (400+ words); scoring them equal to a name hit is what
#    kept genuinely-named tables out of the prompt.
# ---------------------------------------------------------------------------
def test_name_match_outweighs_note_match():
    assert router._NAME_WEIGHT > router._NOTE_WEIGHT * router._MAX_NOTE_HITS


def test_note_hits_are_capped():
    """An essay-length note must not accumulate unlimited score."""
    assert router._MAX_NOTE_HITS <= 3


# ---------------------------------------------------------------------------
# 4. Plural synonyms. _norm applied _SYN to the RAW word and de-pluralised
#    afterwards, so "workers" never reached "employee" - most of the synonym
#    table was dead for the plurals people actually type.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("plural,expected", [
    ("workers", "employee"),
    ("karigars", "employee"),
    ("stones", "packet"),
    ("staffs", "employee"),
    ("sales", "sell"),
    ("colours", "color"),
])
def test_plural_synonyms_resolve(plural, expected):
    assert router._norm(plural) == expected


def test_singular_synonyms_still_resolve():
    assert router._norm("worker") == "employee"
    assert router._norm("karigar") == "employee"


# ---------------------------------------------------------------------------
# 5. Width is bounded and adaptive - padding the prompt with weak matches costs
#    tokens and degrades instruction following on small models.
# ---------------------------------------------------------------------------
def test_never_returns_more_than_the_configured_width(wide_universe):
    for q in ("kapan wise production report", "how many packets", "employee list"):
        assert len(router.select_tables(q)) <= settings.SCHEMA_MAX_TABLES


def test_explicit_k_is_respected(wide_universe):
    assert len(router.select_tables("kapan wise production report", k=3)) <= 3


def test_unmatched_question_falls_back_rather_than_returning_nothing(wide_universe):
    assert router.select_tables("zzzz qqqq xxxx") == router._DEFAULT


# ---------------------------------------------------------------------------
# 6. Routing must never trigger its own database read. extractor.get_tables()
#    is lru_cached on SUCCESS only, so calling it unconditionally re-dialled a
#    down/starting database on EVERY question at ~15s per attempt.
# ---------------------------------------------------------------------------
def test_row_counts_do_not_dial_the_database(monkeypatch):
    """With the schema cache COLD, _row_counts must return {} without calling
    through - not attempt a connection."""
    calls = []

    def _never_call():
        calls.append(1)
        raise AssertionError("the router dialled the database")

    _never_call.cache_info = lambda: type("I", (), {"currsize": 0})()
    monkeypatch.setattr(router.extractor, "get_tables", _never_call)

    assert router._row_counts() == {}
    assert not calls, "the router must never trigger a schema read of its own"


def test_row_counts_used_when_the_cache_is_already_warm(monkeypatch):
    """When extractor HAS the data, use it - the size tier is a real signal."""
    def _warm():
        return [{"name": "tblPacket", "rows": 168_763}]

    _warm.cache_info = lambda: type("I", (), {"currsize": 1})()
    monkeypatch.setattr(router.extractor, "get_tables", _warm)

    assert router._row_counts() == {"tblPacket": 168_763}


def test_row_counts_survive_a_database_error(monkeypatch):
    def _boom():
        raise RuntimeError("connection reset")

    _boom.cache_info = lambda: type("I", (), {"currsize": 1})()
    monkeypatch.setattr(router.extractor, "get_tables", _boom)

    assert router._row_counts() == {}   # degraded ranking, never a failed turn


# ---------------------------------------------------------------------------
# 7. An EMPTY table is demoted, never excluded, and never by a subtraction that
#    could invert the ordering (the relative floor compares scores as a ratio).
# ---------------------------------------------------------------------------
def test_empty_table_penalty_is_a_multiplier_not_a_subtraction():
    assert 0 < router._EMPTY_TABLE_FACTOR < 1


@pytest.mark.parametrize("rows", [0, None, 5, 50_000, 5_000_000])
def test_size_bonus_is_never_negative(rows):
    assert router._size_bonus(rows) >= 0


# ---------------------------------------------------------------------------
# 8. The fallback list must contain only LIVE tables.
#
# _DEFAULT is what an UNRECOGNISED question is answered from, so a dead table
# here produces a confidently wrong answer with no signal that anything is off.
# It used to list tblTimeAttendance (last punch 2025-04-05, EmpId 100% NULL on
# all 393,882 rows) and tblLabourResult (last row 2023-04-12) — two of six.
# ---------------------------------------------------------------------------
_DEAD_FEEDS = {
    "tblLabourResult",        # -> 2023-04-12; live table is tblPointRateLabour
    "tblTimeAttendance",      # -> 2025-04-05; EmpId 100% NULL
    "tblEmployeeCount",       # -> 2021-07-23
    "tblCompanySchedule",     # -> 2022-06-30
    "tblRepairLog",           # -> 2022-02-19
    "tblStockIssue", "tblStockPurchage",   # -> March 2022
    "tblKoted", "tblKtdPacket",            # -> 2019-12-09, parent row corrupt
}


@pytest.mark.parametrize("table", sorted(_DEAD_FEEDS))
def test_no_dead_feed_in_the_default_fallback(table):
    assert table not in router._DEFAULT, (
        f"{table} is a dead feed (see the FEEDS THAT STOPPED data note) and must "
        "not be what an unrecognised question is answered from"
    )


def test_default_fallback_is_not_empty():
    assert len(router._DEFAULT) >= 4
