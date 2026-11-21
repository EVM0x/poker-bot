"""Tests for the shared decision core of the two ring-game bots.

`playground_s6_bot.py` and `playground_s7_bot.py` are near-copies of each other
and the parts that matter are identical: the hand classifier, the strength
score, the bet sizer and the one decision function. Nothing here touches the
network or the account, so the whole brain is testable offline.

Every test runs against **both** modules, because a fix that lands in only one
of them is a bug that is still live in the other.

Run: python3 -m unittest discover -s test -v
"""

import importlib
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

BOTS = ("playground_s6_bot", "playground_s7_bot")

ACTIONS = {"fold", "check", "call", "bet", "raise", "all_in"}


def load(name):
    return importlib.import_module(name)


def spot(**overrides):
    """A legal postflop spot; each test overrides only what it cares about."""
    base = dict(
        hole=["Ah", "Kd"],
        board=["Qc", "7h", "2s"],
        stack=1000,
        bb=2,
        pot=100,
        current_bet=0,
        min_raise=6,
        position=5,
        seat_count=6,
    )
    base.update(overrides)
    return base


class CredentialImportTest(unittest.TestCase):
    """The bots used to read the account file at import time."""

    def test_every_bot_imports_without_an_account_on_disk(self):
        home = tempfile.mkdtemp()
        assert not os.path.exists(os.path.join(home, ".arena-credentials"))
        old = os.environ.get("HOME")
        os.environ["HOME"] = home
        try:
            for name in BOTS:
                module = importlib.reload(load(name))
                self.assertTrue(hasattr(module, "decide"), name)
                self.assertIsNone(module.API_KEY, name)
        finally:
            if old is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old

    def test_the_credentials_are_read_once_and_cached(self):
        for name in BOTS:
            module = load(name)
            home = tempfile.mkdtemp()
            path = os.path.join(home, ".arena-credentials")
            with open(path, "w") as f:
                json.dump({"apiKey": "test-key", "agentId": "test-agent"}, f)
            module.API_KEY = None
            module.AGENT_ID = None
            old = os.environ.get("HOME")
            os.environ["HOME"] = home
            try:
                module._load_credentials()
                self.assertEqual(module.API_KEY, "test-key", name)
                self.assertEqual(module.AGENT_ID, "test-agent", name)
                os.remove(path)  # a second read would now fail
                module._load_credentials()
                self.assertEqual(module.API_KEY, "test-key", name)
            finally:
                if old is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old
                module.API_KEY = None
                module.AGENT_ID = None


class HandKeyTest(unittest.TestCase):
    def test_pairs_are_written_without_a_suit_suffix(self):
        for name in BOTS:
            key = load(name).make_hand_key
            self.assertEqual(key("Ah", "Ad"), "AA", name)
            self.assertEqual(key("2c", "2s"), "22", name)

    def test_suited_and_offsuit(self):
        for name in BOTS:
            key = load(name).make_hand_key
            self.assertEqual(key("Ah", "Kh"), "AKs", name)
            self.assertEqual(key("Ah", "Kd"), "AKo", name)

    def test_the_higher_rank_comes_first_whatever_the_order(self):
        for name in BOTS:
            key = load(name).make_hand_key
            self.assertEqual(key("Kh", "Ah"), key("Ah", "Kh"), name)
            self.assertEqual(key("7d", "7c"), key("7c", "7d"), name)


class StrengthTest(unittest.TestCase):
    """The score has to rank the hands the way poker does."""

    # hand -> cards, from the best down
    LADDER = [
        ("straight flush", ["9h", "8h"], ["7h", "6h", "5h"]),
        ("quads", ["7h", "7d"], ["7c", "7s", "2h"]),
        ("full house", ["7h", "7d"], ["7c", "Kd", "Kh"]),
        ("flush", ["Ah", "9h"], ["7h", "4h", "2h"]),
        ("straight", ["9h", "8d"], ["7c", "6d", "5h"]),
        ("trips", ["7h", "7d"], ["7c", "Kd", "2h"]),
        ("two pair", ["7h", "Kd"], ["7c", "Kh", "2s"]),
        ("pair", ["7h", "Kd"], ["7c", "9h", "2s"]),
        ("high card", ["7h", "Kd"], ["9c", "4h", "2s"]),
    ]

    def test_every_hand_beats_the_one_below_it(self):
        for name in BOTS:
            score = load(name).hand_strength
            scored = [(label, score(h, b)) for label, h, b in self.LADDER]
            for (better, high), (worse, low) in zip(scored, scored[1:]):
                self.assertGreater(high, low, "%s: %s (%d) should beat %s (%d)" % (name, better, high, worse, low))

    def test_a_full_house_beats_a_straight(self):
        # Regression: a full house used to score 80 while a straight scored 85,
        # so the bot played its biggest hands as if they were medium ones.
        for name in BOTS:
            score = load(name).hand_strength
            self.assertGreater(score(["7h", "7d"], ["7c", "Kd", "Kh"]), score(["9h", "8d"], ["7c", "6d", "5h"]), name)

    def test_the_score_stays_inside_its_range(self):
        for name in BOTS:
            score = load(name).hand_strength
            for label, hole, board in self.LADDER:
                value = score(hole, board)
                self.assertGreaterEqual(value, 0, name + " " + label)
                self.assertLessEqual(value, 100, name + " " + label)

    def test_the_wheel_counts_as_a_straight(self):
        for name in BOTS:
            score = load(name).hand_strength
            self.assertGreaterEqual(score(["Ah", "2d"], ["3c", "4s", "5h"]), 85, name)

    def test_a_flush_draw_is_worth_more_than_the_bare_high_card(self):
        for name in BOTS:
            score = load(name).hand_strength
            self.assertGreater(score(["Ah", "Kh"], ["7h", "4h", "2s"]), score(["Ah", "Kd"], ["7c", "4s", "2h"]), name)

    def test_no_hole_cards_scores_zero(self):
        for name in BOTS:
            self.assertEqual(load(name).hand_strength([], []), 0, name)


