"""
test_cut_purity_recipe.py
-------------------------
CUT-PURITY CHANGE AS A RECIPE.

tests/test_cut_purity_change.py pins the RESULT against the client's screen.
This pins the ROUTE: that the question reaches the recipe in code, before any
LLM call, and that the recipe returns the same rows the screen shows.

Why it became a recipe at all: it was the only verified report with no code
behind it. "It still matches their ERP" rested on the model reproducing a
self-joined window query with four traps in it, every time, for the one report
the client checks packet-for-packet.

THREE DESIGN DECISIONS PINNED HERE, each of which is a bug if it drifts:
  1. NO PERIOD. A kapan is one batch of rough, so the kapan IS the scope. The
     recipe must match before resolve_period, and the date picker must not fire.
  2. EXACT KAPAN MATCHING ONLY. OS26/OR26 and NI26/NS26 all exist. A near miss
     must resolve to NOTHING - we have queried the wrong kapan twice already.
  3. NO TOOL SPEC. The corpus worst case sits 60 tokens under the prompt
     ceiling, so this is reachable through the router only.
"""
from datetime import date

import pytest

from app.agent import date_gate, recipe_router as rr, reports, tools
from app.database.runner import run_select

TODAY = date(2026, 8, 31)

THEIR_CUT = {
    (90, "M5003", "EX", "VG"), (51, "M5004", "EX", "VG"),
    (158, "M5005", "EX", "VG"), (149, "M5005", "EX", "VG"),
    (10, "M5005", "EX", "VG"), (26, "M5007", "EX", "VG"),
    (18, "M5008", "EX", "VG"), (124, "M5009", "EX", "VG"),
}


class TestItIsReachableWithoutCostingPromptTokens:

    def test_the_handler_exists(self):
        assert "cut_purity_change" in tools.TOOL_HANDLERS

    def test_but_it_is_not_in_the_tool_specs(self):
        """THE WHOLE POINT. TOOL_SPECS is re-sent on every round of every
        question and the corpus worst case has ~60 tokens of headroom
        (tests/test_prompt_budget.py, whose note says the next move must be a
        reduction, not a third raise). The router reaches this in code instead,
        for nothing. If someone adds a spec, the budget test fails - but this
        says why before they get there."""
        assert "cut_purity_change" not in {s["name"] for s in tools.TOOL_SPECS}

    def test_it_has_a_status_line(self):
        assert tools.friendly_status("cut_purity_change") != "Working…"


class TestRouting:

    @pytest.mark.parametrize("q", [
        "give me cut purity change report of NI26",
        "cut-purity change NI26",
        "NI26 nu cut purity change kadho",
        "cut and purity change for kapan NI26",
        "purity vs cut change NI26",
    ])
    def test_the_phrasings_route_with_the_kapan(self, q):
        hit = rr.match(q, TODAY)
        assert hit == {"recipe": "cut_purity_change", "kapan": "NI26",
                       "lab": "GIA"}   # lab added 2026-09-03

    def test_it_needs_no_period(self):
        """Every other recipe returns None without one. This one must not:
        resolve_period fails on all of these and it still routes."""
        assert rr.resolve_period("cut purity change NI26", TODAY) is None
        assert rr.match("cut purity change NI26", TODAY) is not None

    def test_the_date_picker_does_not_fire(self):
        """The word 'report' would otherwise put a date picker in front of the
        one report that matches their ERP exactly."""
        assert date_gate.needs_date("give me cut purity change report of NI26") is False

    def test_an_unknown_kapan_declines_rather_than_guessing(self):
        assert rr.match("cut purity change of ZZ99", TODAY) is None

    def test_no_kapan_declines(self):
        """Without a kapan there is no scope, so the normal path must ask."""
        assert rr.match("give me the cut purity change report", TODAY) is None

    def test_ordinary_questions_are_untouched(self):
        # "how many employees are there?" used to be here. It is now a
        # quick_fact (app/agent/quick_facts.py), which is the improvement, not
        # a regression - so this uses a question nothing curated claims.
        assert rr.match("what is a kapan?", TODAY) is None
        hit = rr.match("give me report of department MFG - 1 for july 2026", TODAY)
        assert hit and hit["recipe"] == "department_report"


