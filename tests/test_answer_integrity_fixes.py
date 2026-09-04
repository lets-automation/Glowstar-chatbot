"""
test_answer_integrity_fixes.py
------------------------------
Regressions for four LIVE answer-corruption bugs found by the 2026-08-25 audit.

Every one of these shipped WRONG output to the user while 851 tests passed - the
existing suite only ever exercised integer totals, named-column salary SQL, and
non-CAST aggregates, so none of these paths had a case.
"""
import pytest

from app.agent import access_guard, facts

_F = lambda totals, rc=30: {"totals": totals, "row_count": rc, "partial": False}  # noqa: E731


class TestDecimalTotalsAreNotMangled:
    """`[\d,]+` could not match a decimal, so it spliced the computed total into
    the middle of a CORRECT number: '1,330.93' -> '1,330.93.93'."""

    @pytest.mark.parametrize("prose,total", [
        ("A total of 1,330.93 carats.", "1,330.93"),
        ("In total, 76.16 carats were produced.", "76.16"),
        ("The kapan produced 76.16 carats in total.", "76.16"),
        ("Overall, 1,022.5 points.", "1,022.5"),
    ])
    def test_a_correct_decimal_total_is_left_alone(self, prose, total):
        out, fixed = facts.correct_total_claims(prose, _F({"TotalWt": total}))
        assert out == prose, "a correct decimal total must never be rewritten"
        assert fixed == []

    def test_a_wrong_decimal_total_is_still_corrected_whole(self):
        out, fixed = facts.correct_total_claims(
            "A total of 1,250.10 carats.", _F({"TotalWt": "1,330.93"}))
        assert out == "A total of 1,330.93 carats."
        assert fixed == [("1,250.10", "1,330.93")]


class TestTheRewriterIsUnitAndContextAware:
    """It rewrote any number near total-wording, including years and nouns the
    query never counted."""

    def test_a_year_is_never_a_total(self):
        prose = "Overall, 2026 production grew."
        assert facts.correct_total_claims(prose, _F({"TotalPackets": "1,022"}))[0] == prose

    def test_a_number_the_user_supplied_is_never_rewritten(self):
        prose = "In total, 2025 damage was recorded."
        out, _ = facts.correct_total_claims(
            prose, _F({"TotalPackets": "1,022"}), "damage in 2025")
        assert out == prose

    @pytest.mark.parametrize("prose", [
        "Across a total of 5 departments the work was split.",
        "a total of 30 days in June",
        "In total, 3 months were covered.",
    ])
    def test_a_noun_the_query_never_counted_is_not_rewritten(self, prose):
        assert facts.correct_total_claims(prose, _F({"TotalPackets": "1,022"}))[0] == prose

    def test_the_one_correction_it_exists_for_still_happens(self):
        """The 2026-08-24 demo failure: model said 2,403, data said 2,562."""
        out, fixed = facts.correct_total_claims(
            "In total, 2,403 packets were sent.", _F({"PNo": "2,562"}))
        assert out == "In total, 2,562 packets were sent."
        assert fixed == [("2,403", "2,562")]


class TestCastWrappedAggregatesAreTotalled:
    """`CAST(SUM(x) AS decimal(14,3)) AS PWt` matched the type cast as the alias,
    so the carat total silently vanished and the model added it up by hand."""

    SQL = ("SELECT k.KapanName, COUNT(DISTINCT g.Packet_ID) AS PNo, "
           "CAST(SUM(ISNULL(g.PolishedWt,0)) AS decimal(14,3)) AS PWt "
           "FROM tblGIAResult g GROUP BY k.KapanName")

    def test_the_real_alias_is_totalable(self):
        assert "PWt" in facts.aggregate_columns(self.SQL)

    def test_the_sql_type_is_not_mistaken_for_a_column(self):
        assert "decimal" not in facts.aggregate_columns(self.SQL)


class TestDistinctTotalsOnlyWhenAdditive:
    """Summing per-group DISTINCT counts is only valid when each entity belongs
    to one group. Grouped by month it published 374 where the truth was 163."""

    def test_distinct_grouped_by_a_time_bucket_is_withheld(self):
        sql = ("SELECT MONTH(CreatDate) AS M, COUNT(DISTINCT EmpId) AS Workers "
               "FROM tblPlanMaster GROUP BY MONTH(CreatDate)")
        assert "Workers" not in facts.aggregate_columns(sql)

    def test_distinct_grouped_by_an_owning_entity_is_kept(self):
        """A packet belongs to exactly one kapan - this is the client's figure."""
        sql = ("SELECT k.KapanName, COUNT(DISTINCT g.Packet_ID) AS Packets "
               "FROM tblPlanMaster g GROUP BY k.KapanName")
        assert "Packets" in facts.aggregate_columns(sql)

    def test_a_recipe_declaration_is_never_filtered(self):
        sql = "-- lab_results_report(a,b) | totals: PNo, PWt"
        assert facts.aggregate_columns(sql) == {"PNo", "PWt"}


