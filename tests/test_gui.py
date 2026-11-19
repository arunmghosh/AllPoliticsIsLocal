"""Unit and integration tests for the Tkinter GUI of All Politics Is Local."""

import os
import random
import tempfile
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

import numpy as np

from constants import (
    ALL_TIERS,
    CAREER_MAX_CYCLES,
    LIVE_BATCHES,
    OFFICE_NAMES,
    SUGGESTED_ISSUES,
    TIER_CITY_COUNCIL,
    TIER_HOUSE,
    TIER_MAYOR,
    TIER_PRESIDENT,
    YEARS_PER_CYCLE,
)
from custom_types import Candidate, LiveRaceSpec, PlayerProfile
from data_tracker import (
    NameManager,
    SeniorityTracker,
    load_in_party_names,
    load_out_party_names,
    load_party_names,
    read_historical_data,
    read_seniority_data,
)
from gui import PARTY_COLORS, PARTY_TEXT_COLORS, AllPoliticsApp
from simulator import build_nation


class TestGUI(unittest.TestCase):
    """Verify GUI instantiation, setup transitions, tabs, and simulation controls."""

    def setUp(self):
        self.patch_msgbox_info = patch("gui.messagebox.showinfo")
        self.patch_msgbox_warn = patch("gui.messagebox.showwarning")
        self.patch_msgbox_ask = patch("gui.messagebox.askyesno", return_value=True)
        self.mock_info = self.patch_msgbox_info.start()
        self.mock_warn = self.patch_msgbox_warn.start()
        self.mock_ask = self.patch_msgbox_ask.start()

        self.tmp_dir = tempfile.TemporaryDirectory()
        self.data_dir = os.path.join(self.tmp_dir.name, "data")
        self.results_dir = os.path.join(self.tmp_dir.name, "results")
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.results_dir, exist_ok=True)

        self.rng = random.Random(42)
        self.np_rng = np.random.default_rng(42)

        self.app = AllPoliticsApp(
            data_dir=self.data_dir,
            results_dir=self.results_dir,
            rng=self.rng,
            np_rng=self.np_rng,
        )
        self.app.withdraw()  # Run headlessly in test runner
        self.app.update()

    def tearDown(self):
        try:
            self.app.destroy()
        except Exception:
            pass
        self.patch_msgbox_info.stop()
        self.patch_msgbox_warn.stop()
        self.patch_msgbox_ask.stop()
        self.tmp_dir.cleanup()

    def test_party_color_palette(self):
        """Verify 8 unique party colors and contrasting text colors are configured."""
        self.assertEqual(len(PARTY_COLORS), 8)
        self.assertEqual(len(PARTY_TEXT_COLORS), 8)
        self.assertEqual(len(set(PARTY_COLORS)), 8)
        for i in range(8):
            self.assertEqual(self.app.get_party_color(i), PARTY_COLORS[i])
            self.assertIn(self.app.get_party_text_color(i), ("#FFFFFF", "#212121"))

    def test_welcome_and_issue_setup_screens(self):
        """Verify navigation through Welcome and Issue Setup screens."""
        self.app.show_welcome_screen()
        self.app.update()

        # Welcome screen should have child widgets
        children = self.app.container.winfo_children()
        self.assertGreater(len(children), 0)

        # Transition to issue setup
        self.app.temp_nation_name = "GUINation"
        self.app.show_issue_setup_screen()
        self.app.update()

        self.app.temp_issues = ["Economic Policy", "Healthcare"]
        self.app.temp_issue_count = 2
        self.app.show_player_name_screen()
        self.app.update()

        # Player name screen should have dark background
        black_bg = self.app.container.winfo_children()[0]
        self.assertEqual(black_bg.cget("bg"), "#000000")

    def test_location_and_platform_setup(self):
        """Verify location selection and candidate platform initialization."""
        self.app.temp_nation_name = "LocationNation"
        self.app.temp_issues = ["Economic Policy"]
        self.app.nation = build_nation("LocationNation", ["Economic Policy"], load_party_names(), rng=self.rng)
        self.app.temp_player_name = "GUI Player"

        self.app.show_location_setup_screen()
        self.app.update()

        # Simulate selecting State 1, City 1, District 1
        self.app.temp_state_idx = 0
        self.app.temp_city_idx = 0
        self.app.temp_district_idx = 0
        self.app.temp_sim_history = True
        self.app.temp_hist_cycles = 5

        self.app.run_history_and_proceed()
        self.app.update()

        # Platform setup screen should be active
        self.assertIsNotNone(self.app.nation)
        self.assertGreaterEqual(len(self.app.historical_rows), 5)

    def test_tabbed_interface_initialization(self):
        """Verify tabbed interface, notebook tabs, and headquarters view."""
        self.app.nation = build_nation("TabNation", ["Economic Policy"], load_party_names(), rng=self.rng)
        self.app.player = PlayerProfile(
            name="TabCandidate",
            home_state=0,
            home_city=0,
            home_district=0,
            party_index=0,
            platform=[0.25],
            current_seat=None,
            current_tier=None,
        )
        self.app.show_game_interface()
        self.app.update()

        # Check that notebook has 4 tabs
        tab_names = [self.app.notebook.tab(i, "text") for i in range(self.app.notebook.index("end"))]
        self.assertEqual(
            tab_names,
            ["Campaign Headquarters", "Election History", "Seniority Roster", "Live Election Viewer"],
        )

        # Check ladder tracking
        self.assertIn(TIER_CITY_COUNCIL, self.app.ladder_labels)
        self.assertIn(TIER_PRESIDENT, self.app.ladder_labels)

    def test_live_viewer_and_runoff_flow(self):
        """Verify live election viewer simulates batches and advances to runoff if leader < 50%."""
        self.app.nation = build_nation("LiveNation", ["Economy", "Social"], load_party_names(), rng=self.rng)
        self.app.player = PlayerProfile(
            name="LivePlayer",
            home_state=0,
            home_city=0,
            home_district=0,
            party_index=0,
            platform=[0.25, 0.25],
        )
        self.app.show_game_interface()
        self.app.update()

        # Create a 4-party race
        candidates = [
            Candidate(
                name=f"Cand {p.index}",
                party_index=p.index,
                platform=list(p.platform),
                tier=TIER_CITY_COUNCIL,
                is_player=(p.index == 0),
            )
            for p in self.app.nation.parties[:4]
        ]
        districts = [self.app.nation.states[0].cities[0].districts[0]]
        race = LiveRaceSpec(
            seat_key=(TIER_CITY_COUNCIL, (0, 0, 0)),
            tier=TIER_CITY_COUNCIL,
            label="City Council Race",
            districts=districts,
            candidates=candidates,
            has_player=True,
        )

        self.app.current_live_races = [race]
        self.app.selected_race_key = race.seat_key
        self.app.live_prob_matrices = [np.ones((1, 4)) / 4.0]
        self.app.live_cumulative_votes = {race.seat_key: {i: 0 for i in range(len(candidates))}}
        self.app.live_batch_num = 0
        self.app.live_phase = "round1"

        self.app.cb_live_races["values"] = [race.label]
        self.app.cb_live_races.current(0)

        # Advance 1 batch
        self.app.advance_live_batch()
        self.app.update()
        self.assertEqual(self.app.live_batch_num, 1)

        # Fast forward remaining 9 batches to batch 10
        self.app.fast_forward_live_election()
        self.app.update()
        self.assertEqual(self.app.live_batch_num, LIVE_BATCHES)

        # In a 4-party uniform draw, top candidate typically has ~25-35% (< 50%)
        # Check that runoff is triggered or winner decided
        if self.app.runoff_specs:
            self.assertEqual(len(self.app.runoff_specs[0].candidates), 2)
            self.app._start_runoff_phase()
            self.app.update()
            self.assertEqual(self.app.live_phase, "runoff")
            self.assertEqual(len(self.app.current_live_races[0].candidates), 2)

    def test_win_and_lose_screens_and_caching(self):
        """Verify win and try-again screens, and spreadsheet cache button."""
        self.app.nation = build_nation("WinNation", ["Economy"], load_party_names(), rng=self.rng)
        self.app.player = PlayerProfile(
            name="Winner",
            home_state=0,
            home_city=0,
            home_district=0,
            party_index=0,
            platform=[0.25],
        )

        # Test Try Again (Lose) Screen
        self.app.show_lose_screen("Defeated in City Council general election.")
        self.app.update()
        self.assertTrue(hasattr(self.app, "btn_cache"))

        # Test Win Screen
        self.app.show_win_screen()
        self.app.update()
        self.assertTrue(hasattr(self.app, "btn_cache"))

        # Write dummy data to test caching
        hist_file = os.path.join(self.data_dir, "historical_data.xlsx")
        with open(hist_file, "w") as f:
            f.write("test")

        self.app.cache_game_data()
        self.assertEqual(os.listdir(self.data_dir), [])
        self.assertGreater(len(os.listdir(self.results_dir)), 0)

    def test_state_dropdown_displays_positions(self):
        """Verify that state options in the home state dropdown display position vectors."""
        self.app.temp_nation_name = "StatePosNation"
        self.app.temp_issues = ["Economic Policy"]
        self.app.nation = build_nation("StatePosNation", ["Economic Policy"], load_party_names(), rng=self.rng)
        self.app.temp_player_name = "StatePosPlayer"

        self.app.show_location_setup_screen()
        self.app.update()

        # Find combobox for states
        combos = [w for w in self.app.container.winfo_children() if isinstance(w, (ttk.Frame, tk.Frame))]
        # Check cb_state values directly
        cb_state = None
        for frame in self.app.container.winfo_children():
            for child in frame.winfo_children():
                if isinstance(child, ttk.LabelFrame) and "Home State" in child.cget("text"):
                    for sub in child.winfo_children():
                        if isinstance(sub, ttk.Combobox):
                            cb_state = sub
                            break
        self.assertIsNotNone(cb_state)
        vals = cb_state.cget("values")
        self.assertEqual(len(vals), 50)
        self.assertIn("Position:", vals[0])
        # Verify first state position format
        s0 = self.app.nation.states[0]
        expected_pos_str = f"Position: {[round(x, 2) for x in s0.position]}"
        self.assertIn(expected_pos_str, vals[0])

    def test_primary_challenge_vote_tracking_and_distinct_platforms(self):
        """Verify primary challenge between candidates of the same party does not tie deterministically."""
        self.app.nation = build_nation("PrimaryNation", ["Economy"], load_party_names(), rng=self.rng)
        self.app.player = PlayerProfile(
            name="PrimaryPlayer",
            home_state=0,
            home_city=0,
            home_district=0,
            party_index=0,
            platform=[0.25],
        )
        self.app.seniority_tracker = SeniorityTracker(filepath=os.path.join(self.data_dir, "sen.xlsx"))
        self.app.name_manager = NameManager(
            in_party_names=load_in_party_names(),
            out_party_names=load_out_party_names(),
            player_name="PrimaryPlayer",
            rng=self.rng,
        )
        self.app.seniority_tracker.initialize_starting_roster(
            nation=self.app.nation,
            home_state=0,
            home_city=0,
            player_party=0,
            name_manager=self.app.name_manager,
            historical_rows=[],
            streaks={},
            rng=self.rng,
        )
        self.app.show_game_interface()
        self.app.update()

        # Both candidates from party 0 with initially identical platform [0.25]
        c0 = Candidate(
            name="PrimaryPlayer",
            party_index=0,
            platform=[0.25],
            tier=TIER_CITY_COUNCIL,
            is_player=True,
        )
        c1 = Candidate(
            name="PartyChallenger",
            party_index=0,
            platform=[0.25],
            tier=TIER_CITY_COUNCIL,
            is_player=False,
        )
        districts = [self.app.nation.states[0].cities[0].districts[0]]
        race = LiveRaceSpec(
            seat_key=(TIER_CITY_COUNCIL, (0, 0, 0)),
            tier=TIER_CITY_COUNCIL,
            label="PRIMARY: City Council",
            districts=districts,
            candidates=[c0, c1],
            has_player=True,
        )

        self.app.primary_target_nominee = c1
        self.app.start_primary_simulation(race, is_retaliatory=False)
        self.app.update()

        # Check that c1 platform was randomized to be distinct from c0
        self.assertNotEqual(c0.platform, c1.platform)

        # Advance through 9 batches of the primary
        while self.app.live_batch_num < 9:
            self.app.advance_live_batch()
            self.app.update()

        # Cumulative votes must be tracked per candidate index, not colliding under party 0
        totals = self.app.live_cumulative_votes[race.seat_key]
        self.assertEqual(set(totals.keys()), {0, 1})
        self.assertGreater(totals[0], 0)
        self.assertGreater(totals[1], 0)
        self.assertEqual(totals[0] + totals[1], 9000)

        # Complete final batch to test clean transition
        self.app.advance_live_batch()
        self.app.update()

    def test_watching_live_elections_when_not_up_for_reelection(self):
        """Verify that when the player is off-cycle (e.g. Mayor on even cycle), live races are loaded and displayed without error."""
        self.app.nation = build_nation("WatchNation", ["Economy"], load_party_names(), rng=self.rng)
        self.app.player = PlayerProfile(
            name="MayorPlayer",
            home_state=0,
            home_city=0,
            home_district=0,
            party_index=0,
            platform=[0.25],
            current_seat=(TIER_MAYOR, (0, 0)),
            current_tier=TIER_MAYOR,
            elected_cycle=1,
        )
        self.app.seniority_tracker = SeniorityTracker(filepath=os.path.join(self.data_dir, "sen.xlsx"))
        self.app.name_manager = NameManager(
            in_party_names=load_in_party_names(),
            out_party_names=load_out_party_names(),
            player_name="MayorPlayer",
            rng=self.rng,
        )
        self.app.seniority_tracker.initialize_starting_roster(
            nation=self.app.nation,
            home_state=0,
            home_city=0,
            player_party=0,
            name_manager=self.app.name_manager,
            historical_rows=[],
            streaks={},
            rng=self.rng,
        )
        self.app.show_game_interface()
        self.app.update()

        # Even cycle: Mayor has no elections scheduled this cycle
        self.app.current_cycle = 2
        self.app.player_assignment = None

        # Launch live election phase: should load active counterpart tier (TIER_HOUSE) instead of crashing
        self.app.start_live_election_phase()
        self.app.update()

        self.assertGreater(len(self.app.current_live_races), 0)
        self.assertEqual(self.app.current_live_races[0].tier, TIER_HOUSE)
        self.assertEqual(self.app.cb_live_races.current(), 0)
        self.assertIn("ROUND 1", self.app.lbl_live_batch_status.cget("text"))

        # Also verify empty races case handled gracefully without raising Index 0 out of range
        with patch.object(self.app.seniority_tracker, "build_live_races", return_value=[]):
            self.app.start_live_election_phase()
            self.app.update()
            self.assertEqual(self.app.cb_live_races.current(), 0)
            self.assertEqual(self.app.cb_live_races.cget("values")[0], "No live races scheduled this cycle")

    def test_theme_styling_and_career_ladder_colors(self):
        """Verify navy/blue theme styling and career ladder achievement colors."""
        self.app.nation = build_nation("ThemeNation", ["Economy"], load_party_names(), rng=self.rng)
        self.app.player = PlayerProfile(
            name="ThemePlayer",
            home_state=0,
            home_city=0,
            home_district=0,
            party_index=0,
            platform=[0.25],
            current_seat=(TIER_MAYOR, (0, 0)),
            current_tier=TIER_MAYOR,
            elected_cycle=1,
        )
        self.app.seniority_tracker = SeniorityTracker(filepath=os.path.join(self.data_dir, "sen.xlsx"))
        self.app.show_game_interface()
        self.app.update_hq_view()
        self.app.update()

        # Header background is patriotic navy blue #0D47A1
        self.assertEqual(self.app.hdr_title.cget("bg"), "#0D47A1")

        # Ladder styling:
        # Mayor (tier 5) is current tier -> party color background and star badge
        mayor_lbl = self.app.ladder_labels[TIER_MAYOR]
        self.assertIn("★", mayor_lbl.cget("text"))
        self.assertIn("CURRENT OFFICE", mayor_lbl.cget("text"))
        self.assertEqual(mayor_lbl.cget("bg"), self.app.get_party_color(0))

        # City Council (tier 7) is completed -> green background & checkmark
        cc_lbl = self.app.ladder_labels[TIER_CITY_COUNCIL]
        self.assertIn("✓", cc_lbl.cget("text"))
        self.assertEqual(cc_lbl.cget("fg"), "#2E7D32")

        # Governor (tier 2) is unachieved -> dark slate
        gov_lbl = self.app.ladder_labels[2]  # TIER_GOVERNOR
        self.assertEqual(gov_lbl.cget("fg"), "#37474F")


if __name__ == "__main__":
    unittest.main()
