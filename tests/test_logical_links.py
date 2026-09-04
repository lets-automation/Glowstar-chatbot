"""
test_logical_links.py
---------------------
THE DATABASE BARELY DECLARES ITS OWN RELATIONSHIPS.

Measured 2026-08-31: 264 base tables, 51 foreign keys, and only four of those
touch the six busiest tables. tblFinalPacket, tblPointRateLabour,
tblJangadPackets, tblPctChecker and tblPacketPoint declare NONE, so the
"links:" line for them was empty and the model had to infer joins from column
names the schema spells four different ways (PacketId vs Packet_ID, EmpId vs
Emp_ID vs UserID vs MfgEmpId).

context.LOGICAL_LINKS fills that gap, and carries each link's MEASURED match
rate so the model can see when an inner join would silently drop rows.
"""
import pytest

from app.schema import context


class TestLogicalLinksAreRendered:

    @pytest.mark.parametrize("table", [
        "tblFinalPacket", "tblPointRateLabour", "tblJangadPackets",
        "tblPctChecker", "tblPacketPoint",
    ])
    def test_every_undeclared_table_now_has_links(self, table):
        """These five declare no physical foreign key at all."""
        lines = context._relationships_for(table, [])
        assert lines, f"{table} still has no join guidance"

    def test_a_lossy_link_says_so_in_words(self):
        """tblPacketPoint reaches only 61.5% of packets. A live answer summed a
        kapan weight through exactly that join and reported 197.661 carats
        against a true 378.458."""
        line = " ".join(context._relationships_for("tblPacketPoint", []))
        assert "LEFT JOIN" in line and "62%" in line

    def test_a_complete_link_is_not_cluttered_with_a_warning(self):
        line = " ".join(context._relationships_for("tblPacket", []))
        assert "tblDepartMent.ID" in line
        assert "silently drops" not in line

    def test_a_declared_foreign_key_is_not_duplicated(self):
        """When the database DOES declare the link, the curated entry must
        stand aside rather than print it twice."""
        declared = [{"parent_table": "tblPacket", "parent_column": "DepartMentId",
                     "ref_table": "tblDepartMent", "ref_column": "ID"}]
        lines = context._relationships_for("tblPacket", declared)
        assert len([l for l in lines if "DepartMentId" in l]) == 1

    def test_every_recorded_match_rate_is_a_sane_percentage(self):
        for table, links in context.LOGICAL_LINKS.items():
            for col, ref_table, ref_col, pct in links:
                assert 0 < pct <= 100, f"{table}.{col} has pct={pct}"
                assert ref_table.startswith("tbl"), f"{table}.{col} -> {ref_table}"
