"""Tests for vacancy resolution, seniority advancement, tie-breaking, and fallback."""

import os
import random
import tempfile
import unittest

from constants import (
    TIER_CITY_COUNCIL,
    TIER_GOVERNOR,
    TIER_HOUSE,
    TIER_MAYOR,
    TIER_PRESIDENT,
    TIER_SENATOR,
    TIER_STATE_LEG,
)
from custom_types import Candidate, PlayerProfile
from data_tracker import (
    NameManager,
    SeniorityTracker,
    load_in_party_names,
    load_out_party_names,
    load_party_names,
    read_seniority_data,
    run_historical_simulation,
)
from simulator import build_nation, platform_matches_party


class TestSeniority(unittest.TestCase):
    """Verify seniority calculation, tier promotions, tiebreakers, and updates."""

    def test_initial_roster_from_historical_data(self):
        rng = random.Random(101)
        nation = build_nation("SenNation", ["Economy"], load_party_names(), rng=rng)
        with tempfile.TemporaryDirectory() as tmp:
            hist_path = os.path.join(tmp, "historical_data.xlsx")
            sen_path = os.path.join(tmp, "seniority.xlsx")
            rows, streaks = run_historical_simulation(
                nation,
                home_state=0,
                home_city=0,
                home_district=0,
                num_cycles=6,
                filepath=hist_path,
                rng=rng,
            )
            nm = NameManager(
                load_in_party_names(), load_out_party_names(), player_name="Tester", rng=rng
            )
            tracker = SeniorityTracker(filepath=sen_path)
            tracker.initialize_starting_roster(
                nation=nation,
                home_state=0,
                home_city=0,
                player_party=0,
                name_manager=nm,
                historical_rows=rows,
                streaks=streaks,
                rng=rng,
            )

            # City Council seats must all be vacant at start
            self.assertFalse(any(sk[0] == TIER_CITY_COUNCIL for sk in tracker.roster))

            # Check spreadsheet columns and initial Victory Size == 0
            saved_rows = read_seniority_data(sen_path)
            self.assertEqual(len(saved_rows), len(tracker.roster))
            for r in saved_rows:
                self.assertEqual(r["Victory Size"], 0)
                self.assertIn(r["Level of Office"], (1, 2, 3, 4, 5, 6))
                self.assertGreaterEqual(r["Seniority"], 2)

            # Verify President seniority matches consecutive ending rows in historical_data
            pres_key = (TIER_PRESIDENT, ())
            if nation.president_party == 0:
                expected_streak = 0
                for row in reversed(rows):
                    if row["President"] == 0:
                        expected_streak += 1
                    else:
                        break
                self.assertEqual(tracker.roster[pres_key].seniority, expected_streak * 2)

    def test_tiebreaker_by_victory_size_and_fallback_to_lower_tier(self):
        rng = random.Random(202)
        nation = build_nation("TieNation", ["Economy"], load_party_names(), rng=rng)
        player = PlayerProfile(
            name="Player One",
            home_state=0,
            home_city=0,
            home_district=0,
            party_index=0,
            platform=[0.25],
            current_tier=TIER_GOVERNOR,
            current_seat=(TIER_GOVERNOR, (0,)),
        )

        with tempfile.TemporaryDirectory() as tmp:
            tracker = SeniorityTracker(filepath=os.path.join(tmp, "seniority.xlsx"))
            # Two Governors tied at seniority=4; player has higher victory_size
            gov0_key = (TIER_GOVERNOR, (0,))
            gov1_key = (TIER_GOVERNOR, (1,))
            tracker.roster[gov0_key] = Candidate(
                name="Player One",
                party_index=0,
                platform=[0.25],
                tier=TIER_GOVERNOR,
                seat_id=gov0_key,
                seniority=4,
                victory_size=62.5,
                is_player=True,
            )
            tracker.roster[gov1_key] = Candidate(
                name="Rival Gov",
                party_index=0,
                platform=[0.25],
                tier=TIER_GOVERNOR,
                seat_id=gov1_key,
                seniority=4,
                victory_size=55.0,
                is_player=False,
            )

            # Cycle 5 is a Presidential election cycle ((5-1)%4 == 0)
            assignments, player_assign = tracker.resolve_cycle_assignments(5, nation, player)
            self.assertIsNotNone(player_assign)
            self.assertEqual(player_assign.seat_key, (TIER_PRESIDENT, ()))
            self.assertTrue(player_assign.is_promotion)
            self.assertNotIn(gov0_key, tracker.roster)

            # Test fallback: no Governors in party -> most senior Senator runs for President
            tracker2 = SeniorityTracker(filepath=os.path.join(tmp, "seniority2.xlsx"))
            sen_key = (TIER_SENATOR, (3, 1))
            tracker2.roster[sen_key] = Candidate(
                name="Fallback Sen",
                party_index=0,
                platform=[0.25],
                tier=TIER_SENATOR,
                seat_id=sen_key,
                seniority=6,
                victory_size=58.0,
                is_player=False,
            )
            assignments2, _ = tracker2.resolve_cycle_assignments(5, nation, player)
            self.assertEqual(assignments2[(TIER_PRESIDENT, ())].candidate.name, "Fallback Sen")

    def test_post_cycle_seniority_updates_and_term_limit(self):
        rng = random.Random(303)
        nation = build_nation("UpdateNation", ["Economy"], load_party_names(), rng=rng)
        player = PlayerProfile(
            name="Player Hero",
            home_state=0,
            home_city=0,
            home_district=0,
            party_index=0,
            platform=[0.25],
            current_tier=TIER_CITY_COUNCIL,
            current_seat=(TIER_CITY_COUNCIL, (0, 0, 0)),
        )

        with tempfile.TemporaryDirectory() as tmp:
            sen_path = os.path.join(tmp, "seniority.xlsx")
            tracker = SeniorityTracker(filepath=sen_path)
            nm = NameManager(
                load_in_party_names(), load_out_party_names(), player_name=player.name, rng=rng
            )

            cc_key = (TIER_CITY_COUNCIL, (0, 0, 0))
            sl_other_key = (TIER_STATE_LEG, (0, 0, 1))
            mayor_key = (TIER_MAYOR, (0, 0))
            house_key = (TIER_HOUSE, (0, 1))
            gov_pres_key = (TIER_GOVERNOR, (1,))
            gov2_key = (TIER_GOVERNOR, (2,))
            pres_key = (TIER_PRESIDENT, ())

            tracker.roster[cc_key] = Candidate(
                name="Player Hero",
                party_index=0,
                platform=[0.25],
                tier=TIER_CITY_COUNCIL,
                seat_id=cc_key,
                seniority=2,
                victory_size=54.0,
                is_player=True,
            )
            tracker.roster[sl_other_key] = Candidate(
                name="Reelect Leg",
                party_index=0,
                platform=[0.25],
                tier=TIER_STATE_LEG,
                seat_id=sl_other_key,
                seniority=4,
                victory_size=51.0,
            )
            tracker.roster[mayor_key] = Candidate(
                name="Sitting Mayor",
                party_index=0,
                platform=[0.25],
                tier=TIER_MAYOR,
                seat_id=mayor_key,
                seniority=2,
                victory_size=53.0,
            )
            tracker.roster[house_key] = Candidate(
                name="Sitting House",
                party_index=0,
                platform=[0.25],
                tier=TIER_HOUSE,
                seat_id=house_key,
                seniority=4,
                victory_size=57.0,
            )
            tracker.roster[gov_pres_key] = Candidate(
                name="Pres Nominee Gov",
                party_index=0,
                platform=[0.25],
                tier=TIER_GOVERNOR,
                seat_id=gov_pres_key,
                seniority=8,
                victory_size=61.0,
            )
            tracker.roster[gov2_key] = Candidate(
                name="Quiet Gov",
                party_index=0,
                platform=[0.25],
                tier=TIER_GOVERNOR,
                seat_id=gov2_key,
                seniority=4,
                victory_size=60.0,
            )
            tracker.roster[pres_key] = Candidate(
                name="Term Out Pres",
                party_index=0,
                platform=[0.25],
                tier=TIER_PRESIDENT,
                seat_id=pres_key,
                seniority=6,
                victory_size=52.0,
            )

            # Cycle 5 is odd (Mayor up), Presidential election cycle (Pres terms out), State Leg vacant in dist 0
            assignments, p_assign = tracker.resolve_cycle_assignments(5, nation, player)
            # Outgoing President must be term-limited out
            self.assertNotIn("Term Out Pres", {c.name for c in tracker.roster.values()})
            self.assertEqual(assignments[pres_key].candidate.name, "Pres Nominee Gov")
            # Player should promote from City Council (dist 0) -> State Leg (dist 0)
            self.assertEqual(p_assign.seat_key, (TIER_STATE_LEG, (0, 0, 0)))
            self.assertTrue(p_assign.is_promotion)

            # Outcomes: Player wins State Leg (65%), Reelect Leg wins (59%), Sitting Mayor LOSES reelection
            outcomes = {sk: (1, 55.0) for sk in assignments}
            outcomes[(TIER_STATE_LEG, (0, 0, 0))] = (0, 65.0)
            outcomes[sl_other_key] = (0, 59.0)
            outcomes[mayor_key] = (1, 55.0)

            tracker.apply_cycle_outcomes(
                cycle=5,
                nation=nation,
                player=player,
                assignments=assignments,
                outcomes=outcomes,
                name_manager=nm,
                rng=rng,
            )

            # Player moved up -> tier 6, seniority 0, victory_size 65.0
            p_cand = tracker.roster[(TIER_STATE_LEG, (0, 0, 0))]
            self.assertEqual(p_cand.seniority, 0)
            self.assertEqual(p_cand.victory_size, 65.0)
            self.assertEqual(player.current_tier, TIER_STATE_LEG)

            # Reelect Leg won same tier -> seniority 4 + 2 = 6, victory_size 59.0
            self.assertEqual(tracker.roster[sl_other_key].seniority, 6)
            self.assertEqual(tracker.roster[sl_other_key].victory_size, 59.0)

            # Sitting Mayor lost -> removed from roster
            self.assertNotIn(mayor_key, tracker.roster)

            # Quiet Gov was not up -> seniority 4 + 2 = 6
            self.assertEqual(tracker.roster[gov2_key].seniority, 6)

    def test_losing_opponents_redraw_platforms_while_winners_keep_theirs(self):
        rng = random.Random(404)
        nation = build_nation(
            "OppPlatformNation",
            ["Economy", "Social"],
            load_party_names(),
            rng=rng,
        )
        player = PlayerProfile(
            name="Player OppCheck",
            home_state=0,
            home_city=0,
            home_district=0,
            party_index=0,
            platform=[0.25, 0.25],
            current_tier=TIER_CITY_COUNCIL,
            current_seat=(TIER_CITY_COUNCIL, (0, 0, 0)),
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

            seat_a = (TIER_CITY_COUNCIL, (0, 0, 0))  # Player party (0) wins
            seat_b = (TIER_CITY_COUNCIL, (0, 0, 1))  # Opposing party (2) wins

            # Snapshot names and set distinct initial platforms for deterministic verification
            names_a = {
                p: cand.name for p, cand in tracker.opponent_cache[seat_a].items()
            }
            names_b = {
                p: cand.name for p, cand in tracker.opponent_cache[seat_b].items()
            }
            for p, cand in tracker.opponent_cache[seat_a].items():
                cand.platform = [
                    0.01 if nation.parties[p].platform[0] < 0.5 else 0.99,
                    0.01 if nation.parties[p].platform[1] < 0.5 else 0.99,
                ]
            for p, cand in tracker.opponent_cache[seat_b].items():
                cand.platform = [
                    0.02 if nation.parties[p].platform[0] < 0.5 else 0.98,
                    0.02 if nation.parties[p].platform[1] < 0.5 else 0.98,
                ]

            before_a = {
                p: list(cand.platform)
                for p, cand in tracker.opponent_cache[seat_a].items()
            }
            before_b = {
                p: list(cand.platform)
                for p, cand in tracker.opponent_cache[seat_b].items()
            }

            # Add an off-cycle cached seat that is NOT in outcomes
            off_cycle_seat = (TIER_GOVERNOR, (0,))
            off_cand = Candidate(
                name="Off Cycle Opp",
                party_index=1,
                platform=[0.11, 0.88],
                tier=TIER_GOVERNOR,
                seat_id=off_cycle_seat,
            )
            tracker.opponent_cache[off_cycle_seat] = {1: off_cand}

            outcomes = {r.seat_key: (0, 55.0) for r in races}
            outcomes[seat_a] = (0, 62.0)  # Player's party wins seat_a -> opponents 1,2,3 lose
            outcomes[seat_b] = (2, 58.0)  # Opposing party 2 wins seat_b -> 2 keeps, 1 & 3 lose

            tracker.apply_cycle_outcomes(
                cycle=1,
                nation=nation,
                player=player,
                assignments=assignments,
                outcomes=outcomes,
                name_manager=nm,
                rng=random.Random(909),
            )

            # Seat A: all opposing candidates lost -> names preserved, platforms redrawn within party bounds
            for p in (1, 2, 3):
                cand = tracker.opponent_cache[seat_a][p]
                self.assertEqual(cand.name, names_a[p])
                self.assertTrue(
                    platform_matches_party(cand.platform, nation.parties[p].platform)
                )
                self.assertNotEqual(cand.platform, before_a[p])

            # Seat B: winning opposing party 2 kept platform; losing parties 1 & 3 redrawn
            self.assertEqual(tracker.opponent_cache[seat_b][2].name, names_b[2])
            self.assertEqual(tracker.opponent_cache[seat_b][2].platform, before_b[2])
            for p in (1, 3):
                cand = tracker.opponent_cache[seat_b][p]
                self.assertEqual(cand.name, names_b[p])
                self.assertTrue(
                    platform_matches_party(cand.platform, nation.parties[p].platform)
                )
                self.assertNotEqual(cand.platform, before_b[p])

            # Off-cycle seat not in outcomes remains untouched
            self.assertEqual(
                tracker.opponent_cache[off_cycle_seat][1].platform, [0.11, 0.88]
            )

    def test_grudge_cycles_in_office_tracking_across_live_races(self):
        rng = random.Random(505)
        nation = build_nation("GrudgeNation", ["Economy"], load_party_names(), rng=rng)
        player = PlayerProfile(
            name="Grudge Player",
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
                rng=rng,
            )

            # Cycle 1: City Council seats vacant -> incumbent_cycles == 0
            a1, _ = tracker.resolve_cycle_assignments(1, nation, player)
            races1 = tracker.build_live_races(
                TIER_CITY_COUNCIL, 1, nation, player, a1, nm, rng=rng
            )
            race_dist0 = next(r for r in races1 if r.seat_key == (TIER_CITY_COUNCIL, (0, 0, 0)))
            race_dist1 = next(r for r in races1 if r.seat_key == (TIER_CITY_COUNCIL, (0, 0, 1)))
            self.assertIsNone(race_dist0.incumbent_party)
            self.assertEqual(race_dist0.incumbent_cycles, 0)

            outcomes1 = {r.seat_key: (0, 55.0) for r in races1}
            outcomes1[race_dist1.seat_key] = (1, 56.0)
            tracker.apply_cycle_outcomes(1, nation, player, a1, outcomes1, nm, rng=rng)

            # Player won dist 0 -> 1 cycle; Party 1 won dist 1 -> 1 cycle
            self.assertEqual(tracker.roster[race_dist0.seat_key].cycles_in_office, 1)
            self.assertEqual(tracker.seat_streaks[race_dist1.seat_key], (1, 1))

            # Cycle 2: Populate higher tiers so player is not promoted and runs for City Council reelection
            tracker.roster[(TIER_GOVERNOR, (0,))] = Candidate(
                name="Gov 0", party_index=0, platform=[0.25], tier=TIER_GOVERNOR,
                seat_id=(TIER_GOVERNOR, (0,)), seniority=4, cycles_in_office=2,
            )
            for w in range(3):
                tracker.roster[(TIER_SENATOR, (0, w))] = Candidate(
                    name=f"Sen {w}", party_index=0, platform=[0.25], tier=TIER_SENATOR,
                    seat_id=(TIER_SENATOR, (0, w)), seniority=4, cycles_in_office=2,
                )
            for c in range(10):
                tracker.roster[(TIER_HOUSE, (0, c))] = Candidate(
                    name=f"House {c}", party_index=0, platform=[0.25], tier=TIER_HOUSE,
                    seat_id=(TIER_HOUSE, (0, c)), seniority=4, cycles_in_office=2,
                )
            sl0 = (TIER_STATE_LEG, (0, 0, 0))
            tracker.roster[sl0] = Candidate(
                name="Sitting Leg",
                party_index=0,
                platform=[0.25],
                tier=TIER_STATE_LEG,
                seat_id=sl0,
                seniority=2,
                cycles_in_office=1,
            )
            a2, p2_assign = tracker.resolve_cycle_assignments(2, nation, player)
            self.assertEqual(p2_assign.seat_key, race_dist0.seat_key)
            self.assertTrue(p2_assign.is_reelection)
            races2 = tracker.build_live_races(
                TIER_CITY_COUNCIL, 2, nation, player, a2, nm, rng=rng
            )
            race2_dist0 = next(r for r in races2 if r.seat_key == race_dist0.seat_key)
            race2_dist1 = next(r for r in races2 if r.seat_key == race_dist1.seat_key)

            self.assertEqual(race2_dist0.incumbent_party, 0)
            self.assertEqual(race2_dist0.incumbent_cycles, 1)
            self.assertEqual(race2_dist1.incumbent_party, 1)
            self.assertEqual(race2_dist1.incumbent_cycles, 1)

            # Win again in Cycle 2 -> consecutive cycles increments to 2
            tracker.apply_cycle_outcomes(2, nation, player, a2, outcomes1, nm, rng=rng)
            self.assertEqual(tracker.roster[race_dist0.seat_key].cycles_in_office, 2)
            self.assertEqual(tracker.seat_streaks[race_dist1.seat_key], (1, 2))


if __name__ == "__main__":
    unittest.main()