@pytest.mark.integration
class TestKapanResolutionIsExact:

    def test_it_resolves_case_insensitively(self):
        assert reports.resolve_kapan("ni26") == ("NI26", [])
        assert reports.resolve_kapan("  NI26 ") == ("NI26", [])

    def test_the_lookalikes_are_all_real_and_distinct(self):
        """The premise of the whole rule: these are four different batches."""
        for name in ("NI26", "NS26", "OS26", "OR26"):
            assert reports.resolve_kapan(name)[0] == name

    def test_a_near_miss_resolves_to_nothing_and_offers_candidates(self):
        """ONE LETTER APART IS A DIFFERENT BATCH OF DIAMONDS, not a typo -
        the opposite of resolve_department, which fuzzy-matches 'fancy' to
        'Fency' on purpose. Guessing here is how a number for the wrong stones
        reached the client, twice."""
        kapan, suggestions = reports.resolve_kapan("NJ26")
        if suggestions:                      # NJ26 may itself exist
            assert kapan is None
            assert any(s in suggestions for s in ("NI26", "NS26"))

    def test_an_empty_name_is_not_a_match(self):
        assert reports.resolve_kapan("") == (None, [])


@pytest.mark.integration
class TestTheRecipeReturnsTheScreen:

    def test_it_returns_both_tables_with_the_right_counts(self):
        out = reports.cut_purity_report("NI26")
        assert [(s["title"], len(s["rows"])) for s in out["sections"]] == [
            ("Cut changes", 8), ("Purity changes", 18)]

    def test_the_cut_table_matches_packet_for_packet(self):
        out = reports.cut_purity_report("NI26")
        cut = next(s for s in out["sections"] if s["title"] == "Cut changes")
        got = {(int(r["Pkt"]), r["Emp"].strip(),
                r["MFGCut"].strip(), r["GIACut"].strip()) for r in cut["rows"]}
        assert got == THEIR_CUT

    def test_vendor_firms_survive(self):
        """Y-codes are Fency job-work FIRMS. An INNER JOIN to tblEmployee to
        prettify the name drops 3 of NI26's 18 purity changes."""
        out = reports.cut_purity_report("NI26")
        pur = next(s for s in out["sections"] if s["title"] == "Purity changes")
        assert [r for r in pur["rows"] if r["Emp"].strip().startswith("Y")]

    def test_it_names_the_kapan_in_its_own_text(self):
        """Process mistake #1 on this project: echo the kapan back. Twice we
        queried a different one and the client checked our number against a
        report for other stones."""
        assert "NI26" in reports.cut_purity_report("NI26")["text"]

    def test_an_unknown_kapan_refuses_and_says_why(self):
        out = reports.cut_purity_report("ZZ99")
        assert out["text"].startswith("ERROR")
        assert out["sections"] == []
        assert "do NOT pick the closest" in out["text"]

    def test_it_offers_no_totals(self):
        """`| totals:` tells facts.py which columns may be summed. Every column
        here is a grade or a code; totalling a packet number is meaningless."""
        assert "totals:" not in reports.cut_purity_report("NI26")["sql"]


@pytest.mark.integration
class TestEndToEndThroughTheRouter:

    def test_the_answer_echoes_the_kapan_and_carries_both_sheets(self):
        q = "give me cut purity change report of NI26"
        out = rr.answer(rr.match(q, TODAY), q)
        assert "NI26" in out["answer"]
        assert [s["title"] for s in out["data_sections"]] == [
            "Cut changes", "Purity changes"]


class TestTheStageNamedPhrasingRoutes:
    """"cut OR clarity" DID NOT ROUTE, AND THE FREE-SQL ANSWER WAS WRONG.

    Live 2026-09-03. "For kapan NS26, show packets where the MFG grade differs
    from the GIA grade on cut or clarity" missed _CUT_PURITY_RE: the separator
    alternation held and/&//vs/versus but NOT "or". "cut and clarity" routed,
    "cut or clarity" did not.

    Falling through to free SQL, the model returned 337 rows against a true
    288 - it counted 4 damage plans, 9 duplicate pairings, 5 superseded MFG
    rows whose LATER grade agrees with GIA, and 31 rows for packets with no
    GIA row at all, 26 of which had actually been certified at HRD.

    The recipe already existed and was already correct. Only the route was
    missing, so this pins the ROUTE.
    """

    KAPAN_Q = ("For kapan {k}, show packets where the MFG grade differs from "
               "the GIA grade on cut or clarity")

    @pytest.mark.parametrize("q", [
        KAPAN_Q.format(k="NS26"),
        KAPAN_Q.format(k="OR26"),
        "cut, clarity change NS26",
        "cut or purity change for NI26",
        "MFG vs GIA grade difference for kapan NS26",
        "compare the MFG grade and GIA grade for kapan NI26",
    ])
    def test_it_routes_to_the_recipe(self, q):
        m = rr.match(q)
        assert m and m.get("recipe") == "cut_purity_change", (q, m)

    @pytest.mark.parametrize("q", [
        # A _CUT_PURITY_RE hit with no resolvable kapan returns None from
        # match(), which SKIPS the pending and lab branches below it. So a
        # loose pattern here silently costs those recipes their questions.
        "polished GIA pending for MFG - 1 for July 2026",
        "give me polished GIA pending for mfg-1 department of past month",
        "GIA results for MFG-2 for July 2026",
        "compare MFG-1 and MFG-2 GIA results for July 2026",
        "how many stones went to GIA last month",
        "last month ketla stone lab ma send karya?",
    ])
    def test_it_does_not_hijack_lab_or_pending_questions(self, q):
        assert not rr._CUT_PURITY_RE.search(q), q

    def test_the_stage_branch_needs_all_three_tokens(self):
        """mfg + gia + "grade" + a difference word. Two of the four is not
        enough - that is what keeps it off the lab and pending questions."""
        assert not rr._CUT_PURITY_RE.search("mfg and gia for NI26")
        assert not rr._CUT_PURITY_RE.search("mfg gia grade for NI26")
        assert rr._CUT_PURITY_RE.search("mfg grade differs from gia grade")