class TestSalaryCannotEscapeThroughAStarProjection:
    """sql_selects_pay_data reads the SQL TEXT, and `*` names no column. The
    result really came back carrying live wage values."""

    @pytest.mark.parametrize("sql", [
        "SELECT * FROM tblLabourResult",
        "SELECT t.* FROM tblPointRateLabour t",
    ])
    def test_the_text_check_alone_does_not_catch_a_star(self, sql):
        assert access_guard.sql_selects_pay_data(sql) is False

    def test_pay_columns_are_redacted_from_the_result(self):
        cols = ["PacketNo", "LabourAmount", "FinalLabour", "Wt"]
        rows = [{"PacketNo": "P1", "LabourAmount": 0.7, "FinalLabour": 0.64, "Wt": 1.2}]
        keep, clean, dropped = access_guard.redact_pay_columns(cols, rows)
        assert keep == ["PacketNo", "Wt"]
        assert set(dropped) == {"LabourAmount", "FinalLabour"}
        assert clean == [{"PacketNo": "P1", "Wt": 1.2}]

    def test_bonus_and_incentive_columns_are_untouched(self):
        """Bonus/incentive ARE allowed - redaction must not over-reach."""
        cols = ["BonusAmount", "BonusPoint", "CreditPoints", "DebitPoints"]
        rows = [{c: 1 for c in cols}]
        keep, clean, dropped = access_guard.redact_pay_columns(cols, rows)
        assert dropped == [] and keep == cols and clean == rows

    def test_redaction_never_raises(self):
        assert access_guard.redact_pay_columns(None, None)[2] == []


class TestAveragesAndSuperlativesAreComputed:
    """The model saw 30 rows and worked averages and superlatives out over that
    sample. Measured live on 861 kapan groups sorted DESC: the true average per
    kapan is 1,529.24 and the mean of the first 30 rows is 6,495.93 - a 325%
    overstatement. Sorting makes it worse, because the preview is the top of the
    distribution."""

    SQL = "SELECT k.KapanName, COUNT(*) AS Plans FROM t GROUP BY k.KapanName"

    def _rows(self, values):
        return [{"KapanName": f"K{i}", "Plans": v} for i, v in enumerate(values)]

    def test_average_is_over_every_row_not_the_preview(self):
        rows = self._rows([100] * 30 + [10] * 70)   # preview is 100, truth is 37
        f = facts.compute(self.SQL, ["KapanName", "Plans"], rows)
        assert f["row_count"] == 100
        assert f["derived"]["Plans"]["avg"] == "37"

    def test_the_highest_row_is_named_with_its_share(self):
        f = facts.compute(self.SQL, ["KapanName", "Plans"], self._rows([10, 60, 30]))
        hi = f["derived"]["Plans"]["max"]
        assert hi["value"] == "60" and hi["label"] == "K1" and hi["share"] == "60.0%"

    def test_the_lowest_row_is_named_without_a_noisy_share(self):
        f = facts.compute(self.SQL, ["KapanName", "Plans"], self._rows([10, 60, 30]))
        lo = f["derived"]["Plans"]["min"]
        assert lo["value"] == "10" and lo["label"] == "K0" and "share" not in lo

    def test_the_model_note_carries_them(self):
        note = facts.as_model_note(
            facts.compute(self.SQL, ["KapanName", "Plans"], self._rows([10, 60, 30])))
        assert "avg Plans/row=" in note
        assert "highest Plans=60" in note and "60.0% of total" in note

    def test_a_non_totalable_column_gets_no_average(self):
        """Only additive columns reach _derived - an average of a per-group AVG()
        would need weights and is deliberately not attempted."""
        sql = "SELECT KapanName, AVG(Wt) AS AvgWt FROM t GROUP BY KapanName"
        f = facts.compute(sql, ["KapanName", "AvgWt"],
                          [{"KapanName": "K1", "AvgWt": 5}])
        assert f["derived"] == {} and f["totals"] == {}

    def test_an_empty_result_is_safe(self):
        f = facts.compute(self.SQL, ["KapanName", "Plans"], [])
        assert f["derived"] == {} and f["row_count"] == 0


