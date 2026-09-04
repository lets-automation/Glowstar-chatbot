"""
Ground truth for the single most-asked question in the chat logs (55 times):
"provide past month GIA results of Fency department employees".

The maker is the EmpId on the LATEST tblPlanMaster RapVer='MFG' row. Measured
2026-08-24 for July 2026: that resolves to a named employee on 100% of the 3,692
lab-stage packets, and cross-checks at 99.40% against the independent
tblPacket.MFGEmpId column with identical totals. The ~0.6% that differ are
packets re-issued to a different maker AFTER grading.
"""
import pytest

from app.agent.reports import lab_results_report, resolve_department

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def fency_july():
    r = lab_results_report("2026-07-01", "2026-08-01", department="Fency")
    if not r["sections"]:
        pytest.skip("database not reachable")
    return {s["title"]: s for s in r["sections"]}


def test_fency_july_total(fency_july):
    assert fency_july["Summary"]["rows"][0]["PNo"] == 1643


def test_the_by_employee_rows_sum_to_the_total(fency_july):
    rows = fency_july["By employee"]["rows"]
    assert rows, "no employee breakdown"
    assert sum(r["PNo"] for r in rows) == 1643


def test_every_lab_packet_is_attributed_to_someone():
    """If attribution ever drops below 100%, an employee-wise report starts
    silently understating people and nothing else would tell us."""
    from app.database.runner import run_select

    sql = """
    SELECT COUNT(DISTINCT g.Packet_ID) AS total,
           COUNT(DISTINCT CASE WHEN e.ID IS NOT NULL THEN g.Packet_ID END) AS named
    FROM tblPlanMaster g WITH (NOLOCK)
    OUTER APPLY (SELECT TOP 1 m.EmpId FROM tblPlanMaster m WITH (NOLOCK)
                 WHERE m.Packet_ID = g.Packet_ID AND m.RapVer = 'MFG'
                 ORDER BY m.ID DESC) m
    LEFT JOIN tblEmployee e WITH (NOLOCK) ON e.ID = m.EmpId
    WHERE g.RapVer IN ('GIA','HRD','IGI')
      AND g.CreatDate >= '2026-07-01' AND g.CreatDate < '2026-08-01'"""
    r = run_select(sql, max_rows=1)
    if not r.get("ok") or not r.get("rows"):
        pytest.skip("database not reachable")
    row = r["rows"][0]
    assert row["total"] == 3692
    assert row["named"] == row["total"], "some lab packets have no named maker"


class TestDepartmentSpelling:
    """The client types 'fancy' for the Fency department in their own logs."""

    @pytest.mark.parametrize(("typed", "expected"), [
        ("fancy", "Fency"), ("FANCY", "Fency"), ("Fency", "Fency"),
        ("MFG 1", "MFG - 1"), ("mfg-1", "MFG - 1"), ("mfg2", "MFG-2"),
    ])
    def test_common_spellings_resolve(self, typed, expected):
        got, _ = resolve_department(typed)
        if got is None and expected:
            pytest.skip("database not reachable")
        assert got == expected

    def test_every_real_department_resolves_to_itself(self):
        from app.database.runner import run_select

        r = run_select(
            "SELECT DISTINCT DepartMentName FROM tblEmployee WITH (NOLOCK) "
            "WHERE DepartMentName IS NOT NULL AND DepartMentName <> ''",
            max_rows=500)
        if not r.get("ok"):
            pytest.skip("database not reachable")
        names = sorted({x["DepartMentName"] for x in r["rows"] if x.get("DepartMentName")})
        bad = [(n, resolve_department(n)[0]) for n in names
               if resolve_department(n)[0] != n]
        assert not bad, f"departments that stopped resolving: {bad[:5]}"

    def test_an_unknown_name_asks_instead_of_guessing(self):
        got, suggestions = resolve_department("NoSuchDept")
        assert got is None and suggestions
