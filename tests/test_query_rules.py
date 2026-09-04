"""
The SAME question must always be answered from the SAME table.

Regression for the client demo: "provide total number of kapan wise by lab wise
for may month" ran against tblPlanMaster on 21 Aug (89 rows) and tblFinalPacket
on 22 and 24 Aug (53 rows). The client's ERP says 2,562, which only the
tblPlanMaster GIA-stage definition produces.
"""
import re

import pytest

from app.agent import query_rules as qr


@pytest.fixture(autouse=True)
def _no_question_leak():
    """Each test starts with no question in scope, and leaves none behind."""
    with qr.for_question(""):
        yield

WRONG = ("SELECT KapanName, Lab, COUNT(*) AS TotalPackets FROM tblFinalPacket "
         "WHERE CreateDate >= '2026-05-01' GROUP BY KapanName, Lab")
RIGHT = ("SELECT k.KapanName, g.RapVer AS Lab, COUNT(DISTINCT g.Packet_ID) AS Packets "
         "FROM tblPlanMaster g JOIN tblKapan k ON g.KapanId = k.ID "
         "WHERE g.RapVer IN ('GIA','HRD','IGI') AND g.CreatDate >= '2026-05-01' "
         "GROUP BY k.KapanName, g.RapVer")


class TestLabRule:
    @pytest.mark.parametrize("q", [
        "provide total number of kapan wise by lab wise for may month",
        "provide past month gia results of fency department employees",
        "last month ketla stone lab ma send karya?",
        "show this month gia result",
        "give me HRD and IGI results",
    ])
    def test_fires_on_lab_questions(self, q):
        assert qr.directive(q)

    @pytest.mark.parametrize("q", [
        "how many packets are on jangad?",
        "give me report of department MFG - 1 for july 2026",
        "how many oval diamonds do we have in stock?",
    ])
    def test_silent_on_unrelated_questions(self, q):
        """The LAB rule specifically must not fire. Other rules legitimately may
        - a jangad question gets the jangad rule - so this asserts the lab rule,
        not the absence of every directive."""
        assert "lab_results" not in [r.name for r in qr.RULES if r.applies(q)]
        assert not any("tblPlanMaster" in p for p in qr.violations(q, WRONG))

    def test_certified_is_a_different_question_and_not_forced(self):
        # "GIA certified" asks which lab issued the certificate - that IS the
        # LAB column. Forcing the RapVer stage here would be a new wrong answer.
        for q in ("show me GIA certified packets",
                  "which lab certified packet NS26-1?"):
            assert qr.directive(q) == ""
            assert qr.violations(q, WRONG) == []

    def test_wrong_source_is_rejected_with_actionable_fixes(self):
        q = "provide total number of kapan wise by lab wise for may month"
        problems = qr.violations(q, WRONG)
        assert problems
        assert any("tblPlanMaster" in p for p in problems)
        assert any("RapVer" in p for p in problems)
        assert "not run" in qr.rejection(problems)

    def test_correct_query_passes(self):
        q = "provide total number of kapan wise by lab wise for may month"
        assert qr.violations(q, RIGHT) == []


class TestPlumbing:
    def test_question_is_visible_to_the_sql_tool(self):
        with qr.for_question("provide past month gia results"):
            assert "gia" in qr.current_question()
        assert qr.current_question() == ""   # scoped to the turn

    def test_wrong_source_query_is_blocked_before_it_runs(self):
        from app.agent import tools

        with qr.for_question("provide total number of kapan wise by lab wise for may month"):
            text, sql, n, cols, rows = tools.tool_run_sql({"query": WRONG})
        assert text.startswith("ERROR:")
        assert (sql, n, cols, rows) == ("", 0, [], [])   # nothing executed

    def test_every_rule_records_how_it_was_verified(self):
        # An unverified rule is the same guess as before, just harder to see.
        for rule in qr.RULES:
            assert rule.verified, f"rule {rule.name} has no verified figure"

class TestPlanningVerifiedRule:
    """IsVerified is set on 14 rows in the whole database; IsApproved covers
    31,317 packets in 2026 alone. The client asks this one constantly."""

    QUESTION = "aa varsh ma ketla planning verify thaya che?"

    def test_the_dead_flag_is_rejected(self):
        problems = qr.violations(
            self.QUESTION,
            "SELECT COUNT(*) FROM tblPlanMaster WHERE IsVerified = 1")
        assert problems and any("IsApproved" in p for p in problems)

    def test_the_real_flag_passes(self):
        assert qr.violations(
            self.QUESTION,
            "SELECT COUNT(DISTINCT Packet_ID) FROM tblPlanMaster WHERE IsApproved = 1") == []


class TestRepairRule:
    """tblRepairLogNew answers 150,706 repairs for 2025 against a true 3,302."""

    QUESTION = "how many repair records exist for this kapan?"

    @pytest.mark.parametrize("table", ["tblRepairLog", "tblRepairLogNew"])
    def test_decoy_repair_tables_are_rejected(self, table):
        problems = qr.violations(self.QUESTION, f"SELECT COUNT(*) FROM {table}")
        assert problems and any("tblRepairCommentVision" in p for p in problems)

    def test_the_real_register_passes(self):
        assert qr.violations(
            self.QUESTION, "SELECT COUNT(*) FROM tblRepairCommentVision") == []


class TestAttendanceRule:
    """There is no live attendance feed; saying so IS the answer."""

    @pytest.mark.parametrize("q", [
        "show me the attendance report for july",
        "aaje ketla mansu ni hajri chhe?",
        "how many punches yesterday",
    ])
    def test_attendance_questions_get_the_directive(self, q):
        assert "stopped" in qr.directive(q) or "2025" in qr.directive(q)

    @pytest.mark.parametrize("q", [
        "aaje factory ma total ketla mansu chhe?",
        "how many employees are there?",
    ])
    def test_headcount_questions_are_not_hijacked(self, q):
        """A headcount question is answerable and must not be turned into a
        lecture about the dead attendance feed."""
        assert "attendance" not in [r.name for r in qr.RULES if r.applies(q)]

