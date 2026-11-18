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
    YEARS_PER_CYCLE,
)
from custom_types import Candidate, PlayerProfile
from data_tracker import (
    NameManager,
    SeniorityTracker,
    get_max_cycles_for_tier,
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
                max_years = get_max_cycles_for_tier(r["Level of Office"]) * YEARS_PER_CYCLE
                self.assertLessEqual(r["Seniority"], max_years)

            # Verify President seniority matches consecutive ending rows in historical_data, capped at term limit
            pres_key = (TIER_PRESIDENT, ())
            if nation.president_party == 0:
                expected_streak = 0
                for row in reversed(rows):
                    if row["President"] == 0:
                        expected_streak += 1
                    else:
                        break
                expected_years = min(
                    expected_streak * YEARS_PER_CYCLE,
                    get_max_cycles_for_tier(TIER_PRESIDENT) * YEARS_PER_CYCLE,
                )
                self.assertEqual(tracker.roster[pres_key].seniority, expected_years)

    def test_seniority_capped_at_term_limit_after_50_historical_cycles(self):
        """Verify that starting seniority values never exceed the term limit years."""
        rng = random.Random(777)
        nation = build_nation("TermCapNation", ["Economy"], load_party_names(), rng=rng)
        with tempfile.TemporaryDirectory() as tmp:
            hist_path = os.path.join(tmp, "historical_data.xlsx")
            sen_path = os.path.join(tmp, "seniority.xlsx")
            rows, streaks = run_historical_simulation(
                nation,
                home_state=0,
                home_city=0,
                home_district=0,
                num_cycles=50,
                filepath=hist_path,
                rng=rng,
            )
            nm = NameManager(
                load_in_party_names(), load_out_party_names(), player_name="CapTester", rng=rng
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
            saved_rows = read_seniority_data(sen_path)
            self.assertGreater(len(saved_rows), 0)
            for r in saved_rows:
                tier = r["Level of Office"]
                max_allowed = get_max_cycles_for_tier(tier) * YEARS_PER_CYCLE
                self.assertLessEqual(
                    r["Seniority"],
                    max_allowed,
                    f"Seniority {r['Seniority']} exceeds max {max_allowed} for tier {tier}",
                )

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

    def test_term_limits_enforced_across_all_tiers(self):
        from constants import TERM_LIMITS, TERM_LENGTH_CYCLES
        from data_tracker import get_max_cycles_for_tier

        # Verify term limit definitions per spec
        self.assertEqual(TERM_LIMITS[TIER_PRESIDENT], 1)
        self.assertEqual(TERM_LIMITS[TIER_GOVERNOR], 2)
        self.assertEqual(TERM_LIMITS[TIER_MAYOR], 2)
        self.assertEqual(TERM_LIMITS[TIER_SENATOR], 3)
        self.assertEqual(TERM_LIMITS[TIER_HOUSE], 3)
        self.assertEqual(TERM_LIMITS[TIER_STATE_LEG], 3)
        self.assertEqual(TERM_LIMITS[TIER_CITY_COUNCIL], 3)

        # Verify max cycles per tier before term limit
        self.assertEqual(get_max_cycles_for_tier(TIER_PRESIDENT), 4)
        self.assertEqual(get_max_cycles_for_tier(TIER_GOVERNOR), 6)
        self.assertEqual(get_max_cycles_for_tier(TIER_MAYOR), 4)
        self.assertEqual(get_max_cycles_for_tier(TIER_SENATOR), 9)
        self.assertEqual(get_max_cycles_for_tier(TIER_HOUSE), 6)
        self.assertEqual(get_max_cycles_for_tier(TIER_STATE_LEG), 3)
        self.assertEqual(get_max_cycles_for_tier(TIER_CITY_COUNCIL), 3)

        rng = random.Random(505)
        nation = build_nation("TermLimitNation", ["Economy"], load_party_names(), rng=rng)
        player = PlayerProfile(
            name="TermPlayer",
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

            # Populate City Council candidates in home city:
            # Player is at dist 0 with 3 cycles (term limit reached!)
            cc_player_key = (TIER_CITY_COUNCIL, (0, 0, 0))
            tracker.roster[cc_player_key] = Candidate(
                name="TermPlayer", party_index=0, platform=[0.25],
                tier=TIER_CITY_COUNCIL, seat_id=cc_player_key,
                seniority=6, cycles_in_office=3, is_player=True,
            )
            # Council Max is at dist 1 with 3 cycles (term limit reached!)
            cc_max_key = (TIER_CITY_COUNCIL, (0, 0, 1))
            tracker.roster[cc_max_key] = Candidate(
                name="Council Max", party_index=0, platform=[0.25],
                tier=TIER_CITY_COUNCIL, seat_id=cc_max_key,
                seniority=6, cycles_in_office=3,
            )
            # Council Ok is at dist 2 with 2 cycles (eligible for reelection!)
            cc_ok_key = (TIER_CITY_COUNCIL, (0, 0, 2))
            tracker.roster[cc_ok_key] = Candidate(
                name="Council Ok", party_index=0, platform=[0.25],
                tier=TIER_CITY_COUNCIL, seat_id=cc_ok_key,
                seniority=4, cycles_in_office=2,
            )

            # Incumbents for higher tiers holding elections in Cycle 3
            sen2_key = (TIER_SENATOR, (0, 2))
            tracker.roster[sen2_key] = Candidate(
                name="Sen Sitting", party_index=0, platform=[0.25],
                tier=TIER_SENATOR, seat_id=sen2_key,
                seniority=2, cycles_in_office=1,
            )
            m0_key = (TIER_MAYOR, (0, 0))
            tracker.roster[m0_key] = Candidate(
                name="Mayor Sitting", party_index=0, platform=[0.25],
                tier=TIER_MAYOR, seat_id=m0_key,
                seniority=2, cycles_in_office=1,
            )
            sl0_key = (TIER_STATE_LEG, (0, 0, 0))
            tracker.roster[sl0_key] = Candidate(
                name="Leg Sitting", party_index=0, platform=[0.25],
                tier=TIER_STATE_LEG, seat_id=sl0_key,
                seniority=2, cycles_in_office=1,
            )
            sl2_key = (TIER_STATE_LEG, (0, 0, 2))
            tracker.roster[sl2_key] = Candidate(
                name="Leg2 Sitting", party_index=0, platform=[0.25],
                tier=TIER_STATE_LEG, seat_id=sl2_key,
                seniority=2, cycles_in_office=1,
            )

            # Cycle 3: City Council is scheduled, but House (even cycles) is not
            assignments, p_assign = tracker.resolve_cycle_assignments(3, nation, player)

            # TermPlayer and Council Max reached 3-term limit -> cannot seek reelection
            self.assertNotIn(cc_player_key, tracker.roster)
            self.assertNotIn(cc_max_key, tracker.roster)
            self.assertIsNone(p_assign)

            # Council Ok was at 2 terms -> successfully assigned for reelection
            self.assertIn(cc_ok_key, assignments)
            self.assertTrue(assignments[cc_ok_key].is_reelection)
            self.assertEqual(assignments[cc_ok_key].candidate.name, "Council Ok")

    def test_opponent_term_limit_recycling_and_suffix_increment(self):
        rng = random.Random(606)
        nation = build_nation("OppTermNation", ["Economy"], load_party_names(), rng=rng)
        player = PlayerProfile(
            name="OppCheckPlayer",
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
                load_in_party_names(),
                load_out_party_names(),
                player_name=player.name,
                rng=rng,
            )

            assignments, _ = tracker.resolve_cycle_assignments(1, nation, player)
            cc_key = (TIER_CITY_COUNCIL, (0, 0, 1))

            # Initial build: cache opponents for Party 1
            races1 = tracker.build_live_races(
                TIER_CITY_COUNCIL, 1, nation, player, assignments, nm, rng=rng
            )
            race1 = next(r for r in races1 if r.seat_key == cc_key)
            opp1 = next(c for c in race1.candidates if c.party_index == 1)
            initial_name = opp1.name
            initial_plat = list(opp1.platform)

            # Simulate Party 1 winning and serving 3 cycles (reaching 3-term limit for City Council)
            tracker.seat_streaks[cc_key] = (1, 3)

            # Cycle 2 build: City Council term limit (3 cycles) reached for Party 1 incumbent!
            races2 = tracker.build_live_races(
                TIER_CITY_COUNCIL, 2, nation, player, assignments, nm, rng=rng
            )
            race2 = next(r for r in races2 if r.seat_key == cc_key)
            opp2 = next(c for c in race2.candidates if c.party_index == 1)

            # Opponent name must have incremented suffix
            self.assertEqual(opp2.name, f"{initial_name} 2")
            # Grudge cycles for the seat must reset to 0
            self.assertEqual(race2.incumbent_cycles, 0)
            self.assertEqual(tracker.seat_streaks[cc_key], (1, 0))

    def test_get_higher_office_seat_walks_up_to_active_election(self):
        rng = random.Random(701)
        nation = build_nation("WalkNation", ["Economy"], load_party_names(), rng=rng)
        player = PlayerProfile(
            name="MayorWalk",
            home_state=0,
            home_city=0,
            home_district=0,
            party_index=0,
            platform=[0.25],
            current_tier=TIER_MAYOR,
            current_seat=(TIER_MAYOR, (0, 0)),
        )
        from data_tracker import get_higher_office_seat

        # In cycle 2 (even cycle): House has an election -> returns House
        sk_even = get_higher_office_seat(player, 2, nation)
        self.assertEqual(sk_even, (TIER_HOUSE, (0, 0)))

        # In cycle 3 (odd cycle): House has NO election -> walks up to Senate (which has wave 2)
        sk_odd = get_higher_office_seat(player, 3, nation)
        self.assertEqual(sk_odd, (TIER_SENATOR, (0, 2)))

    def test_promotion_purges_old_seat_and_prevents_lower_tier_assignment(self):
        rng = random.Random(702)
        nation = build_nation("PurgeNation", ["Economy"], load_party_names(), rng=rng)
        player = PlayerProfile(
            name="PromotedHero",
            home_state=0,
            home_city=0,
            home_district=0,
            party_index=0,
            platform=[0.25],
            current_tier=TIER_MAYOR,
            current_seat=(TIER_MAYOR, (0, 0)),
        )
        with tempfile.TemporaryDirectory() as tmp:
            sen_path = os.path.join(tmp, "seniority.xlsx")
            tracker = SeniorityTracker(filepath=sen_path)
            nm = NameManager(
                load_in_party_names(),
                load_out_party_names(),
                player_name=player.name,
                rng=rng,
            )

            # Player starts as Mayor in roster
            old_mayor_key = (TIER_MAYOR, (0, 0))
            tracker.roster[old_mayor_key] = Candidate(
                name=player.name,
                party_index=0,
                platform=[0.25],
                tier=TIER_MAYOR,
                seat_id=old_mayor_key,
                seniority=2,
                cycles_in_office=1,
                is_player=True,
            )

            # Player wins Senate election in cycle 2
            sen_key = (TIER_SENATOR, (0, 1))
            sen_cand = Candidate(
                name=player.name,
                party_index=0,
                platform=[0.25],
                tier=TIER_SENATOR,
                seat_id=sen_key,
                seniority=0,
                cycles_in_office=1,
                is_player=True,
            )
            from custom_types import ElectionAssignment

            assign_sen = ElectionAssignment(
                seat_key=sen_key,
                tier=TIER_SENATOR,
                candidate=sen_cand,
                is_promotion=True,
                is_reelection=False,
            )

            # Apply outcomes: player wins Senate!
            tracker.apply_cycle_outcomes(
                cycle=2,
                nation=nation,
                player=player,
                assignments={sen_key: assign_sen},
                outcomes={sen_key: (0, 60.0)},
                name_manager=nm,
                rng=rng,
            )

            # Verify player's old Mayor seat was purged from roster
            self.assertNotIn(old_mayor_key, tracker.roster)
            self.assertIn(sen_key, tracker.roster)
            self.assertEqual(player.current_tier, TIER_SENATOR)
            self.assertEqual(player.current_seat, sen_key)

            # In cycle 3: House vacancy exists, but player is sitting Senator
            # resolve_cycle_assignments must NOT assign player to House or Mayor
            assignments, p_assign = tracker.resolve_cycle_assignments(3, nation, player)
            self.assertIsNone(p_assign)


if __name__ == "__main__":
    unittest.main()
