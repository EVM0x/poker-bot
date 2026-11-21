"""Tests for the heads-up strategy module.

`strategy_hu.py` is the whole brain of the bot: a hand classifier, a strength
score, and one deterministic decision function. Nothing in it does I/O, so it
is testable without a table or a network. These tests pin the behaviour the
live bot relies on — the score bands, the wheel, and the rule that a bet can
never exceed the stack.

Run: python3 -m unittest discover -s test -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import strategy_hu as sh  # noqa: E402


def table(**overrides):
    """A legal heads-up spot; each test overrides only the field it cares about."""
    base = {
        "hole_cards": ["Ah", "Kd"],
        "community_cards": [],
        "stack": 1000,
        "current_bet": 0,
        "pot": 0,
        "min_raise": 6,
        "big_blind": 2,
        "position": "BTN",
        "seat_count": 2,
        "allowed_actions": ["fold", "check", "call", "bet", "raise", "all_in"],
    }
    base.update(overrides)
    return base


class HandKeyTest(unittest.TestCase):
    def test_orders_the_ranks_high_first(self):
        self.assertEqual(sh.hand_key("Kd", "Ah"), "AKo")

    def test_is_symmetric(self):
        self.assertEqual(sh.hand_key("Ah", "Kd"), sh.hand_key("Kd", "Ah"))

    def test_marks_suited_only_when_the_suits_match(self):
        self.assertEqual(sh.hand_key("Ah", "Kh"), "AKs")
        self.assertEqual(sh.hand_key("Ah", "Kd"), "AKo")

    def test_pocket_pair_has_no_suit_suffix(self):
        self.assertEqual(sh.hand_key("9h", "9d"), "99")


class HandStrengthTest(unittest.TestCase):
    def test_no_hole_cards_scores_zero(self):
        self.assertEqual(sh.hand_strength([], []), 0)
        self.assertEqual(sh.hand_strength(["Ah"], []), 0)

    def test_score_always_lands_in_range(self):
        boards = [
            [],
            ["2c", "7d", "9h"],
            ["Ah", "Kh", "Qh", "Jh", "Th"],
        ]
        for hole in (["Ah", "Ad"], ["2c", "7d"], ["As", "Ks"]):
            for board in boards:
                score = sh.hand_strength(hole, board)
                self.assertGreaterEqual(score, 0)
                self.assertLessEqual(score, 100)

    def test_made_hands_rank_in_poker_order(self):
        straight_flush = sh.hand_strength(["Ah", "Kh"], ["Qh", "Jh", "Th"])
        quads = sh.hand_strength(["9h", "9d"], ["9c", "9s", "2d"])
        flush = sh.hand_strength(["Ah", "Kh"], ["7h", "4h", "2h"])
        straight = sh.hand_strength(["9h", "8d"], ["7c", "6s", "5d"])
        trips = sh.hand_strength(["9h", "9d"], ["9c", "2s", "7d"])
        two_pair = sh.hand_strength(["9h", "7d"], ["9c", "7s", "2d"])
        one_pair = sh.hand_strength(["9h", "Ad"], ["9c", "2s", "7d"])

        self.assertEqual(straight_flush, 100)
        self.assertGreater(straight_flush, quads)
        self.assertGreater(quads, flush)
        self.assertGreater(flush, straight)
        self.assertGreater(straight, trips)
        self.assertGreater(trips, two_pair)
        self.assertGreater(two_pair, one_pair)

    def test_the_wheel_counts_as_a_straight(self):
        # A-2-3-4-5 is a straight even though the ranks wrap around the ace.
        self.assertGreaterEqual(sh.hand_strength(["Ah", "2d"], ["3c", "4s", "5h"]), 85)

    def test_broadway_straight_counts(self):
        self.assertGreaterEqual(sh.hand_strength(["Ah", "Kd"], ["Qc", "Js", "Th"]), 85)

    def test_flush_draw_gets_a_bonus_but_cannot_pass_a_made_flush(self):
        draw = sh.hand_strength(["Ah", "Kh"], ["7h", "4h", "2c"])
        made = sh.hand_strength(["Ah", "Kh"], ["7h", "4h", "2h"])
        self.assertLess(draw, made)
        self.assertGreater(draw, sh.hand_strength(["Ah", "Kd"], ["7c", "4s", "2c"]))

    def test_a_higher_pair_scores_higher(self):
        low = sh.hand_strength(["4h", "Ad"], ["4c", "2s", "7d"])
        high = sh.hand_strength(["Kh", "Ad"], ["Kc", "2s", "7d"])
        self.assertGreater(high, low)


class PreflopTest(unittest.TestCase):
    def test_folds_with_fewer_than_two_cards(self):
        self.assertEqual(sh.act(table(hole_cards=["Ah"]))["action"], "fold")

    def test_button_opens_premiums_with_a_raise(self):
        out = sh.act(table(hole_cards=["Ah", "Ad"], position="BTN"))
        self.assertEqual(out["action"], "raise")
        self.assertGreaterEqual(out["amount"], 6)

    def test_button_folds_trash(self):
        self.assertEqual(sh.act(table(hole_cards=["7c", "2d"], position="BTN"))["action"], "fold")

    def test_big_blind_checks_when_there_is_nothing_to_call(self):
        self.assertEqual(
            sh.act(table(hole_cards=["7c", "2d"], position="BB", current_bet=0))["action"],
            "check",
        )

    def test_big_blind_defends_a_small_open(self):
        out = sh.act(table(hole_cards=["9h", "8h"], position="BB", current_bet=6, pot=9))
        self.assertEqual(out["action"], "call")

    def test_big_blind_folds_trash_to_a_large_open(self):
        out = sh.act(table(hole_cards=["7c", "2d"], position="BB", current_bet=20, pot=24))
        self.assertEqual(out["action"], "fold")

    def test_short_stack_shoves_a_premium(self):
        out = sh.act(table(hole_cards=["Ah", "Ad"], position="BTN", stack=20, big_blind=2))
        self.assertEqual(out["action"], "all_in")
        self.assertEqual(out["amount"], 20)


class PostflopTest(unittest.TestCase):
    BOARD = ["Qh", "Jh", "Th"]

    def test_monster_bets_when_checked_to(self):
        out = sh.act(table(hole_cards=["Ah", "Kh"], community_cards=self.BOARD, pot=100))
        self.assertIn(out["action"], {"bet", "all_in"})

    def test_monster_raises_a_bet(self):
        out = sh.act(table(
            hole_cards=["Ah", "Kh"], community_cards=self.BOARD, current_bet=50, pot=100,
        ))
        self.assertIn(out["action"], {"raise", "all_in"})

    def test_trash_folds_to_a_bet(self):
        out = sh.act(table(
            hole_cards=["2c", "7d"], community_cards=["Ah", "Ks", "Qd"],
            current_bet=40, pot=60, position="BB",
        ))
        self.assertEqual(out["action"], "fold")

    def test_trash_checks_when_it_can(self):
        out = sh.act(table(
            hole_cards=["2c", "7d"], community_cards=["Ah", "Ks", "Qd"],
            current_bet=0, pot=60, position="BB",
        ))
        self.assertEqual(out["action"], "check")

    def test_medium_hand_checks_a_scary_board(self):
        # Board has three hearts: the straight draw is not worth betting into.
        out = sh.act(table(
            hole_cards=["9c", "9d"], community_cards=["Kh", "7h", "2h"], pot=100,
            position="BTN",
        ))
        self.assertEqual(out["action"], "check")

    def test_never_bets_more_than_the_stack(self):
        for hole, board in (
            (["Ah", "Kh"], ["Qh", "Jh", "Th"]),
            (["9h", "9d"], ["9c", "7s", "2d"]),
            (["Ah", "Kd"], ["7c", "4s", "2c"]),
        ):
            for pot in (0, 10, 500, 5000):
                out = sh.act(table(hole_cards=hole, community_cards=board, pot=pot, stack=200))
                if "amount" in out:
                    self.assertLessEqual(
                        out["amount"], 200,
                        f"{hole} on {board} pot {pot} bet {out['amount']} over stack",
                    )

    def test_decision_is_deterministic(self):
        spot = table(
            hole_cards=["Ah", "Kh"], community_cards=self.BOARD, current_bet=30, pot=90,
        )
        self.assertEqual(sh.act(spot), sh.act(dict(spot)))


if __name__ == "__main__":
    unittest.main()