class TestNewFeaturesAreNotYetInUse:
    """Match pair and order linkage arrived with the 2026-08-21 backup and carry
    almost no data. Both ways of answering them are wrong: reading 664 off
    tblMatchPairCriteria and calling them pairs, or reading IsMatchPair, getting
    0, and reporting it as if the pairing had failed."""

    @pytest.mark.parametrize("q", [
        "how many match pairs do we have?",
        "which stones are match paired?",
        "show me the match pair criteria",
    ])
    def test_match_pair_questions_are_told_the_feature_is_unused(self, q):
        d = qr.directive(q)
        assert "NOT YET IN USE" in d
        # The COUNT used to be spelled out here and in the directive. It was
        # removed 2026-09-03: a figure in a directive is one the model can
        # recite instead of querying. The POINT survives without it.
        assert "NOT PER PAIR" in d.upper()
        assert "ONE ROW PER STONE" in d.upper()
        assert not re.search(r"\d+\s+rows?", d), (
            "the match-pair directive must not hand over a row count")

    def test_order_linkage_is_covered_too(self):
        assert "no populated order table" in qr.directive("show me order detail wise output")

    @pytest.mark.parametrize("q", [
        "how many packets are on jangad?",
        "give me report of department MFG - 1 for july 2026",
        "provide past month gia results of fency department employees",
    ])
    def test_unrelated_questions_are_untouched(self, q):
        assert "match_pair_and_orders" not in [r.name for r in qr.RULES if r.applies(q)]


class TestOperationalRules:
    """Rules added in the gap-closing pass, each with a measured figure."""

    def test_jangad_counts_packets_not_movements(self):
        q = "how many packets are on jangad?"
        problems = qr.violations(q, "SELECT COUNT(*) FROM tblJangad")
        assert problems and any("tblJangadPackets" in p for p in problems)
        assert qr.violations(
            q, "SELECT COUNT(DISTINCT PacketId) FROM tblJangadPackets WHERE IsReceived=0") == []

    @pytest.mark.parametrize("q", [
        "party wise jangad batavo - gst number sathe",
        "water jet ma total ketla jangad gaya che?",
    ])
    def test_jangad_rule_stays_out_of_party_and_process_questions(self, q):
        assert "jangad_memo" not in [r.name for r in qr.RULES if r.applies(q)]

    def test_headcount_rejects_the_dead_counter_table(self):
        q = "how many employees are there?"
        problems = qr.violations(q, "SELECT TotalEmployee FROM tblEmployeeCount")
        assert problems and any("IsActive" in p for p in problems)

    def test_stock_is_flagged_as_unsettled_rather_than_guessed(self):
        """This used to assert "172,233" was in the directive, as the number
        that proves tblPacket is cumulative. The words prove it; the number
        only invites the model to recite it. See
        test_no_directive_hands_the_model_a_recitable_total below."""
        d = qr.directive("how many oval diamonds do we have in stock?")
        assert "NOT A SETTLED DEFINITION" in d
        assert "every packet ever created" in d
        assert "cannot mean 'right now'" in d

    def test_damage_prefers_the_register_and_warns_about_points(self):
        d = qr.directive("give me the damage report of department MFG - 1")
        assert "IsDamageReport" in d
        assert "NOT money" in d

    def test_every_rule_still_carries_a_verified_figure(self):
        for rule in qr.RULES:
            assert rule.verified, rule.name


class TestBonusVsEarnings:
    """June 2026: BonusAmount 653.10 vs FinalLabour 80,763.23, and the top-5
    lists by each share only ONE person. Picking the wrong column does not
    shift a number, it names the wrong people to the client."""

    Q = "give me top 10 employees who get highest bonus"

    def test_the_dead_labour_table_is_rejected(self):
        problems = qr.violations(
            self.Q, "SELECT TOP 10 EmpName, SUM(FinalLabour) FROM tblLabourResult GROUP BY EmpName")
        assert problems and any("tblPointRateLabour" in p for p in problems)

    def test_the_live_table_passes(self):
        assert qr.violations(
            self.Q,
            "SELECT TOP 10 e.Code, SUM(l.BonusAmount) FROM tblPointRateLabour l "
            "JOIN tblEmployee e ON e.ID = l.Emp_ID GROUP BY e.Code") == []

    def test_the_directive_separates_bonus_from_earnings(self):
        d = qr.directive(self.Q)
        assert "BonusAmount" in d and "FinalLabour" in d
        assert "CODE" in d          # EmpName is a code, not a name

    def test_the_gia_labour_table_is_not_caught_by_the_ban(self):
        """tblLabourResultGIA is a different table - the ban targets
        tblLabourResult exactly."""
        assert qr.violations(self.Q, "SELECT * FROM tblLabourResultGIA") == []


class TestUnanswerableFamilies:
    """Saying 'this is not recorded' IS the correct answer. Substituting a
    nearby number is how a demo produces a confident fiction."""

    def test_sales_are_declared_not_recorded(self):
        d = qr.directive("aa mahine ketla nang vechya ane ketla dollar aavya?")
        assert "RECORDED" in d.upper()
        assert "tblJangad.Amount" in d      # the tempting substitute, named

    def test_the_sales_rule_fires_on_plain_english_too(self):
        """The trigger was r"\bsales?\b|..." with the \b eaten into a literal
        BACKSPACE byte (0x08), so the "sales" alternative could never match: only
        revenue/turnover/sold/invoice reached the rule. Plain "what are our sales
        this year" - the most likely client question - got NO directive at all."""
        for q in ("what are our sales this year", "sales report", "total sales"):
            assert qr.directive(q), f"no directive for {q!r}"

    def test_sales_must_not_claim_the_tables_do_not_exist(self):
        """tblPacketSell and tblBuyerName BOTH exist (0 and 8 rows). Telling the
        client their ERP has no sales table is wrong, and they know it."""
        d = qr.directive("buyer wise revenue")
        assert "tblPacketSell" in d
        low = d.lower()
        assert "no sales, invoice or buyer table" not in low
        assert "there is no sales" not in low

    def test_hold_is_kapan_level_not_packet_level(self):
        """The injected directive said "packets ON HOLD ... tblPacket.IsOnHold = 1,
        which is 2 right now" while RULES correctly said hold is KAPAN-level. The
        injected rule wins at generation time, so "how many packets are on hold"
        answered 2 where the truth is 11,967 (the packets of 34 held kapans) -
        a 6,000x error, verified live 2026-08-25."""
        d = qr.directive("how many packets are on hold")
        assert "KAPAN-LEVEL" in d.upper()
        # "not 2" was the packet-level figure; it is gone for the same
        # reason. What matters is that the KAPAN join is prescribed and the
        # packet flag is declared dead.
        assert "k.IsOnHold = 1" in d
        assert "effectively dead" in d
        assert "never be counted" in d
        assert "which is 2 right now" not in d
        # The FIGURE moved to the rejection message, which is only ever shown
        # once the model has already written the wrong query - there it is the
        # fix, not something to recite. It also stopped being true: the
        # directive said "34 kapans" and the live count is 30, so the pinned
        # number had already drifted while the test still passed.
        assert "11,967" not in d
        problems = qr.violations(
            "how many packets are on hold",
            "SELECT COUNT(*) FROM tblPacket WHERE IsOnHold = 1")
        assert problems and any("KAPAN-level" in p for p in problems)

    @pytest.mark.parametrize("sql", [
        "SELECT COUNT(*) FROM tblPacket WHERE IsOnHold = 1",
        "SELECT COUNT(*) FROM tblPacket p WHERE p.IsOnHold = 1",
    ])
    def test_every_spelling_of_the_dead_hold_flag_is_caught(self, sql):
        """A BARE IsOnHold used to escape. Both forbid patterns required a
        table prefix or a p. alias, but the most natural way to write the wrong
        query has neither - so the 6,000x error walked through the guard built
        to stop it. Found 2026-08-31."""
        assert qr.violations("how many packets are on hold", sql)

    def test_the_correct_kapan_join_still_passes(self):
        assert qr.violations(
            "how many packets are on hold",
            "SELECT COUNT(*) FROM tblPacket p JOIN tblKapan k "
            "ON p.Kapan_ID = k.ID WHERE k.IsOnHold = 1") == []

    def test_junk_grade_is_declared_empty_but_weight_kept(self):
        d = qr.directive("junk nu grade-wise report kadho")
        assert "Grede" in d and "NULL on" in d
        assert "Weight" in d                # what DOES work

    def test_chapka_loss_is_declared_untracked(self):
        d = qr.directive("kapan ma ketlo loss thayo? boil ane chapka bane no loss alag alag batavo.")
        assert "BoilLoss" in d and "chapka" in d.lower()

    @pytest.mark.parametrize("q", ["how many packets are on jangad?", "hello"])
    def test_these_rules_stay_out_of_unrelated_questions(self, q):
        names = [r.name for r in qr.RULES if r.applies(q)]
        for n in ("sales_not_recorded", "junk", "kapan_loss", "bonus_earnings"):
            assert n not in names, f"{n} fired on {q!r}"


