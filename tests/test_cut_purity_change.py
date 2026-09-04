"""
test_cut_purity_change.py
-------------------------
THE ONE REPORT THAT MATCHES THEIR ERP PACKET-FOR-PACKET.

The client's "CUT-PURITY CHANGE" screen compares the MFG plan against the GIA
plan for one kapan, as TWO separate tables - cut changes and purity changes.
Verified against their own screen for kapan NI26 on 2026-08-31 and re-verified
against a fresh screenshot on 2026-09-01: 8 cut changes, 18 purity changes,
identical packets, identical employee codes.

WHY THIS TEST EXISTS
--------------------
The SQL below is NOT a recipe and NOT in app/. It was produced by the MODEL
writing free SQL, which is the point being made about it: free SQL works once
the schema traps are encoded as rules. But that also means the only record of
the verified query was a handoff document. A verified result that lives in a
document and nowhere in the suite is one prompt change away from silently
drifting, and nothing would notice - every OTHER verified report here is either
a recipe or has a test.

So this pins the RESULT, not the route. It does not force the model to write
this SQL; it proves the database still answers this question this way. If it
fails, either the data changed or a rule started steering the model wrong -
both worth knowing before the client sees it.

THE TRAPS THIS QUERY ENCODES (all of them cost us a wrong answer once):
  * `Purity` IS clarity - there is no clarity column.
  * ISNULL(IsDamagePlan, 0) = 0 on both sides.
  * rn = 1 per (Packet_ID, RapVer): the LATEST plan row for each stage.
  * The plan row's own EmpCode - NOT a join to tblEmployee, whose names are not
    unique (15 rows share one name). Y-codes here are Fency vendor firms.
  * ISNULL(col, '') on both sides of the comparison, so a NULL grade counts as
    a change rather than vanishing from the result.
"""
from functools import lru_cache

import pytest

from app.database.runner import run_select

KAPAN = "NI26"

# The verified query filters the kapan in the OUTER query, which makes the
# window function partition across all 1.3M rows of tblPlanMaster. Warm that
# costs about half a second; on a cold buffer pool it ran for over two minutes
# and blew a 120s timeout, which is a flaky test rather than a real failure.
#
# The kapan filter is pushed INTO the CTE here. That is safe because no packet's
# plan rows ever span two kapans - checked 2026-09-01:
#     SELECT COUNT(*) FROM (SELECT Packet_ID FROM tblPlanMaster
#       GROUP BY Packet_ID HAVING COUNT(DISTINCT KapanId) > 1) x   ->   0
# so restricting the partition to one kapan cannot drop the GIA row that the
# self-join needs. Both forms were run side by side and returned IDENTICAL sets
# for Cut and Purity; this one is ~2x faster warm and bounded cold.
_SQL = """
WITH s AS (
  SELECT pm.Packet_ID, pm.PacketName, pm.RapVer, pm.Cut, pm.Purity, pm.EmpCode,
         ROW_NUMBER() OVER (PARTITION BY pm.Packet_ID, pm.RapVer
                            ORDER BY pm.ID DESC) rn
  FROM tblPlanMaster pm WITH (NOLOCK)
  JOIN tblKapan k ON k.ID = pm.KapanId AND k.KapanName = '{kapan}'
  WHERE ISNULL(pm.IsDamagePlan, 0) = 0)
SELECT a.PacketName Pkt, a.EmpCode Emp, a.{col} MFGVal, b.{col} GIAVal
FROM s a
JOIN s b ON b.Packet_ID = a.Packet_ID AND b.RapVer = 'GIA' AND b.rn = 1
WHERE a.RapVer = 'MFG' AND a.rn = 1
  AND ISNULL(a.{col}, '') <> ISNULL(b.{col}, '')"""

# Read off the client's own screen, 2026-09-01. (packet, empcode, MFG, GIA).
THEIR_CUT = {
    (90, "M5003", "EX", "VG"), (51, "M5004", "EX", "VG"),
    (158, "M5005", "EX", "VG"), (149, "M5005", "EX", "VG"),
    (10, "M5005", "EX", "VG"), (26, "M5007", "EX", "VG"),
    (18, "M5008", "EX", "VG"), (124, "M5009", "EX", "VG"),
}
THEIR_PURITY = {
    (2, "Y126", "SI1", "VS2"), (37, "Y126", "SI1", "VS2"),
    (10, "M5005", "SI1", "VS2"), (49, "M5007", "SI1", "VS2"),
    (108, "Y126", "SI2", "SI1"), (22, "M5005", "SI2", "SI1"),
    (147, "M5007", "SI2", "SI1"), (24, "M5008", "SI2", "SI1"),
    (143, "M5009", "SI2", "SI1"), (98, "M5009", "SI2", "SI1"),
    (126, "M5005", "VS1", "VVS2"), (16, "M5007", "VS1", "VVS2"),
    (161, "M5007", "VS1", "VVS2"), (94, "M5004", "VS2", "VS1"),
    (167, "M5005", "VS2", "VS1"), (58, "M5005", "VS2", "VVS2"),
    (145, "M5004", "VVS2", "VVS1"), (124, "M5009", "VVS2", "VVS1"),
}


@lru_cache(maxsize=None)
def _rows(col):
    """CACHED: five test cases ask the same two questions; the query
    should run twice, not ten times."""
    r = run_select(_SQL.format(col=col, kapan=KAPAN), max_rows=500, timeout=300)
    assert r["ok"], r.get("error")
    return frozenset((int(x["Pkt"]), (x["Emp"] or "").strip(),
                      (x["MFGVal"] or "").strip(), (x["GIAVal"] or "").strip())
                     for x in r["rows"])


@pytest.mark.integration
class TestCutPurityChangeMatchesTheirScreen:

    @pytest.mark.parametrize("col,want", [("Cut", THEIR_CUT),
                                          ("Purity", THEIR_PURITY)])
    def test_it_matches_packet_for_packet(self, col, want):
        got = _rows(col)
        assert set(got) == set(want), (
            f"{col}: missing from ours {sorted(set(want) - set(got))}; "
            f"extra in ours {sorted(set(got) - set(want))}")

    def test_the_headline_counts_are_8_and_18(self):
        """The two numbers actually spoken aloud to the client."""
        assert (len(_rows("Cut")), len(_rows("Purity"))) == (8, 18)

    def test_vendor_firms_are_not_dropped(self):
        """Y-codes are Fency job-work FIRMS, not karigars. An INNER JOIN to
        tblEmployee to prettify the name is how they get silently lost - the
        plan row's own EmpCode is what the client's screen shows."""
        assert {r for r in _rows("Purity") if r[1].startswith("Y")}

    def test_cut_and_purity_are_separate_questions(self):
        """TWO tables, not one. A packet can change purity without changing
        cut, and collapsing them into a single 'changed' list is a different
        report from the one they check against."""
        cut_pkts = {r[0] for r in _rows("Cut")}
        pur_pkts = {r[0] for r in _rows("Purity")}
        assert cut_pkts != pur_pkts
        assert cut_pkts & pur_pkts          # 10 and 124 appear in both
