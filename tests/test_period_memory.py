"""
The period the user already gave must survive the next turn.

The client demo, 2026-08-21: they asked for a kapan/lab breakdown, the bot asked
which period, they said "may month" - and on the very next question it asked
which month again. Re-asking for a period that is still on screen reads as
broken.

The earlier attempts at this leaked in the opposite direction: remembering only
SILENCED the picker and trusted the model to notice the period in the history.
It did not, and the follow-up widened to all history until the context blew. So
both halves are tested here - the picker stays away AND the period reaches the
prompt.
"""
import pytest

from app.agent import date_gate as dg

ASKED = [
    {"role": "user", "content": "provide total number of kapan wise by lab wise"},
    {"role": "assistant", "content": "Which period should I cover?"},
    {"role": "user", "content": "may month"},
]


class TestThePickerDoesNotReAsk:
    def test_follow_up_does_not_ask_for_the_period_again(self):
        assert not dg.needs_date("give me total by kapan wise", ASKED)

    def test_a_first_turn_with_no_period_still_asks(self):
        assert dg.needs_date("give me report of department MFG - 1", [])

    def test_the_memory_expires(self):
        """Three topics later the conversation has moved on - ask again."""
        stale = ASKED + [
            {"role": "user", "content": "how many packets are on jangad"},
            {"role": "user", "content": "and the junk report"},
        ]
        assert dg.needs_date("give me the damage report of department MFG - 1", stale)


class TestThePeriodReachesTheModel:
    def test_the_remembered_period_is_injected(self):
        with dg.carrying_period(ASKED, "give me total by kapan wise"):
            directive = dg.carried_period_directive()
        assert "may month" in directive
        assert "Do NOT widen to all history" in directive

    def test_it_reaches_the_actual_prompt(self):
        from app.agent import tools

        with dg.carrying_period(ASKED, "give me total by kapan wise"):
            prompt = tools.system_prompt_for("give me total by kapan wise")
        assert "PERIOD CARRIED OVER" in prompt and "may month" in prompt

    def test_an_explicit_period_in_the_new_question_wins(self):
        """'and what about June?' must not keep answering for May."""
        with dg.carrying_period(ASKED, "and what about June 2026?"):
            assert dg.carried_period() == ""

    def test_nothing_is_carried_when_no_period_was_ever_given(self):
        with dg.carrying_period([{"role": "user", "content": "hi"}], "show me stock"):
            assert dg.carried_period_directive() == ""

    def test_the_carry_is_scoped_to_one_turn(self):
        with dg.carrying_period(ASKED, "give me total by kapan wise"):
            assert dg.carried_period()
        assert dg.carried_period() == ""