class TestKapanAndFourC:
    def test_kapan_pieces_ambiguity_is_disclosed(self):
        d = qr.directive("oq26 kapan ma total ketla piece hata?")
        assert "THREE DEFENSIBLE ANSWERS" in d
        # The three FIGURES named the OQ26 answer outright - ask "kapan OQ26
        # ma ketla piece hata?" and the model could recite 839 without
        # running anything. The three SOURCES are what the rule is for.
        assert "tblPacket rows" in d
        assert "SUM(tblPacket.Pcs)" in d
        assert "tblFinalPacket" in d
        assert "839" not in d and "585" not in d and "682" not in d

    def test_final_point_uses_the_f_prefixed_columns(self):
        d = qr.directive("oq26 kapan ma final point / final polish weight ketlu nikalyu?")
        assert "FMFGPoint" in d
        assert "pre-final" in d

    def test_the_fluorescence_spelling_trap_is_named(self):
        d = qr.directive("total fluorescent stones broken down by colour.")
        assert "Florecent" in d and "Florocent" in d
        assert "never" in d.lower()      # 'Fluorescent' exists on neither table

    def test_hold_is_a_settled_figure_inside_the_stock_rule(self):
        d = qr.directive("atyare ketla diamond hold par che?")
        assert "IsOnHold" in d

    @pytest.mark.parametrize("q", ["hello", "how many employees are there?"])
    def test_these_stay_out_of_unrelated_questions(self, q):
        names = [r.name for r in qr.RULES if r.applies(q)]
        for n in ("kapan_pieces_points", "four_c_breakdown"):
            assert n not in names, f"{n} fired on {q!r}"



class TestShapeFamilyRule:
    """The base shape code is a MINORITY of its own family.

    Measured 2026-08-31 on tblPacket: the OV family holds 8,207 packets and
    plain 'OV' is only 3,265 of them (40%) - F.OV alone is bigger. Cold case
    COLD-08 answered 2,986 for "how many oval diamonds do we have in stock?"
    against a true 7,591, with the glossary note that explains this ALREADY
    routed into its prompt. Prose lost, so the query is rejected instead.
    """

    QUESTION = "how many oval diamonds do we have in stock?"

    @pytest.mark.parametrize("q", [
        "how many oval diamonds do we have in stock?",
        "pear shape na ketla stone che?",
        "give me the marquise count by kapan",
    ])
    def test_fires_on_shape_questions(self, q):
        assert qr.directive(q)

    @pytest.mark.parametrize("sql", [
        "SELECT COUNT(*) FROM tblPacket WHERE RunningProcess='IN Stock' AND Shape='OV'",
        "SELECT COUNT(*) FROM tblPacket WHERE p.Shape = 'OV'",
    ])
    def test_the_base_code_equality_is_rejected_with_the_codes(self, sql):
        problems = qr.violations(self.QUESTION, sql)
        assert problems and any("F.OV" in p for p in problems)

    def test_a_single_element_in_list_is_the_same_bug(self):
        """IN ('OV') under-counts exactly as much as = 'OV', so it is caught
        separately rather than being spelled around."""
        problems = qr.violations(
            self.QUESTION, "SELECT COUNT(*) FROM tblPacket WHERE Shape IN ('OV')")
        assert problems and any("only the base code" in p for p in problems)

    @pytest.mark.parametrize("sql", [
        "SELECT COUNT(*) FROM tblPacket WHERE Shape IN ('OV','F.OV','S.OV','OVM')",
        "SELECT COUNT(*) FROM tblPacket WHERE Shape LIKE '%OV%'",
    ])
    def test_a_family_wide_query_passes(self, sql):
        assert qr.violations(self.QUESTION, sql) == []

    def test_the_directive_names_every_family(self):
        d = qr.directive(self.QUESTION)
        assert "F.OV" in d and "F.PS" in d and "S.MQ" in d

    @pytest.mark.parametrize("q", ["hello", "how many packets are on jangad?"])
    def test_stays_out_of_unrelated_questions(self, q):
        assert "shape_family" not in [r.name for r in qr.RULES if r.applies(q)]