class LegalBetTest(unittest.TestCase):
    def test_a_bet_below_the_minimum_is_refused(self):
        for name in BOTS:
            size = load(name).legal_bet
            self.assertIsNone(size(1, 0.7, 1000, 6), name)
            self.assertIsNone(size(4, 1.2, 1000, 6), name)

    def test_a_bet_at_the_minimum_is_allowed(self):
        for name in BOTS:
            size = load(name).legal_bet
            self.assertEqual(size(10, 0.6, 1000, 6), 6, name)

    def test_a_bet_never_exceeds_the_stack(self):
        for name in BOTS:
            size = load(name).legal_bet
            self.assertEqual(size(10000, 2.5, 300, 6), 300, name)

    def test_an_empty_pot_bets_the_minimum(self):
        for name in BOTS:
            size = load(name).legal_bet
            self.assertEqual(size(0, 0.5, 1000, 6), 6, name)


class DecideTest(unittest.TestCase):
    def test_every_action_is_one_the_table_knows(self):
        for name in BOTS:
            decide = load(name).decide
            for hole in (["Ah", "Ad"], ["7h", "2d"], ["Kh", "Qd"]):
                for board in ([], ["Qc", "7h", "2s"]):
                    action, amount, reason = decide(**spot(hole=hole, board=board))
                    self.assertIn(action, ACTIONS, name)
                    self.assertIsInstance(amount, int, name)
                    self.assertIsInstance(reason, str, name)
                    self.assertTrue(reason, name)

    # spots that actually reach each betting branch, so the invariant below is
    # exercised instead of skipped: monster, strong, medium c-bet, weak stab
    BETTING_SPOTS = [
        (["7h", "7d"], ["7c", "Kd", "Kh"]),   # full house -> monster
        (["7h", "Kd"], ["7c", "Kh", "2s"]),   # two pair -> strong
        (["Ah", "Ad"], ["7c", "Kd", "2h"]),   # overpair -> medium
        (["9h", "9d"], ["Kc", "4s", "2h"]),   # underpair -> weak
    ]

    def test_a_bet_is_never_smaller_than_the_minimum_raise(self):
        # Regression: a small pot produced a bet of 0, which the server rejects.
        for name in BOTS:
            decide = load(name).decide
            for pot in (0, 1, 3, 5, 8, 20, 100, 900):
                for min_raise in (2, 6, 40):
                    for hole, board in self.BETTING_SPOTS:
                        action, amount, reason = decide(
                            **spot(hole=hole, board=board, pot=pot, min_raise=min_raise)
                        )
                        if action in ("bet", "raise"):
                            self.assertGreaterEqual(
                                amount, min_raise,
                                "%s: %s %d with min_raise %d (pot %d, board %s) — %s"
                                % (name, action, amount, min_raise, pot, board, reason),
                            )

    def test_no_action_ever_commits_more_than_the_stack(self):
        for name in BOTS:
            decide = load(name).decide
            for stack in (20, 60, 300, 1000):
                for current_bet in (0, 6, 40, 200):
                    action, amount, _ = decide(**spot(stack=stack, current_bet=current_bet))
                    self.assertLessEqual(amount, stack, "%s: %s %d > stack %d" % (name, action, amount, stack))
                    self.assertGreaterEqual(amount, 0, name)

    def test_a_full_house_is_played_as_a_monster(self):
        # Strength 92 now clears the monster threshold of 85, so the bot bets
        # big instead of taking the medium line.
        for name in BOTS:
            action, amount, reason = load(name).decide(
                **spot(hole=["7h", "7d"], board=["7c", "Kd", "Kh"], pot=100)
            )
            self.assertEqual(action, "bet", "%s: %s" % (name, reason))
            self.assertEqual(amount, 250, name)

    def test_junk_folds_to_a_bet(self):
        for name in BOTS:
            action, _, _ = load(name).decide(**spot(hole=["7h", "2d"], board=["Qc", "9h", "4s"], current_bet=80))
            self.assertEqual(action, "fold", name)

    def test_a_premium_hand_opens_preflop(self):
        for name in BOTS:
            action, amount, _ = load(name).decide(**spot(hole=["Ah", "Ad"], board=[], pot=3, current_bet=0, min_raise=4))
            self.assertIn(action, ("raise", "all_in"), name)
            self.assertGreaterEqual(amount, 4, name)

    def test_the_big_blind_checks_when_it_is_free(self):
        for name in BOTS:
            action, amount, _ = load(name).decide(
                **spot(hole=["7h", "2d"], board=[], pot=4, current_bet=0, position=0)
            )
            self.assertEqual(action, "check", name)
            self.assertEqual(amount, 0, name)

    def test_a_short_stack_shoves_or_folds(self):
        for name in BOTS:
            decide = load(name).decide
            action, amount, _ = decide(**spot(hole=["Ah", "Ad"], board=[], stack=10, bb=2, pot=3, min_raise=4))
            self.assertEqual(action, "all_in", name)
            self.assertEqual(amount, 10, name)
            action, amount, _ = decide(**spot(hole=["7h", "2d"], board=[], stack=10, bb=2, pot=3, min_raise=4))
            self.assertEqual(action, "fold", name)
            self.assertEqual(amount, 0, name)

    def test_the_same_spot_always_gets_the_same_answer(self):
        for name in BOTS:
            decide = load(name).decide
            first = decide(**spot())
            for _ in range(20):
                self.assertEqual(decide(**spot()), first, name)


if __name__ == "__main__":
    unittest.main()
