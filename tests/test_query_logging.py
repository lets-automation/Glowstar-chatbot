"""
Every query that runs must be visible in the log.

A pinned recipe reports itself to the agent as ONE comment marker
("-- lab_results_report(...)"), because it runs several queries. That marker was
all that reached agent.log, so the SQL behind a report - exactly the SQL we most
want to audit against the client's ERP - became invisible.

And a turn that ran NO query still logged "ok". Seen live 2026-08-25 08:43:
"give me kapan wise gia results for june month" logged ok / 0 rows / no SQL,
while the same question a minute later returned 37 rows. Nothing recorded what
was answered in between.
"""
import logging

import pytest


class TestRecipeQueriesAreLogged:
    @pytest.mark.integration
    def test_each_section_query_is_logged_with_its_row_count(self, caplog):
        from app.agent.reports import lab_results_report

        with caplog.at_level(logging.INFO, logger="glowstar"):
            out = lab_results_report("2026-05-01", "2026-06-01")
        if not out["sections"]:
            pytest.skip("database not reachable")
        logged = [r.getMessage() for r in caplog.records if "RECIPE SQL" in r.getMessage()]
        assert len(logged) >= 3, "expected one log line per report section"
        assert any("tblPlanMaster" in m for m in logged), "the real table must appear"
        assert any("RapVer" in m for m in logged), "the real filter must appear"

    @pytest.mark.integration
    def test_a_failing_section_is_logged_as_an_error(self, caplog):
        from app.agent import reports

        with caplog.at_level(logging.INFO, logger="glowstar"):
            cols, rows, err = reports._rows("SELECT * FROM tblNoSuchTable")
        assert err
        assert any("RECIPE SQL FAILED" in r.getMessage() for r in caplog.records)


class TestNoQueryTurnsAreFlagged:
    def test_a_turn_that_ran_nothing_is_flagged(self, caplog):
        from app.core.logging_util import log_interaction

        with caplog.at_level(logging.INFO, logger="glowstar"):
            log_interaction("give me kapan wise gia results for june month", [], 0)
        assert any("NO-QUERY TURN" in r.getMessage() for r in caplog.records)

    def test_a_normal_turn_is_not_flagged(self, caplog):
        from app.core.logging_util import log_interaction

        with caplog.at_level(logging.INFO, logger="glowstar"):
            log_interaction("q", ["SELECT 1"], 1)
        assert not any("NO-QUERY TURN" in r.getMessage() for r in caplog.records)

    def test_an_errored_turn_is_not_double_reported(self, caplog):
        """An error already explains itself - do not also cry NO-QUERY."""
        from app.core.logging_util import log_interaction

        with caplog.at_level(logging.INFO, logger="glowstar"):
            log_interaction("q", [], 0, error="provider exploded")
        msgs = [r.getMessage() for r in caplog.records]
        assert any("ERROR" in m for m in msgs)
        assert not any("NO-QUERY TURN" in m for m in msgs)