class TestDateRangeExclusiveRule:
    """BETWEEN on a smalldatetime silently drops the last day.

    Every period column in play (CreatDate, CreateDate, CreatedDate,
    ReciveTime, ApproveDate) is smalldatetime, so '2026-07-31' means midnight.
    Measured on tblPlanMaster for July 2026 GIA/HRD/IGI: 3,492 with BETWEEN
    against a true 3,692 - 200 packets lost with nothing in the answer to show
    it. reports.py already refuses an inclusive end on the TOOL path; this is
    the same guard for hand-written SQL.
    """

    QUESTION = "last month ketla stone lab ma send karya?"

    @pytest.mark.parametrize("q", [
        "last month ketla stone lab ma send karya?",
        "give me report of department MFG - 1 for July 2026",
        "how many packets in 2025?",
        "aa mahine ketla packet thaya?",
    ])
    def test_fires_on_dated_questions(self, q):
        assert "date_range_exclusive" in [r.name for r in qr.RULES if r.applies(q)]

    @pytest.mark.parametrize("q", [
        # "jangad" starts with "jan": a month pattern of jan|feb|...[a-z]* also
        # matched jangad, marker, maybe and decide, firing this rule on
        # questions with no date in them at all. Caught before release; kept as
        # a regression because the cost is a directive on nearly every turn.
        "how many packets are on jangad?",
        "marker 2 department na packets",
        "maybe show me the stock",
        "hello",
    ])
    def test_does_not_fire_on_undated_questions(self, q):
        assert "date_range_exclusive" not in [r.name for r in qr.RULES if r.applies(q)]

    def test_between_on_dates_is_rejected(self):
        problems = qr.violations(
            self.QUESTION,
            "SELECT COUNT(DISTINCT Packet_ID) FROM tblPlanMaster "
            "WHERE RapVer IN ('GIA','HRD','IGI') "
            "AND CreatDate BETWEEN '2026-07-01' AND '2026-07-31'")
        assert problems and any("NEXT_PERIOD_START" in p for p in problems)

    def test_the_exclusive_form_passes(self):
        assert qr.violations(
            self.QUESTION,
            "SELECT COUNT(DISTINCT Packet_ID) FROM tblPlanMaster "
            "WHERE RapVer IN ('GIA','HRD','IGI') "
            "AND CreatDate >= '2026-07-01' AND CreatDate < '2026-08-01'") == []

    def test_a_numeric_between_is_untouched(self):
        """Weight ranges are load-bearing in empty_result.py - only DATE
        literals are the bug."""
        assert qr.violations(
            "kapan QA26 size range from 0.3 to 0.80 for july 2026",
            "SELECT * FROM tblPacket WHERE CurrentWt BETWEEN 0.30 AND 0.80") == []


def test_no_trigger_contains_a_backspace_byte():
    """A literal backslash-b written into a non-raw string becomes 0x08.

    This file has been bitten once already (the sales/loss triggers silently
    became BACKSPACE and matched nothing), and it happened again while adding
    shape_family and date_range_exclusive. A 0x08 in a pattern does not raise -
    it just quietly stops matching - so it is asserted rather than reviewed.
    """
    for rule in qr.RULES:
        assert chr(8) not in rule.trigger.pattern, f"{rule.name} trigger"
        for patterns in (rule.require_all, rule.forbid):
            for rx, _why in patterns:
                # A forbid may be a CALLABLE (see reads_grade_off_the_packet):
                # a resolved check rather than a pattern, so there is no string
                # to inspect - and no backslash for the file to eat either.
                if callable(rx):
                    continue
                assert chr(8) not in rx, f"{rule.name} enforcement"


class TestFinalPointsRule:
    """Only an 'F' separates the final point from the pre-final one.

    Measured 2026-08-31 on kapan OQ26 (398 tblPacketPoint rows): FMFGPoint
    6,107.39 against MFGPoint 5,965.98. kapan_pieces_points already says this
    and stays advisory on purpose, because "how many pieces" has three
    defensible answers. "Final point" has one, so it is enforced.
    """

    QUESTION = "OQ26 kapan ma final point / final polish weight ketlu nikalyu?"

    def test_the_pre_final_column_is_rejected(self):
        problems = qr.violations(
            self.QUESTION,
            "SELECT SUM(MFGPoint) FROM tblPacketPoint WHERE KapanName='OQ26'")
        assert problems and any("FMFGPoint" in p for p in problems)

    @pytest.mark.parametrize("col", [
        "FMFGPoint", "FMarkerPoint", "FScopePoint", "FHLMPoint", "FMKBPoint",
    ])
    def test_every_f_prefixed_column_passes(self, col):
        """The lookbehind must not reject the correct column: MFGPoint is a
        substring of FMFGPoint, so a plain alternation would catch both."""
        assert qr.violations(
            self.QUESTION,
            f"SELECT SUM({col}) FROM tblPacketPoint WHERE KapanName='OQ26'") == []

    def test_it_stays_out_of_a_plain_piece_count(self):
        assert "final_points" not in [
            r.name for r in qr.RULES if r.applies("oq26 kapan ma ketla piece hata?")]


class TestEmployeeIdentityRule:
    """A name is not an identity.

    Measured 2026-08-31: fifteen tblEmployee rows match MAIYANI VIJAYABHAI
    (M2001, V001, Y001, G001, IGI001, HRD001, MFGAD003/5/7 ...) spread across
    MFG-2, Vision 360, Fency, GIA, IGI, HRD and Administrator, and nine rows
    share SUTARIYA NARESHKUMAR exactly. A per-person figure grouped on the name
    sums all of them and reports it as one worker's.
    """

    QUESTION = "total bonus of employee MAIYANI VIJAYABHAI in June 2026"

    def test_a_name_only_query_is_rejected(self):
        problems = qr.violations(
            self.QUESTION,
            "SELECT e.FirstName, e.LastName, SUM(r.BonusAmount) "
            "FROM tblPointRateLabour r JOIN tblEmployee e ON r.Emp_ID = e.ID "
            "WHERE e.FirstName LIKE '%MAIYANI%' GROUP BY e.FirstName, e.LastName")
        assert problems and any("Code" in p for p in problems)

    def test_a_join_key_is_not_proof_of_identity(self):
        """Emp_ID appears as a JOIN key in the query above and says nothing
        about whether the OUTPUT separates the duplicates - an earlier draft
        accepted it and let the merging query straight through."""
        problems = qr.violations(
            self.QUESTION,
            "SELECT e.FirstName, SUM(r.BonusAmount) FROM tblPointRateLabour r "
            "JOIN tblEmployee e ON r.Emp_ID = e.ID GROUP BY e.FirstName")
        assert problems

    def test_carrying_the_code_passes(self):
        assert qr.violations(
            self.QUESTION,
            "SELECT e.Code, e.FirstName, e.LastName, SUM(r.BonusAmount) "
            "FROM tblPointRateLabour r JOIN tblEmployee e ON r.Emp_ID = e.ID "
            "GROUP BY e.Code, e.FirstName, e.LastName") == []

    def test_the_column_is_code_not_empcode(self):
        """tblEmployee has Code; there is no EmpCode. Demanding a column that
        does not exist would cost a round to an invalid-column error, which is
        the trap four_c_breakdown documents for 'Fluorescent'."""
        d = qr.directive(self.QUESTION)
        assert "NOT EmpCode" in d

    def test_a_lookalike_column_does_not_satisfy_it(self):
        """DepartMentCode contains 'Code' but is not the employee identity."""
        assert qr.violations(
            self.QUESTION, "SELECT e.FirstName, e.DepartMentCode FROM tblEmployee e")

    @pytest.mark.parametrize("q", ["hello", "how many employees are there?"])
    def test_stays_out_of_unrelated_questions(self, q):
        assert "employee_identity" not in [r.name for r in qr.RULES if r.applies(q)]


