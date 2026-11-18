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
        setup_inputs = ["TimeoutNation", "1", "1", "Player", "1", "1", "1", "n", "0.25"]

        def feed_input(text):
            if setup_inputs:
                return setup_inputs.pop(0)
            return "n"

        def fake_live(races, parties, player_party, input_fn, output_fn=print, **kwargs):
            return {r.seat_key: (0, 60.0) for r in races}, []

        def fake_default(pop_pos, platforms, rng=None, **kwargs):
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
                    raw_input_fn=feed_input,
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

    def test_primary_challenge_win_flow(self):
        # Player wins City Council in cycle 1. In cycle 2, issues primary challenge for State Leg, wins it, and wins general!
        inputs = iter(
            [
                "PrimNation", "1", "1", "HeroPrim", "1", "1", "1", "n", "0.25",
                # Cycle 1: City Council general tweak
                "n",
                # Cycle 2: Primary challenge prompt -> yes!
                "y",
                # Tweak before primary
                "n",
                # Cycle 3 quit
                "q",
            ]
        )
        outputs: list[str] = []

        from custom_types import Candidate, ElectionAssignment

        def fake_resolve(self, cycle, nation, player):
            if cycle == 1:
                cc_key = (TIER_CITY_COUNCIL, (0, 0, 0))
                cand = Candidate(name=player.name, party_index=0, platform=[0.25], tier=TIER_CITY_COUNCIL, seat_id=cc_key, is_player=True)
                assign = ElectionAssignment(seat_key=cc_key, tier=TIER_CITY_COUNCIL, candidate=cand, is_promotion=False, is_reelection=False)
                return {cc_key: assign}, assign
            sl_key = (TIER_STATE_LEG, (0, 0, 0))
            sl_cand = Candidate(name="Leg Nominee", party_index=0, platform=[0.25], tier=TIER_STATE_LEG, seat_id=sl_key, is_player=False)
            assign_sl = ElectionAssignment(seat_key=sl_key, tier=TIER_STATE_LEG, candidate=sl_cand, is_promotion=True, is_reelection=False)
            cc_key = (TIER_CITY_COUNCIL, (0, 0, 0))
            cand = Candidate(name=player.name, party_index=0, platform=[0.25], tier=TIER_CITY_COUNCIL, seat_id=cc_key, is_player=True)
            assign_cc = ElectionAssignment(seat_key=cc_key, tier=TIER_CITY_COUNCIL, candidate=cand, is_promotion=False, is_reelection=True)
            return {sl_key: assign_sl, cc_key: assign_cc}, assign_cc

        def fake_live(races, parties, player_party, input_fn, output_fn=print, **kwargs):
            return {r.seat_key: (0, 60.0) for r in races}, []

        def fake_primary(seat_key, tier, label, districts, player_cand, opponent_cand, party, input_fn, output_fn=print, **kwargs):
            return player_cand, 58.0

        with tempfile.TemporaryDirectory() as tmp:
            data_dir = os.path.join(tmp, "data")
            results_dir = os.path.join(tmp, "results")
            with (
                patch.object(runner.SeniorityTracker, "resolve_cycle_assignments", fake_resolve),
                patch("runner.run_live_elections", side_effect=fake_live),
                patch("runner.run_live_primary_race", side_effect=fake_primary),
            ):
                with self.assertRaises(QuitGame):
                    runner.run_single_game(
                        raw_input_fn=lambda _: next(inputs),
                        output_fn=outputs.append,
                        data_dir=data_dir,
                        results_dir=results_dir,
                        rng=random.Random(10),
                    )
            joined = "\n".join(outputs)
            self.assertIn("PRIMARY VICTORY: You defeated Leg Nominee", joined)
            self.assertIn("nominee for State Legislature", joined)

    def test_primary_challenge_lose_no_stakes_retains_office(self):
        # Player is Mayor (not up for reelection in even cycle 2). Challenges House nominee, loses primary -> retains Mayor office
        inputs = iter(
            [
                "MayorNation", "1", "1", "MayorHero", "1", "1", "1", "n", "0.25",
                # Cycle 1: initial run
                "n",  # tweak?
                # Cycle 2: Primary challenge prompt for House -> yes!
                "y",
                "n",  # tweak?
                "q",  # quit
            ]
        )
        outputs: list[str] = []

        from custom_types import Candidate, ElectionAssignment

        def fake_resolve(self, cycle, nation, player):
            if cycle == 1:
                m_key = (TIER_MAYOR, (0, 0))
                cand = Candidate(name=player.name, party_index=0, platform=[0.25], tier=TIER_MAYOR, seat_id=m_key, is_player=True, cycles_in_office=2, seniority=4)
                assign = ElectionAssignment(seat_key=m_key, tier=TIER_MAYOR, candidate=cand, is_promotion=False, is_reelection=True)
                return {m_key: assign}, assign
            h_key = (TIER_HOUSE, (0, 0))
            h_cand = Candidate(name="Other House", party_index=0, platform=[0.25], tier=TIER_HOUSE, seat_id=h_key, is_player=False)
            assign = ElectionAssignment(seat_key=h_key, tier=TIER_HOUSE, candidate=h_cand, is_promotion=True, is_reelection=False)
            return {h_key: assign}, None

        def fake_live(races, parties, player_party, input_fn, output_fn=print, **kwargs):
            return {r.seat_key: (0, 60.0) for r in races}, []

        def fake_primary(seat_key, tier, label, districts, player_cand, opponent_cand, party, input_fn, output_fn=print, **kwargs):
            return opponent_cand, 54.0  # Player loses primary!

        with tempfile.TemporaryDirectory() as tmp:
            data_dir = os.path.join(tmp, "data")
            results_dir = os.path.join(tmp, "results")

            with (
                patch.object(runner.SeniorityTracker, "resolve_cycle_assignments", fake_resolve),
                patch("runner.run_live_elections", side_effect=fake_live),
                patch("runner.run_live_primary_race", side_effect=fake_primary),
            ):
                with self.assertRaises(QuitGame):
                    runner.run_single_game(
                        raw_input_fn=lambda _: next(inputs),
                        output_fn=outputs.append,
                        data_dir=data_dir,
                        results_dir=results_dir,
                        rng=random.Random(11),
                    )

            joined = "\n".join(outputs)
            self.assertIn("NO STAKES", joined)
            self.assertIn("PRIMARY DEFEAT", joined)
            self.assertIn("You retain your current office as Mayor", joined)

    def test_primary_challenge_lose_high_stakes_game_over(self):
        # Player is City Council (up for reelection every cycle). Challenges State Leg, loses primary -> Game Over!
        inputs = iter(
            [
                "StakesNation", "1", "1", "StakesHero", "1", "1", "1", "n", "0.25",
                # Cycle 1: City Council win
                "n",  # tweak?
                # Cycle 2: Primary challenge prompt -> yes!
                "y",
                "n",  # tweak?
                "n",  # save results? no
            ]
        )
        outputs: list[str] = []

        def fake_live(races, parties, player_party, input_fn, output_fn=print, **kwargs):
            return {r.seat_key: (0, 60.0) for r in races}, []

        def fake_primary(seat_key, tier, label, districts, player_cand, opponent_cand, party, input_fn, output_fn=print, **kwargs):
            return opponent_cand, 57.0  # Player loses primary!

        from custom_types import Candidate, ElectionAssignment

        def fake_resolve(self, cycle, nation, player):
            if cycle == 1:
                cc_key = (TIER_CITY_COUNCIL, (0, 0, 0))
                cand = Candidate(name=player.name, party_index=0, platform=[0.25], tier=TIER_CITY_COUNCIL, seat_id=cc_key, is_player=True)
                assign = ElectionAssignment(seat_key=cc_key, tier=TIER_CITY_COUNCIL, candidate=cand, is_promotion=False, is_reelection=False)
                return {cc_key: assign}, assign
            sl_key = (TIER_STATE_LEG, (0, 0, 0))
            sl_cand = Candidate(name="Leg Nominee", party_index=0, platform=[0.25], tier=TIER_STATE_LEG, seat_id=sl_key, is_player=False)
            assign_sl = ElectionAssignment(seat_key=sl_key, tier=TIER_STATE_LEG, candidate=sl_cand, is_promotion=True, is_reelection=False)
            cc_key = (TIER_CITY_COUNCIL, (0, 0, 0))
            cand = Candidate(name=player.name, party_index=0, platform=[0.25], tier=TIER_CITY_COUNCIL, seat_id=cc_key, is_player=True)
            assign_cc = ElectionAssignment(seat_key=cc_key, tier=TIER_CITY_COUNCIL, candidate=cand, is_promotion=False, is_reelection=True)
            return {sl_key: assign_sl, cc_key: assign_cc}, assign_cc

        with tempfile.TemporaryDirectory() as tmp:
            data_dir = os.path.join(tmp, "data")
            results_dir = os.path.join(tmp, "results")
            with (
                patch.object(runner.SeniorityTracker, "resolve_cycle_assignments", fake_resolve),
                patch("runner.run_live_elections", side_effect=fake_live),
                patch("runner.run_live_primary_race", side_effect=fake_primary),
            ):
                outcome = runner.run_single_game(
                    raw_input_fn=lambda _: next(inputs),
                    output_fn=outputs.append,
                    data_dir=data_dir,
                    results_dir=results_dir,
                    rng=random.Random(12),
                )
            self.assertEqual(outcome, "lost_election")
            joined = "\n".join(outputs)
            self.assertIn("STAKES: You are up for re-election", joined)
            self.assertIn("PRIMARY DEFEAT", joined)
            self.assertIn("Game Over!", joined)

    def test_primary_challenge_general_loss_no_stakes_retains_office(self):
        # Player is Mayor (not up for reelection in cycle 2). Wins primary for House, but loses general election -> retains Mayor!
        inputs = iter(
            [
                "GenLossNation", "1", "1", "MayorGen", "1", "1", "1", "n", "0.25",
                "n",  # tweak cycle 1
                "y",  # issue primary challenge? yes!
                "n",  # tweak before primary? no
                "q",  # quit after cycle 2
            ]
        )
        outputs: list[str] = []

        from custom_types import Candidate, ElectionAssignment

        def fake_resolve(self, cycle, nation, player):
            if cycle == 1:
                m_key = (TIER_MAYOR, (0, 0))
                cand = Candidate(name=player.name, party_index=0, platform=[0.25], tier=TIER_MAYOR, seat_id=m_key, is_player=True, cycles_in_office=2, seniority=4)
                assign = ElectionAssignment(seat_key=m_key, tier=TIER_MAYOR, candidate=cand, is_promotion=False, is_reelection=True)
                return {m_key: assign}, assign
            h_key = (TIER_HOUSE, (0, 0))
            h_cand = Candidate(name="Other House", party_index=0, platform=[0.25], tier=TIER_HOUSE, seat_id=h_key, is_player=False)
            assign = ElectionAssignment(seat_key=h_key, tier=TIER_HOUSE, candidate=h_cand, is_promotion=True, is_reelection=False)
            return {h_key: assign}, None

        def fake_primary(seat_key, tier, label, districts, player_cand, opponent_cand, party, input_fn, output_fn=print, **kwargs):
            return player_cand, 60.0  # Player wins primary!

        def fake_live(races, parties, player_party, input_fn, output_fn=print, **kwargs):
            # In cycle 1, player wins (party 0). In cycle 2 (House general), player loses (party 1 wins)!
            if any(r.tier == TIER_MAYOR for r in races):
                return {r.seat_key: (0, 60.0) for r in races}, []
            return {r.seat_key: (1, 65.0) for r in races}, []

        with tempfile.TemporaryDirectory() as tmp:
            data_dir = os.path.join(tmp, "data")
            results_dir = os.path.join(tmp, "results")
            with (
                patch.object(runner.SeniorityTracker, "resolve_cycle_assignments", fake_resolve),
                patch("runner.run_live_elections", side_effect=fake_live),
                patch("runner.run_live_primary_race", side_effect=fake_primary),
            ):
                with self.assertRaises(QuitGame):
                    runner.run_single_game(
                        raw_input_fn=lambda _: next(inputs),
                        output_fn=outputs.append,
                        data_dir=data_dir,
                        results_dir=results_dir,
                        rng=random.Random(13),
                    )
            joined = "\n".join(outputs)
            self.assertIn("PRIMARY VICTORY", joined)
            self.assertIn("You lost the general election", joined)
            self.assertIn("you retain your current office!", joined)

    def test_retaliatory_primary_challenge_after_defying_party_manager(self):
        # Defying party manager triggers retaliatory primary in the next election
        inputs = iter(
            [
                "RetalNation", "1", "1", "RetalHero", "1", "1", "1", "n", "0.25",
                "n",  # cycle 1 tweak
                # Cycle 2: Primary challenge prompt -> yes!
                "y",
                "n",  # tweak
                # Cycle 3: Player faces retaliatory primary challenge!
                "n",  # tweak before primary
                # Cycle 3: General election
                "n",  # tweak general
                "q",  # quit
            ]
        )
        outputs: list[str] = []

        from custom_types import Candidate, ElectionAssignment

        def fake_resolve(self, cycle, nation, player):
            if cycle == 1:
                # Re-elected Mayor in cycle 1 (already completed 1 term)
                m_key = (TIER_MAYOR, (0, 0))
                cand = Candidate(name=player.name, party_index=0, platform=[0.25], tier=TIER_MAYOR, seat_id=m_key, is_player=True, cycles_in_office=2, seniority=4)
                assign = ElectionAssignment(seat_key=m_key, tier=TIER_MAYOR, candidate=cand, is_promotion=False, is_reelection=True)
                return {m_key: assign}, assign
            if cycle == 2:
                # Cycle 2: House up, not selected
                h_key = (TIER_HOUSE, (0, 0))
                h_cand = Candidate(name="House Nominee", party_index=0, platform=[0.25], tier=TIER_HOUSE, seat_id=h_key, is_player=False)
                assign = ElectionAssignment(seat_key=h_key, tier=TIER_HOUSE, candidate=h_cand, is_promotion=True, is_reelection=False)
                return {h_key: assign}, None
            # Cycle 3: Mayor reelection (odd cycle)
            m_key = (TIER_MAYOR, (0, 0))
            cand = Candidate(name=player.name, party_index=0, platform=[0.25], tier=TIER_MAYOR, seat_id=m_key, is_player=True)
            assign = ElectionAssignment(seat_key=m_key, tier=TIER_MAYOR, candidate=cand, is_promotion=False, is_reelection=True)
            return {m_key: assign}, assign

        def fake_primary(seat_key, tier, label, districts, player_cand, opponent_cand, party, input_fn, output_fn=print, **kwargs):
            if "House" in label:
                # Cycle 2: player loses primary with no stakes
                return opponent_cand, 55.0
            # Cycle 3: player survives retaliatory primary!
            return player_cand, 60.0

        def fake_live(races, parties, player_party, input_fn, output_fn=print, **kwargs):
            return {r.seat_key: (0, 60.0) for r in races}, []

        with tempfile.TemporaryDirectory() as tmp:
            data_dir = os.path.join(tmp, "data")
            results_dir = os.path.join(tmp, "results")
            with (
                patch.object(runner.SeniorityTracker, "resolve_cycle_assignments", fake_resolve),
                patch("runner.run_live_elections", side_effect=fake_live),
                patch("runner.run_live_primary_race", side_effect=fake_primary),
            ):
                with self.assertRaises(QuitGame):
                    runner.run_single_game(
                        raw_input_fn=lambda _: next(inputs),
                        output_fn=outputs.append,
                        data_dir=data_dir,
                        results_dir=results_dir,
                        rng=random.Random(14),
                    )
            joined = "\n".join(outputs)
            self.assertIn("RETALIATORY PRIMARY CHALLENGE", joined)
            self.assertIn("You survived the retaliatory primary challenge", joined)

    def test_retaliatory_primary_challenge_waits_for_next_player_election(self):
        # Defying party manager sets pending_party_challenge.
        # In cycle 3, player is sitting Senator not up for election -> NO retaliatory primary in cycle 3!
        # In cycle 4, player is up for election -> retaliatory primary challenge triggers for Senate seat!
        inputs = iter(
            [
                "WaitNation", "1", "1", "WaitHero", "1", "1", "1", "n", "0.25",
                # Cycle 1: initial run
                "n",
                # Cycle 2: Primary challenge prompt -> yes!
                "y",
                "n",  # tweak before primary
                # Cycle 3: Player is sitting Senator, NOT up for election!
                # Player just watches live election -> no primary prompt, no tweak prompt!
                # Cycle 4: Player's Senate seat is up for election -> retaliatory challenge triggers!
                "n",  # tweak before retaliatory primary
                "n",  # tweak before general election
                "q",  # quit after cycle 4
            ]
        )
        outputs: list[str] = []

        from custom_types import Candidate, ElectionAssignment

        def fake_resolve(self, cycle, nation, player):
            if cycle == 1:
                # Re-elected House Member in cycle 1 (already completed 1 term)
                h_key = (TIER_HOUSE, (0, 0))
                cand = Candidate(name=player.name, party_index=0, platform=[0.25], tier=TIER_HOUSE, seat_id=h_key, is_player=True, cycles_in_office=2, seniority=4)
                assign = ElectionAssignment(seat_key=h_key, tier=TIER_HOUSE, candidate=cand, is_promotion=False, is_reelection=True)
                return {h_key: assign}, assign
            if cycle == 2:
                # Senate seat up, nominee is someone else
                s_key = (TIER_SENATOR, (0, 1))
                s_cand = Candidate(name="Other Senator", party_index=0, platform=[0.25], tier=TIER_SENATOR, seat_id=s_key, is_player=False)
                assign = ElectionAssignment(seat_key=s_key, tier=TIER_SENATOR, candidate=s_cand, is_promotion=True, is_reelection=False)
                return {s_key: assign}, None
            if cycle == 3:
                # Cycle 3: player is sitting Senator, not up for election. House seat is up with an NPC.
                h_key = (TIER_HOUSE, (0, 0))
                h_cand = Candidate(name="House Guy", party_index=0, platform=[0.25], tier=TIER_HOUSE, seat_id=h_key, is_player=False)
                assign = ElectionAssignment(seat_key=h_key, tier=TIER_HOUSE, candidate=h_cand, is_promotion=True, is_reelection=False)
                return {h_key: assign}, None
            # Cycle 4: player is up for reelection in Senate!
            s_key = (TIER_SENATOR, (0, 1))
            cand = Candidate(name=player.name, party_index=0, platform=[0.25], tier=TIER_SENATOR, seat_id=s_key, is_player=True)
            assign = ElectionAssignment(seat_key=s_key, tier=TIER_SENATOR, candidate=cand, is_promotion=False, is_reelection=True)
            return {s_key: assign}, assign

        def fake_primary(seat_key, tier, label, districts, player_cand, opponent_cand, party, input_fn, output_fn=print, **kwargs):
            # In cycle 2: player wins primary challenge
            # In cycle 4: player survives retaliatory primary challenge!
            return player_cand, 62.0

        def fake_live(races, parties, player_party, input_fn, output_fn=print, **kwargs):
            return {r.seat_key: (0, 60.0) for r in races}, []

        with tempfile.TemporaryDirectory() as tmp:
            data_dir = os.path.join(tmp, "data")
            results_dir = os.path.join(tmp, "results")
            with (
                patch.object(runner.SeniorityTracker, "resolve_cycle_assignments", fake_resolve),
                patch("runner.run_live_elections", side_effect=fake_live),
                patch("runner.run_live_primary_race", side_effect=fake_primary),
            ):
                with self.assertRaises(QuitGame):
                    runner.run_single_game(
                        raw_input_fn=lambda _: next(inputs),
                        output_fn=outputs.append,
                        data_dir=data_dir,
                        results_dir=results_dir,
                        rng=random.Random(15),
                    )
            joined = "\n".join(outputs)
            # Verify cycle 3 showed player watching, not in retaliatory challenge
            self.assertIn("You are not up for election this cycle (currently Senator)", joined)
            # Verify cycle 4 had retaliatory challenge for Senator
            self.assertIn("entered a challenger against you for Senator", joined)
            self.assertNotIn("entered a challenger against you for House", joined)

    def test_must_serve_at_least_one_complete_term_before_advancing(self):
        # Player is elected Mayor for the first time in cycle 1.
        # In cycle 2 (served 1/2 cycles of Mayor term), player CANNOT advance (no promotion, no primary challenge prompt).
        # In cycle 3 (completed full 2-cycle term), player CAN advance / challenge.
        inputs = iter(
            [
                "TermNation", "1", "1", "TermHero", "1", "1", "1", "n", "0.25",
                # Cycle 1: elected Mayor for first time
                "n",  # tweak?
                # Cycle 2: in middle of first term (cannot advance) -> watches live election, no primary challenge prompt!
                # Cycle 3: term completed -> primary challenge prompt appears!
                "y",  # issue primary challenge? yes!
                "n",  # tweak before primary
                "q",  # quit
            ]
        )
        outputs: list[str] = []

        from custom_types import Candidate, ElectionAssignment

        def fake_resolve(self, cycle, nation, player):
            if cycle == 1:
                # Elected Mayor for first time
                m_key = (TIER_MAYOR, (0, 0))
                cand = Candidate(name=player.name, party_index=0, platform=[0.25], tier=TIER_MAYOR, seat_id=m_key, is_player=True)
                assign = ElectionAssignment(seat_key=m_key, tier=TIER_MAYOR, candidate=cand, is_promotion=False, is_reelection=False)
                return {m_key: assign}, assign
            if cycle == 2:
                # House nominee exists in cycle 2
                h_key = (TIER_HOUSE, (0, 0))
                h_cand = Candidate(name="House Nominee", party_index=0, platform=[0.25], tier=TIER_HOUSE, seat_id=h_key, is_player=False)
                assign = ElectionAssignment(seat_key=h_key, tier=TIER_HOUSE, candidate=h_cand, is_promotion=True, is_reelection=False)
                return {h_key: assign}, None
            # Cycle 3: Senate nominee exists
            s_key = (TIER_SENATOR, (0, 2))
            s_cand = Candidate(name="Senate Nominee", party_index=0, platform=[0.25], tier=TIER_SENATOR, seat_id=s_key, is_player=False)
            assign = ElectionAssignment(seat_key=s_key, tier=TIER_SENATOR, candidate=s_cand, is_promotion=True, is_reelection=False)
            return {s_key: assign}, None

        def fake_primary(seat_key, tier, label, districts, player_cand, opponent_cand, party, input_fn, output_fn=print, **kwargs):
            return player_cand, 60.0

        def fake_live(races, parties, player_party, input_fn, output_fn=print, **kwargs):
            return {r.seat_key: (0, 60.0) for r in races}, []

        with tempfile.TemporaryDirectory() as tmp:
            data_dir = os.path.join(tmp, "data")
            results_dir = os.path.join(tmp, "results")
            with (
                patch.object(runner.SeniorityTracker, "resolve_cycle_assignments", fake_resolve),
                patch("runner.run_live_elections", side_effect=fake_live),
                patch("runner.run_live_primary_race", side_effect=fake_primary),
            ):
                with self.assertRaises(QuitGame):
                    runner.run_single_game(
                        raw_input_fn=lambda _: next(inputs),
                        output_fn=outputs.append,
                        data_dir=data_dir,
                        results_dir=results_dir,
                        rng=random.Random(16),
                    )
            joined = "\n".join(outputs)
            # In Cycle 2, player was not up for election and was NOT offered a primary challenge
            self.assertIn("CYCLE 2", joined)
            self.assertIn("You are not up for election this cycle (currently Mayor)", joined)
            # In Cycle 3, after serving a complete term, primary challenge was offered and won
            self.assertIn("CYCLE 3", joined)
            self.assertIn("PRIMARY VICTORY: You defeated Senate Nominee", joined)


if __name__ == "__main__":
    unittest.main()