class TestPeriodIsEnforcedBeforeExecution:
    """period_guard also runs in postprocess, but by then the answer already
    reports all-time numbers and all it can do is warn: "production in May 2026"
    from an unfiltered tblFinalPacket shows 179,990 where May is 3,227 - 56x.
    Rejecting pre-execution means the wrong number is never produced."""

    from app.agent import period_guard as _pg

    Q = "production in May 2026"

    def test_an_unfiltered_dated_query_is_rejected(self):
        msg = self._pg.missing_period_filter(self.Q, "SELECT COUNT(*) FROM tblFinalPacket")
        assert msg and "BLOCKED" in msg

    def test_the_rejection_names_the_correct_date_column(self):
        """The spellings are one letter apart and the note must not be trusted:
        tblFinalPacket=CreateDate, tblPlanMaster=CreatDate. Both were read out of
        INFORMATION_SCHEMA on 2026-08-26."""
        assert "tblFinalPacket.CreateDate" in self._pg.missing_period_filter(
            self.Q, "SELECT COUNT(*) FROM tblFinalPacket")
        assert "tblPlanMaster.CreatDate" in self._pg.missing_period_filter(
            self.Q, "SELECT COUNT(*) FROM tblPlanMaster")

    @pytest.mark.parametrize("q,sql", [
        # already filtered - including via a subquery, which is why the SQL is
        # scanned as raw text
        ("production in May 2026", "SELECT COUNT(*) FROM tblFinalPacket WHERE CreateDate>='2026-05-01'"),
        ("production in May 2026", "SELECT COUNT(*) FROM tblFinalPacket WHERE Id IN (SELECT Id FROM x WHERE CreatDate>='2026-05-01')"),
        # no bounded period named
        ("total production", "SELECT COUNT(*) FROM tblFinalPacket"),
        # all-time is explicitly what was asked
        ("production of all time", "SELECT COUNT(*) FROM tblFinalPacket"),
        # "may" the modal verb, not the month
        ("may I see the stock summary", "SELECT COUNT(*) FROM tblFinalPacket"),
        # current state, not a period
        ("atyare ketla diamond hold par che",
         "SELECT COUNT(*) FROM tblPacket p JOIN tblKapan k ON p.Kapan_ID=k.ID WHERE k.IsOnHold=1"),
        # table is not whitelisted -> degrade to the postprocess banner
        ("production in May 2026", "SELECT COUNT(*) FROM tblDepartMent"),
        # a recipe call carries its own dates
        ("production in May 2026", "-- department_report(MFG-1, 2026-05-01, 2026-06-01)"),
    ])
    def test_it_does_not_reject_a_legitimate_query(self, q, sql):
        assert self._pg.missing_period_filter(q, sql) == ""

    def test_no_cold_case_ground_truth_sql_is_rejected(self):
        """THE safety property. A false rejection costs a wasted round on a
        question that was already right, so every ground-truth SQL in the cold
        suite must pass untouched."""
        from scripts.cold_cases import COLD_CASES

        bad = [c["id"] for c in COLD_CASES
               if c.get("truthSql")
               and self._pg.missing_period_filter(c.get("question", ""), c["truthSql"])]
        assert bad == [], f"false rejections: {bad}"

    def test_the_whitelist_only_holds_verified_columns(self):
        """Every entry was read from INFORMATION_SCHEMA. tblGIAResult is absent
        because that table does not exist, and a table with no date column must
        never be added - it would make an unfilterable query unanswerable."""
        assert "tblGIAResult" not in self._pg._PERIOD_DATE_COLUMN
        assert self._pg._PERIOD_DATE_COLUMN["tblFinalPacket"] == "CreateDate"
        assert self._pg._PERIOD_DATE_COLUMN["tblPlanMaster"] == "CreatDate"
        assert self._pg._PERIOD_DATE_COLUMN["tblJunk"] == "CreateDate"  # not IssueDate


class TestCountGuardSeesEveryQuery:
    """count_guard was blind to every query but the captured winner.

    Measured over 95 logged COUNT-MISMATCH hits (2026-08-26): 81 - 85% - were on
    a result holding exactly ONE row. A 1-row result is an aggregate, so the row
    CONTAINS the count; comparing "4,007 packets" against "1 row" is meaningless
    and the answer was right. That is why the guard could never be escalated
    beyond log-only: it would have "corrected" correct answers.
    """

    WINNER = [{"Department": "Fency", "Packets": 19}]
    SQL = ["SELECT COUNT(*) FROM tblFinalPacket"]
    Q = "Fency department production for June 2026"

    def _sections(self, value):
        return [{"title": "Total", "columns": ["Packets"], "rows": [{"Packets": value}]}]

    def test_the_real_logged_false_positive_is_gone(self):
        from app.agent import count_guard as cg

        answer = "Fency department produced 4,007 packets in June 2026."
        assert cg.count_mismatch(answer, self.WINNER, 1, self.Q, self.SQL) is not None
        assert cg.count_mismatch(answer, self.WINNER, 1, self.Q, self.SQL,
                                 sections=self._sections(4007)) is None

    def test_a_genuinely_wrong_count_is_still_caught(self):
        from app.agent import count_guard as cg

        hit = cg.count_mismatch("In total, 9,999 packets were produced.",
                                self.WINNER, 1, self.Q, self.SQL,
                                sections=self._sections(4007))
        assert hit == (9999, "packets")

    def test_widening_can_only_reduce_firing(self):
        """The safety property: extra supported values can never CREATE a
        mismatch, so this change cannot introduce a new false positive."""
        from app.agent import count_guard as cg

        answer = "There were 4,007 packets and 250 stones."
        narrow = cg.count_mismatch(answer, self.WINNER, 1, self.Q, self.SQL)
        wide = cg.count_mismatch(answer, self.WINNER, 1, self.Q, self.SQL,
                                 sections=self._sections(4007))
        assert narrow is not None
        assert wide is None or wide != narrow

    def test_malformed_sections_are_ignored(self):
        from app.agent import count_guard as cg

        for junk in ([None], [{}], [{"rows": None}], ["not a dict"], []):
            cg.count_mismatch("There were 4,007 packets.", self.WINNER, 1,
                              self.Q, self.SQL, sections=junk)


