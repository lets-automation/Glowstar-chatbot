"""
The three wrong answers reported live on 2026-08-27, locked down.

    1. "polish planned done but gia certification pending for MFG-1, july"
       answered 201 once and "2 kapan" the next time - a pending question
       written as a filter instead of an anti-join, and reported in the wrong
       unit.

    2. "kapan QA26 ... purity FL to VVS2 ... size 0.3 to 0.80 ... marker 2"
       answered 0. The true answer is 1: the size filter ran on PolishedWt,
       which is NULL on all 325 packets of that in-process kapan.

    3. the same question's "for marker 2 department" - tblPacket.DepartMentId
       says where a packet is NOW ("Laser"), not who worked on it.

Every figure asserted here was measured against the 2026-08-21 backup
(AasthaErp_new); the anti-join SHAPE is copied from the client's own stored
procedure dbo.GetPLSSUM. The database-backed checks are marked `integration` so the
suite still runs without a server.
"""
from __future__ import annotations

import pytest

from app.agent import query_rules as qr

# A question that needs the anti-join, in the user's own words.
Q_PENDING = ("give me data whose polish planned is already done but gia "
             "certification is pending for MFG-1 department for july month")
Q_QA26 = ("from kapan QA26 give me packets that has purity between FL to VVS2 "
          "and size range from 0.3 to 0.80 for marker 2 department")


class TestPendingIsAnAntiJoin:
    """'X done but Y pending' is defined by the ABSENCE of a later stage row."""

    def test_the_rule_fires_on_the_reported_question(self):
        assert "stage_pending" in [r.name for r in qr.RULES if r.applies(Q_PENDING)]

    @pytest.mark.parametrize("phrasing", [
        "polished GIA pending for mfg-1 department of past month",
        "how many packets are remaining for GIA certification",
        "MFG baki che tevi packets batavo",
        "which packets are yet to be sent to lab",
        "outstanding PLS work for july",
    ])
    def test_it_fires_across_the_phrasings_users_actually_use(self, phrasing):
        assert "stage_pending" in [r.name for r in qr.RULES if r.applies(phrasing)]

    def test_a_filter_on_the_done_stage_alone_is_rejected(self):
        """This is the shape that produced '2 kapan' - it counts FINISHED work."""
        sql = ("SELECT COUNT(DISTINCT p.KapanId) FROM tblPlanMaster p "
               "WHERE p.RapVer='PLS' AND p.CreatDate>='2026-07-01' "
               "AND p.CreatDate<'2026-08-01'")
        problems = qr.violations(Q_PENDING, sql)
        assert problems, "a pending query with no anti-join must be rejected"
        # The rejection must say what makes a PLS row pending: that it is the
        # packet's LATEST approved one. It used to say "the ABSENCE of the
        # later stage row", which taught the plain anti-join - the reading that
        # answered 12 where the client counts 2.
        assert any("LATEST" in p for p in problems)

    @pytest.mark.parametrize("anti_join", [
        "AND NOT EXISTS (SELECT 1 FROM tblPlanMaster g WHERE g.Packet_ID=p.Packet_ID "
        "AND g.RapVer='GIA' AND g.IsDamagePlan=0 AND g.IsApproved=1)",
        "AND p.Packet_ID NOT IN (SELECT Packet_ID FROM tblPlanMaster "
        "WHERE RapVer='GIA' AND IsApproved=1)",
    ])
    def test_the_erp_s_own_shape_is_now_REJECTED(self, anti_join):
        """THIS TEST USED TO ASSERT THE OPPOSITE, AND THAT WAS THE BUG.

        The shape is lifted from dbo.GetPLSSUM, so it looked unimpeachable, and
        the validator was written to bless it. But "has PLS, has no GIA row"
        also keeps stones that HAVE moved on - graded at another lab, or
        re-planned after grading - and it answered 12 for the one question the
        client checked against their own screen, where they count 2.

        The recipe was fixed first. This closes the OTHER path: a question the
        router does not match falls through to the model writing SQL, and until
        now nothing there stopped it reproducing exactly this query. The
        rejection carries the positional form to write instead.
        """
        sql = ("SELECT COUNT(DISTINCT p.Packet_ID) FROM tblPlanMaster p "
               "WHERE p.RapVer='PLS' AND p.IsDamagePlan=0 AND p.IsApproved=1 "
               "AND p.CreatDate>='2026-07-01' AND p.CreatDate<'2026-08-01' "
               + anti_join)
        problems = qr.violations(Q_PENDING, sql)
        assert problems, "the plain anti-join must no longer pass"
        assert any("NOT MOVED ON" in p for p in problems)

    def test_a_left_join_is_null_is_rejected_too(self):
        """Same wrong reading, written as a LEFT JOIN. Blocking only the
        NOT EXISTS spelling would just move the wrong answer one keyword over."""
        sql = ("SELECT COUNT(DISTINCT p.Packet_ID) FROM tblPlanMaster p "
               "LEFT JOIN tblPlanMaster g ON g.Packet_ID=p.Packet_ID AND g.RapVer='GIA' "
               "WHERE p.RapVer='PLS' AND g.ID IS NULL")
        assert qr.violations(Q_PENDING, sql)

    @pytest.mark.parametrize("positional", [
        # NOT EXISTS against a LATER row - column vs column, which is what
        # separates it from an ordinary date filter.
        "AND NOT EXISTS (SELECT 1 FROM tblPlanMaster nx WHERE nx.Packet_ID=p.Packet_ID "
        "AND nx.IsApproved=1 AND nx.CreatDate > p.CreatDate)",
        # The same idea as MAX(ID)...
        "AND p.ID = (SELECT MAX(ID) FROM tblPlanMaster x WHERE x.Packet_ID=p.Packet_ID "
        "AND x.IsApproved=1)",
        # ...and as TOP 1 ORDER BY DESC. A model told to write the positional
        # form must not be rejected for choosing a different spelling of it.
        "AND p.ID = (SELECT TOP 1 x.ID FROM tblPlanMaster x WHERE x.Packet_ID=p.Packet_ID "
        "AND x.IsApproved=1 ORDER BY x.CreatDate DESC, x.ID DESC)",
    ])
    def test_the_positional_forms_pass(self, positional):
        sql = ("SELECT COUNT(DISTINCT p.Packet_ID) FROM tblPlanMaster p "
               "WHERE p.RapVer='PLS' AND ISNULL(p.IsDamagePlan,0)=0 AND p.IsApproved=1 "
               "AND p.CreatDate>='2026-07-01' AND p.CreatDate<'2026-08-01' "
               + positional)
        assert qr.violations(Q_PENDING, sql) == []

    def test_a_date_filter_is_not_positional_evidence(self):
        """`CreatDate >= '2026-07-01'` is a period filter, not proof that
        nothing came after. The check only counts a comparison whose right-hand
        side is another COLUMN, and >= never counts."""
        sql = ("SELECT COUNT(DISTINCT p.Packet_ID) FROM tblPlanMaster p "
               "WHERE p.RapVer='PLS' AND p.CreatDate>='2026-07-01' "
               "AND NOT EXISTS (SELECT 1 FROM tblPlanMaster g "
               "WHERE g.Packet_ID=p.Packet_ID AND g.RapVer='GIA')")
        assert qr.violations(Q_PENDING, sql)

    def test_the_directive_names_the_unit_and_the_flags(self):
        """The 201-vs-2-kapan split was a UNIT bug as much as a join bug."""
        d = qr.directive(Q_PENDING)
        assert "COUNT(DISTINCT Packet_ID)" in d
        assert "IsDamagePlan" in d and "IsApproved" in d


