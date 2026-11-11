"""Tests for election schedules, platform constraints, hotkeys, and stop conditions."""

import os
import random
import tempfile
import unittest
from unittest.mock import patch

from constants import (
    CAREER_MAX_CYCLES,
    TIER_CITY_COUNCIL,
    TIER_GOVERNOR,
    TIER_HOUSE,
    TIER_MAYOR,
    TIER_PRESIDENT,
    TIER_SENATOR,
    TIER_STATE_LEG,
)
from custom_types import QuitGame, RestartGame
from data_tracker import load_party_names
import runner
from simulator import (
    build_parties,
    find_party_for_platform,
    is_election_cycle,
    is_valid_candidate_coordinate,
    platform_matches_party,
)


class TestRules(unittest.TestCase):
    """Verify game rules: election schedules, party bounds, hotkeys, win/loss stops."""

    def test_election_cycle_schedules(self):
        # City Council & State Leg: every cycle
        for c in range(1, 10):
            self.assertTrue(is_election_cycle(TIER_CITY_COUNCIL, c))
            self.assertTrue(is_election_cycle(TIER_STATE_LEG, c))

        # Mayor: odd cycles; House: even cycles
        for c in range(1, 10):
            self.assertEqual(is_election_cycle(TIER_MAYOR, c), c % 2 == 1)
            self.assertEqual(is_election_cycle(TIER_HOUSE, c), c % 2 == 0)

        # Governor & Senator waves A(0), B(1), C(2)
        self.assertTrue(is_election_cycle(TIER_GOVERNOR, 1, wave=0))
        self.assertFalse(is_election_cycle(TIER_GOVERNOR, 1, wave=1))
        self.assertTrue(is_election_cycle(TIER_GOVERNOR, 2, wave=1))
        self.assertTrue(is_election_cycle(TIER_GOVERNOR, 3, wave=2))
        self.assertTrue(is_election_cycle(TIER_SENATOR, 4, wave=0))

        # President: every 4 cycles (1, 5, 9, ...)
        pres_cycles = [c for c in range(1, 14) if is_election_cycle(TIER_PRESIDENT, c)]
        self.assertEqual(pres_cycles, [1, 5, 9, 13])

    def test_platform_validation_and_party_lock(self):
        parties = build_parties(2, load_party_names())
        self.assertFalse(is_valid_candidate_coordinate(0.50))
        self.assertFalse(is_valid_candidate_coordinate(0.00))
        self.assertFalse(is_valid_candidate_coordinate(1.00))
        self.assertFalse(is_valid_candidate_coordinate(0.123))
        self.assertTrue(is_valid_candidate_coordinate(0.01))
        self.assertTrue(is_valid_candidate_coordinate(0.49))
        self.assertTrue(is_valid_candidate_coordinate(0.51))
        self.assertTrue(is_valid_candidate_coordinate(0.99))

        p_idx = find_party_for_platform([0.12, 0.88], parties)
        self.assertEqual(parties[p_idx].platform, [0.25, 0.75])
        self.assertTrue(platform_matches_party([0.49, 0.51], parties[p_idx].platform))
        self.assertFalse(platform_matches_party([0.51, 0.51], parties[p_idx].platform))

        with self.assertRaises(ValueError):
            find_party_for_platform([0.50, 0.75], parties)

    def test_global_hotkeys_quit_and_restart_wipe_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = os.path.join(tmp, "data")
            os.makedirs(data_dir, exist_ok=True)
            dummy_file = os.path.join(data_dir, "historical_data.xlsx")
            with open(dummy_file, "w", encoding="utf-8") as f:
                f.write("dummy")

            prompt_q = runner.make_prompt_fn(raw_input_fn=lambda _: "Q", data_dir=data_dir)
            with self.assertRaises(QuitGame):
                prompt_q("Enter anything: ")
            self.assertEqual(os.listdir(data_dir), [])

            with open(dummy_file, "w", encoding="utf-8") as f:
                f.write("dummy")
            prompt_r = runner.make_prompt_fn(raw_input_fn=lambda _: "r", data_dir=data_dir)
            with self.assertRaises(RestartGame):
                prompt_r("Enter anything: ")
            self.assertEqual(os.listdir(data_dir), [])

    def test_restart_then_quit_in_main_driver(self):
        inputs = iter(["MyNation", "r", "OtherNation", "q"])
        outputs: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = os.path.join(tmp, "data")
            results_dir = os.path.join(tmp, "results")
            result = runner.main(
                raw_input_fn=lambda _: next(inputs),
                output_fn=outputs.append,
                data_dir=data_dir,
                results_dir=results_dir,
            )
            self.assertIsNone(result)
            joined = "\n".join(outputs)
            self.assertIn("Restarting game", joined)
            self.assertIn("Exiting game", joined)
            self.assertEqual(os.listdir(data_dir), [])

    def test_lose_election_stop_condition(self):
        # Player picks party 0 ([0.25]), mock live election to always return party 1 -> immediate loss on cycle 1
        inputs = iter(
            [
                "LossNation",  # nation name
                "1",  # 1 issue
                "1",  # Economic Policy
                "Tester",  # candidate name
                "1",  # home state 1
                "1",  # home city 1
                "1",  # home district 1
                "n",  # skip historical
                "0.25",  # platform -> party 0
                "n",  # tweak? no
                "n",  # save results? no
            ]
        )

        def fake_live(races, parties, player_party, input_fn, output_fn=print, **kwargs):
            return {r.seat_key: (1, 75.0) for r in races}, []

        with tempfile.TemporaryDirectory() as tmp:
            data_dir = os.path.join(tmp, "data")
            results_dir = os.path.join(tmp, "results")
            with patch("runner.run_live_elections", side_effect=fake_live):
                outcome = runner.run_single_game(
                    raw_input_fn=lambda _: next(inputs),
                    output_fn=lambda _: None,
                    data_dir=data_dir,
                    results_dir=results_dir,
                    rng=random.Random(1),
                )
            self.assertEqual(outcome, "lost_election")
            self.assertEqual(os.listdir(data_dir), [])

    def test_timeout_25_cycles_stop_condition(self):
        # Player always wins City Council (party 0), while State Leg in home district stays party 0 forever (never vacates)
        inputs = ["TimeoutNation", "1", "1", "Player", "1", "1", "1", "n", "0.25"]
        for _ in range(CAREER_MAX_CYCLES):
            inputs.append("n")  # tweak platform? no
        inputs.append("n")  # save results? no
        it = iter(inputs)

        def fake_live(races, parties, player_party, input_fn, output_fn=print, **kwargs):
            return {r.seat_key: (0, 60.0) for r in races}, []

        def fake_default(pop_pos, platforms, rng=None):
            return 0  # Party 0 holds State Leg & Mayor forever so no vacancy opens

        with tempfile.TemporaryDirectory() as tmp:
            data_dir = os.path.join(tmp, "data")
            results_dir = os.path.join(tmp, "results")
            with (
                patch("runner.run_live_elections", side_effect=fake_live),
                patch("runner.run_default_election", side_effect=fake_default),
                patch("data_tracker.run_default_election", side_effect=fake_default),
            ):
                outcome = runner.run_single_game(
                    raw_input_fn=lambda _: next(it),
                    output_fn=lambda _: None,
                    data_dir=data_dir,
                    results_dir=results_dir,
                    rng=random.Random(2),
                )
            self.assertEqual(outcome, "lost_timeout")

    def test_win_presidency_stop_condition(self):
        # Mock resolve_cycle_assignments so on cycle 1 player runs for President and wins!
        inputs = iter(
            [
                "WinNation",
                "1",
                "1",
                "PresWinner",
                "1",
                "1",
                "1",
                "n",
                "0.25",
                "n",  # tweak?
                "n",  # save results?
            ]
        )

        from custom_types import Candidate, ElectionAssignment

        def fake_resolve(self, cycle, nation, player):
            p_cand = Candidate(
                name=player.name,
                party_index=player.party_index,
                platform=list(player.platform),
                tier=TIER_PRESIDENT,
                seat_id=(TIER_PRESIDENT, ()),
                is_player=True,
            )
            assign = ElectionAssignment(
                seat_key=(TIER_PRESIDENT, ()),
                tier=TIER_PRESIDENT,
                candidate=p_cand,
                is_promotion=True,
                is_reelection=False,
            )
            return {(TIER_PRESIDENT, ()): assign}, assign

        def fake_live(races, parties, player_party, input_fn, output_fn=print, **kwargs):
            return {r.seat_key: (0, 58.0) for r in races}, []

        with tempfile.TemporaryDirectory() as tmp:
            data_dir = os.path.join(tmp, "data")
            results_dir = os.path.join(tmp, "results")
            with (
                patch.object(runner.SeniorityTracker, "resolve_cycle_assignments", fake_resolve),
                patch("runner.run_live_elections", side_effect=fake_live),
            ):
                outcome = runner.run_single_game(
                    raw_input_fn=lambda _: next(inputs),
                    output_fn=lambda _: None,
                    data_dir=data_dir,
                    results_dir=results_dir,
                    rng=random.Random(3),
                )
            self.assertEqual(outcome, "won")


if __name__ == "__main__":
    unittest.main()