class TestRecipeDateRangesFailLoudly:
    """Reported live 2026-08-26: "Provide me GIA results of may month" answered
    "I wasn't able to pull that from the database just now... could you
    rephrase?" - while "last month GIA results" worked.

    The recipe ran on unparseable dates and returned its confident header ("the
    figures below are already computed and reconciled against their ERP") with
    NO figures under it. The model was right to refuse, but nothing told it the
    DATES were the problem, so it could not recover and blamed the question."""

    from app.agent import reports as _r

    @pytest.mark.parametrize("a,b", [
        ("may", "month"), ("", ""), ("2026-5-1", "2026-6-1"), ("not-a-date", "2026-06-01"),
    ])
    def test_an_unusable_range_is_rejected(self, a, b):
        msg = self._r.invalid_period(a, b)
        assert msg.startswith("BLOCKED")
        assert "YYYY-MM-DD" in msg

    def test_the_rejection_tells_the_model_not_to_ask_the_user(self):
        """The user's question was already clear; only the tool call was wrong."""
        assert "do NOT ask the user" in self._r.invalid_period("may", "month")

    def test_a_reversed_range_is_rejected(self):
        assert "must be AFTER" in self._r.invalid_period("2026-06-01", "2026-05-01")

    def test_the_end_exclusive_off_by_one_is_rejected(self):
        """from=1st, to=last-day-of-the-same-month reads as "the whole month" but
        end-exclusive it silently drops a day: May 2026 as 05-01..05-31 returns
        2,495 packets instead of 2,562. Nothing about that answer looks wrong."""
        msg = self._r.invalid_period("2026-05-01", "2026-05-31")
        assert "LAST DAY" in msg and "2026-06-01" in msg

    @pytest.mark.parametrize("a,b", [
        ("2026-05-01", "2026-06-01"),   # a whole month, correctly end-exclusive
        ("2026-05-01", "2026-05-15"),   # a genuine part-month range
        ("2026-01-01", "2027-01-01"),   # a whole year
        ("2026-05-31", "2026-06-30"),   # not starting on the 1st - not the trap
    ])
    def test_a_valid_range_passes(self, a, b):
        assert self._r.invalid_period(a, b) == ""


class TestUndisclosedScopeIsDisclosed:
    """Reported live 2026-08-26. "Provide me last month GIA results employee
    wise" named no department, but the model passed department='Fency' (the
    by-employee section only exists when a department is given). The answer then
    opened "Overall, 1,643 packets across 27 kapans" - one department presented
    as the company. July's true figure is 3,692 across 39 kapans, so 56% of the
    work vanished and nothing on screen said "Fency"."""

    from app.agent import reports as _r

    SQL = ["SELECT ... WHERE e.DepartMentName = 'Fency' AND g.CreatDate>='2026-07-01'"]

    def test_a_filter_the_user_never_named_is_disclosed(self):
        out = self._r.undisclosed_scope(
            "Provide me last month GIA results employee wise", self.SQL)
        assert "Fency" in out and "not the" in out

    def test_a_filter_the_user_did_name_gets_the_plain_form(self):
        """Named or chosen, the scope is still STATED - it just loses the nudge
        back to the company-wide figure."""
        out = self._r.scope_line("GIA results for Fency department last month", self.SQL)
        assert "Fency" in out and "not the whole company" not in out
        assert self._r.undisclosed_scope(
            "GIA results for Fency department last month", self.SQL) == ""

    def test_a_resolved_spelling_still_counts_as_named(self):
        """The user types "MFG 1", the recipe resolves "MFG - 1" - same thing."""
        assert self._r.undisclosed_scope(
            "report of MFG 1 for July", ["WHERE e.DepartMentName = 'MFG - 1'"]) == ""

    def test_an_unfiltered_query_is_not_flagged(self):
        assert self._r.scope_line("GIA results last month",
                                  ["SELECT COUNT(*) FROM t"]) == ""

    def test_the_period_is_rendered_inclusively(self):
        """The SQL is END-EXCLUSIVE. A line reading "1 Aug" over a July report
        would contradict the very report it labels."""
        sql = ["WHERE e.DepartMentName='Fency' AND d >= '2026-07-01' AND d < '2026-08-01'"]
        assert "July 2026" in self._r.scope_line("Fency", sql)
        part = ["WHERE e.DepartMentName='Fency' AND d >= '2026-07-05' AND d < '2026-07-13'"]
        assert "12 Jul" in self._r.scope_line("Fency", part)

    def test_a_chosen_filter_is_still_stated(self):
        """The live case: the user tapped a "Fency" chip, so the question WAS
        "Fency" - correct data, but the prose said "Overall" and never said
        Fency. Stating the scope is what makes the exported answer verifiable."""
        assert "Fency" in self._r.scope_line("Fency", self.SQL)

    def test_it_never_touches_numbers(self):
        """It only ever prepends a sentence, so a false positive costs one
        redundant line - never a changed figure."""
        out = self._r.undisclosed_scope("anything", self.SQL)
        assert out.startswith(">") and "1,643" not in out


class TestTheWriteUpLeadsWithTheDimensionAsked:
    """Reported live 2026-08-26: the user asked for GIA results "employee wise".
    The recipe correctly built a "By employee" section, then told the model to
    "present the summary and the BY-KAPAN table" - hardcoded. The model obeyed,
    narrated kapans, and never mentioned the employee table it had just built
    (it reached the Excel, unread)."""

    from app.agent import reports as _r

    def _lead(self, dept):
        import re
        t = self._r.lab_results_report("2026-07-01", "2026-08-01", "", dept)["text"]
        m = re.search(r"Present the summary and the ([\w-]+) table", t)
        return m.group(1) if m else None

    def test_a_department_report_leads_with_employees(self):
        """A by-employee section exists only when a department was given, which
        is exactly when the user asked about people."""
        assert self._lead("Fency") == "by-employee"

    def test_a_company_wide_report_still_leads_with_kapans(self):
        assert self._lead("") == "by-kapan"

    def test_the_helper_follows_the_sections_actually_built(self):
        assert self._r._lead_table([("Summary", ""), ("By employee", "")]) == "by-employee"
        assert self._r._lead_table([("Summary", ""), ("By kapan", "")]) == "by-kapan"


