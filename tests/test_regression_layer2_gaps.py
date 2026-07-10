"""
test_regression_layer2_gaps.py
------------------------------
REGRESSION LOCK for the Layer-2 gap fixes (2026-07-10).

The Layer-2 trap-bank audit (LAYER2_RESULTS.md) graded 60 realistic client
questions against real-DB ground truth and found 12 where the bot would still
misfire EVEN ON CLAUDE — because the router never surfaced the table holding the
answer, and/or the glossary never flagged the trap. Each fix was made in
app/schema/context.py (KEY_TABLES), app/schema/glossary.py (TABLE_NOTES +
DATA_NOTES) and app/schema/router.py (stopwords / synonyms / master tie-break).

Like the Layer-1 lock, this asserts the mechanism of each fix WITHOUT a DB or an
LLM: routing scores are computed from table-name + glossary-note keywords only
(the _key_columns DB read is mocked, exactly as the Layer-1 router tests do), and
the clarify/not-tracked guidance is checked as plain text. So these 12 gaps
cannot silently re-open via a glossary/router edit.

Run: python -m pytest tests/test_regression_layer2_gaps.py -q
"""

import pytest

from app.schema import router
from app.schema.context import KEY_TABLES
from app.schema.glossary import (
    TABLE_NOTES,
    render_data_notes,
    render_glossary_text,
)

# The 6 tables added to KEY_TABLES so the router can reach them at all.
GAP_TABLES = [
    "tblKapan",
    "tblCompany",
    "tblEmpNativeAddress",
    "tblParty",
    "tblSupplier",
    "tblBuyerName",
]


@pytest.fixture()
def router_no_db(monkeypatch):
    """Score routing on static name+note keywords only (no DB), like Layer 1."""
    monkeypatch.setattr(router, "_key_columns", lambda: {t: [] for t in KEY_TABLES})


# ---------------------------------------------------------------------------
# 1. The gap tables are reachable (in KEY_TABLES) and the tblJunk duplicate that
#    was silently clobbering the rich note is gone.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("table", GAP_TABLES)
def test_gap_table_is_a_router_candidate(table):
    assert table in KEY_TABLES, f"{table} must be in KEY_TABLES to be routable"


def test_tbljunk_note_is_the_rich_one():
    # There used to be TWO 'tblJunk' keys in TABLE_NOTES; the later stub
    # ("Rejected/scrap diamond material.") overrode the detailed note. Assert the
    # rich note survives (it names bhangar + the usable Weight column).
    note = TABLE_NOTES["tblJunk"]["note"]
    assert "bhangar" in note and "Weight" in note


# ---------------------------------------------------------------------------
# 2. Routing gap fixes — the needed table is now surfaced (DB-free). Each entry
#    passes if ANY of the expected tables appears (some questions are ambiguous
#    across several correct entities, e.g. clients -> party/supplier/buyer).
# ---------------------------------------------------------------------------
ROUTE_GAPS = [
    ("Q22 same-city-as-company", "How many workers live in the same city as the company?", {"tblCompany"}),
    ("Q23 native district", "List each employee with their native district.", {"tblEmpNativeAddress"}),
    ("Q31 average parcel size", "Average parcel size.", {"tblKapan"}),
    ("Q32 who are our clients", "Who are our clients?", {"tblParty", "tblSupplier", "tblBuyerName"}),
    ("Q33 packets created today", "Show me packets created today.", {"tblPacket"}),
    ("Q34 kapans finished this year", "Which kapans were finished this year?", {"tblKapan"}),
    ("Q40 certificate pdf", "Download the certificate PDF for this stone.", {"tblPacketDetail"}),
    ("Q43 kapan most junk", "Which kapan produced the most junk by weight?", {"tblJunk"}),
    ("Q51 karigar (gujlish)", "Surat na ketla karigar che?", {"tblEmpDetail", "tblEmployee"}),
]


@pytest.mark.parametrize("label,question,expected_any", ROUTE_GAPS)
def test_routing_gap_fixed(router_no_db, label, question, expected_any):
    picked = set(router.select_tables(question, k=4))
    assert expected_any & picked, f"{label}: need one of {expected_any}, got {sorted(picked)}"


# ---------------------------------------------------------------------------
# 3. Router mechanics the fixes rely on (guard against a silent revert).
# ---------------------------------------------------------------------------
def test_pronouns_are_stopwords():
    # "we/our/us" carry no routing signal; without this, notes that say "who WE
    # buy from" matched any "...do we have" question (broke Q25 25-pointers).
    assert {"we", "our", "us"} <= router._STOP


def test_karigar_synonym_maps_to_employee():
    assert router._SYN.get("karigar") == "employee"


def test_kapan_is_a_master_and_primary_table():
    # Kapan master must win score ties over packet-family tables.
    assert "tblKapan" in router._PRIMARY
    assert "tblKapan" in router._MASTER


# ---------------------------------------------------------------------------
# 4. Glossary clarify / not-tracked notes present (pure text). These are the
#    fixes for the judgment gaps where routing was fine but the bot could
#    fabricate instead of clarifying/declining.
# ---------------------------------------------------------------------------
_GLOSS = (render_data_notes() + "\n" + render_glossary_text()).lower()


@pytest.mark.parametrize(
    "label,tokens",
    [
        ("Q29 diamonds-unit ambiguity", ["how many diamonds", "ambiguous"]),
        ("Q35 value ambiguity", ["roughvalue", "estvalue", "oestimate", "restimate"]),
        ("Q39 margin not tracked", ["margin", "profit", "cost basis"]),
        ("Q40 certificate metadata", ["certificate", "reportno", "inscription"]),
    ],
)
def test_glossary_gap_note_present(label, tokens):
    missing = [t for t in tokens if t not in _GLOSS]
    assert not missing, f"{label}: missing tokens {missing}"