class TestDepartmentMeansTheStageWorkerNotTheCurrentLocation:

    def test_the_rule_fires_when_a_department_is_named(self):
        for q in (Q_PENDING, Q_QA26, "GIA results for Fency department"):
            assert "stage_department" in [r.name for r in qr.RULES if r.applies(q)]

    def test_it_steers_without_rejecting(self):
        """Both columns are legitimate - they answer different questions - so
        this rule must never reject a query."""
        for sql in (
            "SELECT COUNT(*) FROM tblPacket p WHERE p.DepartMentId = 16",
            "SELECT COUNT(*) FROM tblPlanMaster pm JOIN tblEmployee e ON e.ID=pm.EmpId "
            "WHERE e.DepartMentName='Marker-2'",
        ):
            assert qr.violations("packets for marker 2 department", sql) == []

    def test_the_directive_distinguishes_the_two_readings(self):
        d = qr.directive(Q_QA26)
        assert "DepartMentId" in d and "DepartMentName" in d


class TestNoNewFalseRejections:
    """The bar every rule in this file has to clear."""

    def test_the_new_rules_reject_no_cold_case_ground_truth(self):
        from scripts.cold_cases import COLD_CASES

        new_rules = {"stage_pending", "stage_department"}
        offenders = []
        for c in COLD_CASES:
            sql = c.get("truthSql")
            if not sql:
                continue
            q = c.get("question", "")
            for rule in qr.RULES:
                if rule.name in new_rules and rule.applies(q) and rule.check(sql):
                    offenders.append((c.get("id"), rule.name))
        assert offenders == [], f"new rules falsely reject: {offenders}"