class TestSuperlativesOnNonAdditiveColumns:
    """Reported live 2026-08-26. A Fency lab report said "PJ26 had the largest
    negative difference at -7.79%". The true lowest DiffPer is NT26 at -10.0%.

    DiffPer is a PERCENTAGE, deliberately excluded from `totalable` because
    summing it is nonsense - which meant no extremes were computed for it and
    the superlative was left to the model. Percentages and rates are exactly the
    columns a write-up makes superlative claims about.

    The principle: min/max are a scan of the complete result and are ALWAYS
    exact. Only sum and average need additivity."""

    SQL = "SELECT Kapan, COUNT(*) AS PNo, AVG(x) AS DiffPer FROM t GROUP BY Kapan"
    ROWS = [{"Kapan": "OP26", "PNo": 11, "DiffPer": 32.5},
            {"Kapan": "PJ26", "PNo": 27, "DiffPer": -7.79},
            {"Kapan": "NT26", "PNo": 1, "DiffPer": -10.0}]

    def _f(self):
        return facts.compute(self.SQL, ["Kapan", "PNo", "DiffPer"], self.ROWS)

    def test_the_percentage_column_gets_extremes(self):
        d = self._f()["derived"]["DiffPer"]
        assert d["max"]["value"] == "32.5" and d["max"]["label"] == "OP26"
        assert d["min"]["value"] == "-10" and d["min"]["label"] == "NT26"

    def test_the_percentage_column_gets_NO_average_or_total(self):
        """A mean of per-group percentages needs weights - it would be a new
        wrong number, which is the whole failure mode being removed."""
        f = self._f()
        assert "DiffPer" not in f["totals"]
        assert "avg" not in f["derived"]["DiffPer"]

    def test_the_note_names_the_lowest(self):
        note = facts.as_model_note(self._f())
        assert "lowest DiffPer=-10 (NT26)" in note

    def test_the_label_column_is_not_treated_as_a_metric(self):
        assert "Kapan" not in self._f()["derived"]

    def test_a_column_with_one_number_is_skipped(self):
        f = facts.compute("SELECT a, b FROM t", ["a", "b"],
                          [{"a": "x", "b": 5}, {"a": "y", "b": None}])
        assert "b" not in f["derived"]


class TestAdvisoryRulesAreEnforced:
    """A query_rules Rule with no require_all/forbid is a SUGGESTION.

    Verified end-to-end on Gemini 2026-08-26: the `damage` directive DID fire on
    "2025 ma damage na ketla paisa katya karigar pase thi?" and the answer still
    came back -14,816.33, where the damage register gives -11,536.82. Firing is
    not enforcing - which is the whole lesson of this file.
    """

    from app.agent import query_rules as _qr

    Q = "2025 ma damage na ketla paisa katya karigar pase thi?"

    def test_the_correct_source_passes(self):
        sql = ("SELECT SUM(Amount) FROM tblPlanReport WHERE IsDamageReport=1 "
               "AND CreatedDate>='2025-01-01' AND CreatedDate<'2026-01-01'")
        assert self._qr.violations(self.Q, sql) == []

    @pytest.mark.parametrize("sql", [
        "SELECT SUM(Amount) FROM tblPlanMaster WHERE IsDamagePlan=1",
        "SELECT SUM(BonusAmount) FROM tblPointRateLabour WHERE BonusAmount<0",
    ])
    def test_a_wrong_source_is_rejected(self, sql):
        assert self._qr.violations(self.Q, sql), f"not rejected: {sql}"

    def test_the_plan_row_flag_is_forbidden_for_a_damage_total(self):
        """IsDamagePlan gives a different count (175 vs 179 for July 2026)."""
        v = self._qr.violations(
            self.Q, "SELECT SUM(Amount) FROM tblPlanReport WHERE IsDamagePlan=1")
        assert any("IsDamagePlan" in x for x in v)


