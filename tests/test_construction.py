"""Tests that all nation, party, and position vector data structures build correctly."""

import random
import unittest

from constants import (
    CITIES_PER_STATE,
    CONSERVATIVE_PLATFORM,
    DISTRICTS_PER_CITY,
    LIBERAL_PLATFORM,
    MAX_POS,
    MID_POS,
    MIN_POS,
    NUM_STATES,
    SENATORS_PER_STATE,
)
from data_tracker import load_party_names
from simulator import build_nation, build_parties


class TestConstruction(unittest.TestCase):
    """Verify geographic hierarchy, party counts, and position vector properties."""

    def test_party_counts_and_unique_platforms(self):
        party_names = load_party_names()
        for num_issues in (1, 2, 3):
            parties = build_parties(num_issues, party_names)
            self.assertEqual(len(parties), 2**num_issues)
            seen = set()
            for idx, party in enumerate(parties):
                self.assertEqual(party.index, idx)
                self.assertEqual(len(party.platform), num_issues)
                self.assertTrue(
                    all(v in (CONSERVATIVE_PLATFORM, LIBERAL_PLATFORM) for v in party.platform)
                )
                seen.add(tuple(party.platform))
            self.assertEqual(len(seen), 2**num_issues)

        with self.assertRaises(ValueError):
            build_parties(0, party_names)
        with self.assertRaises(ValueError):
            build_parties(4, party_names)

    def test_nation_hierarchy_and_positions(self):
        rng = random.Random(12345)
        party_names = load_party_names()
        issues = ["Economy", "Healthcare", "Environment"]
        nation = build_nation("Testland", issues, party_names, rng=rng)

        self.assertEqual(nation.name, "Testland")
        self.assertEqual(nation.issues, issues)
        self.assertEqual(nation.position, [MID_POS, MID_POS, MID_POS])
        self.assertEqual(len(nation.parties), 8)
        self.assertEqual(len(nation.states), NUM_STATES)

        wave_counts = {0: 0, 1: 0, 2: 0}
        total_cities = 0
        total_districts = 0

        for s_idx, state in enumerate(nation.states):
            self.assertEqual(state.index, s_idx)
            self.assertIn(state.wave, (0, 1, 2))
            wave_counts[state.wave] += 1
            self.assertEqual(len(state.senator_parties), SENATORS_PER_STATE)
            self._assert_valid_vector(state.position, 3)

            self.assertEqual(len(state.cities), CITIES_PER_STATE)
            total_cities += len(state.cities)
            for c_idx, city in enumerate(state.cities):
                self.assertEqual(city.index, c_idx)
                self.assertEqual(city.state_index, s_idx)
                self._assert_valid_vector(city.position, 3)

                self.assertEqual(len(city.districts), DISTRICTS_PER_CITY)
                total_districts += len(city.districts)
                for d_idx, dist in enumerate(city.districts):
                    self.assertEqual(dist.index, d_idx)
                    self.assertEqual(dist.city_index, c_idx)
                    self.assertEqual(dist.state_index, s_idx)
                    self._assert_valid_vector(dist.position, 3)

        self.assertEqual(total_cities, 500)
        self.assertEqual(total_districts, 20000)
        self.assertEqual(wave_counts, {0: 17, 1: 17, 2: 16})

    def test_triangular_inheritance_clusters_around_parent(self):
        rng = random.Random(99)
        party_names = load_party_names()
        nation = build_nation("TriNation", ["Issue 1"], party_names, rng=rng)

        conservative_states = [s for s in nation.states if s.position[0] <= 0.15]
        liberal_states = [s for s in nation.states if s.position[0] >= 0.85]
        self.assertTrue(conservative_states and liberal_states)

        cons_city_mean = sum(
            c.position[0] for s in conservative_states for c in s.cities
        ) / (len(conservative_states) * CITIES_PER_STATE)
        lib_city_mean = sum(
            c.position[0] for s in liberal_states for c in s.cities
        ) / (len(liberal_states) * CITIES_PER_STATE)

        self.assertLess(cons_city_mean, 0.45)
        self.assertGreater(lib_city_mean, 0.55)

    def _assert_valid_vector(self, vec: list[float], expected_len: int) -> None:
        self.assertEqual(len(vec), expected_len)
        for val in vec:
            self.assertGreaterEqual(val, MIN_POS)
            self.assertLessEqual(val, MAX_POS)
            self.assertAlmostEqual(val, round(val, 2), places=6)


if __name__ == "__main__":
    unittest.main()

