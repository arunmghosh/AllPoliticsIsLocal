"""Tests for name pools, shuffling/pointer drawing, recycling suffixes, and opponent reuse."""

import os
import random
import tempfile
import unittest

from constants import TIER_CITY_COUNCIL, TIER_STATE_LEG
from custom_types import PlayerProfile
from data_tracker import (
    NameManager,
    SeniorityTracker,
    load_in_party_names,
    load_out_party_names,
    load_party_names,
)
from simulator import build_nation


class TestNaming(unittest.TestCase):
    """Verify name file specs, pointer-based drawing, recycling, and tier caching."""

    def test_name_files_counts_and_uniqueness(self):
        parties = load_party_names()
        in_names = load_in_party_names()
        out_names = load_out_party_names()

        self.assertEqual(len(parties), 8)
        self.assertEqual(len(set(parties)), 8)

        self.assertEqual(len(in_names), 500)
        self.assertEqual(len(set(in_names)), 500)
        self.assertTrue(all(" " in name for name in in_names))

        self.assertEqual(len(out_names), 2500)
        self.assertEqual(len(set(out_names)), 2500)
        self.assertTrue(all(" " in name for name in out_names))

        self.assertEqual(len(set(in_names) & set(out_names)), 0)

    def test_in_party_sequential_pointer_and_recycling(self):
        pool_in = ["Alice A", "Bob B", "Carol C"]
        pool_out = ["Opp 1", "Opp 2", "Opp 3"]

        nm1 = NameManager(pool_in, pool_out, player_name="Bob B", rng=random.Random(7))
        nm2 = NameManager(pool_in, pool_out, player_name="Bob B", rng=random.Random(7))

        drawn1 = [nm1.draw_in_party_name() for _ in range(7)]
        drawn2 = [nm2.draw_in_party_name() for _ in range(7)]
        self.assertEqual(drawn1, drawn2)

        # Player name "Bob B" must never appear without a suffix
        self.assertNotIn("Bob B", drawn1)
        # No duplicate names drawn
        self.assertEqual(len(set(drawn1)), 7)
        # Suffixes "2" and "3" should appear as we wrap around the 3-name list
        self.assertTrue(any(name.endswith(" 2") for name in drawn1))
        self.assertTrue(any(name.endswith(" 3") for name in drawn1))

    def test_active_names_never_duplicated(self):
        pool_in = ["Jane Doe", "John Roe"]
        pool_out = ["Opp One", "Opp Two", "Opp Three"]
        nm = NameManager(pool_in, pool_out, rng=random.Random(1))

        active = {"Jane Doe", "Opp One"}
        in_name = nm.draw_in_party_name(active)
        self.assertEqual(in_name, "John Roe")
        out_name = nm.draw_out_party_name(active)
        self.assertNotEqual(out_name, "Opp One")

    def test_opponent_names_persist_same_tier_and_refresh_on_level_up(self):
        rng = random.Random(42)
        nation = build_nation("NameNation", ["Economy"], load_party_names(), rng=rng)
        player = PlayerProfile(
            name="Hero Player",
            home_state=0,
            home_city=0,
            home_district=0,
            party_index=0,
            platform=[0.25],
        )

        with tempfile.TemporaryDirectory() as tmp:
            tracker = SeniorityTracker(filepath=os.path.join(tmp, "seniority.xlsx"))
            nm = NameManager(
                load_in_party_names(),
                load_out_party_names(),
                player_name=player.name,
                rng=random.Random(10),
            )

            assignments1, _ = tracker.resolve_cycle_assignments(1, nation, player)
            races_cc_1 = tracker.build_live_races(
                TIER_CITY_COUNCIL, 1, nation, player, assignments1, nm, rng=rng
            )
            opp_names_cc_1 = {
                r.seat_key: {c.party_index: c.name for c in r.candidates if c.party_index != 0}
                for r in races_cc_1
            }

            # Same tier on cycle 2 -> must reuse exact same opponent names
            races_cc_2 = tracker.build_live_races(
                TIER_CITY_COUNCIL, 2, nation, player, assignments1, nm, rng=rng
            )
            opp_names_cc_2 = {
                r.seat_key: {c.party_index: c.name for c in r.candidates if c.party_index != 0}
                for r in races_cc_2
            }
            self.assertEqual(opp_names_cc_1, opp_names_cc_2)

            # Level up to State Leg -> must draw fresh opponent names
            races_sl = tracker.build_live_races(
                TIER_STATE_LEG, 2, nation, player, assignments1, nm, rng=rng
            )
            all_cc_opps = {
                name for d in opp_names_cc_1.values() for name in d.values()
            }
            all_sl_opps = {
                c.name for r in races_sl for c in r.candidates if c.party_index != 0
            }
            self.assertEqual(len(all_sl_opps), 40)
            self.assertEqual(len(all_cc_opps & all_sl_opps), 0)


if __name__ == "__main__":
    unittest.main()

