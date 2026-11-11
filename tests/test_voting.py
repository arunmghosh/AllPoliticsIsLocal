"""Tests for election probability math, RCV scaling, batches, and backlash oscillation."""

import random
import unittest

import numpy as np

from constants import (
    LIVE_BATCHES,
    TIER_CITY_COUNCIL,
    TIER_GOVERNOR,
    TIER_PRESIDENT,
    VOTES_PER_BATCH,
    VOTES_PER_DISTRICT,
)
from custom_types import Candidate, LiveRaceSpec
from data_tracker import load_party_names
from simulator import (
    allocate_batch_votes,
    apply_live_cycle_oscillation,
    build_nation,
    compute_backlash_position,
    compute_probabilities,
    compute_rcv_percentages,
    num_voting_rounds,
    precompute_race_probabilities,
    simulate_district_batch,
    simulate_live_batch,
)


class TestVoting(unittest.TestCase):
    """Verify voting probability distribution, RCV math, batches, and oscillation."""

    def test_probabilities_inverse_distance_and_zero_distance_smoothing(self):
        probs = compute_probabilities([0.25, 0.75], [[0.25, 0.75], [0.75, 0.25]])
        self.assertAlmostEqual(sum(probs), 1.0, places=9)
        self.assertGreater(probs[0], 0.95)
        self.assertGreater(probs[0], probs[1])

        # Equal distances yield equal probabilities
        equal_probs = compute_probabilities([0.50], [[0.25], [0.75]])
        self.assertAlmostEqual(equal_probs[0], 0.50, places=9)
        self.assertAlmostEqual(equal_probs[1], 0.50, places=9)

    def test_backlash_oscillation_and_boundary_guards(self):
        # Population 0.50 vs conservative status quo 0.25 -> shifts +0.01 to 0.51
        self.assertEqual(compute_backlash_position([0.50], [0.25]), [0.51])
        # Population 0.51 vs liberal status quo 0.75 -> shifts -0.01 to 0.50
        self.assertEqual(compute_backlash_position([0.51], [0.75]), [0.50])
        # Boundary guard: at 0.01 (< 0.25) -> no shift; at 0.99 (> 0.75) -> no shift
        self.assertEqual(compute_backlash_position([0.01, 0.99], [0.25, 0.75]), [0.01, 0.99])
        # Equal to status quo -> no shift
        self.assertEqual(compute_backlash_position([0.50], [0.50]), [0.50])

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

    def test_district_batch_and_vote_allocation_helpers(self):
        rng = random.Random(15)
        shares = simulate_district_batch([0.6, 0.25, 0.1, 0.05], rng=rng)
        self.assertAlmostEqual(sum(shares), 1.0, places=9)
        votes = allocate_batch_votes(shares, VOTES_PER_BATCH)
        self.assertEqual(sum(votes), VOTES_PER_BATCH)
        self.assertTrue(all(v >= 0 for v in votes))

    def test_all_politics_is_local_live_oscillation_scope(self):
        rng = random.Random(55)
        nation = build_nation("LocalNation", ["Economy"], load_party_names(), rng=rng)
        nation.president_party = 0
        nation.states[0].governor_party = 0
        nation.states[0].senator_parties = [0, 0, 0]
        dist = nation.states[0].cities[0].districts[0]
        dist.position = [0.40]
        dist.state_leg_party = 0  # 0.25
        dist.city_council_party = 0  # 0.25

        before_nation = list(nation.position)
        before_state0 = list(nation.states[0].position)

        # When President & Governor are live, Nation and State do NOT oscillate,
        # while the tracked district DOES oscillate away from 0.25 -> 0.41!
        apply_live_cycle_oscillation(
            nation=nation,
            home_state=0,
            home_city=0,
            home_district=0,
            live_tiers={TIER_PRESIDENT, TIER_GOVERNOR},
            district_incumbents_tracked=True,
        )
        self.assertEqual(nation.position, before_nation)
        self.assertEqual(nation.states[0].position, before_state0)
        self.assertEqual(dist.position, [0.41])


if __name__ == "__main__":
    unittest.main()