@pytest.mark.integration
class TestTheRecipeAnswersTheseKapansCorrectly:
    """The counts the free-SQL path got wrong, pinned against the recipe."""

    def test_ni26_still_matches_their_screen(self):
        out = reports.cut_purity_report("NI26")
        n = {s["title"]: len(s["rows"]) for s in out["sections"]}
        assert (n.get("Cut changes"), n.get("Purity changes")) == (8, 18)

    @pytest.mark.parametrize("kapan", ["NS26", "OR26", "NI26"])
    def test_the_properties_the_free_sql_got_wrong(self, kapan):
        """INVARIANTS, NOT A SNAPSHOT.

        The first version of this test asserted "NS26 == 288 packets". That
        pins a number I computed myself from the same query, so it proves
        nothing about correctness and breaks on the next DB restore for a
        reason that is not a bug.

        What the free-SQL answer actually got wrong were four PROPERTIES, and
        those are checkable for ANY kapan against the database directly:

          * no damage plan may contribute a row
          * no packet without a GIA row may appear
          * a packet may appear at most once per table
          * the MFG row compared must be that packet's LATEST MFG row

        (The 337-vs-288 split was 4 damage plans, 31 no-GIA rows, 9 duplicate
        pairings and 5 superseded MFG rows - one per property.)
        """
        out = reports.cut_purity_report(kapan)
        assert out["sections"], f"{kapan} produced no sections"

        for sec in out["sections"]:
            col = "MFGCut" if sec["title"].startswith("Cut") else "MFGPurity"
            gia = "GIACut" if sec["title"].startswith("Cut") else "GIAPurity"
            rows = [r if isinstance(r, dict)
                    else dict(zip(sec["columns"], r)) for r in sec["rows"]]

            pkts = [r["Pkt"] for r in rows]
            assert len(pkts) == len(set(pkts)), (
                f"{kapan}/{sec['title']}: a packet appears more than once")

            for r in rows:
                assert (r[gia] or "").strip(), (
                    f"{kapan} packet {r['Pkt']}: blank GIA grade - that packet "
                    "has no GIA row and is not a change")
                assert (r[col] or "").strip() != (r[gia] or "").strip(), (
                    f"{kapan} packet {r['Pkt']}: listed as changed but equal")

            self._assert_rows_are_live_and_latest(kapan, rows)

    @staticmethod
    def _assert_rows_are_live_and_latest(kapan, rows):
        """Every reported MFG grade must be the packet's LATEST non-damage MFG
        row - read back from the database, not from the recipe."""
        if not rows:
            return
        pkts = ", ".join(str(int(r["Pkt"])) for r in rows)
        truth = run_select(f"""
            SELECT p.PacketNo AS Pkt, m.Cut, m.Purity, m.IsDamagePlan
            FROM tblPacket p
            JOIN tblKapan k ON k.ID = p.Kapan_ID AND k.KapanName = '{kapan}'
            CROSS APPLY (SELECT TOP 1 x.Cut, x.Purity, x.IsDamagePlan
                         FROM tblPlanMaster x
                         WHERE x.Packet_ID = p.ID AND x.RapVer = 'MFG'
                           AND ISNULL(x.IsDamagePlan, 0) = 0
                         ORDER BY x.ID DESC) m
            WHERE p.PacketNo IN ({pkts})""", max_rows=2000, timeout=300)
        assert truth["ok"], truth.get("error")
        latest = {int(r["Pkt"]): r for r in truth["rows"]}
        for r in rows:
            t = latest.get(int(r["Pkt"]))
            assert t is not None, f"{kapan} packet {r['Pkt']} has no clean MFG row"
            assert not t["IsDamagePlan"], (
                f"{kapan} packet {r['Pkt']}: reported off a DAMAGE plan")
            col = "Cut" if "MFGCut" in r else "Purity"
            assert (r[f"MFG{col}"] or "").strip() == (t[col] or "").strip(), (
                f"{kapan} packet {r['Pkt']}: reported a SUPERSEDED MFG "
                f"{col} ({r[f'MFG{col}']}) - the latest is {t[col]}")


