"""
test_plan_recipes.py
--------------------
THE THREE QUESTION SHAPES THAT HAD NO RECIPE.

Audit 2026-09-03. Of the eight shapes asked in a working session, three fell
through to free SQL every time - and free SQL produced EVERY wrong answer of
that session:

    MFG vs GIA on NS26 ....... 337 rows against a true 288
    plans by Marker-2 on QA26 ... 1 packet  against a true 4
    GIA pending for MFG-1 ....... 12 packets against a true 2

query_rules can reject a shape it already knows is wrong. It cannot make the
model reconstruct sibling-plan handling, a positional stage test, or the
difference between a planned weight and a rough one. So the shapes got
recipes, and this pins them.

The figures below were each verified by hand against the database earlier in
that session, and the properties they encode are the ones the free-SQL answers
broke.

BOTH RECIPES ARE ROUTER-MATCHED, NOT TOOLS. TOOL_SPECS is re-sent on every
round; two more specs cost ~680 tokens/round and blew the prompt budget the
day they were added. See the note above TOOL_HANDLERS.
"""
import pytest

from app.agent import recipe_router as rr, reports, tools


class TestClarityLadder:
    """"IF to VS2" is a RANGE on a ladder, not two values."""

    def test_a_range_expands_to_every_grade_between(self):
        codes, err = reports.resolve_clarity_range("IF", "VS2")
        assert err == ""
        assert codes == ["IF", "VVS1", "VVS2", "VS1", "VS2"]

    def test_the_ends_may_arrive_in_either_order(self):
        assert (reports.resolve_clarity_range("VS2", "IF")[0]
                == reports.resolve_clarity_range("IF", "VS2")[0])

    def test_no_range_means_every_grade(self):
        assert reports.resolve_clarity_range("", "")[0] == list(
            reports.CLARITY_LADDER)

    def test_an_unknown_grade_is_refused_not_guessed(self):
        codes, err = reports.resolve_clarity_range("XX", "VS2")
        assert codes == [] and err.startswith("ERROR")

    def test_si3_is_not_offered_because_it_is_not_stored(self):
        """The trade ladder has SI3; this database does not."""
        assert "SI3" not in reports.CLARITY_LADDER


class TestTheRouterParsesTheFilters:
    """The parameters are extracted in CODE, so they cannot be mis-filled."""

    Q = ("from kapan QA26 give me packets that has purity between FL to VVS2 "
         "and size range from 0.3 to 0.80 for marker 2 department")

    def test_clarity_range(self):
        assert rr.clarity_range_in(self.Q) == ("FL", "VVS2")

    def test_weight_range(self):
        assert rr.weight_range_in(self.Q) == (0.3, 0.8)

    def test_a_reversed_weight_range_still_means_the_same_band(self):
        assert rr.weight_range_in("size 0.80 to 0.30") == (0.3, 0.8)

    def test_the_department_survives_the_decimals(self):
        """A DIFFERENT DEPARTMENT, NOT A SPELLING.

        Splitting on non-alphanumerics turns "0.80" into "0" and "80", which
        joined its neighbour into the window "0 80 marker" - and that
        fuzzy-matched the department literally named "Marker". The question
        asked for Marker-2. Both exist, with different people.
        """
        assert rr.department_in(self.Q)[0] == "Marker-2"

    def test_a_bare_marker_still_resolves_to_bare_marker(self):
        assert rr.department_in("give me packets for Marker department")[0] == "Marker"

    def test_authoring_phrasings_name_a_department_too(self):
        """"planned by Blocking" names one without the word 'department'."""
        assert rr.department_in("packets planned by Blocking")[0] == "Blocking"
        assert rr.department_in("plans created by Sarin in kapan OM26")[0] == "Sarin"

    @pytest.mark.parametrize("q", ["how many packets are on jangad?", "hello",
                                   "give me total of all departments"])
    def test_no_department_is_invented(self, q):
        assert rr.department_in(q)[0] is None

    def test_stage_pair(self):
        assert rr.stage_gap_in(
            "packets that have an approved CLV plan but no approved PLS plan "
            "yet") == ("CLV", "PLS")