class TestLivenessProbeExemption:
    """Proving a source is dead must stay legal.

    Cold case EDA-1's ground truth is SELECT MAX(Date) FROM tblEmployeeCount,
    whose answer (2021-07-23) IS the finding. The headcount rule forbids that
    table - correctly - and so forbade the query that proves it is dead.
    """

    def test_a_max_date_probe_on_a_forbidden_table_is_exempt(self):
        assert qr.violations(
            "Aaje factory ma total ketla mansu (worker) chhe?",
            "SELECT MAX(Date) AS LastHeadcountDate FROM tblEmployeeCount "
            "WITH (NOLOCK)") == []

    def test_a_bare_count_is_not_exempt(self):
        """Exempting COUNT too would re-open SELECT COUNT(*) FROM
        tblRepairLogNew - 150,706 against a true 3,302, the exact wrong number
        the repairs rule exists to stop."""
        assert not qr.is_liveness_probe("SELECT COUNT(*) FROM tblRepairLogNew")
        assert qr.violations(
            "how many repair records exist for this kapan?",
            "SELECT COUNT(*) FROM tblRepairLogNew")

    @pytest.mark.parametrize("sql", [
        "SELECT MAX(a.Date) FROM tblEmployeeCount a JOIN tblEmployee b ON a.id=b.id",
        "SELECT MAX(Date) FROM tblEmployeeCount GROUP BY Dept",
        "SELECT MAX(Date), SUM(Amount) FROM tblEmployeeCount",
    ])
    def test_it_fails_closed(self, sql):
        """A join, a grouping or a second output column all disqualify it -
        the exemption must not become a bypass."""
        assert not qr.is_liveness_probe(sql)


class TestDamageRuleStillEnforced:
    """DRS-2 regression. The damage directive FIRED and was ignored (-14,816.33
    against a register total of -11,536.82), which is why it carries
    require_all/forbid. Asserted here so it cannot quietly return to advisory.
    """

    QUESTION = ("2025 ma damage na ketla paisa katya karigar pase thi? "
                "Damage deduction total kitna hua?")

    @pytest.mark.parametrize("sql", [
        "SELECT COUNT(*) FROM tblPlanMaster WHERE IsDamagePlan=1",
        "SELECT SUM(DebitPoints) FROM tblPointRateLabour WHERE ProcessDate >= '2025-01-01'",
    ])
    def test_the_wrong_source_is_rejected(self, sql):
        assert qr.violations(self.QUESTION, sql)

    def test_the_damage_register_passes(self):
        assert qr.violations(
            self.QUESTION,
            "SELECT SUM(Amount) FROM tblPlanReport WHERE IsDamageReport = 1 "
            "AND CreatedDate >= '2025-01-01' AND CreatedDate < '2026-01-01'") == []


class TestWeightViaPointsJoinRule:
    """tblPacketPoint has no weight column, so a weight summed through it is
    restricted to the packets that happen to have a points row.

    Measured 2026-08-31 on kapan OQ26: 398 of 839 packets are in
    tblPacketPoint, so SUM(CurrentWt) through the join is 197.661 against a
    true 378.458. Seen live: the model asked for OQ26's final point AND polish
    weight wrote ONE query for both and got the points right (6,107.39) and the
    weight 48% short - which is what makes it dangerous, the answer looks
    sourced.
    """

    QUESTION = "OQ26 kapan ma final point / final polish weight ketlu nikalyu?"

    def test_a_weight_summed_through_the_points_join_is_rejected(self):
        problems = qr.violations(
            self.QUESTION,
            "SELECT SUM(p.CurrentWt) AS w, SUM(pp.FMFGPoint) AS pts "
            "FROM tblPacket p JOIN tblPacketPoint pp ON pp.Packet_ID = p.ID "
            "WHERE pp.KapanName = 'OQ26'")
        assert problems and any("197.661" in p for p in problems)

    def test_separate_queries_both_pass(self):
        assert qr.violations(
            self.QUESTION,
            "SELECT SUM(p.CurrentWt) FROM tblPacket p "
            "JOIN tblKapan k ON p.Kapan_ID = k.ID WHERE k.KapanName='OQ26'") == []
        assert qr.violations(
            self.QUESTION,
            "SELECT SUM(FMFGPoint) FROM tblPacketPoint WHERE KapanName='OQ26'") == []


class TestNoRollupTotalsRule:
    """ROLLUP repeats each figure at several levels and the rows do not say
    which are detail and which are subtotals.

    Measured 2026-08-31 from a live run of DRS-2: GROUP BY ROLLUP(e.ID, name,
    dept) returned 976 rows summing to -43,309.04, its own grand-total row said
    -10,827.26, and the plain ungrouped truth is -11,536.82. The model reported
    -43,309.04 - 3.75x - from a query whose table, flag and dates were right.
    """

    QUESTION = "2025 ma damage na ketla paisa katya karigar pase thi?"

    @pytest.mark.parametrize("clause", [
        "GROUP BY ROLLUP(e.ID, e.FirstName)",
        "GROUP BY CUBE(e.ID, e.FirstName)",
        "GROUP BY GROUPING SETS ((e.ID), ())",
    ])
    def test_every_multi_level_grouping_is_rejected(self, clause):
        problems = qr.violations(
            self.QUESTION,
            f"SELECT SUM(pr.Amount) FROM tblPlanReport pr "
            f"LEFT JOIN tblEmployee e ON pr.EmpID = e.ID "
            f"WHERE pr.IsDamageReport = 1 {clause}")
        assert problems and any("plain GROUP BY" in p for p in problems)

    def test_a_plain_group_by_passes(self):
        assert qr.violations(
            self.QUESTION,
            "SELECT e.Code, SUM(pr.Amount) FROM tblPlanReport pr "
            "LEFT JOIN tblEmployee e ON pr.EmpID = e.ID "
            "WHERE pr.IsDamageReport = 1 "
            "AND pr.CreatedDate >= '2025-01-01' AND pr.CreatedDate < '2026-01-01' "
            "GROUP BY e.Code") == []