class TestEmptyResultDiagnosis:
    """A filter that CANNOT match is not an answer of zero."""

    def test_a_query_with_no_range_filter_is_not_diagnosed(self):
        from app.agent import empty_result

        sql = "SELECT PacketNo FROM tblPacket p WHERE p.KapanName = 'ZZZ'"
        assert empty_result.diagnose(sql) == ""

    def test_between_is_not_split_into_two_predicates(self):
        """`BETWEEN 0.30 AND 0.80` is ONE predicate; splitting on its AND left a
        dangling '0.80' that read as a filter of its own."""
        from app.agent import empty_result

        preds = empty_result._split_and(
            "p.KapanName = 'QA26' AND p.PolishedWt BETWEEN 0.30 AND 0.80")
        assert preds == ["p.KapanName = 'QA26'",
                         "p.PolishedWt BETWEEN 0.30 AND 0.80"]

    def test_the_probe_keeps_the_alias_the_model_wrote(self):
        """Scope predicates are reused verbatim and carry `p.` prefixes, so the
        probe must re-declare the alias or fail to bind."""
        from app.agent import empty_result

        parsed = empty_result._classify(
            "SELECT p.PacketNo FROM tblPacket p WITH (NOLOCK) "
            "WHERE p.KapanName = 'QA26' AND p.PolishedWt BETWEEN 0.30 AND 0.80")
        assert parsed is not None
        table, alias, scope, suspects = parsed
        assert (table, alias) == ("tblPacket", "p")
        assert suspects == ["PolishedWt"]
        assert scope == ["p.KapanName = 'QA26'"]

    def test_a_join_condition_is_not_mistaken_for_a_scope_filter(self):
        """`ON e.ID = p.EmpId` names two aliases and belongs to neither table."""
        from app.agent import empty_result

        parsed = empty_result._classify(
            "SELECT p.PacketNo FROM tblPacket p "
            "LEFT JOIN tblEmployee e ON e.ID = p.EmpId "
            "WHERE p.KapanName = 'QA26' AND p.PolishedWt BETWEEN 0.30 AND 0.80")
        assert parsed is not None
        assert all("e." not in s for s in parsed[2])


@pytest.mark.integration
class TestAgainstTheRealDatabase:
    """The measured figures behind the rules above. Needs SQL Server."""

    QA26_FILTERS = ("p.KapanName = 'QA26' "
                    "AND p.Purity IN ('FL','IF','VVS1','VVS2')")

    def _count(self, where):
        from app.database.runner import run_select

        r = run_select(f"SELECT COUNT(*) AS n FROM tblPacket p WITH (NOLOCK) "
                       f"WHERE {where}", max_rows=1)
        if not r["ok"]:
            pytest.skip(f"database unavailable: {r['error'][:80]}")
        return r["rows"][0]["n"]

    def test_the_reported_zero_was_the_wrong_weight_column(self):
        assert self._count(f"{self.QA26_FILTERS} "
                           "AND p.PolishedWt BETWEEN 0.30 AND 0.80") == 0
        assert self._count(f"{self.QA26_FILTERS} "
                           "AND p.CurrentWt BETWEEN 0.30 AND 0.80") == 1

    def test_the_diagnosis_names_the_dead_column_and_a_live_one(self):
        from app.agent import empty_result

        note = empty_result.diagnose(
            "SELECT p.PacketNo FROM tblPacket p WITH (NOLOCK) "
            f"WHERE {self.QA26_FILTERS} AND p.PolishedWt BETWEEN 0.30 AND 0.80")
        if not note:
            pytest.skip("database unavailable")
        assert "PolishedWt is EMPTY" in note
        assert "CurrentWt" in note
        assert "NOT the answer" in note

    def test_a_genuine_zero_is_reported_as_a_real_finding(self):
        """The diagnosis must not cry wolf when the column IS populated."""
        from app.agent import empty_result

        note = empty_result.diagnose(
            "SELECT p.PacketNo FROM tblPacket p WITH (NOLOCK) "
            "WHERE p.KapanName = 'QA26' AND p.CurrentWt BETWEEN 900 AND 999")
        if not note:
            pytest.skip("database unavailable")
        assert "genuinely matched nothing" in note
        assert "0 is the correct answer" in note

    def test_a_misspelt_kapan_is_reported_as_a_bad_filter_not_as_zero(self):
        from app.agent import empty_result

        note = empty_result.diagnose(
            "SELECT p.PacketNo FROM tblPacket p WITH (NOLOCK) "
            "WHERE p.KapanName = 'QA26XX' AND p.CurrentWt BETWEEN 0.3 AND 0.8")
        if not note:
            pytest.skip("database unavailable")
        assert "no rows" in note and "check the spelling" in note

    def test_the_erp_definition_of_pls_done_gia_pending(self):
        """dbo.GetPLSSUM's own shape, scoped to MFG - 1 for July 2026."""
        from app.database.runner import run_select

        r = run_select("""
SELECT COUNT(DISTINCT p.Packet_ID) AS Packets, COUNT(DISTINCT p.KapanId) AS Kapans
FROM tblPlanMaster p WITH (NOLOCK)
OUTER APPLY (SELECT TOP 1 mm.EmpId FROM tblPlanMaster mm WITH (NOLOCK)
             WHERE mm.Packet_ID=p.Packet_ID AND mm.RapVer='MFG' ORDER BY mm.ID DESC) m
LEFT JOIN tblEmployee e WITH (NOLOCK) ON e.ID=m.EmpId
WHERE p.RapVer='PLS' AND p.IsDamagePlan=0 AND p.IsApproved=1
  AND e.DepartMentName='MFG - 1'
  AND p.CreatDate>='2026-07-01' AND p.CreatDate<'2026-08-01'
  AND NOT EXISTS (SELECT 1 FROM tblPlanMaster g WITH (NOLOCK)
                  WHERE g.Packet_ID=p.Packet_ID AND g.RapVer='GIA'
                    AND g.IsDamagePlan=0 AND g.IsApproved=1)
""", max_rows=1)
        if not r["ok"]:
            pytest.skip(f"database unavailable: {r['error'][:80]}")
        assert r["rows"][0]["Packets"] == 12
        assert r["rows"][0]["Kapans"] == 5

    def test_the_department_that_did_the_work_is_not_the_packets_location(self):
        """QA26 packet 301 sits in Laser but was planned by Marker-2."""
        from app.database.runner import run_select

        r = run_select("""
SELECT d.Name AS CurrentDept, e.DepartMentName AS PlannedBy
FROM tblPacket p WITH (NOLOCK)
LEFT JOIN tblDepartMent d WITH (NOLOCK) ON d.ID = p.DepartMentId
OUTER APPLY (SELECT TOP 1 pm.EmpId FROM tblPlanMaster pm WITH (NOLOCK)
             WHERE pm.Packet_ID = p.ID AND pm.RapVer='CLV' ORDER BY pm.ID DESC) c
LEFT JOIN tblEmployee e WITH (NOLOCK) ON e.ID = c.EmpId
WHERE p.KapanName='QA26' AND p.PacketNo='301'
""", max_rows=1)
        if not r["ok"] or not r["rows"]:
            pytest.skip("database unavailable")
        assert r["rows"][0]["CurrentDept"] == "Laser"
        assert r["rows"][0]["PlannedBy"] == "Marker-2"