class TestRoutingCostsNothingUntilUsed:

    def test_neither_recipe_is_in_tool_specs(self):
        """They are matched in code, like cut_purity_change. Two extra specs
        cost ~680 tokens on EVERY round and blew the prompt budget."""
        names = {s["name"] for s in tools.TOOL_SPECS}
        assert "plan_rows" not in names
        assert "stage_gap" not in names

    def test_but_both_are_dispatchable(self):
        assert "plan_rows" in tools.TOOL_HANDLERS
        assert "stage_gap" in tools.TOOL_HANDLERS

    @pytest.mark.parametrize("q,recipe", [
        ("from kapan QA26 give me packets that has purity between FL to VVS2 "
         "and size range from 0.3 to 0.80 for marker 2 department", "plan_rows"),
        ("from kapan QA26 give me packets planned by Marker-2 with purity "
         "VS1 to VS2 and size 0.3 to 0.8", "plan_rows"),
        ("For kapan NS26, list the packets that have an approved CLV plan but "
         "no approved PLS plan yet, with clarity IF to VS2 and planned weight "
         "between 0.50 and 1.00 carat", "stage_gap"),
        ("kapan NS26 packets still sitting at CLV with no PLS", "stage_gap"),
    ])
    def test_the_session_questions_route(self, q, recipe):
        m = rr.match(q)
        assert m and m["recipe"] == recipe, (q, m)

    def test_pls_to_a_lab_stays_with_the_pending_recipe(self):
        """pending_lab_results also carries the DESTINATION lab off the PLS
        row, which stage_gap cannot - so it must win that question."""
        m = rr.match("give me polished GIA pending for mfg-1 department of "
                     "July 2026")
        assert m and m["recipe"] == "pending_lab_results"


@pytest.mark.integration
class TestTheRecipesReproduceTheVerifiedAnswers:
    """Each figure was measured by hand against the database first."""

    def test_plans_by_marker_2_in_qa26(self):
        out = reports.plan_rows_report("QA26", department="Marker-2",
                                       clarity_from="FL", clarity_to="VVS2",
                                       wt_min=0.30, wt_max=0.80)
        rows = out["sections"][0]["rows"]
        assert len(rows) == 4
        assert {r["PacketNo"] for r in rows} == {232, 253, 220, 291}
        # Half of Marker-2's plans in QA26 are unapproved. They are INCLUDED
        # with a flag - an unapproved plan is still one somebody created.
        assert sum(1 for r in rows if not r["IsApproved"]) == 1
        # Planned values, off the plan row. tblPacket reads SI1/VS1 and a 2ct
        # rough weight for two of these.
        assert all(r["Clarity"] == "VVS2" for r in rows)

    def test_a_stage_gap_reports_both_readings(self):
        out = reports.stage_gap_report("NS26", "CLV", "PLS",
                                       clarity_from="IF", clarity_to="VS2",
                                       wt_min=0.50, wt_max=1.00)
        rows = out["sections"][0]["rows"]
        assert {r["PacketNo"] for r in rows} == {3, 584}
        # SIBLING PLANS. Packet 3 carries three approved CLV rows written the
        # same day - RD 0.830, PS 0.310, PS 0.180. Deduping to the newest kept
        # the SI1/0.180 one, failed both filters and lost the packet entirely.
        assert 3 in {r["PacketNo"] for r in rows}
        # The counter-reading must be stated, not hidden: both these stones
        # HAVE moved on (to ADM), so "still sitting at CLV" is 0.
        assert "positional reading" in out["text"]
        assert all(r["LatestApprovedStage"] == "ADM" for r in rows)

    def test_the_positional_reading_is_narrower(self):
        anti = reports.stage_gap_report("NS26", "CLV", "PLS",
                                        clarity_from="IF", clarity_to="VS2",
                                        wt_min=0.50, wt_max=1.00)
        pos = reports.stage_gap_report("NS26", "CLV", "PLS",
                                       clarity_from="IF", clarity_to="VS2",
                                       wt_min=0.50, wt_max=1.00,
                                       positional=True)
        n_anti = len(anti["sections"][0]["rows"]) if anti["sections"] else 0
        n_pos = len(pos["sections"][0]["rows"]) if pos["sections"] else 0
        assert n_pos <= n_anti
        assert (n_anti, n_pos) == (2, 0)

    def test_os26_gives_three(self):
        out = reports.stage_gap_report("OS26", "CLV", "PLS",
                                       clarity_from="IF", clarity_to="VS2",
                                       wt_min=0.50, wt_max=1.00)
        assert {r["PacketNo"] for r in out["sections"][0]["rows"]} == {39, 51, 77}


@pytest.mark.integration
class TestBadInputIsRefusedNotGuessed:

    def test_an_unknown_kapan(self):
        out = reports.stage_gap_report("ZZ99", "CLV", "PLS")
        assert out["text"].startswith("ERROR")
        assert "do NOT pick the closest one" in out["text"]

    def test_an_unknown_stage(self):
        out = reports.stage_gap_report("NS26", "CLV", "XYZ")
        assert out["text"].startswith("ERROR") and "RST" in out["text"]

    def test_an_unknown_department(self):
        out = reports.plan_rows_report("NS26", department="Nowhere")
        assert out["text"].startswith("ERROR")

    def test_an_unknown_clarity(self):
        out = reports.plan_rows_report("NS26", clarity_from="XX",
                                       clarity_to="VS2")
        assert out["text"].startswith("ERROR")