class TestEveryRealKapanIsReachable:
    """FORTY-SEVEN REAL KAPANS COULD NEVER BE NAMED.

    Audit 2026-09-03 over all 865 in tblKapan:

      * 31 are ordinary English words - AA, GO, IN, IS, IT, ME, MY, NO, ON,
        OR, TO, US, VS ... - and sat on the _NOT_A_KAPAN stopword list, so
        they resolved to nothing however the user asked. "kapan AA" appears in
        the client's own logs.
      * 16 more use the '21WD' shape, which _KAPAN_TOKEN_RE could not match at
        all.

    The stopword list is still right for a BARE token; what lifts it is the
    user explicitly saying "kapan <name>".
    """

    @staticmethod
    def _all_kapan_names():
        r = run_select("SELECT DISTINCT KapanName FROM tblKapan WITH (NOLOCK) "
                       "WHERE KapanName IS NOT NULL AND KapanName <> ''",
                       max_rows=2000, timeout=300)
        assert r["ok"], r.get("error")
        return [x["KapanName"].strip() for x in r["rows"] if x.get("KapanName")]

    @pytest.mark.integration
    def test_every_kapan_resolves_when_explicitly_named(self):
        # MA/NA/NI/NO/NU are Gujarati POSTPOSITIONS as well as kapan names -
        # "kapan ma" means IN THE KAPAN. Resolving them would report on a batch
        # nobody asked about, so they decline and the caller asks. Everything
        # else must resolve. Was 47 unreachable before the audit.
        AMBIGUOUS = {"MA", "NA", "NI", "NO", "NU"}
        bad = [n for n in self._all_kapan_names()
               if n.upper() not in AMBIGUOUS
               and rr.kapan_in(f"cut purity change of kapan {n}")[0] != n]
        assert bad == [], f"unreachable kapans: {sorted(bad)[:25]}"

    @pytest.mark.integration
    def test_no_kapan_question_is_met_with_the_date_picker(self):
        AMBIGUOUS = {"MA", "NA", "NI", "NO", "NU"}
        bad = [n for n in self._all_kapan_names()
               if n.upper() not in AMBIGUOUS
               and date_gate.needs_date(f"gia results for kapan {n}", [])]
        assert bad == [], f"date-picked kapans: {sorted(bad)[:25]}"

    @pytest.mark.parametrize("q", [
        # A stopword that is NOT called a kapan must stay a stopword, or the
        # router reports on the wrong batch of diamonds.
        "give me report of department MFG - 1",
        "how many packets are on jangad",
        "give me total of all departments",
        "aa varsh ma ketla planning verify thaya che?",
        "aa mahine ketla nang thaya?",
        # ...including directly in front of the noun: "OF kapan AA" resolved to
        # the real kapan named OF until the waiver was made one-directional.
        "cut purity change of kapan AA",
    ])
    def test_a_bare_stopword_never_becomes_a_kapan(self, q):
        got, _ = rr.kapan_in(q)
        assert got in (None, "AA"), f"{q!r} resolved to {got!r}"


class TestTheReportIsNotGiaOnly:
    """MFG vs HRD MATCHED NO RECIPE AND FELL THROUGH TO FREE SQL.

    175 packets are graded at HRD and 6 at IGI. The comparison was hardcoded
    to GIA, so "MFG vs HRD cut grade" routed nowhere - onto the unguarded path
    that returned 337 rows against a true 288 for the GIA form of the same
    question.
    """

    @pytest.mark.parametrize("lab", ["GIA", "HRD", "IGI"])
    def test_each_lab_routes_and_carries_itself(self, lab):
        m = rr.match(f"For kapan NS26, show packets where the MFG cut grade "
                     f"is different from the {lab} cut grade")
        assert m and m["recipe"] == "cut_purity_change"
        assert m["lab"] == lab

    @pytest.mark.integration
    def test_the_verified_gia_figures_are_unchanged(self):
        """Parameterising the lab must not move the one ERP-verified result."""
        out = reports.cut_purity_report("NI26")
        n = {s["title"]: len(s["rows"]) for s in out["sections"]}
        assert (n.get("Cut changes"), n.get("Purity changes")) == (8, 18)

    @pytest.mark.integration
    def test_a_lab_with_little_data_answers_honestly_rather_than_erroring(self):
        out = reports.cut_purity_report("NS26", "IGI")
        assert "sections" in out and "ERROR" not in out["text"]

    def test_an_unknown_lab_is_refused_not_guessed(self):
        out = reports.cut_purity_report("NS26", "SGL")
        assert out["text"].startswith("ERROR")
        assert "GIA, HRD, IGI" in out["text"]
