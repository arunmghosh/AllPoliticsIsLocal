"""Tests for election probability math, RCV scaling, batches, and grudge factor."""

import math
import os
import random
import tempfile
import unittest

import numpy as np

from constants import (
    DIRICHLET_KAPPA,
    GRUDGE_BASE,
    LIVE_BATCHES,
    SMOOTHING_TERM,
    TIER_CITY_COUNCIL,
    VOTES_PER_BATCH,
    VOTES_PER_DISTRICT,
)
from custom_types import Candidate, District, LiveRaceSpec
from data_tracker import load_party_names, run_historical_simulation
from simulator import (
    allocate_batch_votes,
    build_nation,
    compute_probabilities,
    compute_rcv_percentages,
    num_voting_rounds,
    precompute_race_probabilities,
    simulate_district_batch,
    simulate_live_batch,
)


class TestVoting(unittest.TestCase):
    """Verify voting probability distribution, RCV math, batches, and grudge factor."""

    def test_probabilities_inverse_sqrt_distance_and_live_consistency(self):
        pop = [0.25, 0.75]
        plats = [[0.25, 0.75], [0.75, 0.25]]
        probs = compute_probabilities(pop, plats)
        self.assertAlmostEqual(sum(probs), 1.0, places=9)

        s0 = 1.0 / math.sqrt(0.0 + SMOOTHING_TERM)
        s1 = 1.0 / math.sqrt(math.sqrt(0.5) + SMOOTHING_TERM)
        self.assertAlmostEqual(probs[0], s0 / (s0 + s1), places=9)
        self.assertAlmostEqual(probs[1], s1 / (s0 + s1), places=9)
        self.assertGreater(probs[0], probs[1])

        # Live race probability matrix must match compute_probabilities on the same district
        race = LiveRaceSpec(
            seat_key=(TIER_CITY_COUNCIL, (0, 0, 0)),
            tier=TIER_CITY_COUNCIL,
            label="Test",
            districts=[District(index=0, city_index=0, state_index=0, position=pop)],
            candidates=[
                Candidate(name="A", party_index=0, platform=plats[0], tier=TIER_CITY_COUNCIL),
                Candidate(name="B", party_index=1, platform=plats[1], tier=TIER_CITY_COUNCIL),
            ],
        )
        mat = precompute_race_probabilities(race)
        self.assertAlmostEqual(float(mat[0, 0]), probs[0], places=9)
        self.assertAlmostEqual(float(mat[0, 1]), probs[1], places=9)

        # Equal distances yield equal probabilities
        equal_probs = compute_probabilities([0.50], [[0.25], [0.75]])
        self.assertAlmostEqual(equal_probs[0], 0.50, places=9)
        self.assertAlmostEqual(equal_probs[1], 0.50, places=9)

    def test_grudge_factor_multiplies_incumbent_distance(self):
        self.assertEqual(GRUDGE_BASE, 1.06)
        pop = [0.50]
        plats = [[0.25], [0.75]]

        # C = 0: equal distances -> 50/50
        probs_c0 = compute_probabilities(pop, plats, incumbent_cycles=[0, 0])
        self.assertAlmostEqual(probs_c0[0], 0.50, places=9)

        # Incumbent party 0 with C = 5 consecutive cycles -> distance 0.25 * 1.06^5
        probs_c5 = compute_probabilities(pop, plats, incumbent_cycles=[5, 0])
        d0_grudge = 0.25 * (GRUDGE_BASE ** 5)
        s0 = 1.0 / math.sqrt(d0_grudge + SMOOTHING_TERM)
        s1 = 1.0 / math.sqrt(0.25 + SMOOTHING_TERM)
        self.assertAlmostEqual(probs_c5[0], s0 / (s0 + s1), places=9)
        self.assertLess(probs_c5[0], probs_c0[0])

        # Live probability matrix applies identical 1.06^C factor to incumbent_party
        race = LiveRaceSpec(
            seat_key=(TIER_CITY_COUNCIL, (0, 0, 0)),
            tier=TIER_CITY_COUNCIL,
            label="Grudge Test",
            districts=[District(index=0, city_index=0, state_index=0, position=pop)],
            candidates=[
                Candidate(name="Inc", party_index=0, platform=plats[0], tier=TIER_CITY_COUNCIL),
                Candidate(name="Chal", party_index=1, platform=plats[1], tier=TIER_CITY_COUNCIL),
            ],
            incumbent_party=0,
            incumbent_cycles=5,
        )
        mat = precompute_race_probabilities(race)
        self.assertAlmostEqual(float(mat[0, 0]), probs_c5[0], places=9)
        self.assertAlmostEqual(float(mat[0, 1]), probs_c5[1], places=9)

    def test_live_batch_voting_and_rcv_winner_at_least_50_percent(self):
        rng = random.Random(77)
        np_rng = np.random.default_rng(77)
        party_names = load_party_names()

        for num_issues in (1, 2, 3):
            num_parties = 2**num_issues
            self.assertEqual(num_voting_rounds(num_parties), num_parties // 2)
            nation = build_nation(
                f"VoteTest{num_issues}",
                [f"Issue {i}" for i in range(num_issues)],
                party_names,
                rng=rng,
            )

            # Single-district race and multi-district race (40 districts)
            for districts in (
                [nation.states[0].cities[0].districts[0]],
                nation.states[0].cities[0].districts,
            ):
                candidates = [
                    Candidate(
                        name=f"Cand {p.index}",
                        party_index=p.index,
                        platform=list(p.platform),
                        tier=TIER_CITY_COUNCIL,
                    )
                    for p in nation.parties
                ]
                race = LiveRaceSpec(
                    seat_key=(TIER_CITY_COUNCIL, (0, 0, 0)),
                    tier=TIER_CITY_COUNCIL,
                    label="Test Race",
                    districts=districts,
                    candidates=candidates,
                )
                prob_mat = precompute_race_probabilities(race)
                totals = {p.index: 0 for p in nation.parties}
                for _ in range(LIVE_BATCHES):
                    batch_votes = simulate_live_batch(
                        race, prob_matrix=prob_mat, rng=rng, np_rng=np_rng
                    )
                    self.assertEqual(sum(batch_votes), VOTES_PER_BATCH * len(districts))
                    for c, v in zip(candidates, batch_votes):
                        totals[c.party_index] += v

                self.assertEqual(sum(totals.values()), VOTES_PER_DISTRICT * len(districts))
                rcv_pcts = compute_rcv_percentages(totals, num_parties)
                winner_pct = max(rcv_pcts.values())
                self.assertGreaterEqual(winner_pct, 50.0 - 1e-9)

    def test_dirichlet_batch_distribution_and_vote_allocation_helpers(self):
        self.assertEqual(DIRICHLET_KAPPA, 20.0)
        rng = random.Random(15)
        probs = [0.6, 0.25, 0.1, 0.05]
        shares = simulate_district_batch(probs, rng=rng)
        self.assertAlmostEqual(sum(shares), 1.0, places=9)
        self.assertTrue(all(s >= 0.0 for s in shares))

        votes = allocate_batch_votes(shares, VOTES_PER_BATCH)
        self.assertEqual(sum(votes), VOTES_PER_BATCH)
        self.assertTrue(all(v >= 0 for v in votes))

        # Verify empirical Dirichlet(kappa * probs) mean and variance across samples
        samples = [simulate_district_batch(probs, rng=rng) for _ in range(1500)]
        for i, p_i in enumerate(probs):
            col = [s[i] for s in samples]
            mean = sum(col) / len(col)
            var = sum((x - mean) ** 2 for x in col) / len(col)
            expected_var = p_i * (1.0 - p_i) / (DIRICHLET_KAPPA + 1.0)
            self.assertAlmostEqual(mean, p_i, delta=0.02)
            self.assertAlmostEqual(var, expected_var, delta=0.004)

    def test_population_positions_unchanged_after_historical_simulation(self):
        rng = random.Random(55)
        nation = build_nation("FixedPopNation", ["Economy"], load_party_names(), rng=rng)
        before_nation = list(nation.position)
        before_state = list(nation.states[0].position)
        before_city = list(nation.states[0].cities[0].position)
        before_dist = list(nation.states[0].cities[0].districts[0].position)

        with tempfile.TemporaryDirectory() as tmp:
            hist_path = os.path.join(tmp, "historical_data.xlsx")
            rows, _ = run_historical_simulation(
                nation=nation,
                home_state=0,
                home_city=0,
                home_district=0,
                num_cycles=10,
                filepath=hist_path,
                rng=rng,
            )
            self.assertEqual(len(rows), 10)

        self.assertEqual(nation.position, before_nation)
        self.assertEqual(nation.states[0].position, before_state)
        self.assertEqual(nation.states[0].cities[0].position, before_city)
        self.assertEqual(nation.states[0].cities[0].districts[0].position, before_dist)


if __name__ == "__main__":
    unittest.main()

