"""
Three defects found by running the real question against a live model on
2026-08-24, after the pinned lab report was wired in. Each one put something
wrong in front of the user while the underlying numbers were correct.
"""
import pytest

from app.agent import period_guard, postprocess

RECIPE_SQL = "-- lab_results_report('2026-05-01', '2026-06-01', '')"
DEPT_SQL = "-- department_report('Fency', '2026-06-01', '2026-07-01')"


class TestPinnedReportIsPeriodFiltered:
    """A recipe reports its call as a comment; comments get stripped, so the
    scope guard saw no date and warned "not filtered to that period" directly
    above correctly-filtered May figures."""

    @pytest.mark.parametrize("sql", [RECIPE_SQL, DEPT_SQL])
    def test_no_false_scope_banner(self, sql):
        assert not period_guard.unfiltered_period(
            "provide total number of kapan wise by lab wise for may month",
            [sql], [{"Kapan": "NS26"}])

    def test_a_genuinely_unfiltered_query_still_warns(self):
        assert period_guard.unfiltered_period(
            "provide total number of kapan wise by lab wise for may month",
            ["SELECT KapanName, COUNT(*) FROM tblFinalPacket GROUP BY KapanName"],
            [{"Kapan": "NS26"}])


class TestEmptyTableSkeleton:
    """The model was told to stop rendering the table and sometimes emitted the
    skeleton anyway - a lone alignment row. That counted as "a table exists", so
    the real one was suppressed and the client saw a heading and no data."""

    SKELETON = ("Here is the breakdown by kapan:\n\n|:---|---:|---:|\n\n"
                "And by lab:\n\n|:---|---:|")
    REAL = "| Kapan | PNo |\n|---|---|\n| NS26 | 551 |\n| NT26 | 229 |"

    def test_skeleton_is_not_a_table(self):
        assert not postprocess.looks_like_data_table(self.SKELETON)

    def test_real_table_is_a_table(self):
        assert postprocess.looks_like_data_table(self.REAL)

    def test_orphan_separators_are_stripped(self):
        out = postprocess.strip_empty_tables(self.SKELETON)
        assert "|:---|" not in out
        assert "Here is the breakdown by kapan:" in out

    def test_real_table_survives_stripping(self):
        assert postprocess.strip_empty_tables(self.REAL) == self.REAL

    def test_the_real_data_is_appended_when_only_a_skeleton_was_written(self):
        rows = [{"Kapan": "NS26", "PNo": 551}, {"Kapan": "NT26", "PNo": 229}]
        out = postprocess.ensure_data_shown(
            postprocess.strip_empty_tables(self.SKELETON),
            ["Kapan", "PNo"], rows, has_visual=False)
        assert "NS26" in out and "551" in out


@pytest.mark.integration
class TestDataCutoffIsLive:
    """A hardcoded cutoff rots at the next restore: after the 2026-08-21 backup
    went in, the bot still told users the data ended 2026-07-27."""

    def test_cutoff_comes_from_the_database(self):
        from app.schema.extractor import data_cutoff

        cutoff = data_cutoff()
        if not cutoff:
            pytest.skip("database not reachable")
        assert cutoff.startswith("2026-"), cutoff
        assert "2026-07-27" not in cutoff

    def test_note_never_shows_the_placeholder(self):
        from app.schema.glossary import render_data_notes

        assert "{DATA_CUTOFF}" not in render_data_notes("how many packets today?")
