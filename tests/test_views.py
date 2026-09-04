"""
test_views.py
-------------
CURATED VIEWS - the wrong query made inexpressible instead of forbidden.

Each figure asserted here is one the bot has previously got WRONG against the
raw tables: oval stock (answered 2,986, then 7,321, true 7,591), packets on
hold (answered 2, true 11,967), packets sent to the lab (answered 2,896, then
3,492, true 3,692).
"""
import pytest

from app.agent import query_rules as qr
from app.core.sql_guard import validate_and_prepare
from app.schema import views


class TestInlining:
    """A derived table MUST carry an alias in T-SQL, and the model may or may
    not have written one."""

    def test_a_bare_reference_gets_the_view_name_as_its_alias(self):
        out = views.inline_views("SELECT COUNT(*) FROM v_packet WHERE Shape = 'OV'")
        assert "FROM (" in out and ") AS v_packet" in out

    @pytest.mark.parametrize("sql", [
        "SELECT COUNT(*) FROM v_packet p WHERE p.Shape = 'OV'",
        "SELECT COUNT(*) FROM v_packet AS p WHERE p.Shape = 'OV'",
    ])
    def test_the_models_own_alias_is_reused(self, sql):
        out = views.inline_views(sql)
        assert ") AS p" in out
        assert ") AS v_packet" not in out, "two aliases would be a syntax error"

    @pytest.mark.parametrize("kw", ["WHERE", "GROUP BY Shape", "JOIN tblKapan k ON 1=1"])
    def test_a_keyword_is_not_mistaken_for_an_alias(self, kw):
        out = views.inline_views(f"SELECT COUNT(*) FROM v_packet {kw}")
        assert ") AS v_packet" in out

    @pytest.mark.parametrize("sql", [
        "SELECT COUNT(*) FROM tblPacket",
        "SELECT COUNT(*) FROM v_bogus",
        "SELECT 1",
    ])
    def test_everything_else_is_left_exactly_alone(self, sql):
        assert views.inline_views(sql) == sql

    def test_two_views_in_one_query_are_both_expanded(self):
        out = views.inline_views(
            "SELECT COUNT(*) FROM v_lab l JOIN v_packet p ON p.PacketId = l.PacketId")
        assert out.count("FROM (") >= 1 and ") AS l" in out and ") AS p" in out

    def test_referenced_lists_only_known_views(self):
        assert views.referenced("SELECT * FROM v_lab l JOIN v_packet p ON 1=1") == [
            "v_lab", "v_packet"]
        assert views.referenced("SELECT * FROM tblPacket") == []


def test_inlining_keeps_the_row_cap_working():
    """THE REASON VIEWS ARE INLINED RATHER THAN PREPENDED AS CTEs.

    sql_guard.ensure_row_cap returns any statement starting with WITH
    untouched - it says so in its own docstring - so CTE-shaped views would
    silently disable the row cap on every query the model writes. A derived
    table keeps the statement a plain leading SELECT.
    """
    ok, prepared = validate_and_prepare(
        views.inline_views("SELECT * FROM v_packet"), cap=1000)
    assert ok
    assert prepared.lstrip().upper().startswith("SELECT TOP")


class TestSubsumption:
    """A view IS the enforcement, so the rule it replaces must stand aside -
    otherwise the correct query is rejected by the guard built to protect it."""

    CORRECT = [
        ("how many oval diamonds do we have in stock?",
         "SELECT COUNT(*) AS n FROM v_packet WHERE Shape = 'OV' AND IsInStock = 1"),
        ("how many packets are on hold",
         "SELECT COUNT(*) AS n FROM v_packet WHERE IsOnHold = 1"),
        ("last month ketla stone lab ma send karya?",
         "SELECT COUNT(DISTINCT PacketId) AS n FROM v_lab "
         "WHERE SentOn >= '2026-07-01' AND SentOn < '2026-08-01'"),
    ]

    @pytest.mark.parametrize("q,sql", CORRECT)
    def test_a_correct_view_query_is_not_rejected(self, q, sql):
        assert qr.violations(q, sql) == []

    @pytest.mark.parametrize("q,sql", [
        ("how many oval diamonds do we have in stock?",
         "SELECT COUNT(*) FROM tblPacket WHERE Shape = 'OV'"),
        ("how many packets are on hold",
         "SELECT COUNT(*) FROM tblPacket WHERE IsOnHold = 1"),
    ])
    def test_the_raw_table_trap_is_still_rejected(self, q, sql):
        assert qr.violations(q, sql)

    @pytest.mark.parametrize("sql", [
        "SELECT COUNT(*) FROM v_lab WHERE SentOn BETWEEN '2026-07-01' AND '2026-07-31'",
        "SELECT COUNT(*) FROM v_packet GROUP BY ROLLUP(Shape, Color)",
    ])
    def test_rules_a_view_does_not_subsume_still_apply(self, sql):
        """A BETWEEN on dates or a ROLLUP is just as wrong against a view as
        against a raw table."""
        assert qr.violations("last month ketla stone lab ma send karya?", sql)

    def test_every_subsumed_name_is_a_real_rule(self):
        """A typo here would silently disable nothing, or worse, nothing at
        all - so the contract is checked against the actual rule set."""
        names = {r.name for r in qr.RULES}
        for view, subsumed in views.SUBSUMES.items():
            unknown = subsumed - names
            assert not unknown, f"{view} claims to subsume unknown rules: {unknown}"


@pytest.mark.integration
class TestTheViewsReturnTheRightNumbers:
    """Every figure here is one the raw-table query got wrong."""

    def _one(self, sql):
        from app.database.runner import run_select

        r = run_select(views.inline_views(sql), max_rows=5)
        assert r["ok"], r["error"]
        return list(r["rows"][0].values())[0]

    def test_no_packet_is_lost_by_the_view(self):
        assert self._one("SELECT COUNT(*) AS n FROM v_packet") == 172233

    def test_oval_stock_counts_the_whole_family(self):
        assert self._one(
            "SELECT COUNT(*) AS n FROM v_packet "
            "WHERE Shape = 'OV' AND IsInStock = 1") == 7591

    def test_emerald_is_not_mangled_by_the_variant_mapping(self):
        """A blanket 'strip a trailing M' would turn EM into E. The mapping is
        explicit for exactly this reason."""
        assert self._one("SELECT COUNT(*) AS n FROM v_packet WHERE Shape = 'EM'") == 7059

    def test_hold_is_resolved_at_kapan_level(self):
        assert self._one(
            "SELECT COUNT(*) AS n FROM v_packet WHERE IsOnHold = 1") == 11967

    def test_the_lab_view_makes_the_wrong_count_impossible(self):
        """COUNT(*) and COUNT(DISTINCT PacketId) must AGREE - that is what
        stops the stage-row inflation the raw table invites."""
        where = "WHERE SentOn >= '2026-07-01' AND SentOn < '2026-08-01'"
        assert self._one(f"SELECT COUNT(*) AS n FROM v_lab {where}") == 3692
        assert self._one(
            f"SELECT COUNT(DISTINCT PacketId) AS n FROM v_lab {where}") == 3692

    def test_the_stage_view_dedupes_without_losing_packets(self):
        assert self._one("SELECT COUNT(DISTINCT PacketId) AS n FROM v_stage") == 171834
