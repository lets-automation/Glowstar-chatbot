"""
test_lab_gate.py
----------------
"ALL LABS, OR A SPECIFIC LAB?" - ASKED IN CODE, BEFORE ANY LLM CALL.

The client's rule, given 2026-08-31: a pending question counts ALL labs by
default (GIA + HRD + IGI), and the bot must ask which lab rather than assume
GIA. See app/agent/lab_gate.py.

THE TEST THAT MATTERS MOST is test_the_all_labs_chip_does_not_ask_again.
Tapping a clarify chip re-sends its text as the next question, so a chip that
does not itself count as an answer puts the same question back on screen
forever. It is a one-line regression and an infinite loop in front of a client.
"""
import pytest

from app.agent import lab_gate


def _user(*texts):
    return [{"role": "user", "content": t} for t in texts]


class TestWhenTheGateFires:

    @pytest.mark.parametrize("q", [
        "how many packets are pending for the lab last month",
        "polish done but certification pending for MFG-1",
        "ketla packet lab na baki chhe",
        "polished but certificate pending last month",
    ])
    def test_a_pending_lab_question_with_no_lab_named_asks(self, q):
        assert lab_gate.needs_lab(q) is True

    @pytest.mark.parametrize("q", [
        "gia pending last month",
        "hrd pending for mfg-1 last month",
        "IGI pending",
    ])
    def test_a_named_lab_is_not_re_asked(self, q):
        assert lab_gate.needs_lab(q) is False

    @pytest.mark.parametrize("q", [
        "give me GIA results of july",          # completed work, not pending
        "how many employees do we have",
        "what is a kapan",
        "",
    ])
    def test_a_non_pending_question_is_untouched(self, q):
        assert lab_gate.needs_lab(q) is False

    def test_a_bare_pending_question_names_no_stage_and_is_left_alone(self):
        """"how many total were pending" is not necessarily about the lab.
        Claiming it here would be the same guess that started this whole bug."""
        assert lab_gate.needs_lab("how many total were pending last month") is False


class TestTheChipsAnswerTheQuestionTheyAsk:
    """Tapping a chip SENDS ITS TEXT as the next question, so every chip this
    gate offers must make the gate stand down when it comes back."""

    QUESTION = "how many packets are pending for the lab last month"

    def test_every_chip_settles_the_choice(self):
        for chip in lab_gate.ask_lab_response(self.QUESTION)["clarify_options"]:
            assert lab_gate.needs_lab(chip) is False, chip

    def test_the_all_labs_chip_does_not_ask_again(self):
        """THE LOOP. "all labs" names no single lab, so without an explicit
        all-labs escape this chip comes back and re-asks forever."""
        chips = lab_gate.ask_lab_response(self.QUESTION)["clarify_options"]
        all_chip = chips[0]
        assert "all labs" in all_chip
        assert lab_gate.named_lab(all_chip) == "", "must not resolve to one lab"
        assert lab_gate.needs_lab(all_chip) is False

    def test_the_specific_chips_resolve_to_their_lab(self):
        chips = lab_gate.ask_lab_response(self.QUESTION)["clarify_options"]
        assert [lab_gate.named_lab(c) for c in chips[1:]] == list(lab_gate.LABS)

    def test_all_labs_is_offered_first(self):
        """It is the client's default, so it must be one tap away."""
        chips = lab_gate.ask_lab_response(self.QUESTION)["clarify_options"]
        assert len(chips) == 4 and "all labs" in chips[0]

    def test_NONE_is_never_offered(self):
        """tblPlanMaster.LAB also holds 'NONE' - not a lab, but a stone that is
        not going to one. Offering it would invite a nonsense answer."""
        chips = lab_gate.ask_lab_response(self.QUESTION)["clarify_options"]
        assert not any("NONE" in c for c in chips)

    def test_the_payload_does_not_trigger_the_date_picker(self):
        out = lab_gate.ask_lab_response(self.QUESTION)
        assert out["ask_date"] is False
        assert out["ok"] is True and out["rows_returned"] == 0


class TestExplicitAllLabsPhrasings:

    @pytest.mark.parametrize("q", [
        "pending for the lab last month for all labs",
        "lab pending, all three",
        "certification pending across every lab",
        "lab pending badha lab",
    ])
    def test_they_count_as_an_answer(self, q):
        assert lab_gate.states_lab_choice(q) is True
        assert lab_gate.needs_lab(q) is False


class TestHistoryMemory:

    Q = "how many packets are pending for the lab last month"

    def test_a_lab_chosen_a_turn_ago_is_not_re_asked(self):
        """After answering "GIA", the follow-ups off that answer must not each
        put the same question back on screen - the failure date_gate already
        had with the period picker."""
        assert lab_gate.needs_lab(self.Q, _user("gia pending last month")) is False

    def test_it_expires_so_a_new_topic_asks_again(self):
        old = _user("gia pending last month", "and the damage report",
                    "now kapan wise production")
        assert lab_gate.needs_lab(self.Q, old) is True

    def test_the_most_recent_choice_wins(self):
        assert lab_gate.remembered_lab(_user("gia pending", "hrd pending")) == "HRD"

    def test_all_labs_clears_an_earlier_single_lab(self):
        """Otherwise "actually, all of them" would keep answering for GIA."""
        h = _user("gia pending last month", "actually show me all labs")
        assert lab_gate.remembered_lab(h) == ""

    def test_only_user_turns_count(self):
        """The bot's own prose mentions GIA constantly - it must never be read
        as the user having chosen."""
        h = [{"role": "assistant", "content": "GIA results for July were 2,529"}]
        assert lab_gate.needs_lab(self.Q, h) is True