class TestDamageInnerJoinRule:
    """An inner join to tblEmployee drops damage nobody is attributed to.

    Measured 2026-08-31 for calendar 2025: the inner join keeps 2,103 of the
    2,398 register rows and totals -10,827.26 against a true -11,536.82. The
    295 dropped rows have an EmpID matching no employee - real deductions,
    excluded because the join was only there to show a name.
    """

    QUESTION = "2025 ma damage na ketla paisa katya karigar pase thi?"
    WHERE = ("WHERE pr.IsDamageReport = 1 AND pr.CreatedDate >= '2025-01-01' "
             "AND pr.CreatedDate < '2026-01-01'")

    def test_the_inner_join_is_rejected(self):
        problems = qr.violations(
            self.QUESTION,
            f"SELECT SUM(pr.Amount) FROM tblPlanReport pr "
            f"JOIN tblEmployee e ON pr.EmpID = e.ID {self.WHERE}")
        assert problems and any("LEFT JOIN" in p for p in problems)

    def test_the_left_join_passes(self):
        assert qr.violations(
            self.QUESTION,
            f"SELECT SUM(pr.Amount) FROM tblPlanReport pr "
            f"LEFT JOIN tblEmployee e ON pr.EmpID = e.ID {self.WHERE}") == []

    def test_no_join_at_all_passes(self):
        assert qr.violations(
            self.QUESTION,
            "SELECT SUM(Amount) FROM tblPlanReport WHERE IsDamageReport = 1 "
            "AND CreatedDate >= '2025-01-01' AND CreatedDate < '2026-01-01'") == []


