"""Tests for live election scoping, 10-batch reporting, and batch prompts."""

import os
import random
import tempfile
import unittest

import numpy as np

from constants import (
    LIVE_BATCHES,
    TIER_CITY_COUNCIL,
    TIER_GOVERNOR,
    TIER_HOUSE,
    TIER_MAYOR,
    TIER_PRESIDENT,
    TIER_SENATOR,
    TIER_STATE_LEG,
    VOTES_PER_DISTRICT,
)
from custom_types import PlayerProfile, QuitGame
from data_tracker import (
    NameManager,
    SeniorityTracker,
    load_in_party_names,
    load_out_party_names,
    load_party_names,
)
from reporter import run_live_elections
from runner import make_prompt_fn
from simulator import build_nation


class TestLive(unittest.TestCase):
    """Verify live election scope rules and 10-batch user-paced reporting."""

    def test_live_scope_for_all_seven_tiers(self):
        rng = random.Random(12)
        nation = build_nation("ScopeNation", ["Economy"], load_party_names(), rng=rng)
        with tempfile.TemporaryDirectory() as tmp:
            tracker = SeniorityTracker(filepath=os.path.join(tmp, "seniority.xlsx"))

            # City Council & State Leg: 40 races in home city
            self.assertEqual(
                len(tracker.get_live_seat_keys(TIER_CITY_COUNCIL, 1, nation, 3, 2)), 40
            )
            self.assertEqual(
                len(tracker.get_live_seat_keys(TIER_STATE_LEG, 2, nation, 3, 2)), 40
            )
            # Mayor: 10 in home state on odd cycles, 0 on even
            self.assertEqual(len(tracker.get_live_seat_keys(TIER_MAYOR, 1, nation, 3, 2)), 10)
            self.assertEqual(len(tracker.get_live_seat_keys(TIER_MAYOR, 2, nation, 3, 2)), 0)
            # House: 10 in home state on even cycles, 0 on odd
            self.assertEqual(len(tracker.get_live_seat_keys(TIER_HOUSE, 2, nation, 3, 2)), 10)
            self.assertEqual(len(tracker.get_live_seat_keys(TIER_HOUSE, 1, nation, 3, 2)), 0)
            # Senate: 1 race in your home state per cycle (wave A/B/C)
            sen_keys = tracker.get_live_seat_keys(TIER_SENATOR, 1, nation, 3, 2)
            self.assertEqual(sen_keys, [(TIER_SENATOR, (3, 0))])
            # Governor: 17, 17, 16 states across cycles 1, 2, 3
            self.assertEqual(len(tracker.get_live_seat_keys(TIER_GOVERNOR, 1, nation, 3, 2)), 17)
            self.assertEqual(len(tracker.get_live_seat_keys(TIER_GOVERNOR, 2, nation, 3, 2)), 17)
            self.assertEqual(len(tracker.get_live_seat_keys(TIER_GOVERNOR, 3, nation, 3, 2)), 16)
            # President: 1 national race on presidential cycle
            self.assertEqual(
                tracker.get_live_seat_keys(TIER_PRESIDENT, 1, nation, 3, 2),
                [(TIER_PRESIDENT, ())],
            )

    def test_ten_batch_reporting_prompts_and_final_call(self):
        rng = random.Random(88)
        np_rng = np.random.default_rng(88)
        nation = build_nation(
            "LiveNation", ["Economy", "Healthcare"], load_party_names(), rng=rng
        )
        player = PlayerProfile(
            name="Live Player",
            home_state=0,
            home_city=0,
            home_district=0,
            party_index=0,
            platform=[0.25, 0.25],
        )

        with tempfile.TemporaryDirectory() as tmp:
            tracker = SeniorityTracker(filepath=os.path.join(tmp, "seniority.xlsx"))
            nm = NameManager(
                load_in_party_names(),
                load_out_party_names(),
                player_name=player.name,
                rng=rng,
            )
            assignments, _ = tracker.resolve_cycle_assignments(1, nation, player)
            races = tracker.build_live_races(
                TIER_CITY_COUNCIL, 1, nation, player, assignments, nm, rng=rng
            )
            self.assertEqual(len(races), 40)
            self.assertTrue(any(r.has_player for r in races))

            prompts: list[str] = []
            outputs: list[str] = []

            def fake_input(msg: str) -> str:
                prompts.append(msg)
                return ""

            outcomes, batches = run_live_elections(
                races=races,
                parties=nation.parties,
                player_party=0,
                input_fn=fake_input,
                output_fn=outputs.append,
                rng=rng,
                np_rng=np_rng,
            )

            self.assertEqual(len(batches), LIVE_BATCHES)
            self.assertEqual(len(prompts), LIVE_BATCHES)
            self.assertEqual(len(outcomes), 40)

            # Check incremental reporting from 10% to 100%
            joined = "\n".join(outputs)
            self.assertIn("Batch 1/10", joined)
            self.assertIn("Batch 10/10", joined)
            self.assertIn("FINAL CALLED ELECTION RESULTS", joined)
            self.assertIn("[YOUR RACE]", joined)

            # Final batch total votes per district race == 10,000
            final_snap = batches[-1].race_snapshots[0]
            self.assertEqual(final_snap.votes_reported, VOTES_PER_DISTRICT)
            self.assertEqual(sum(final_snap.candidate_votes.values()), VOTES_PER_DISTRICT)
            self.assertGreaterEqual(outcomes[final_snap.seat_key][1], 50.0 - 1e-9)

    def test_empty_live_races_and_batch_hotkey_quit(self):
        rng = random.Random(9)
        nation = build_nation("EmptyLive", ["Economy"], load_party_names(), rng=rng)
        outputs: list[str] = []
        outcomes, batches = run_live_elections(
            races=[],
            parties=nation.parties,
            player_party=0,
            input_fn=lambda _: "",
            output_fn=outputs.append,
        )
        self.assertEqual(outcomes, {})
        self.assertEqual(batches, [])
        self.assertIn("No elections in your live scope", outputs[0])

        # Verify Q at batch prompt wipes data and quits
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = os.path.join(tmp, "data")
            os.makedirs(data_dir, exist_ok=True)
            with open(os.path.join(data_dir, "seniority.xlsx"), "w", encoding="utf-8") as f:
                f.write("temp")
            tracker = SeniorityTracker(filepath=os.path.join(data_dir, "seniority.xlsx"))
            nm = NameManager(
                load_in_party_names(), load_out_party_names(), player_name="P", rng=rng
            )
            player = PlayerProfile("P", 0, 0, 0, 0, [0.25])
            assignments, _ = tracker.resolve_cycle_assignments(1, nation, player)
            races = tracker.build_live_races(
                TIER_CITY_COUNCIL, 1, nation, player, assignments, nm, rng=rng
            )
            prompt_fn = make_prompt_fn(raw_input_fn=lambda _: "q", data_dir=data_dir)
            with self.assertRaises(QuitGame):
                run_live_elections(
                    races=races[:1],
                    parties=nation.parties,
                    player_party=0,
                    input_fn=prompt_fn,
                    output_fn=lambda _: None,
                    rng=rng,
                )
            self.assertEqual(os.listdir(data_dir), [])


if __name__ == "__main__":
    unittest.main()