class TestTheLabRecipeRefusesPendingQuestions:
    """A "pending" question is not a "results" question.

    Reported live 2026-08-31. "give me polished GIA pending for mfg-1
    department of past month" was answered by the lab_results recipe, which
    reports the packets the lab HAS graded: 379 packets carrying BOTH a PLSAmt
    (16,248.69) and a GIAAmt (16,199.77). A packet pending GIA cannot have a
    GIA amount, so the answer contradicted itself; the follow-up "how many
    total were pending" then returned 0 in the same session.

    query_rules.stage_pending already existed, already fired on both questions
    and was already enforced - but it guards run_sql, and a TOOL call never
    reaches it. The recipe's own description ("THE ONLY WAY TO ANSWER a lab /
    GIA / HRD / IGI results question") is what pulled a pending question in.
    """

    import pytest as _pytest

    @staticmethod
    def _run(question):
        from app.agent import query_rules, tools

        with query_rules.for_question(question):
            return tools.tool_lab_results(
                {"from_date": "2026-07-01", "to_date": "2026-08-01"})[0]

    @_pytest.mark.parametrize("q", [
        "give me polished GIA pending for mfg-1 department of past month",
        "how many total were pending in last month",
        "polished but GIA pending",
    ])
    def test_a_pending_question_is_refused(self, q):
        text = self._run(q)
        assert text.startswith("ERROR: this recipe reports")
        assert "anti-join" in text.lower() or "NOT EXISTS" in text

    @_pytest.mark.parametrize("q", [
        "give me lab results for July 2026",
        "kapan wise gia results for july 2026",
    ])
    def test_a_real_results_question_still_runs(self, q):
        assert not self._run(q).startswith("ERROR: this recipe reports")

    def test_the_refusal_carries_the_rules_own_directive(self):
        """One definition of "pending", not two. The refusal reuses
        stage_pending's trigger AND its directive, so the two cannot drift."""
        from app.agent import query_rules

        rule = next(r for r in query_rules.RULES if r.name == "stage_pending")
        text = self._run("how many total were pending in last month")
        assert rule.directive[:60] in text