def test_every_directive_stays_inside_the_prompt_budget():
    """A rule is only cheap if the directives it JOINS stay small. Measured at
    400 tokens by test_a_rule_is_cheap_and_conditional; this checks the real
    client questions, where several rules fire at once."""
    questions = [
        "provide past month gia results of fency department employees",
        "total bonus of employee MAIYANI VIJAYABHAI in June 2026",
        "OQ26 kapan ma final point / final polish weight ketlu nikalyu?",
        "how many oval diamonds do we have in stock?",
        "2025 ma damage na ketla paisa katya karigar pase thi?",
        "give me report of department MFG - 1 for July 2026",
    ]
    over = {q: len(qr.directive(q)) // 4 for q in questions
            if len(qr.directive(q)) // 4 >= 400}
    assert not over, f"directives over budget: {over}"


class TestKapanValueSnapshotRule:
    """tblKapanValue re-writes every active kapan once a day.

    Measured 2026-08-31: 61,221 rows covering 1,050 kapans (~58 snapshots
    each). SUM(RoughWt) over it is 17,469,238.68 against a true tblKapan
    SUM(Weight) of 226,631.26 - a 77x inflation that still reads as a plausible
    lifetime intake.
    """

    QUESTION = "kapan wise rough weight batavo"

    def test_a_raw_sum_is_rejected(self):
        problems = qr.violations(
            self.QUESTION, "SELECT SUM(RoughWt) FROM tblKapanValue")
        assert problems and any("77x" in p for p in problems)

    def test_a_windowed_dedup_is_allowed(self):
        """ROW_NUMBER over a PARTITION is the documented way to take one row
        per kapan, so a query carrying it is doing the right thing."""
        assert qr.violations(
            self.QUESTION,
            "SELECT SUM(RoughWt) FROM (SELECT *, ROW_NUMBER() OVER "
            "(PARTITION BY KapanId ORDER BY CreatedAt DESC) rn "
            "FROM tblKapanValue) t WHERE rn = 1") == []

    def test_the_real_kapan_table_passes(self):
        assert qr.violations(
            self.QUESTION, "SELECT SUM(Weight) FROM tblKapan") == []


class TestPctCheckerJoinRule:
    """The attribution register covers about half the finished packets.

    Measured 2026-08-31 against tblFinalPacket: LEFT JOIN 180,066 rows, INNER
    JOIN 95,920 - an inner join drops 46.7% of the production while still
    looking like a complete employee report.
    """

    QUESTION = "who polished these packets"

    def test_the_inner_join_is_rejected(self):
        problems = qr.violations(
            self.QUESTION,
            "SELECT COUNT(*) FROM tblFinalPacket f "
            "JOIN tblPctChecker c ON c.PacketId = f.PacketId")
        assert problems and any("46.7%" in p for p in problems)

    def test_the_left_join_passes(self):
        assert qr.violations(
            self.QUESTION,
            "SELECT COUNT(*) FROM tblFinalPacket f "
            "LEFT JOIN tblPctChecker c ON c.PacketId = f.PacketId") == []


class TestRateCardNotMoneyRule:
    """The rate tables are price lists, not payments.

    Measured 2026-08-31: SUM(Amount) over tblLabourRate is 64,311,533.58 where
    the money actually paid (tblPointRateLabour) is 3,884,709.83 - 16.6x, and
    both are rupee figures, so nothing about the wrong one looks wrong.
    """

    QUESTION = "total labour paid this year"

    @pytest.mark.parametrize("table", [
        "tblLabourRate", "tblReportRate", "tblBonusRate"])
    def test_summing_a_rate_card_is_rejected(self, table):
        problems = qr.violations(
            self.QUESTION, f"SELECT SUM(Amount) FROM {table}")
        assert problems and any("rate CARD" in p for p in problems)

    def test_looking_up_a_single_rate_is_allowed(self):
        """These tables are legitimate for reading ONE rate - the rule is
        about summing them, not touching them."""
        assert qr.violations(
            self.QUESTION,
            "SELECT TOP 1 Amount FROM tblLabourRate WHERE Shape = 'RD'") == []


def test_no_directive_hands_the_model_a_recitable_total():
    """A FIGURE IN A DIRECTIVE IS A TIME BOMB.

    Directives are injected BEFORE the model queries, so any total in one is a
    number it can answer with instead of running SQL. Measured 2026-08-31 on
    Qwen3-30B-A3B: asked for oval stock it replied "7,321 packets" - the
    glossary's own worked example, where the live figure is 7,591 - having run
    no query at all.

    They also rot silently. Every figure here was verified when written; by
    2026-08-31 the hold directive's "34 kapans" was 30.

    So the rules that fire on a question must not contain that question's
    answer. The measured figures live on in two safe places: source COMMENTS,
    which the model never sees, and REJECTION MESSAGES, which appear only after
    the model has already written the wrong query.

    Scoped to the rules whose directive answers their own trigger. The others
    are listed explicitly rather than silently skipped - shrink this list, do
    not grow it.
    """
    import re

    STILL_CARRY_FIGURES = {
        "repairs",             # 150,706 decoy rows vs a true 3,302
        "attendance",          # 393,882 rows in a dead feed
        "bonus_earnings",      # 80,763 FinalLabour - a BLOCKED salary column
        "junk",                # 215,158 / 76,887
        "kapan_value_snapshot",  # 61,221 snapshot rows over 1,050 kapans
    }
    # A BARE NUMBER IS JUST AS RECITABLE AS A COMMA-SEPARATED ONE.
    #
    # This only matched comma-thousands, so "IsVerified is set on 14 rows in
    # the entire database" sailed straight through - and on 2026-09-03 the
    # model answered "14" to "aa varsh ma ketla planning verify thaya che?",
    # TWICE, quoting the dead flag's row count as the year's sign-off total.
    # COUNT-MISMATCH caught it in the log; this test did not.
    #
    # So a digit followed by a countable noun counts too. Bare years and
    # decimals are left alone - it is "<n> rows/packets/..." that reads as an
    # answer the model can give without running SQL.
    RECITABLE = re.compile(
        r"\b\d{1,3}(?:,\d{3})+\b"
        r"|\b\d+\s+(?:rows?|packets?|stones?|kapans?|employees?"
        r"|records?|people|workers?|changes?|plans?)\b",
        re.IGNORECASE,
    )
    offenders = {
        r.name: RECITABLE.findall(r.directive)
        for r in qr.RULES
        if r.name not in STILL_CARRY_FIGURES and RECITABLE.search(r.directive)
    }
    assert not offenders, f"directives handing the model a total: {offenders}"


class TestPlanAttributesComeFromThePlanRow:
    """A PLAN'S PURITY AND SIZE ARE ON THE PLAN ROW, NOT ON THE PACKET.

    Live 2026-09-03. "from kapan QA26 give me packets that has purity between
    FL to VVS2 and size range from 0.3 to 0.80 for marker 2 department" was
    answered off tblPacket - p.Purity and p.CurrentWt - and returned ONE
    packet where the plans Marker-2 created give FOUR.

    The one it returned, packet 301, has a Marker-2 plan proposing PolishedWt
    0.200, outside the band asked for. It matched only because CurrentWt reads
    0.464, which in QA26 is the ROUGH weight: tblPacket.PolishedWt is NULL on
    all 325 of its packets because nothing in the kapan has been cut. A rough
    weight was shown to the user as the stone's size.

    Both columns are enforced because fixing either alone is still wrong:
    packet/packet 1, packet/plan 7, plan/packet 1, plan/plan 4.
    """

    QUESTION = ("from kapan QA26 give me packets that has purity between FL to "
                "VVS2 and size range from 0.3 to 0.80 for marker 2 department")

    BAD = ("SELECT p.PacketNo, p.Purity, p.CurrentWt AS Carats "
           "FROM tblPacket p JOIN tblPlanMaster pm ON p.ID = pm.Packet_ID "
           "WHERE p.Kapan_ID = 1569 AND p.Purity IN ('FL','IF','VVS1','VVS2') "
           "AND p.CurrentWt BETWEEN 0.3 AND 0.80")

    GOOD = ("SELECT ISNULL(pk.PacketNo, pm.PacketName) AS PacketNo, pm.Purity, "
            "CAST(pm.PolishedWt AS decimal(10,3)) AS PlannedWt, e.Code "
            "FROM tblPlanMaster pm "
            "JOIN tblKapan k ON k.ID = pm.KapanId "
            "JOIN tblEmployee e ON e.ID = pm.EmpId "
            "LEFT JOIN tblPacket pk ON pk.ID = pm.Packet_ID "
            "WHERE k.KapanName = 'QA26' "
            "AND REPLACE(e.DepartMentName,' ','') = 'Marker-2' "
            "AND pm.Purity IN ('FL','IF','VVS1','VVS2') "
            "AND pm.PolishedWt BETWEEN 0.30 AND 0.80")

    @pytest.mark.parametrize("q", [
        "give me packets for marker 2 department",
        "plan created by marker-2 in kapan QA26",
        "show me the plans created by marker 3",
        "what did marker2 plan last month",
        # THE RULE IS ABOUT THE QUESTION SHAPE, NOT THE DEPARTMENT NAME.
        # The first draft only fired on "marker <n>" and on the literal
        # phrase "plan(s) created/made", so it covered Marker-2/3/4 and
        # missed every other planning department though the trap is
        # identical. 12 of 18 department/kapan combinations let the wrong
        # SQL through until the trigger was widened.
        "give me packets planned by Blocking with purity VS1",
        "packets planned by Sarin in kapan OM26",
        "give me packets for Dilate department with purity VS1",
        "give me packets for MFG-6 department with clarity VS2",
        "who planned the stones in kapan NY26 for Galaxy",
    ])
    def test_it_fires_on_plan_questions(self, q):
        assert any(r.name == "plan_attributes_from_the_plan_row"
                   for r in qr.RULES if r.applies(q)), q

    @pytest.mark.parametrize("q", [
        # The packet columns are RIGHT for these - the stone as it stands now,
        # or an achieved weight. COLD-07 is the second one.
        "how many oval diamonds do we have in stock?",
        "OQ26 kapan ma final point / final polish weight ketlu nikalyu?",
        "where is packet 301 right now",
        "which packets are lying in marker 2 currently",
    ])
    def test_it_stays_out_of_current_state_questions(self, q):
        assert not any(r.name == "plan_attributes_from_the_plan_row"
                       for r in qr.RULES if r.applies(q)), q

    def test_the_packet_columns_are_rejected(self):
        problems = qr.violations(self.QUESTION, self.BAD)
        assert len(problems) == 2, problems
        assert any("PolishedWt" in p for p in problems)
        assert any("tblPlanMaster.Purity" in p for p in problems)

    def test_fixing_only_the_weight_is_still_rejected(self):
        """packet purity + plan weight returns 7 against a true 4, so the
        purity half must bite on its own."""
        half_fixed = self.BAD.replace(
            "p.CurrentWt BETWEEN 0.3 AND 0.80",
            "pm.PolishedWt BETWEEN 0.30 AND 0.80").replace(
            "p.CurrentWt AS Carats", "pm.PolishedWt AS PlannedWt")
        assert qr.violations(self.QUESTION, half_fixed)

    def test_fixing_only_the_purity_is_still_rejected(self):
        """plan purity + packet weight returns 1 against a true 4."""
        half_fixed = self.BAD.replace("p.Purity IN", "pm.Purity IN")
        assert qr.violations(self.QUESTION, half_fixed)

    def test_the_correct_query_passes(self):
        assert qr.violations(self.QUESTION, self.GOOD) == []

    def test_joining_tblPacket_for_identity_is_not_punished(self):
        """tblPlanMaster.PacketName is NULL on 96% of QA26's marking rows, so
        the packet number HAS to come from tblPacket. Forbidding the table
        rather than the attribute predicates would make the query unwritable."""
        assert "tblPacket" in self.GOOD
        assert qr.violations(self.QUESTION, self.GOOD) == []

    @pytest.mark.parametrize("dept", [
        "Marker-3", "Blocking", "Sarin", "MFG-6", "Dilate", "Galaxy"])
    def test_the_packet_columns_are_rejected_for_any_department(self, dept):
        """Generalisation check: the same wrong SQL must be caught whoever
        planned the stone, and the same right SQL must pass."""
        q = (f"from kapan OM26 give me packets planned by {dept} with "
             "purity VS1 and size 0.4 to 0.9")
        bad = ("SELECT p.PacketNo, p.Purity, p.CurrentWt FROM tblPacket p "
               "JOIN tblPlanMaster pm ON p.ID = pm.Packet_ID "
               "WHERE p.Purity IN ('VS1') AND p.CurrentWt BETWEEN 0.4 AND 0.9")
        good = ("SELECT pk.PacketNo, pm.Purity, pm.PolishedWt "
                "FROM tblPlanMaster pm JOIN tblEmployee e ON e.ID = pm.EmpId "
                "LEFT JOIN tblPacket pk ON pk.ID = pm.Packet_ID "
                "WHERE pm.Purity IN ('VS1') "
                "AND pm.PolishedWt BETWEEN 0.4 AND 0.9")
        assert qr.violations(q, bad), dept
        assert qr.violations(q, good) == [], dept

    def test_the_patterns_carry_no_eaten_backslash(self):
        """The first draft of this rule shipped with every word boundary
        turned into a 0x08 BACKSPACE byte - the failure this file warns about
        in the _ENFORCEMENT header. Assert the bytes, not the intent."""
        r = next(x for x in qr.RULES
                 if x.name == "plan_attributes_from_the_plan_row")
        blobs = ([r.trigger.pattern, r.unless.pattern]
                 + [p for p, _ in r.forbid if not callable(p)])
        assert not any(chr(8) in b for b in blobs), blobs


class TestALabListingIsNotACount:
    """DEMANDING A COUNT REFUSED THE QUESTION.

    Live 2026-09-03. "For kapan OR26, show packets where the MFG grade differs
    from the GIA grade on cut or clarity" is a per-packet LISTING - one row per
    packet, so it cannot carry COUNT(DISTINCT Packet_ID). lab_results fires on
    any mention of GIA and required exactly that, so the guard rejected the
    query; the model then REFUSED the question outright and offered the
    lab_results tool instead.

    What it refused is the query that reproduces the client's own CUT-PURITY
    CHANGE screen packet-for-packet - see test_cut_purity_change.py.

    A false rejection costs a working answer, which this file argues is worse
    than the bug. So a query with NO aggregate has nothing to report in the
    wrong unit and is exempt; anything that DOES aggregate must still count
    packets, and every wrong-unit shape below stays rejected.
    """

    LISTING_Q = ("For kapan OR26, show packets where the MFG grade differs "
                 "from the GIA grade on cut or clarity")
    COUNT_Q = "how many stones went to GIA last month"

    LISTING = ("WITH s AS (SELECT pm.Packet_ID, pm.PacketName, pm.RapVer, "
               "pm.Cut, pm.Purity, pm.EmpCode, ROW_NUMBER() OVER (PARTITION BY "
               "pm.Packet_ID, pm.RapVer ORDER BY pm.ID DESC) rn "
               "FROM tblPlanMaster pm JOIN tblKapan k ON k.ID = pm.KapanId "
               "AND k.KapanName = 'OR26' WHERE ISNULL(pm.IsDamagePlan,0) = 0) "
               "SELECT a.PacketName, a.EmpCode, a.Cut, b.Cut, a.Purity, b.Purity "
               "FROM s a JOIN s b ON b.Packet_ID = a.Packet_ID AND "
               "b.RapVer = 'GIA' AND b.rn = 1 WHERE a.RapVer = 'MFG' AND a.rn = 1 "
               "AND ISNULL(a.Cut,'') <> ISNULL(b.Cut,'')")

    def test_the_per_packet_listing_is_not_rejected(self):
        assert qr.violations(self.LISTING_Q, self.LISTING) == []

    def test_the_right_count_still_passes(self):
        assert qr.violations(
            self.COUNT_Q,
            "SELECT COUNT(DISTINCT pm.Packet_ID) FROM tblPlanMaster pm "
            "WHERE pm.RapVer IN ('GIA','HRD','IGI')") == []

    @pytest.mark.parametrize("sql,why", [
        ("SELECT k.KapanName, COUNT(DISTINCT pm.KapanId) FROM tblPlanMaster pm "
         "JOIN tblKapan k ON k.ID = pm.KapanId WHERE pm.RapVer = 'GIA' "
         "GROUP BY k.KapanName", "COUNT(DISTINCT KapanId) is 1 by construction"),
        ("SELECT COUNT(*) FROM tblPlanMaster pm WHERE pm.RapVer = 'GIA'",
         "COUNT(*) double-counts stage rows"),
        ("SELECT SUM(pm.Amount) FROM tblPlanMaster pm WHERE pm.RapVer = 'GIA'",
         "aggregates without counting packets"),
    ])
    def test_every_wrong_unit_is_still_rejected(self, sql, why):
        assert qr.violations(self.COUNT_Q, sql), why

    def test_the_exemption_needs_no_aggregate_at_all(self):
        """The escape is "no aggregate", not "is a SELECT". A listing that
        also aggregates must still count packets."""
        assert qr.violations(
            self.LISTING_Q,
            "SELECT a.PacketName, COUNT(*) AS n FROM tblPlanMaster a "
            "WHERE a.RapVer = 'GIA' GROUP BY a.PacketName")