class TestEnforcementOnlyBlocksActivelyWrongSources:
    """A forbid must fire where the query returns a WRONG number, never merely
    an EMPTY one.

    The first draft of _ENFORCEMENT also forbade tblPacketSell, tblJunk.Grede,
    ChapkaLoss, IsMatchPair and tblTimeAttendance - all verified dead. Replaying
    the 40 cold-case ground-truth SQLs rejected SIX, and those six turned out to
    be PROOF queries: the correct answer to "junk grade-wise report" is "grade is
    not recorded", and you establish that with
        SELECT COUNT(DISTINCT Grede) FROM tblJunk WHERE Grede IS NOT NULL
    Forbidding the dead column forbids proving it is dead. An empty result is
    self-describing; a wrong one is not."""

    from app.agent import query_rules as _qr

    def test_no_cold_case_truth_sql_is_rejected_by_the_new_enforcement(self):
        """THE safety bar. Only the three PRE-EXISTING rules may reject, and
        those are tracked separately - the enforcement added here adds none."""
        from scripts.cold_cases import COLD_CASES

        pre_existing = {"COLD-05", "EDA-1", "CT-04"}
        bad = [c["id"] for c in COLD_CASES
               if c.get("truthSql")
               and self._qr.violations(c.get("question", ""), c["truthSql"])
               and c["id"] not in pre_existing]
        assert bad == [], f"new enforcement falsely rejects: {bad}"

    @pytest.mark.parametrize("q,sql", [
        # proving a dead source is empty must stay legal
        ("junk grade wise report",
         "SELECT COUNT(DISTINCT Grede) AS n FROM tblJunk WHERE Grede IS NOT NULL"),
        ("what are our sales", "SELECT COUNT(*) AS n FROM tblPacketSell"),
        ("boil and chapka loss",
         "SELECT COUNT(*) AS n FROM tblKapan WHERE ISNULL(ChapkaLoss,0) <> 0"),
        ("match pair report",
         "SELECT COUNT(*) AS n FROM tblPlanMaster WHERE IsMatchPair = 1"),
    ])
    def test_a_proof_query_on_an_empty_source_is_allowed(self, q, sql):
        assert self._qr.violations(q, sql) == []

    @pytest.mark.parametrize("q,sql", [
        ("how many packets on hold",
         "SELECT COUNT(*) FROM tblPacket p WHERE p.IsOnHold = 1"),
        ("fluorescent breakdown", "SELECT Fluorescent FROM tblPacket"),
    ])
    def test_an_actively_wrong_source_is_still_rejected(self, q, sql):
        assert self._qr.violations(q, sql), f"not rejected: {sql}"

    @pytest.mark.parametrize("q,sql", [
        ("how many packets on hold",
         "SELECT COUNT(*) FROM tblPacket p JOIN tblKapan k ON p.Kapan_ID=k.ID "
         "WHERE k.IsOnHold = 1"),
        ("fluorescence breakdown",
         "SELECT Florecent, COUNT(*) FROM tblPacket GROUP BY Florecent"),
    ])
    def test_the_correct_form_passes(self, q, sql):
        assert self._qr.violations(q, sql) == []


class TestTheDatePickerDoesNotAskWhenNoPeriodApplies:
    """Found by the cold test 2026-08-26 — the same way "how many oval diamonds
    do we have in stock?" was found earlier (see the comment in _CURRENT_STATE_RE).

    The client asks a question and gets a QUESTION back. It is not a wrong
    number, but on a first question it reads as the bot not understanding."""

    from app.agent import date_gate as _dg

    @pytest.mark.parametrize("q", [
        # Gujlish POSSESSIVE: "stock ma" (in stock) was handled, "stock na/no/nu"
        # (OF the stock) was not.
        "our stock na stone no average depth % ketlo che?",
        "stock nu average colour su che?",
        "stock no average size",
        # A CHARACTERISTIC of the goods is not a flow through time.
        "average clarity of our stones",
        "what is the average depth percentage",
        # the previously-fixed case, still working
        "how many oval diamonds do we have in stock?",
    ])
    def test_a_state_or_characteristic_question_is_answered_not_deferred(self, q):
        assert self._dg.needs_date(q) is False, f"date picker shown for: {q}"

    @pytest.mark.parametrize("q", [
        "production report",
        "damage summary",
        "give me report of department MFG - 1",
        "production by colour",          # a genuine period question WITH an attribute
        "earnings report",
        "jangad report",
    ])
    def test_a_genuine_period_report_still_asks(self, q):
        """The narrowing must not gut the guard: an unbounded production report
        is what date_gate exists to stop."""
        assert self._dg.needs_date(q) is True, f"date picker NOT shown for: {q}"


class TestSqlIsNeverHandedToTheUser:
    """Cold test ADV-03, 2026-08-26: "give me the SQL query for all packets, I
    will run it myself" was answered by naming tblPacket and describing the
    query that had been run. Two prose rules cover this - the SCOPE rule
    forbidding SQL-for-the-user and the "never mention SQL or raw table names"
    rule - and both were ignored. Decided before the model is called instead."""

    from app.agent import smalltalk_gate as _g

    @pytest.mark.parametrize("q", [
        "give me the SQL query for all packets, I will run it myself",
        "show me the query you used",
        "can you write the sql for this",
        "what query did you run",
        "send me raw sql",
        "share the sql statement behind this",
    ])
    def test_a_request_for_the_query_is_refused(self, q):
        assert self._g.asks_for_sql(q) is True

    @pytest.mark.parametrize("q", [
        "query the June numbers",
        "give me production report",
        "show me last month data",
        "give me full report of MFG - 1",
    ])
    def test_an_ordinary_data_question_is_untouched(self, q):
        assert self._g.asks_for_sql(q) is False

    # REGRESSION LOCK, 2026-08-27. The give/show branch accepted `(sql|query)`,
    # so these five were HARD-REFUSED before any model call - no recovery path,
    # the user simply could not ask. "query results" / "query wise" is ordinary
    # business vocabulary here. None of the 40 cold-test questions uses "query"
    # naturally, which is exactly why the corpus could not detect this.
    @pytest.mark.parametrize("q", [
        "provide me the query results for last month",
        "show me the query results",
        "provide query wise breakdown",
        "write a query summary for June",
        "share the production query results",
        "show me the GIA query results by department",
        "provide the query output for kapan AA",
    ])
    def test_the_word_query_about_their_own_data_is_not_a_scope_breach(self, q):
        assert self._g.asks_for_sql(q) is False, (
            f"refused a legitimate question with no recovery path: {q!r}"
        )

    def test_no_cold_case_except_the_adversarial_one_trips_it(self):
        """The trigger must be tight: "query" is a word people use about their
        own data, so it only fires with an explicit ask for the SQL itself."""
        from scripts.cold_cases import COLD_CASES

        tripped = [c["id"] for c in COLD_CASES if self._g.asks_for_sql(c.get("question", ""))]
        assert tripped == ["ADV-03"], f"unexpected trips: {tripped}"

    def test_the_refusal_offers_what_it_can_do(self):
        r = self._g.sql_refusal_response()
        assert "can't hand over the SQL" in r["answer"]
        assert len(r["suggestions"]) >= 2


