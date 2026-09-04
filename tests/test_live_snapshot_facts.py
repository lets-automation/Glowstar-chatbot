"""
test_live_snapshot_facts.py
---------------------------
THE BIGGEST UNCOVERED CLUSTER: "what is true right now".

Audit 2026-09-03 over 206 real logged questions. Of the 101 still reaching free
SQL, 24 were one-line counts of the CURRENT state - "how many packets are in
stock", "how many kapans do we have", "how many packets are on jangad", "atyare
ketla diamond hold par che". Cheapest to cover, most often asked, and each one
already had a verified reading that free SQL kept missing.

These take NO period. A date picker on "how many packets are on jangad" is the
same category error as one on "how many people work here".

NO FIGURE IS ASSERTED HERE. Row counts move on every restore; what must not
move is WHICH TABLE AND COLUMN the answer is read from, and that is what these
tests pin. The one exception is the memo/jangad agreement, which is a
RELATIONSHIP between two figures and holds whatever the numbers are.
"""
import pytest

from app.agent import quick_facts as qf, recipe_router as rr


class TestTheRightQuestionsTrigger:

    @pytest.mark.parametrize("q,fact", [
        ("how many packets are on jangad?", "on_jangad"),
        ("How many packets are currently out on jangad?", "on_jangad"),
        ("how many stones are out on memo right now?", "on_memo"),
        ("atyare ketla diamond hold par che?", "on_hold"),
        ("how many packets are in stock right now?", "in_stock"),
        ("how many kapans do we have?", "kapan_count"),
        ("how many kapans are there", "kapan_count"),
        ("how many packets are there", "packet_total"),
        ("How many diamonds do we have?", "packet_total"),
    ])
    def test_it_fires(self, q, fact):
        m = qf.match(q)
        assert m and m["fact"] == fact, (q, m)

    @pytest.mark.parametrize("q,why", [
        # A SHAPE makes it a breakdown, not a scalar - and "oval" needs the
        # whole family (OV + F.OV + S.OV), which a flat count cannot give.
        ("how many oval diamonds do we have in stock?", "shape needs the family"),
        # A named kapan and a piece count is kapan_pieces, a different fact.
        ("kapan OQ26 ma total ketla piece hata?", "belongs to kapan_pieces"),
        ("how many employees do we have?", "belongs to headcount"),
        ("Party wise jangad batavo", "a breakdown, not a count"),
        ("which kapan produced the most junk by weight", "a ranking"),
        ("how many packets were made in June 2026", "a period question"),
    ])
    def test_it_stays_out_of_other_questions(self, q, why):
        m = qf.match(q)
        got = m["fact"] if m else None
        assert got not in ("on_jangad", "on_memo", "on_hold", "in_stock",
                           "kapan_count", "packet_total"), (q, why, got)

    @pytest.mark.parametrize("q", [
        "how many packets are on jangad?",
        "how many stones are out on memo right now?",
        "atyare ketla diamond hold par che?",
        "how many kapans do we have?",
    ])
    def test_none_of_them_asks_for_a_date(self, q):
        """A live snapshot has no time dimension. The date picker on these was
        pure friction."""
        from app.agent import date_gate
        assert date_gate.needs_date(q, []) is False, q


@pytest.mark.integration
class TestTheAnswersReadTheRightColumn:

    @staticmethod
    def _answer(q):
        out = rr.answer(rr.match(q), q)
        return out.get("answer") or ""

    # THESE PIN THE QUERY, NOT THE PROSE. The note under a fact is shown to
    # the client verbatim (no model in the loop), so it was rewritten in
    # business language on 2026-09-03 and will be reworded again. What must
    # never change is WHICH TABLE AND COLUMN the number is read from.

    @staticmethod
    def _sql(key):
        return next(f for f in qf.FACTS if f.key == key).sql(None)

    def test_hold_is_kapan_level_not_the_dead_packet_flag(self):
        """tblPacket.IsOnHold is set on two rows in the whole table. Counting
        it reports 2 where the real figure is five digits."""
        sql = self._sql("on_hold")
        assert "tblKapan" in sql and "k.IsOnHold = 1" in sql
        assert "p.IsOnHold" not in sql
        a = self._answer("atyare ketla diamond hold par che?")
        assert "held kapans" in a
        assert not a.startswith("**2 packets**")

    def test_jangad_counts_packets_not_movements(self):
        """tblJangad is the movement register - one row per Issue or Receive -
        and counting it overstates by roughly 16x."""
        sql = self._sql("on_jangad")
        assert "tblJangadPackets" in sql
        import re
        assert not re.search(r"FROM\s+tblJangad", sql), (
            "counting the movement register, not the packets")
        assert "IsReceived, 0) = 0" in sql

    def test_memo_and_jangad_are_the_same_goods_out_state(self):
        """A RELATIONSHIP, not a figure: they are the same stones recorded two
        ways and must agree closely, whatever the numbers are after a restore.
        If they ever diverge, one of the two readings has broken."""
        import re

        def carats(text):
            m = re.search(r"\(([\d,]+\.?\d*) ct\)", text)
            return float(m.group(1).replace(",", "")) if m else None

        j = carats(self._answer("how many packets are on jangad?"))
        m = carats(self._answer("how many stones are out on memo right now?"))
        assert j and m, (j, m)
        assert abs(j - m) / max(j, m) < 0.05, f"jangad {j} vs memo {m}"

    def test_memo_weight_is_not_the_empty_polished_column(self):
        """PolishedWt is NULL on all but one on-memo packet, so summing it
        reported about ONE carat for a thousand stones - a figure off by 400x
        that would have gone straight into a demo. CurrentWt is populated on
        all of them."""
        sql = self._sql("on_memo")
        assert "CurrentWt" in sql
        assert "PolishedWt" not in sql
        assert "(1.001 ct)" not in self._answer(
            "how many stones are out on memo right now?")

    def test_stock_is_declared_unsettled_rather_than_stated_as_fact(self):
        a = self._answer("how many packets are in stock?")
        assert "settled definition" in a.lower()
        assert "not been finished" in a          # the other basis is offered

    def test_the_total_is_not_passed_off_as_on_hand(self):
        a = self._answer("How many diamonds do we have?")
        assert "NOT what is on hand" in a

    def test_kapan_count_survives_the_reserved_word(self):
        """"Open" is a T-SQL reserved word. The first version aliased a column
        to it, the query failed, the error was swallowed and the fact rendered
        BLANK - worse than an error, because it looks like an answer."""
        a = self._answer("how many kapans do we have?")
        assert a.strip(), "kapan_count rendered nothing"
        assert "kapans" in a and "still open" in a