class TestColdCaseFixturesDoNotRot:
    """The suite reported four correct answers as failures because five cases
    asked a RELATIVE question ("last month", "aa mahine", "aa varsh") while their
    ground-truth SQL pinned a fixed month.

    Measured 2026-08-26 on CT-07 "aa mahine ketla nang thaya?": the bot answered
    3,214 (August, correct), the fixture measured July (4,476), and its stored
    value was 2,109 (pre-restore) - wrong twice over. A test that lies about the
    system is worse than no test, because you stop reading it."""

    from scripts import cold_cases as _cc

    RELATIVE = ("last month", "this month", "aa mahine", "chalu mahina",
                "aa varsh", "aa varshe", "this year", "last year")

    def test_no_relative_question_pins_a_date_literal(self):
        import re

        bad = []
        for c in self._cc.COLD_CASES:
            q = (c.get("question") or "").lower()
            sql = c.get("truthSql") or ""
            if any(w in q for w in self.RELATIVE) and re.search(r"'20\d\d-\d\d-\d\d'", sql):
                # resolved tokens are fine - they were computed from today
                if not self._is_current(sql):
                    bad.append(c["id"])
        assert bad == [], f"these cases will rot next month: {bad}"

    def _is_current(self, sql):
        """A resolved token always lands inside the current or adjacent year."""
        import re
        from datetime import date

        years = {int(y) for y in re.findall(r"'(20\d\d)-\d\d-\d\d'", sql)}
        now = date.today().year
        return years and all(now - 2 <= y <= now + 1 for y in years)

    def test_every_token_resolves(self):
        left = [c["id"] for c in self._cc.COLD_CASES if "{" in (c.get("truthSql") or "")]
        assert left == [], f"unresolved period tokens: {left}"

    def test_the_periods_are_half_open_and_ordered(self):
        p = self._cc._PERIODS
        assert p["{LAST_MONTH_END}"] == p["{THIS_MONTH_START}"], "ranges must abut"
        assert p["{LAST_MONTH_START}"] < p["{LAST_MONTH_END}"]
        assert p["{THIS_MONTH_START}"] < p["{THIS_MONTH_END}"]
        assert p["{YEAR_START}"] < p["{YEAR_END}"]

    def test_month_overflow_normalises(self):
        """January must roll back to the previous December, not month 0."""
        from datetime import date

        assert self._cc._month_first(2026, 0) == date(2025, 12, 1)
        assert self._cc._month_first(2026, 13) == date(2027, 1, 1)


class TestTheScopeBannerCanAlwaysNameItsPeriod:
    """The banner interpolates period_phrase(), which fell back to the literal
    string "that period" - so two client-facing answers opened with
    "you asked about **that period**, but this result is not filtered to that
    period". Gibberish, found by the cold test 2026-08-26 (EDA-1, CT-05).

    Suppressing the banner instead was tried first and LOST a legitimate warning
    (test_a_genuinely_unfiltered_query_still_warns in test_report_presentation).
    So the phrase is NAMED rather than the warning dropped."""

    from app.agent import period_guard as _pg
    from app.agent import date_gate as _dg

    @pytest.mark.parametrize("q,expected", [
        ("provide total number of kapan wise by lab wise for may month", "May"),
        ("Provide me GIA results of may month", "May"),
        ("production in May 2026", "May 2026"),
        ("damage last month", "last month"),
        # Gujlish periods rendered in English for the banner
        ("Aa mahine ketla nang vechya", "this month"),
        ("gaya mahine nu production", "last month"),
    ])
    def test_a_real_period_is_named(self, q, expected):
        assert self._pg.period_phrase(q) == expected

    def test_may_the_modal_verb_is_not_a_month(self):
        """_MONTHS deliberately omits bare "may"; the May patterns are
        context-qualified so "may I see..." stays unnamed."""
        assert self._pg.period_phrase("may I see the stock summary") == \
            self._pg._UNKNOWN_PERIOD

    def test_a_question_with_no_period_is_never_bannered(self):
        """"Aaje" (today) is a current-state question - the banner claimed the
        user had asked about a period when they had asked for a headcount."""
        for q in ("Aaje factory ma total ketla mansu (worker) chhe?",
                  "how many workers today",
                  "how many employees are there"):
            assert self._pg.unfiltered_period(
                q, ["SELECT COUNT(*) AS n FROM tblEmployee"], [{"n": 1}]) is False

    def test_aaje_is_recognised_as_current_state(self):
        assert self._dg.asks_current_state("Aaje factory ma total ketla mansu chhe?")
        assert self._dg.asks_current_state("how many workers today")
        assert not self._dg.asks_current_state("production last month")

    def test_a_nameable_period_left_unfiltered_still_warns(self):
        """The guard must not have been gutted by the naming fix."""
        assert self._pg.unfiltered_period(
            "production in May 2026",
            ["SELECT COUNT(*) AS n FROM tblFinalPacket"], [{"n": 1}]) is True


class TestBlockedQueriesAreNotRecordedAsSources:
    """tool_run_sql returned result["sql"] on failure, so a query that NEVER RAN
    landed in sql_used - and everything downstream treats sql_used as where the
    answer came from: postprocess.build_citation names it, export_query can pick
    it for the download, and period_guard, undisclosed_scope and count_guard all
    inspect it.

    Cold test ADV-07 (2026-08-26): the model reached for tblTimeAttendance_Demo,
    sql_guard blocked it, no fabricated data reached the user - but the blocked
    statement was still recorded as a source."""

    from app.agent import tools as _t
    from app.agent import query_rules as _qr

    def _run(self, sql):
        self._qr.set_question("test")
        return self._t.run_tool("run_sql", {"query": sql})[:5]

    def test_a_blocked_stale_copy_is_not_recorded(self):
        text, sql, *_ = self._run("SELECT COUNT(*) AS n FROM tblTimeAttendance_Demo")
        assert sql == "", "a blocked query must not appear as a source"
        assert text.startswith("ERROR"), "the model must still see why"

    def test_a_failed_query_is_not_recorded(self):
        text, sql, *_ = self._run("SELECT COUNT(*) AS n FROM tblNoSuchTable")
        assert sql == "" and text.startswith("ERROR")

    def test_a_successful_query_is_still_recorded(self):
        text, sql, *_ = self._run("SELECT COUNT(*) AS n FROM tblEmployee")
        assert "tblEmployee" in sql and not text.startswith("ERROR")


class TestLossQuestionsMustReadALossColumn:
    """Cold test COLD-02: "June ma manufacturing ma ketlu value loss thayu?" -
    true answer 1,382.894 carats (tblPacketHistory.WightLoss). The model
    differenced two money columns and answered "manufacturing ADDED value -
    Rs 108,394.66 higher": wrong metric, wrong sign, and a currency symbol on a
    figure that is not money."""

    from app.agent import query_rules as _qr

    Q = "June ma manufacturing ma ketlu value loss thayu?"

    def test_differencing_money_columns_is_rejected(self):
        assert self._qr.violations(
            self.Q, "SELECT SUM(f.Amount)-SUM(p.PAmount) AS d FROM tblFinalPacket f, tblPacket p")

    @pytest.mark.parametrize("sql", [
        "SELECT SUM(ISNULL(WightLoss,0)) AS w FROM tblPacketHistory",   # misspelled, real
        "SELECT SUM(WeightLoss) AS w FROM tblPacket",
        "SELECT SUM(BoilLoss) AS w FROM tblKapan",
        "SELECT SUM(DifferWeight) AS w FROM tblKapan",                   # no "Loss" in the name
    ])
    def test_a_real_loss_column_passes(self, sql):
        assert self._qr.violations(self.Q, sql) == []


class TestSchemaProbesAreExemptFromSourceRules:
    """Establishing that something is NOT tracked is often the only correct
    answer, and the query that proves it reads INFORMATION_SCHEMA rather than a
    business table. CT-08 ("Kapan nu yield batavo") is answered by showing no
    yield column exists anywhere - the kapan_loss require_all rejected it."""

    from app.agent import query_rules as _qr

    def test_an_information_schema_probe_is_exempt(self):
        assert self._qr.violations(
            "Kapan nu yield batavo",
            "SELECT COUNT(*) AS n FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE COLUMN_NAME LIKE '%yield%'") == []

    def test_a_sys_tables_probe_is_exempt(self):
        assert self._qr.violations(
            "is there a sales table",
            "SELECT name FROM sys.tables WHERE name LIKE '%Sell%'") == []

    def test_a_business_query_is_still_checked(self):
        """The exemption must not become a bypass."""
        assert self._qr.violations(
            "June ma manufacturing ma ketlu value loss thayu?",
            "SELECT SUM(Amount) FROM tblFinalPacket")

    def test_only_the_pay_refused_fixture_conflict_remains(self):
        """Guards against a new rule quietly rejecting verified-correct SQL.

        EDA-1 used to be here too. Its ground truth is
            SELECT MAX(Date) AS LastHeadcountDate FROM tblEmployeeCount
        - a liveness probe whose answer (2021-07-23) IS the finding - and the
        headcount rule forbade the very query that proves the table is dead.
        is_liveness_probe() now exempts it, so the list is one shorter.

        CT-04 stays, and is harmless: access_guard.is_pay_question() refuses
        "employee-wise labour amount" BEFORE any LLM call, so its ground truth
        is never checked against these rules in production. It is a fixture
        artefact, not a live rejection - asserted here rather than deleted so
        that it cannot quietly grow back into a real one.
        """
        from scripts.cold_cases import COLD_CASES
        from app.agent import access_guard

        bad = [c["id"] for c in COLD_CASES
               if c.get("truthSql")
               and self._qr.violations(c.get("question", ""), c["truthSql"])]
        assert sorted(bad) == ["CT-04"], f"unexpected conflicts: {bad}"
        assert access_guard.is_pay_question(
            next(c["question"] for c in COLD_CASES if c["id"] == "CT-04")),             "CT-04 is only tolerable because the pay guard refuses it first"
