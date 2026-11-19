"""Tkinter graphical user interface for All Politics Is Local.

Provides an interactive GUI for nation configuration, candidate setup,
tabbed gameplay (Campaign Headquarters, Election History, Seniority, and
Live Election Viewer), primary challenges, live runoff voting with dedicated
party colors, and dedicated win/try-again end screens.
"""

import math
import os
import random
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional

import numpy as np

from constants import (
    ALL_TIERS,
    CAREER_MAX_CYCLES,
    CITIES_PER_STATE,
    DATA_DIR,
    DISTRICTS_PER_CITY,
    HISTORICAL_DATA_FILE,
    HISTORICAL_HEADERS,
    LIVE_BATCHES,
    LIVE_SCOPE_TITLES,
    MAX_HISTORICAL_CYCLES,
    MAX_ISSUES,
    MID_POS,
    MIN_ISSUES,
    NUM_STATES,
    NUM_WAVES,
    OFFICE_NAMES,
    RESULTS_DIR,
    SENATORS_PER_STATE,
    SENIORITY_FILE,
    SENIORITY_HEADERS,
    SUGGESTED_ISSUES,
    TERM_LENGTH_CYCLES,
    TERM_LIMITS,
    TIER_CITY_COUNCIL,
    TIER_GOVERNOR,
    TIER_HOUSE,
    TIER_MAYOR,
    TIER_PRESIDENT,
    TIER_SENATOR,
    TIER_STATE_LEG,
    VOTES_PER_BATCH,
    VOTES_PER_DISTRICT,
    WAVE_LABELS,
    YEARS_PER_CYCLE,
)
from custom_types import (
    Candidate,
    City,
    District,
    ElectionAssignment,
    LiveBatchResult,
    LiveRaceSnapshot,
    LiveRaceSpec,
    Nation,
    Party,
    PlayerProfile,
    PositionVector,
    SeatKey,
    State,
)
from data_tracker import (
    NameManager,
    SeniorityTracker,
    append_historical_row,
    build_historical_row,
    get_active_live_tier_for_player,
    get_candidate_cycles,
    get_higher_office_seat,
    get_max_cycles_for_tier,
    get_seat_party,
    get_seat_population_position,
    is_player_up_for_reelection,
    load_in_party_names,
    load_out_party_names,
    load_party_names,
    player_has_served_complete_term,
    read_historical_data,
    read_seniority_data,
    run_historical_simulation,
    save_results,
    wipe_data,
    write_historical_data,
    write_seniority_data,
)
from simulator import (
    build_nation,
    compute_probabilities,
    compute_vote_percentages,
    euclidean_distance,
    find_party_for_platform,
    format_seat_label,
    get_seat_districts,
    is_election_cycle,
    is_valid_candidate_coordinate,
    precompute_race_probabilities,
    run_default_election,
    sample_candidate_platform,
    sample_distinct_platform,
    simulate_live_batch,
)

# Dedicated party colors across the entire game (up to 8 parties)
PARTY_COLORS = [
    "#1E88E5",  # P0: Blue
    "#E53935",  # P1: Red
    "#43A047",  # P2: Green
    "#FB8C00",  # P3: Orange
    "#8E24AA",  # P4: Purple
    "#00ACC1",  # P5: Cyan
    "#FDD835",  # P6: Gold
    "#D81B60",  # P7: Magenta
]

PARTY_TEXT_COLORS = [
    "#FFFFFF",
    "#FFFFFF",
    "#FFFFFF",
    "#FFFFFF",
    "#FFFFFF",
    "#FFFFFF",
    "#212121",
    "#FFFFFF",
]


class AllPoliticsApp(tk.Tk):
    """Main Tkinter window and controller for the All Politics Is Local simulation."""

    def __init__(
        self,
        data_dir: str = DATA_DIR,
        results_dir: str = RESULTS_DIR,
        rng: Optional[random.Random] = None,
        np_rng: Optional[np.random.Generator] = None,
    ) -> None:
        super().__init__()
        self.title("All Politics Is Local")
        self.geometry("980x740")
        self.minsize(860, 640)

        self.data_dir = data_dir
        self.results_dir = results_dir
        self.rng = rng or random.Random()
        self.np_rng = np_rng or np.random.default_rng()

        # Engine state
        self.party_names = load_party_names()
        self.in_party_names = load_in_party_names()
        self.out_party_names = load_out_party_names()

        self.nation: Optional[Nation] = None
        self.player: Optional[PlayerProfile] = None
        self.seniority_tracker: Optional[SeniorityTracker] = None
        self.name_manager: Optional[NameManager] = None

        self.current_cycle: int = 1
        self.start_cycle: int = 1
        self.historical_rows: list[dict] = []
        self.assignments: dict[SeatKey, ElectionAssignment] = {}
        self.player_assignment: Optional[ElectionAssignment] = None

        # Setup temporary state
        self.temp_nation_name: str = "Republic of Antigravity"
        self.temp_issue_count: int = 1
        self.temp_issues: list[str] = [SUGGESTED_ISSUES[0]]
        self.temp_player_name: str = "Candidate"
        self.temp_state_idx: int = 0
        self.temp_city_idx: int = 0
        self.temp_district_idx: int = 0
        self.temp_sim_history: bool = True
        self.temp_hist_cycles: int = 50

        # Live election viewer state
        self.current_live_races: list[LiveRaceSpec] = []
        self.live_prob_matrices: list[np.ndarray] = []
        self.live_cumulative_votes: dict[SeatKey, dict[int, int]] = {}
        self.live_batch_num: int = 0
        self.live_phase: str = "idle"  # idle, round1, runoff, primary
        self.selected_race_key: Optional[SeatKey] = None
        self.decided_live_outcomes: dict[SeatKey, tuple[int, float]] = {}
        self.runoff_specs: list[LiveRaceSpec] = []
        self.runoff_candidates: dict[SeatKey, list[Candidate]] = {}
        self.round1_snapshots: dict[SeatKey, LiveRaceSnapshot] = {}

        # Primary challenge state
        self.active_primary_race: Optional[LiveRaceSpec] = None
        self.primary_target_nominee: Optional[Candidate] = None
        self.primary_higher_sk: Optional[SeatKey] = None
        self.primary_has_stakes: bool = False
        self.primary_is_retaliatory: bool = False
        self.player_in_general_no_stakes: bool = False

        # Status logs
        self.game_log: list[str] = []

        # Container for swappable screens
        self.container = ttk.Frame(self)
        self.container.pack(fill=tk.BOTH, expand=True)

        self._configure_styles()
        self.show_welcome_screen()

    def _configure_styles(self) -> None:
        """Configure TTK widget styling with patriotic blue/red palette."""
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        # Typography & Labels
        style.configure("Header.TLabel", font=("Helvetica", 18, "bold"), foreground="#0D47A1")
        style.configure("Subheader.TLabel", font=("Helvetica", 13, "bold"), foreground="#1565C0")
        style.configure("Title.TLabel", font=("Helvetica", 24, "bold"), foreground="#0D47A1")
        style.configure("Bold.TLabel", font=("Helvetica", 11, "bold"), foreground="#1565C0")
        style.configure("Danger.TLabel", font=("Helvetica", 13, "bold"), foreground="#C62828")
        style.configure("Success.TLabel", font=("Helvetica", 13, "bold"), foreground="#2E7D32")

        # Cards & Containers
        style.configure("Card.TFrame", relief=tk.GROOVE, borderwidth=1)
        style.configure("TLabelframe.Label", font=("Helvetica", 11, "bold"), foreground="#0D47A1")

        # Action Buttons (Blue primary, Red danger)
        style.configure(
            "Action.TButton",
            font=("Helvetica", 11, "bold"),
            background="#1565C0",
            foreground="#FFFFFF",
        )
        style.map(
            "Action.TButton",
            background=[("active", "#0D47A1"), ("pressed", "#0D47A1")],
            foreground=[("active", "#FFFFFF"), ("pressed", "#FFFFFF")],
        )

        style.configure(
            "Danger.TButton",
            font=("Helvetica", 11, "bold"),
            background="#C62828",
            foreground="#FFFFFF",
        )
        style.map(
            "Danger.TButton",
            background=[("active", "#B71C1C"), ("pressed", "#B71C1C")],
            foreground=[("active", "#FFFFFF"), ("pressed", "#FFFFFF")],
        )

        # Treeview Headings in deep navy blue
        style.configure(
            "Treeview.Heading",
            font=("Helvetica", 10, "bold"),
            background="#0D47A1",
            foreground="#FFFFFF",
        )
        style.map(
            "Treeview.Heading",
            background=[("active", "#1565C0")],
            foreground=[("active", "#FFFFFF")],
        )

    def _clear_container(self) -> None:
        """Remove all child widgets from container."""
        for widget in self.container.winfo_children():
            widget.destroy()

    def get_party_color(self, party_index: int) -> str:
        """Return dedicated hex color for party_index."""
        return PARTY_COLORS[party_index % len(PARTY_COLORS)]

    def get_party_text_color(self, party_index: int) -> str:
        """Return contrast foreground text color for party_index."""
        return PARTY_TEXT_COLORS[party_index % len(PARTY_TEXT_COLORS)]

    # =========================================================================
    # 1. SETUP FLOW
    # =========================================================================

    def show_welcome_screen(self) -> None:
        """Screen 1: Welcome screen and nation name entry."""
        self._clear_container()

        frame = ttk.Frame(self.container, padding=30)
        frame.pack(fill=tk.BOTH, expand=True)

        title = ttk.Label(
            frame,
            text="ALL POLITICS IS LOCAL",
            style="Title.TLabel",
            anchor="center",
        )
        title.pack(pady=(40, 10))

        sub = ttk.Label(
            frame,
            text=(
                "A dynamic political career simulation.\n"
                "Advance through seven tiers of office, build seniority, survive elections,\n"
                "and win the Presidency within 50 years (25 cycles)."
            ),
            font=("Helvetica", 12),
            justify="center",
            anchor="center",
        )
        sub.pack(pady=(0, 40))

        card = ttk.LabelFrame(frame, text=" Nation Configuration ", padding=20)
        card.pack(pady=10, fill=tk.X, padx=80)

        lbl = ttk.Label(card, text="Enter the name of your nation:", font=("Helvetica", 11))
        lbl.pack(anchor=tk.W, pady=(0, 6))

        name_var = tk.StringVar(value=self.temp_nation_name)
        entry = ttk.Entry(card, textvariable=name_var, font=("Helvetica", 12))
        entry.pack(fill=tk.X, pady=(0, 15))
        entry.focus_set()

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=30)

        def on_next() -> None:
            val = name_var.get().strip()
            if not val:
                messagebox.showwarning("Input Required", "Please enter a name for your nation.")
                return
            self.temp_nation_name = val
            self.show_issue_setup_screen()

        nxt_btn = ttk.Button(btn_frame, text="Continue to Issue Setup ->", command=on_next)
        nxt_btn.pack(ipadx=10, ipady=5)

    def show_issue_setup_screen(self) -> None:
        """Screen 2: Select number and names of political issues (1-3)."""
        self._clear_container()

        frame = ttk.Frame(self.container, padding=30)
        frame.pack(fill=tk.BOTH, expand=True)

        title = ttk.Label(frame, text="Political Issues Setup", style="Header.TLabel")
        title.pack(pady=(10, 15), anchor=tk.W)

        desc = ttk.Label(
            frame,
            text=(
                "Select how many political issues define the ideological landscape (1 to 3).\n"
                "1 issue creates 2 parties, 2 issues create 4 parties, 3 issues create 8 parties."
            ),
            font=("Helvetica", 11),
        )
        desc.pack(pady=(0, 15), anchor=tk.W)

        count_frame = ttk.Frame(frame)
        count_frame.pack(fill=tk.X, pady=5)

        ttk.Label(count_frame, text="Number of Issues:", font=("Helvetica", 11, "bold")).pack(
            side=tk.LEFT, padx=(0, 10)
        )
        count_var = tk.IntVar(value=len(self.temp_issues) or 1)

        issues_container = ttk.Frame(frame)
        issues_container.pack(fill=tk.BOTH, expand=True, pady=15)

        issue_vars: list[tk.StringVar] = []

        def refresh_issue_selectors() -> None:
            for w in issues_container.winfo_children():
                w.destroy()
            issue_vars.clear()

            n = count_var.get()
            for i in range(n):
                i_frame = ttk.LabelFrame(issues_container, text=f" Issue {i + 1} ", padding=10)
                i_frame.pack(fill=tk.X, pady=6)

                default_name = (
                    self.temp_issues[i]
                    if i < len(self.temp_issues)
                    else (SUGGESTED_ISSUES[i] if i < len(SUGGESTED_ISSUES) else f"Custom Issue {i + 1}")
                )
                var = tk.StringVar(value=default_name)
                issue_vars.append(var)

                cb = ttk.Combobox(
                    i_frame,
                    textvariable=var,
                    values=SUGGESTED_ISSUES,
                    font=("Helvetica", 11),
                )
                cb.pack(fill=tk.X, side=tk.LEFT, expand=True, padx=(0, 10))
                ttk.Label(
                    i_frame,
                    text="(Select from list or type custom name)",
                    font=("Helvetica", 9, "italic"),
                ).pack(side=tk.RIGHT)

        for c in (1, 2, 3):
            rb = ttk.Radiobutton(
                count_frame,
                text=f"{c} Issue{'s' if c > 1 else ''} ({2**c} Parties)",
                variable=count_var,
                value=c,
                command=refresh_issue_selectors,
            )
            rb.pack(side=tk.LEFT, padx=10)

        refresh_issue_selectors()

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=20)

        def on_back() -> None:
            self.show_welcome_screen()

        def on_next() -> None:
            chosen = [v.get().strip() for v in issue_vars]
            if any(not c for c in chosen):
                messagebox.showwarning("Input Required", "Please provide a name for all issues.")
                return
            if len(set(chosen)) < len(chosen):
                messagebox.showwarning("Duplicate Issues", "Each issue must have a unique name.")
                return
            self.temp_issue_count = count_var.get()
            self.temp_issues = chosen
            self.show_player_name_screen()

        ttk.Button(btn_frame, text="<- Back", command=on_back).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Continue to Candidate Name ->", command=on_next).pack(
            side=tk.RIGHT
        )

    def show_player_name_screen(self) -> None:
        """Screen 3: Black screen with a dialog box to enter candidate name."""
        self._clear_container()

        # Pure dark black background per specification
        black_bg = tk.Frame(self.container, bg="#000000")
        black_bg.pack(fill=tk.BOTH, expand=True)

        # Centered dialog box / card with navy border
        card = tk.Frame(black_bg, bg="#131C2E", bd=2, relief=tk.RIDGE, padx=32, pady=30)
        card.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

        lbl_title = tk.Label(
            card,
            text="Candidate Registration",
            font=("Helvetica", 16, "bold"),
            bg="#131C2E",
            fg="#90CAF9",
        )
        lbl_title.pack(pady=(0, 15))

        lbl_prompt = tk.Label(
            card,
            text="Enter your candidate name:",
            font=("Helvetica", 12),
            bg="#131C2E",
            fg="#ECEFF1",
        )
        lbl_prompt.pack(anchor=tk.W, pady=(0, 8))

        name_var = tk.StringVar(value=self.temp_player_name)
        entry = tk.Entry(
            card,
            textvariable=name_var,
            font=("Helvetica", 13),
            bg="#1E293B",
            fg="#FFFFFF",
            insertbackground="#FFFFFF",
            width=32,
            highlightthickness=1,
            highlightbackground="#1976D2",
            highlightcolor="#42A5F5",
        )
        entry.pack(fill=tk.X, pady=(0, 20))
        entry.focus_set()

        btn_row = tk.Frame(card, bg="#131C2E")
        btn_row.pack(fill=tk.X)

        def on_continue() -> None:
            c_name = name_var.get().strip()
            if not c_name:
                messagebox.showwarning("Input Required", "Candidate name cannot be empty.")
                return
            self.temp_player_name = c_name
            # Initialize the nation hierarchy
            self.nation = build_nation(
                name=self.temp_nation_name,
                issues=self.temp_issues,
                party_names=self.party_names,
                rng=self.rng,
            )
            self.show_location_setup_screen()

        btn = tk.Button(
            btn_row,
            text="Enter the Arena ->",
            font=("Helvetica", 11, "bold"),
            bg="#1976D2",
            fg="#FFFFFF",
            activebackground="#0D47A1",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            padx=14,
            pady=7,
            command=on_continue,
        )
        btn.pack(side=tk.RIGHT)

    def show_location_setup_screen(self) -> None:
        """Screen 4: Consecutive dropdown menus for State, City, District with position readouts."""
        self._clear_container()
        assert self.nation is not None

        frame = ttk.Frame(self.container, padding=25)
        frame.pack(fill=tk.BOTH, expand=True)

        title = ttk.Label(frame, text="Select Home State, City & District", style="Header.TLabel")
        title.pack(anchor=tk.W, pady=(0, 8))

        desc = ttk.Label(
            frame,
            text=(
                f"Candidate: {self.temp_player_name} | Nation: {self.nation.name}\n"
                "Browse through dropdown menus to select where your career begins.\n"
                "Your first campaign will be for City Council in your chosen district."
            ),
            font=("Helvetica", 11),
        )
        desc.pack(anchor=tk.W, pady=(0, 15))

        # State selector
        state_frame = ttk.LabelFrame(frame, text=" 1. Home State (1-50) ", padding=12)
        state_frame.pack(fill=tk.X, pady=6)

        state_options = [
            f"State {s.index + 1} (Wave {WAVE_LABELS[s.wave]}) - Position: {[round(x, 2) for x in s.position]}"
            for s in self.nation.states
        ]
        state_var = tk.StringVar(value=state_options[self.temp_state_idx])
        cb_state = ttk.Combobox(
            state_frame,
            textvariable=state_var,
            values=state_options,
            state="readonly",
            font=("Helvetica", 11),
        )
        cb_state.pack(fill=tk.X, side=tk.LEFT, expand=True, padx=(0, 15))

        lbl_state_pos = ttk.Label(state_frame, text="", font=("Helvetica", 10, "bold"))
        lbl_state_pos.pack(side=tk.RIGHT)

        # City selector
        city_frame = ttk.LabelFrame(frame, text=" 2. Home City (1-10) ", padding=12)
        city_frame.pack(fill=tk.X, pady=6)

        city_var = tk.StringVar()
        cb_city = ttk.Combobox(
            city_frame,
            textvariable=city_var,
            state="readonly",
            font=("Helvetica", 11),
        )
        cb_city.pack(fill=tk.X, side=tk.LEFT, expand=True, padx=(0, 15))

        lbl_city_pos = ttk.Label(city_frame, text="", font=("Helvetica", 10, "bold"))
        lbl_city_pos.pack(side=tk.RIGHT)

        # District selector
        dist_frame = ttk.LabelFrame(frame, text=" 3. Home District (1-40) ", padding=12)
        dist_frame.pack(fill=tk.X, pady=6)

        dist_var = tk.StringVar()
        cb_dist = ttk.Combobox(
            dist_frame,
            textvariable=dist_var,
            state="readonly",
            font=("Helvetica", 11),
        )
        cb_dist.pack(fill=tk.X, side=tk.LEFT, expand=True, padx=(0, 15))

        lbl_dist_pos = ttk.Label(dist_frame, text="", font=("Helvetica", 10, "bold"))
        lbl_dist_pos.pack(side=tk.RIGHT)

        def update_district_options() -> None:
            assert self.nation is not None
            s_idx = cb_state.current()
            c_idx = cb_city.current()
            if s_idx < 0:
                s_idx = 0
            if c_idx < 0:
                c_idx = 0
            city_obj = self.nation.states[s_idx].cities[c_idx]
            dist_opts = [
                f"District {d.index + 1} - Position: {[round(x, 2) for x in d.position]}"
                for d in city_obj.districts
            ]
            cb_dist["values"] = dist_opts
            cb_dist.current(min(self.temp_district_idx, len(dist_opts) - 1))
            d_idx = cb_dist.current()
            d_pos = city_obj.districts[d_idx].position
            lbl_dist_pos.config(text=f"District Position: {[round(x, 2) for x in d_pos]}")

        def update_city_options(*args) -> None:
            assert self.nation is not None
            s_idx = cb_state.current()
            if s_idx < 0:
                s_idx = 0
            state_obj = self.nation.states[s_idx]
            lbl_state_pos.config(
                text=f"State Position: {[round(x, 2) for x in state_obj.position]} | Wave {WAVE_LABELS[state_obj.wave]}"
            )
            city_opts = [
                f"City {c.index + 1} - Position: {[round(x, 2) for x in c.position]}"
                for c in state_obj.cities
            ]
            cb_city["values"] = city_opts
            cb_city.current(min(self.temp_city_idx, len(city_opts) - 1))
            c_idx = cb_city.current()
            c_pos = state_obj.cities[c_idx].position
            lbl_city_pos.config(text=f"City Position: {[round(x, 2) for x in c_pos]}")
            update_district_options()

        def on_city_change(*args) -> None:
            assert self.nation is not None
            s_idx = cb_state.current()
            c_idx = cb_city.current()
            if s_idx >= 0 and c_idx >= 0:
                c_pos = self.nation.states[s_idx].cities[c_idx].position
                lbl_city_pos.config(text=f"City Position: {[round(x, 2) for x in c_pos]}")
            update_district_options()

        def on_dist_change(*args) -> None:
            assert self.nation is not None
            s_idx = cb_state.current()
            c_idx = cb_city.current()
            d_idx = cb_dist.current()
            if s_idx >= 0 and c_idx >= 0 and d_idx >= 0:
                d_pos = self.nation.states[s_idx].cities[c_idx].districts[d_idx].position
                lbl_dist_pos.config(text=f"District Position: {[round(x, 2) for x in d_pos]}")

        cb_state.bind("<<ComboboxSelected>>", update_city_options)
        cb_city.bind("<<ComboboxSelected>>", on_city_change)
        cb_dist.bind("<<ComboboxSelected>>", on_dist_change)

        update_city_options()

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=25)

        def on_next() -> None:
            self.temp_state_idx = max(0, cb_state.current())
            self.temp_city_idx = max(0, cb_city.current())
            self.temp_district_idx = max(0, cb_dist.current())
            self.show_history_prompt_dialog()

        ttk.Button(btn_frame, text="Continue to History Simulation ->", command=on_next).pack(
            side=tk.RIGHT
        )

    def show_history_prompt_dialog(self) -> None:
        """Screen 5: Modal dialog asking if user wants to simulate prior election history."""
        win = tk.Toplevel(self)
        win.title("Simulate Prior History")
        win.geometry("480x280")
        win.transient(self)
        win.grab_set()

        frm = ttk.Frame(win, padding=20)
        frm.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            frm,
            text="Simulate Prior Election History?",
            font=("Helvetica", 13, "bold"),
        ).pack(pady=(0, 10))

        ttk.Label(
            frm,
            text=(
                "Would you like to simulate prior election history (up to 50 cycles)?\n\n"
                "This populates 'historical_data.xlsx' and 'seniority.xlsx' with realistic "
                "historical incumbents, giving you voting patterns and seniority rosters."
            ),
            wraplength=420,
            justify=tk.LEFT,
            font=("Helvetica", 10),
        ).pack(pady=(0, 15))

        cycle_frame = ttk.Frame(frm)
        cycle_frame.pack(fill=tk.X, pady=(0, 15))

        ttk.Label(cycle_frame, text="Cycles to simulate (1 - 50):", font=("Helvetica", 10)).pack(
            side=tk.LEFT, padx=(0, 10)
        )
        cycles_var = tk.IntVar(value=50)
        sp_cycles = ttk.Spinbox(cycle_frame, from_=1, to=50, textvariable=cycles_var, width=6)
        sp_cycles.pack(side=tk.LEFT)

        btn_row = ttk.Frame(frm)
        btn_row.pack(fill=tk.X, pady=10)

        def on_skip() -> None:
            self.temp_sim_history = False
            self.temp_hist_cycles = 0
            win.destroy()
            self.show_platform_setup_screen()

        def on_simulate() -> None:
            self.temp_sim_history = True
            c = cycles_var.get()
            self.temp_hist_cycles = max(1, min(c, MAX_HISTORICAL_CYCLES))
            win.destroy()
            self.run_history_and_proceed()

        ttk.Button(btn_row, text="Skip (Start Clean)", command=on_skip).pack(side=tk.LEFT)
        ttk.Button(btn_row, text="Simulate History ->", command=on_simulate).pack(side=tk.RIGHT)

    def run_history_and_proceed(self) -> None:
        """Run historical simulation in background and proceed to platform setup."""
        assert self.nation is not None
        hist_path = os.path.join(self.data_dir, "historical_data.xlsx")
        self.historical_rows, self.historical_streaks = run_historical_simulation(
            nation=self.nation,
            home_state=self.temp_state_idx,
            home_city=self.temp_city_idx,
            home_district=self.temp_district_idx,
            num_cycles=self.temp_hist_cycles,
            filepath=hist_path,
            rng=self.rng,
        )
        self.show_platform_setup_screen()

    def show_platform_setup_screen(self) -> None:
        """Screen 6: Choose player's candidate platform and discover party affiliation."""
        self._clear_container()
        assert self.nation is not None

        frame = ttk.Frame(self.container, padding=25)
        frame.pack(fill=tk.BOTH, expand=True)

        title = ttk.Label(frame, text="Set Your Candidate Platform", style="Header.TLabel")
        title.pack(anchor=tk.W, pady=(0, 6))

        dist_obj = (
            self.nation.states[self.temp_state_idx]
            .cities[self.temp_city_idx]
            .districts[self.temp_district_idx]
        )
        desc = ttk.Label(
            frame,
            text=(
                f"Your Home District: State {self.temp_state_idx + 1}, "
                f"City {self.temp_city_idx + 1}, District {self.temp_district_idx + 1}\n"
                f"District Ideology: {[round(x, 2) for x in dist_obj.position]}\n\n"
                "Select a position for each issue in increments of 0.01 (excluding exactly 0.50).\n"
                "Positions < 0.50 are Conservative; positions > 0.50 are Liberal."
            ),
            font=("Helvetica", 11),
        )
        desc.pack(anchor=tk.W, pady=(0, 15))

        coords_frame = ttk.LabelFrame(frame, text=" Issue Positions (0.01 - 0.99) ", padding=15)
        coords_frame.pack(fill=tk.X, pady=6)

        coord_vars: list[tk.DoubleVar] = []
        party_info_var = tk.StringVar()

        def update_party_preview(*args) -> None:
            assert self.nation is not None
            current_vals: PositionVector = []
            for v in coord_vars:
                val = round(v.get(), 2)
                if val == MID_POS:
                    val = 0.49
                current_vals.append(val)
            try:
                p_idx = find_party_for_platform(current_vals, self.nation.parties)
                p_name = self.nation.parties[p_idx].name
                col = self.get_party_color(p_idx)
                party_info_var.set(f"Party Alignment: {p_name} (Party {p_idx})")
                lbl_party_badge.config(
                    text=f"  {p_name}  ",
                    bg=col,
                    fg=self.get_party_text_color(p_idx),
                )
            except Exception:
                party_info_var.set("Invalid coordinates (must not equal 0.50)")

        for i, issue_name in enumerate(self.nation.issues):
            i_row = ttk.Frame(coords_frame)
            i_row.pack(fill=tk.X, pady=8)

            dist_coord = dist_obj.position[i]
            # Default to district's side
            default_val = 0.25 if dist_coord < MID_POS else 0.75
            var = tk.DoubleVar(value=default_val)
            coord_vars.append(var)

            ttk.Label(i_row, text=f"{issue_name}:", font=("Helvetica", 11, "bold"), width=20).pack(
                side=tk.LEFT
            )

            sp = ttk.Spinbox(
                i_row,
                from_=0.01,
                to=0.99,
                increment=0.01,
                textvariable=var,
                width=6,
                format="%.2f",
                command=update_party_preview,
            )
            sp.pack(side=tk.LEFT, padx=10)
            sp.bind("<KeyRelease>", lambda e: update_party_preview())

            ttk.Label(
                i_row,
                text=f"(District position: {dist_coord:.2f})",
                font=("Helvetica", 9, "italic"),
            ).pack(side=tk.LEFT, padx=10)

        # Party preview badge
        preview_box = ttk.Frame(frame, padding=10)
        preview_box.pack(fill=tk.X, pady=10)

        lbl_party_badge = tk.Label(
            preview_box,
            text="",
            font=("Helvetica", 12, "bold"),
            padx=10,
            pady=4,
        )
        lbl_party_badge.pack(side=tk.LEFT, padx=(0, 15))

        lbl_party_text = ttk.Label(
            preview_box,
            textvariable=party_info_var,
            font=("Helvetica", 12, "bold"),
        )
        lbl_party_text.pack(side=tk.LEFT)

        update_party_preview()

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=20)

        def on_start() -> None:
            assert self.nation is not None
            final_coords: PositionVector = []
            for v in coord_vars:
                c = round(v.get(), 2)
                if not is_valid_candidate_coordinate(c):
                    messagebox.showwarning(
                        "Invalid Platform",
                        f"Coordinate {c} is invalid. Values must be between 0.01 and 0.99, and cannot equal 0.50.",
                    )
                    return
                final_coords.append(c)

            p_idx = find_party_for_platform(final_coords, self.nation.parties)

            self.player = PlayerProfile(
                name=self.temp_player_name,
                home_state=self.temp_state_idx,
                home_city=self.temp_city_idx,
                home_district=self.temp_district_idx,
                party_index=p_idx,
                platform=final_coords,
                current_seat=None,
                current_tier=None,
                elected_cycle=None,
            )

            # Initialize tracker and name manager
            sen_path = os.path.join(self.data_dir, "seniority.xlsx")
            self.seniority_tracker = SeniorityTracker(filepath=sen_path)
            self.name_manager = NameManager(
                in_party_names=self.in_party_names,
                out_party_names=self.out_party_names,
                player_name=self.player.name,
                rng=self.rng,
            )

            if not self.temp_sim_history:
                # Initialize starting cycle 0 historical simulation
                hist_path = os.path.join(self.data_dir, "historical_data.xlsx")
                self.historical_rows, self.historical_streaks = run_historical_simulation(
                    nation=self.nation,
                    home_state=self.temp_state_idx,
                    home_city=self.temp_city_idx,
                    home_district=self.temp_district_idx,
                    num_cycles=0,
                    filepath=hist_path,
                    rng=self.rng,
                )

            self.seniority_tracker.initialize_starting_roster(
                nation=self.nation,
                home_state=self.temp_state_idx,
                home_city=self.temp_city_idx,
                player_party=self.player.party_index,
                name_manager=self.name_manager,
                historical_rows=self.historical_rows,
                streaks=getattr(self, "historical_streaks", {}),
                rng=self.rng,
            )

            self.current_cycle = len(self.historical_rows) + 1
            self.start_cycle = self.current_cycle
            self.game_log.clear()
            self.game_log.append(
                f"Campaign initialized for {self.player.name} ({self.nation.parties[p_idx].name})."
            )

            self.show_game_interface()
            self.prepare_cycle()

        ttk.Button(btn_frame, text="Launch Political Career ->", command=on_start).pack(
            side=tk.RIGHT, ipadx=10, ipady=4
        )

    # =========================================================================
    # 2. MAIN GAME INTERFACE & TABS
    # =========================================================================

    def show_game_interface(self) -> None:
        """Create main persistent interface with header and 4 tabs."""
        self._clear_container()

        main_frm = ttk.Frame(self.container)
        main_frm.pack(fill=tk.BOTH, expand=True)

        # Header Bar - patriotic deep navy blue
        header = tk.Frame(main_frm, bg="#0D47A1", padx=15, pady=10)
        header.pack(fill=tk.X, side=tk.TOP)

        self.hdr_title = tk.Label(
            header,
            text="",
            font=("Helvetica", 13, "bold"),
            bg="#0D47A1",
            fg="#FFFFFF",
        )
        self.hdr_title.pack(side=tk.LEFT)

        self.hdr_party_badge = tk.Label(
            header,
            text="",
            font=("Helvetica", 11, "bold"),
            padx=10,
            pady=3,
        )
        self.hdr_party_badge.pack(side=tk.LEFT, padx=12)

        self.hdr_office_lbl = tk.Label(
            header,
            text="",
            font=("Helvetica", 11),
            bg="#0D47A1",
            fg="#E3F2FD",
        )
        self.hdr_office_lbl.pack(side=tk.LEFT)

        # Global buttons (Quit in Red, Restart in Blue)
        btn_quit = tk.Button(
            header,
            text="Quit",
            font=("Helvetica", 10, "bold"),
            bg="#C62828",
            fg="#FFFFFF",
            activebackground="#B71C1C",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            padx=10,
            pady=3,
            command=self.confirm_quit,
        )
        btn_quit.pack(side=tk.RIGHT, padx=(6, 0))

        btn_restart = tk.Button(
            header,
            text="Restart",
            font=("Helvetica", 10, "bold"),
            bg="#1976D2",
            fg="#FFFFFF",
            activebackground="#1565C0",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            padx=10,
            pady=3,
            command=self.confirm_restart,
        )
        btn_restart.pack(side=tk.RIGHT)

        # Tabbed Notebook
        self.notebook = ttk.Notebook(main_frm)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=(8, 4))

        # Tab 1: Campaign Headquarters
        self.tab_hq = ttk.Frame(self.notebook, padding=15)
        self.notebook.add(self.tab_hq, text="Campaign Headquarters")
        self._setup_hq_tab()

        # Tab 2: Election History
        self.tab_history = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab_history, text="Election History")
        self._setup_history_tab()

        # Tab 3: Seniority Roster
        self.tab_seniority = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.tab_seniority, text="Seniority Roster")
        self._setup_seniority_tab()

        # Tab 4: Live Election Viewer
        self.tab_live = ttk.Frame(self.notebook, padding=15)
        self.notebook.add(self.tab_live, text="Live Election Viewer")
        self._setup_live_viewer_tab()

        self.update_header()

    def update_header(self) -> None:
        """Refresh header bar with current cycle, office, and party badge."""
        if not self.player or not self.nation:
            return
        career_cycle = self.current_cycle - self.start_cycle + 1
        self.hdr_title.config(
            text=f"Cycle {self.current_cycle} (Year {career_cycle * YEARS_PER_CYCLE - 1}) | Career Cycle {career_cycle}/{CAREER_MAX_CYCLES}"
        )

        p_idx = self.player.party_index
        p_name = self.nation.parties[p_idx].name
        self.hdr_party_badge.config(
            text=f" {p_name} ",
            bg=self.get_party_color(p_idx),
            fg=self.get_party_text_color(p_idx),
        )

        curr_office = (
            OFFICE_NAMES[self.player.current_tier]
            if self.player.current_tier is not None
            else "Candidate (City Council)"
        )
        self.hdr_office_lbl.config(text=f"| {self.player.name} - {curr_office}")

    # =========================================================================
    # TAB 1: CAMPAIGN HEADQUARTERS
    # =========================================================================

    def _setup_hq_tab(self) -> None:
        """Construct Campaign Headquarters tab."""
        # Top Card: Status & Ladder
        top_frame = ttk.Frame(self.tab_hq)
        top_frame.pack(fill=tk.X, pady=(0, 10))

        # Status info card
        self.hq_info_card = ttk.LabelFrame(top_frame, text=" Candidate & Career Status ", padding=12)
        self.hq_info_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))

        self.lbl_hq_office = ttk.Label(self.hq_info_card, text="", font=("Helvetica", 12, "bold"))
        self.lbl_hq_office.pack(anchor=tk.W, pady=2)

        self.lbl_hq_term = ttk.Label(self.hq_info_card, text="", font=("Helvetica", 10))
        self.lbl_hq_term.pack(anchor=tk.W, pady=2)

        self.lbl_hq_platform = ttk.Label(self.hq_info_card, text="", font=("Helvetica", 10))
        self.lbl_hq_platform.pack(anchor=tk.W, pady=2)

        # Career Ladder Tracker
        ladder_card = ttk.LabelFrame(top_frame, text=" Presidential Path (Tiers 7 -> 1) ", padding=12)
        ladder_card.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.ladder_labels: dict[int, tk.Label] = {}
        ladder_tiers = [
            (TIER_CITY_COUNCIL, "7. City Council"),
            (TIER_STATE_LEG, "6. State Legislature"),
            (TIER_MAYOR, "5. Mayor"),
            (TIER_HOUSE, "4. House of Reps"),
            (TIER_SENATOR, "3. Senator"),
            (TIER_GOVERNOR, "2. Governor"),
            (TIER_PRESIDENT, "1. President (GOAL)"),
        ]
        for tier, t_name in ladder_tiers:
            lbl = tk.Label(
                ladder_card,
                text=f"  {t_name}  ",
                font=("Helvetica", 9),
                anchor="w",
                padx=6,
                pady=2,
            )
            lbl.pack(anchor=tk.W, fill=tk.X, pady=1)
            self.ladder_labels[tier] = lbl

        # Action Area / Primary Opportunity Box
        self.action_card = ttk.LabelFrame(self.tab_hq, text=" Actions & Election Decisions ", padding=12)
        self.action_card.pack(fill=tk.X, pady=10)

        self.lbl_action_status = ttk.Label(
            self.action_card,
            text="",
            font=("Helvetica", 11, "bold"),
            wraplength=800,
        )
        self.lbl_action_status.pack(anchor=tk.W, pady=(0, 8))

        self.btn_row_hq = ttk.Frame(self.action_card)
        self.btn_row_hq.pack(fill=tk.X)

        self.btn_start_election = ttk.Button(
            self.btn_row_hq,
            text="Proceed to Election ->",
            style="Action.TButton",
            command=self.start_live_election_phase,
        )
        self.btn_start_election.pack(side=tk.LEFT, padx=(0, 10), ipady=3)

        self.btn_tweak_platform = ttk.Button(
            self.btn_row_hq,
            text="Tweak Platform",
            command=self.open_tweak_platform_dialog,
        )
        self.btn_tweak_platform.pack(side=tk.LEFT, padx=(0, 10))

        self.btn_primary_challenge = tk.Button(
            self.btn_row_hq,
            text="Issue Primary Challenge",
            font=("Helvetica", 10, "bold"),
            bg="#C62828",
            fg="#FFFFFF",
            activebackground="#B71C1C",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            padx=12,
            pady=4,
            command=self.handle_issue_primary_challenge,
        )
        # Hidden by default until eligible

        # News & Campaign Log
        log_frame = ttk.LabelFrame(self.tab_hq, text=" Campaign Log & News ", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 0))

        self.txt_log = tk.Text(
            log_frame,
            wrap=tk.WORD,
            font=("Courier", 10),
            bg="#FAFAFA",
            state=tk.DISABLED,
        )
        log_scroll = ttk.Scrollbar(log_frame, command=self.txt_log.yview)
        self.txt_log.config(yscrollcommand=log_scroll.set)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.txt_log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def log_message(self, message: str) -> None:
        """Append a message to the campaign log."""
        self.game_log.append(message)
        self.txt_log.config(state=tk.NORMAL)
        self.txt_log.insert(tk.END, message + "\n")
        self.txt_log.see(tk.END)
        self.txt_log.config(state=tk.DISABLED)

    def update_hq_view(self) -> None:
        """Update Headquarters widgets with current player status."""
        if not self.player or not self.seniority_tracker:
            return

        curr_office = (
            OFFICE_NAMES[self.player.current_tier]
            if self.player.current_tier is not None
            else "None (Initial Candidate)"
        )
        self.lbl_hq_office.config(text=f"Current Office: {curr_office}")

        # Term and cycles info
        term_text = "Not yet elected"
        if self.player.current_tier is not None and self.player.current_seat is not None:
            cand = self.seniority_tracker.roster.get(self.player.current_seat)
            cyc = get_candidate_cycles(cand) if cand else 0
            max_c = get_max_cycles_for_tier(self.player.current_tier)
            term_len = TERM_LENGTH_CYCLES[self.player.current_tier]
            curr_term = (cyc // term_len) + 1
            max_terms = TERM_LIMITS[self.player.current_tier]
            term_text = f"Cycles Served: {cyc} | Term {min(curr_term, max_terms)} of {max_terms} (Max {max_c} cycles)"
        self.lbl_hq_term.config(text=term_text)

        self.lbl_hq_platform.config(
            text=f"Platform: {[round(x, 2) for x in self.player.platform]}"
        )

        # Highlight career ladder with vibrant badges
        ladder_tiers = [
            (TIER_CITY_COUNCIL, "7. City Council"),
            (TIER_STATE_LEG, "6. State Legislature"),
            (TIER_MAYOR, "5. Mayor"),
            (TIER_HOUSE, "4. House of Reps"),
            (TIER_SENATOR, "3. Senator"),
            (TIER_GOVERNOR, "2. Governor"),
            (TIER_PRESIDENT, "1. President (GOAL)"),
        ]
        for tier, lbl in self.ladder_labels.items():
            t_name = next(name for t, name in ladder_tiers if t == tier)
            if tier == self.player.current_tier:
                p_color = self.get_party_color(self.player.party_index)
                p_txt = self.get_party_text_color(self.player.party_index)
                lbl.config(
                    text=f" ★ {t_name} [CURRENT OFFICE]",
                    font=("Helvetica", 10, "bold"),
                    bg=p_color,
                    fg=p_txt,
                )
            elif self.player.current_tier is not None and tier > self.player.current_tier:
                lbl.config(
                    text=f" ✓ {t_name} (Completed)",
                    font=("Helvetica", 9, "bold"),
                    bg="#E8F5E9",
                    fg="#2E7D32",
                )
            else:
                lbl.config(
                    text=f"   {t_name}",
                    font=("Helvetica", 9),
                    bg="#F8FAFC",
                    fg="#37474F",
                )

    # =========================================================================
    # TAB 2 & 3: ELECTION HISTORY & SENIORITY
    # =========================================================================

    def _setup_history_tab(self) -> None:
        """Construct Treeview for historical_data.xlsx."""
        cols = HISTORICAL_HEADERS
        self.tree_history = ttk.Treeview(self.tab_history, columns=cols, show="headings")

        for col in cols:
            self.tree_history.heading(col, text=col)
            width = 60 if col == "Cycle" else 100
            self.tree_history.column(col, width=width, anchor=tk.CENTER)

        vsb = ttk.Scrollbar(self.tab_history, orient=tk.VERTICAL, command=self.tree_history.yview)
        hsb = ttk.Scrollbar(self.tab_history, orient=tk.HORIZONTAL, command=self.tree_history.xview)
        self.tree_history.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree_history.pack(fill=tk.BOTH, expand=True)

    def refresh_history_tab(self) -> None:
        """Reload history rows into Treeview."""
        self.tree_history.delete(*self.tree_history.get_children())
        hist_path = os.path.join(self.data_dir, "historical_data.xlsx")
        rows = read_historical_data(hist_path)
        for r in rows:
            vals = [r.get(c, "") for c in HISTORICAL_HEADERS]
            self.tree_history.insert("", tk.END, values=vals)

    def _setup_seniority_tab(self) -> None:
        """Construct Treeview for seniority.xlsx."""
        cols = ["Name", "Level of Office", "Office Name", "Seniority", "Victory Size"]
        self.tree_seniority = ttk.Treeview(self.tab_seniority, columns=cols, show="headings")

        self.tree_seniority.heading("Name", text="Candidate Name")
        self.tree_seniority.heading("Level of Office", text="Tier")
        self.tree_seniority.heading("Office Name", text="Office")
        self.tree_seniority.heading("Seniority", text="Seniority (Years)")
        self.tree_seniority.heading("Victory Size", text="Victory Margin (%)")

        self.tree_seniority.column("Name", width=180, anchor=tk.W)
        self.tree_seniority.column("Level of Office", width=60, anchor=tk.CENTER)
        self.tree_seniority.column("Office Name", width=140, anchor=tk.W)
        self.tree_seniority.column("Seniority", width=110, anchor=tk.CENTER)
        self.tree_seniority.column("Victory Size", width=120, anchor=tk.CENTER)

        vsb = ttk.Scrollbar(self.tab_seniority, orient=tk.VERTICAL, command=self.tree_seniority.yview)
        self.tree_seniority.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree_seniority.pack(fill=tk.BOTH, expand=True)

        self.tree_seniority.tag_configure("player", background="#BBDEFB", font=("Helvetica", 10, "bold"))

    def refresh_seniority_tab(self) -> None:
        """Reload in-party seniority roster into Treeview."""
        self.tree_seniority.delete(*self.tree_seniority.get_children())
        sen_path = os.path.join(self.data_dir, "seniority.xlsx")
        rows = read_seniority_data(sen_path)
        for r in rows:
            t_idx = r.get("Level of Office", 7)
            t_name = OFFICE_NAMES.get(t_idx, f"Tier {t_idx}")
            is_player = self.player is not None and r.get("Name") == self.player.name
            tag = ("player",) if is_player else ()
            vals = [
                r.get("Name", ""),
                t_idx,
                t_name,
                f"{r.get('Seniority', 0)} yrs",
                f"{r.get('Victory Size', 0.0):.2f}%",
            ]
            self.tree_seniority.insert("", tk.END, values=vals, tags=tag)

    # =========================================================================
    # TAB 4: LIVE ELECTION VIEWER
    # =========================================================================

    def _setup_live_viewer_tab(self) -> None:
        """Construct Live Election Viewer tab."""
        # Race selector bar
        sel_frame = ttk.Frame(self.tab_live, padding=(0, 0, 0, 10))
        sel_frame.pack(fill=tk.X)

        ttk.Label(sel_frame, text="View Race:", font=("Helvetica", 11, "bold")).pack(
            side=tk.LEFT, padx=(0, 10)
        )
        self.live_race_var = tk.StringVar()
        self.cb_live_races = ttk.Combobox(
            sel_frame,
            textvariable=self.live_race_var,
            state="readonly",
            font=("Helvetica", 11),
            width=50,
        )
        self.cb_live_races.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.cb_live_races.bind("<<ComboboxSelected>>", self._on_live_race_selected)

        # Status badge & Reporting bar
        self.live_status_card = ttk.LabelFrame(self.tab_live, text=" Election Status ", padding=10)
        self.live_status_card.pack(fill=tk.X, pady=(0, 10))

        self.lbl_live_batch_status = ttk.Label(
            self.live_status_card,
            text="Waiting for election night returns...",
            font=("Helvetica", 12, "bold"),
        )
        self.lbl_live_batch_status.pack(anchor=tk.W)

        self.lbl_live_votes_reported = ttk.Label(
            self.live_status_card,
            text="",
            font=("Helvetica", 10),
        )
        self.lbl_live_votes_reported.pack(anchor=tk.W)

        # Candidates Results Display Frame (Scrollable)
        res_container = ttk.Frame(self.tab_live)
        res_container.pack(fill=tk.BOTH, expand=True, pady=5)

        self.canvas_res = tk.Canvas(res_container, bg="#FFFFFF", highlightthickness=0)
        res_scroll = ttk.Scrollbar(res_container, command=self.canvas_res.yview)
        self.canvas_res.configure(yscrollcommand=res_scroll.set)

        self.results_inner_frame = ttk.Frame(self.canvas_res)
        self.results_window = self.canvas_res.create_window(
            (0, 0), window=self.results_inner_frame, anchor="nw"
        )

        def _on_canvas_configure(event):
            self.canvas_res.itemconfig(self.results_window, width=event.width)

        self.canvas_res.bind("<Configure>", _on_canvas_configure)
        self.results_inner_frame.bind(
            "<Configure>",
            lambda e: self.canvas_res.configure(scrollregion=self.canvas_res.bbox("all")),
        )

        res_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas_res.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Bottom Controls
        ctrl_bar = ttk.Frame(self.tab_live, padding=(0, 10, 0, 0))
        ctrl_bar.pack(fill=tk.X, side=tk.BOTTOM)

        self.btn_live_next = ttk.Button(
            ctrl_bar,
            text="Advance to Next Batch ->",
            style="Action.TButton",
            command=self.advance_live_batch,
        )
        self.btn_live_next.pack(side=tk.RIGHT, ipadx=10, ipady=4)

        self.btn_live_finish_all = ttk.Button(
            ctrl_bar,
            text="Complete All Batches",
            command=self.fast_forward_live_election,
        )
        self.btn_live_finish_all.pack(side=tk.RIGHT, padx=10)

    def _on_live_race_selected(self, event=None) -> None:
        """Handle race switch in dropdown."""
        idx = self.cb_live_races.current()
        if idx >= 0 and idx < len(self.current_live_races):
            self.selected_race_key = self.current_live_races[idx].seat_key
            self.refresh_live_results_display()

    def refresh_live_results_display(self) -> None:
        """Render candidate cards and progress bars for the currently selected race."""
        for w in self.results_inner_frame.winfo_children():
            w.destroy()

        if not self.selected_race_key or not self.nation:
            return

        race = next((r for r in self.current_live_races if r.seat_key == self.selected_race_key), None)
        if not race:
            return

        race_totals = self.live_cumulative_votes.get(self.selected_race_key, {})
        total_votes = sum(race_totals.values())

        # Sort candidate indices descending by votes
        sorted_cand_indices = sorted(
            range(len(race.candidates)),
            key=lambda i: (race_totals.get(i, 0), -race.candidates[i].party_index),
            reverse=True,
        )

        num_dist = len(race.districts)
        dist_total_target = VOTES_PER_DISTRICT * num_dist
        pct_reported = int((total_votes / dist_total_target) * 100) if dist_total_target > 0 else 0

        self.lbl_live_votes_reported.config(
            text=f"Total Votes Counted: {total_votes:,} / {dist_total_target:,} ({pct_reported}% Reporting) across {num_dist} district(s)"
        )

        for rank, cand_idx in enumerate(sorted_cand_indices, start=1):
            cand = race.candidates[cand_idx]
            p_idx = cand.party_index
            p_color = self.get_party_color(p_idx)
            p_txt_col = self.get_party_text_color(p_idx)
            p_name = self.nation.parties[p_idx].name
            votes = race_totals.get(cand_idx, 0)
            pct = (votes / total_votes * 100.0) if total_votes > 0 else 0.0

            c_frame = ttk.Frame(self.results_inner_frame, style="Card.TFrame", padding=10)
            c_frame.pack(fill=tk.X, pady=4, padx=5)

            # Left badge: Party
            lbl_badge = tk.Label(
                c_frame,
                text=f" {p_name} ",
                bg=p_color,
                fg=p_txt_col,
                font=("Helvetica", 10, "bold"),
                padx=8,
                pady=2,
            )
            lbl_badge.pack(side=tk.LEFT, padx=(0, 10))

            # Candidate name and indicators
            you_tag = " * [YOU]" if cand.is_player else ""
            lead_tag = "  (LEADER)" if (rank == 1 and total_votes > 0) else ""
            lbl_name = ttk.Label(
                c_frame,
                text=f"{cand.name}{you_tag}{lead_tag}",
                font=("Helvetica", 11, "bold" if cand.is_player else "normal"),
            )
            lbl_name.pack(side=tk.LEFT, padx=(0, 10))

            # Vote count & percentage readout
            lbl_votes = ttk.Label(
                c_frame,
                text=f"{votes:,} votes ({pct:.2f}%)",
                font=("Helvetica", 11, "bold"),
            )
            lbl_votes.pack(side=tk.RIGHT, padx=10)

            # Custom colored progress bar Canvas
            bar_canvas = tk.Canvas(c_frame, height=14, width=180, bg="#E0E0E0", highlightthickness=0)
            bar_canvas.pack(side=tk.RIGHT, padx=5)
            bar_width = int((pct / 100.0) * 180)
            if bar_width > 0:
                bar_canvas.create_rectangle(0, 0, bar_width, 14, fill=p_color, outline="")

    # =========================================================================
    # 3. GAMEPLAY CYCLE & ENGINE ORCHESTRATION
    # =========================================================================

    def prepare_cycle(self) -> None:
        """Evaluate cycle nominations, vacancies, and primary challenge options."""
        assert self.nation is not None and self.player is not None and self.seniority_tracker is not None

        # Check time limit
        career_cycle = self.current_cycle - self.start_cycle + 1
        if career_cycle > CAREER_MAX_CYCLES:
            self.show_lose_screen(
                f"Time limit reached: {CAREER_MAX_CYCLES} cycles (50 years) elapsed without reaching the Presidency."
            )
            return

        self.update_header()
        self.update_hq_view()
        self.refresh_history_tab()
        self.refresh_seniority_tab()

        # Resolve cycle nominations
        self.assignments, self.player_assignment = self.seniority_tracker.resolve_cycle_assignments(
            cycle=self.current_cycle,
            nation=self.nation,
            player=self.player,
        )

        player_was_promoted = (
            self.player_assignment is not None
            and self.player_assignment.is_promotion
            and self.player.current_tier is not None
            and self.player_assignment.tier < self.player.current_tier
        )

        # Check term limits
        is_term_limited = False
        if self.player.current_tier is not None:
            max_cyc = get_max_cycles_for_tier(self.player.current_tier)
            cyc_count = 0
            if self.player.current_seat in self.seniority_tracker.roster:
                cyc_count = get_candidate_cycles(
                    self.seniority_tracker.roster[self.player.current_seat]
                )
            elif self.player.current_seat in self.seniority_tracker.seat_streaks:
                streak_p, streak_c = self.seniority_tracker.seat_streaks[self.player.current_seat]
                if streak_p == self.player.party_index:
                    cyc_count = streak_c
            if cyc_count >= max_cyc:
                is_term_limited = True

        is_up_for_reelection = (
            is_player_up_for_reelection(self.player, self.current_cycle, self.nation)
            or is_term_limited
        )

        # Check if player was term-limited without advancement options
        if self.player_assignment is None and is_term_limited:
            t_name = OFFICE_NAMES.get(self.player.current_tier, "office")
            self.show_lose_screen(
                f"You reached your term limit as {t_name} and were not able to advance to higher office."
            )
            return

        # Check eligibility for primary challenge
        higher_sk = get_higher_office_seat(self.player, self.current_cycle, self.nation)
        has_completed_term = player_has_served_complete_term(
            self.player,
            self.current_cycle,
            self.seniority_tracker.roster.get(self.player.current_seat)
            if self.player.current_seat is not None
            else None,
        )
        can_issue_primary = (
            self.player.current_tier is not None
            and not player_was_promoted
            and not self.player.pending_party_challenge
            and higher_sk is not None
            and has_completed_term
        )

        target_nominee = None
        if can_issue_primary and higher_sk is not None:
            higher_assign = self.assignments.get(higher_sk)
            if higher_assign is not None and higher_assign.candidate is not None:
                if not higher_assign.candidate.is_player:
                    target_nominee = higher_assign.candidate
                else:
                    can_issue_primary = False
            else:
                can_issue_primary = False

        self.primary_target_nominee = target_nominee
        self.primary_higher_sk = higher_sk
        self.primary_has_stakes = is_up_for_reelection
        self.player_in_general_no_stakes = False

        # Update action buttons
        if can_issue_primary and target_nominee and higher_sk:
            stakes_msg = (
                "STAKES: You are up for re-election. If you challenge and lose, you lose the game!"
                if is_up_for_reelection
                else "NO STAKES: You are not up for re-election. If you challenge and lose, you retain your current office."
            )
            self.lbl_action_status.config(
                text=(
                    f"PRIMARY OPPORTUNITY: You were not selected to advance to {format_seat_label(higher_sk)}.\n"
                    f"{target_nominee.name} is the party's assigned nominee.\n{stakes_msg}"
                )
            )
            self.btn_primary_challenge.pack(side=tk.LEFT, padx=10)
        else:
            self.btn_primary_challenge.pack_forget()
            if self.player_assignment is not None:
                verb = (
                    "advanced to run for"
                    if self.player_assignment.is_promotion
                    else ("running for re-election for" if self.player_assignment.is_reelection else "running for")
                )
                self.lbl_action_status.config(
                    text=f"You are {verb} {format_seat_label(self.player_assignment.seat_key)}!"
                )
            else:
                curr_t = self.player.current_tier or TIER_CITY_COUNCIL
                self.lbl_action_status.config(
                    text=f"You are not up for election this cycle. You will watch {LIVE_SCOPE_TITLES[curr_t]}."
                )

        # Retaliatory primary check
        if (
            self.player_assignment is not None
            and self.player_assignment.candidate is not None
            and self.player_assignment.candidate.is_player
            and self.player.pending_party_challenge
        ):
            self.primary_is_retaliatory = True
            self.lbl_action_status.config(
                text=(
                    "RETALIATORY PRIMARY CHALLENGE: Because you previously defied the party manager, "
                    f"a primary challenger has been entered against you for {format_seat_label(self.player_assignment.seat_key)}!"
                )
            )
        else:
            self.primary_is_retaliatory = False

        self.notebook.select(self.tab_hq)

    def handle_issue_primary_challenge(self) -> None:
        """Launch primary challenge against target nominee."""
        assert self.player and self.primary_target_nominee and self.primary_higher_sk and self.seniority_tracker
        ans = messagebox.askyesno(
            "Confirm Primary Challenge",
            f"Are you sure you want to issue a primary challenge against {self.primary_target_nominee.name} for "
            f"{format_seat_label(self.primary_higher_sk)}?\n\n"
            + (
                "WARNING: High Stakes! Losing means Game Over!"
                if self.primary_has_stakes
                else "No Stakes: If you lose, you retain your current office."
            ),
        )
        if not ans:
            return

        self.player.pending_party_challenge = True
        if self.primary_has_stakes and self.player.current_seat is not None:
            self.seniority_tracker.roster.pop(self.player.current_seat, None)
            self.seniority_tracker.seat_streaks.pop(self.player.current_seat, None)
            if self.player.current_seat in self.assignments:
                old_assign = self.assignments[self.player.current_seat]
                if old_assign.candidate and old_assign.candidate.is_player:
                    old_assign.candidate = None
                    old_assign.is_reelection = False
            self.player.current_seat = None
            self.player.current_tier = None

        self.btn_primary_challenge.pack_forget()

        # Build primary race spec
        assert self.nation is not None
        player_cand = Candidate(
            name=self.player.name,
            party_index=self.player.party_index,
            platform=list(self.player.platform),
            tier=self.primary_higher_sk[0],
            seat_id=self.primary_higher_sk,
            seniority=0,
            victory_size=0.0,
            is_player=True,
        )
        districts = get_seat_districts(self.primary_higher_sk, self.nation)
        race_spec = LiveRaceSpec(
            seat_key=self.primary_higher_sk,
            tier=self.primary_higher_sk[0],
            label=f"PRIMARY: {format_seat_label(self.primary_higher_sk)}",
            districts=districts,
            candidates=[player_cand, self.primary_target_nominee],
            has_player=True,
        )

        self.start_primary_simulation(race_spec, is_retaliatory=False)

    def start_primary_simulation(self, race_spec: LiveRaceSpec, is_retaliatory: bool) -> None:
        """Set up and switch to live primary election viewer."""
        self.active_primary_race = race_spec
        self.primary_is_retaliatory = is_retaliatory
        self.live_phase = "primary"
        self.current_live_races = [race_spec]
        self.selected_race_key = race_spec.seat_key

        # Ensure candidates in primary have distinct platforms to avoid deterministic ties
        if len(race_spec.candidates) >= 2:
            c0, c1 = race_spec.candidates[0], race_spec.candidates[1]
            if c0.platform == c1.platform:
                c1.platform = sample_distinct_platform(
                    self.nation.parties[c1.party_index].platform,
                    existing_platform=c0.platform,
                    rng=self.rng,
                )

        self.live_prob_matrices = [precompute_race_probabilities(race_spec)]
        # Track votes by candidate index (0..N-1) to handle same-party candidates
        self.live_cumulative_votes = {
            race_spec.seat_key: {i: 0 for i in range(len(race_spec.candidates))}
        }
        self.live_batch_num = 0

        self.cb_live_races["values"] = [race_spec.label]
        self.cb_live_races.current(0)

        self.notebook.select(self.tab_live)
        self.advance_live_batch()

    def start_live_election_phase(self) -> None:
        """Launch general live election phase (or retaliatory primary if pending)."""
        assert self.nation and self.player and self.seniority_tracker and self.name_manager

        # If facing retaliatory primary, execute it first
        if self.primary_is_retaliatory and self.player_assignment:
            chal_name = self.name_manager.draw_in_party_name(self.seniority_tracker.active_names())
            chal_plat = sample_distinct_platform(
                self.nation.parties[self.player.party_index].platform,
                existing_platform=self.player.platform,
                rng=self.rng,
            )
            chal_cand = Candidate(
                name=chal_name,
                party_index=self.player.party_index,
                platform=chal_plat,
                tier=self.player_assignment.tier,
                seat_id=self.player_assignment.seat_key,
                seniority=0,
                victory_size=0.0,
                is_player=False,
            )
            districts = get_seat_districts(self.player_assignment.seat_key, self.nation)
            race_spec = LiveRaceSpec(
                seat_key=self.player_assignment.seat_key,
                tier=self.player_assignment.tier,
                label=f"RETALIATORY PRIMARY: {format_seat_label(self.player_assignment.seat_key)}",
                districts=districts,
                candidates=[self.player_assignment.candidate, chal_cand],
                has_player=True,
            )
            self.start_primary_simulation(race_spec, is_retaliatory=True)
            return

        # Build general live races; when player not up for re-election, show active elections
        if self.player_assignment:
            live_tier = self.player_assignment.tier
        else:
            live_tier = get_active_live_tier_for_player(self.player, self.current_cycle)

        self.current_live_races = self.seniority_tracker.build_live_races(
            live_tier=live_tier,
            cycle=self.current_cycle,
            nation=self.nation,
            player=self.player,
            assignments=self.assignments,
            name_manager=self.name_manager,
            rng=self.rng,
        )

        if not self.current_live_races:
            self.cb_live_races["values"] = ["No live races scheduled this cycle"]
            self.cb_live_races.current(0)
            self.selected_race_key = None
            self.lbl_live_batch_status.config(text="No live elections scheduled this cycle.")
            self.btn_live_next.config(
                text="Proceed to Next Cycle", command=self._finalize_cycle_after_voting
            )
            self.notebook.select(self.tab_live)
            return

        self.live_prob_matrices = [precompute_race_probabilities(r) for r in self.current_live_races]
        # Track votes by candidate index (0..N-1)
        self.live_cumulative_votes = {
            r.seat_key: {i: 0 for i in range(len(r.candidates))}
            for r in self.current_live_races
        }
        self.live_batch_num = 0
        self.live_phase = "round1"
        self.decided_live_outcomes.clear()
        self.runoff_specs.clear()
        self.round1_snapshots.clear()

        race_labels = [
            f"{r.label}{' * [YOUR RACE]' if r.has_player else ''}"
            for r in self.current_live_races
        ]
        self.cb_live_races["values"] = race_labels

        # Default dropdown to player's race if present
        player_race_idx = next(
            (i for i, r in enumerate(self.current_live_races) if r.has_player), 0
        )
        self.cb_live_races.current(player_race_idx)
        self.selected_race_key = self.current_live_races[player_race_idx].seat_key

        self.btn_live_next.config(
            text="Advance to Next Batch ->",
            command=self.advance_live_batch,
        )
        self.notebook.select(self.tab_live)
        self.advance_live_batch()

    def advance_live_batch(self) -> None:
        """Simulate one batch (1 to 10) in the active live voting phase."""
        if self.live_batch_num >= LIVE_BATCHES:
            self._handle_round_completion()
            return

        self.live_batch_num += 1

        # Simulate batch for all races in current scope
        for race, prob_mat in zip(self.current_live_races, self.live_prob_matrices):
            batch_counts = simulate_live_batch(
                race,
                prob_matrix=prob_mat,
                rng=self.rng,
                np_rng=self.np_rng,
            )
            r_totals = self.live_cumulative_votes[race.seat_key]
            for cand_idx, count in enumerate(batch_counts):
                r_totals[cand_idx] += count

        phase_title = (
            "PRIMARY ELECTION"
            if self.live_phase == "primary"
            else ("ROUND 1 LIVE VOTING" if self.live_phase == "round1" else "RUNOFF ELECTION")
        )
        self.lbl_live_batch_status.config(
            text=f"{phase_title}: Batch {self.live_batch_num}/{LIVE_BATCHES}"
        )

        self.refresh_live_results_display()

        if self.live_batch_num >= LIVE_BATCHES:
            self._handle_round_completion()

    def fast_forward_live_election(self) -> None:
        """Fast forward remaining batches to complete current round."""
        while self.live_batch_num < LIVE_BATCHES:
            self.advance_live_batch()

    def _handle_round_completion(self) -> None:
        """Handle end of 10 batches for primary, round 1, or runoff."""
        if self.live_phase == "primary":
            self._resolve_primary_completion()
        elif self.live_phase == "round1":
            self._resolve_round1_completion()
        elif self.live_phase == "runoff":
            self._resolve_runoff_completion()

    def _resolve_primary_completion(self) -> None:
        """Resolve primary challenge results."""
        assert self.active_primary_race and self.player
        r_totals = self.live_cumulative_votes[self.active_primary_race.seat_key]
        sorted_indices = sorted(
            range(len(self.active_primary_race.candidates)),
            key=lambda i: (r_totals.get(i, 0), -self.active_primary_race.candidates[i].party_index),
            reverse=True,
        )
        winner_idx = sorted_indices[0]
        winner = self.active_primary_race.candidates[winner_idx]
        total_v = sum(r_totals.values())
        win_pct = (r_totals[winner_idx] / total_v) * 100.0 if total_v > 0 else 50.0

        if self.primary_is_retaliatory:
            if winner.is_player:
                messagebox.showinfo(
                    "Primary Victory!",
                    f"You survived the retaliatory primary challenge with {win_pct:.2f}% of the vote!",
                )
                self.player.pending_party_challenge = False
                self.log_message(f"Survived retaliatory primary challenge ({win_pct:.2f}%).")
                self.primary_is_retaliatory = False
                self.start_live_election_phase()
            else:
                self.show_lose_screen(
                    f"You were defeated in the retaliatory primary challenge ({win_pct:.2f}%)."
                )
        else:
            target_name = (
                self.primary_target_nominee.name if self.primary_target_nominee else "the incumbent"
            )
            if winner.is_player:
                messagebox.showinfo(
                    "Primary Victory!",
                    f"You defeated {target_name} ({win_pct:.2f}%) and won the nomination!",
                )
                if self.primary_higher_sk:
                    self.log_message(
                        f"Won primary challenge for {format_seat_label(self.primary_higher_sk)} ({win_pct:.2f}%)."
                    )
                    higher_assign = self.assignments.get(self.primary_higher_sk)
                    if higher_assign:
                        higher_assign.candidate = winner
                        higher_assign.is_promotion = True
                        self.player_assignment = higher_assign
                self.player_in_general_no_stakes = not self.primary_has_stakes
                self.start_live_election_phase()
            else:
                if self.primary_has_stakes:
                    self.show_lose_screen(
                        f"You lost the primary challenge to {target_name} ({win_pct:.2f}%) while up for re-election."
                    )
                else:
                    curr_off = (
                        OFFICE_NAMES[self.player.current_tier]
                        if self.player.current_tier is not None
                        else "Candidate"
                    )
                    messagebox.showinfo(
                        "Primary Defeat",
                        f"You were defeated by {target_name} ({win_pct:.2f}%).\n"
                        f"You retain your current office as {curr_off}.",
                    )
                    self.log_message(f"Defeated in primary challenge ({win_pct:.2f}%). Retained current office.")
                    self.player_assignment = None
                    self.start_live_election_phase()

    def _resolve_round1_completion(self) -> None:
        """Evaluate Round 1 results; advance top 2 to runoff if leader < 50%."""
        self.runoff_specs.clear()
        self.runoff_candidates.clear()

        for race in self.current_live_races:
            r_totals = self.live_cumulative_votes[race.seat_key]
            total_v = sum(r_totals.values())
            sorted_indices = sorted(
                range(len(race.candidates)),
                key=lambda i: (r_totals.get(i, 0), -race.candidates[i].party_index),
                reverse=True,
            )
            leader_idx = sorted_indices[0]
            leader = race.candidates[leader_idx]
            leader_pct = (r_totals[leader_idx] / total_v) * 100.0 if total_v > 0 else 0.0

            if len(race.candidates) <= 2 or leader_pct >= 50.0:
                self.decided_live_outcomes[race.seat_key] = (leader.party_index, leader_pct)
            else:
                top_two = [race.candidates[sorted_indices[0]], race.candidates[sorted_indices[1]]]
                self.runoff_candidates[race.seat_key] = top_two
                self.runoff_specs.append(
                    LiveRaceSpec(
                        seat_key=race.seat_key,
                        tier=race.tier,
                        label=f"{race.label} (Runoff)",
                        districts=race.districts,
                        candidates=top_two,
                        has_player=any(c.is_player for c in top_two),
                        incumbent_party=race.incumbent_party,
                        incumbent_cycles=race.incumbent_cycles,
                    )
                )

        if not self.runoff_specs:
            self._finalize_cycle_after_voting()
        else:
            # Announce runoff and transition to runoff round
            self.lbl_live_batch_status.config(
                text="ROUND 1 COMPLETE: No candidate reached 50%. Proceeding to Runoff between top 2."
            )
            self.btn_live_next.config(
                text="Proceed to Runoff ->",
                command=self._start_runoff_phase,
            )

    def _start_runoff_phase(self) -> None:
        """Configure Live Election Viewer for Runoff round between top 2 candidates."""
        self.live_phase = "runoff"
        self.current_live_races = list(self.runoff_specs)
        self.live_prob_matrices = [precompute_race_probabilities(r) for r in self.current_live_races]
        self.live_cumulative_votes = {
            r.seat_key: {i: 0 for i in range(len(r.candidates))}
            for r in self.current_live_races
        }
        self.live_batch_num = 0

        race_labels = [
            f"{r.label}{' * [YOUR RACE]' if r.has_player else ''}"
            for r in self.current_live_races
        ]
        self.cb_live_races["values"] = race_labels
        player_idx = next((i for i, r in enumerate(self.current_live_races) if r.has_player), 0)
        self.cb_live_races.current(player_idx)
        self.selected_race_key = self.current_live_races[player_idx].seat_key

        self.btn_live_next.config(
            text="Advance to Next Batch ->",
            command=self.advance_live_batch,
        )
        self.advance_live_batch()

    def _resolve_runoff_completion(self) -> None:
        """Resolve final called runoff winners (guaranteed >= 50%)."""
        for race in self.current_live_races:
            r_totals = self.live_cumulative_votes[race.seat_key]
            total_v = sum(r_totals.values())
            sorted_indices = sorted(
                range(len(race.candidates)),
                key=lambda i: (r_totals.get(i, 0), -race.candidates[i].party_index),
                reverse=True,
            )
            winner_idx = sorted_indices[0]
            winner = race.candidates[winner_idx]
            win_pct = (r_totals[winner_idx] / total_v) * 100.0 if total_v > 0 else 50.0
            self.decided_live_outcomes[race.seat_key] = (winner.party_index, win_pct)

        self._finalize_cycle_after_voting()

    def _finalize_cycle_after_voting(self) -> None:
        """Compute default elections, update history/seniority, and check win/lose."""
        assert self.nation and self.player and self.seniority_tracker and self.name_manager

        # Simulate non-live default races
        default_outcomes: dict = {}
        num_parties = len(self.nation.parties)
        party_platforms = [p.platform for p in self.nation.parties]

        for sk, assignment in self.assignments.items():
            if sk in self.decided_live_outcomes:
                continue
            pop_pos = get_seat_population_position(self.nation, sk)
            inc_p, inc_c = self.seniority_tracker.get_incumbent_grudge(
                sk, assignment, self.player.party_index
            )
            inc_cycles = [
                inc_c if (p == inc_p and inc_c > 0) else 0
                for p in range(num_parties)
            ]
            winner = run_default_election(
                pop_pos,
                party_platforms,
                rng=self.rng,
                incumbent_cycles=inc_cycles,
            )
            default_outcomes[sk] = (winner, 0.0)

        all_outcomes = {**default_outcomes, **self.decided_live_outcomes}

        # Check player's result
        player_lost = False
        player_won_presidency = False
        if self.player_assignment is not None:
            win_p, win_pct = all_outcomes[self.player_assignment.seat_key]
            if win_p != self.player.party_index:
                if self.player_in_general_no_stakes:
                    self.log_message(
                        f"Lost election for {format_seat_label(self.player_assignment.seat_key)} ({win_pct:.2f}%). "
                        f"Retained office as {OFFICE_NAMES[self.player.current_tier]}."
                    )
                    player_lost = False
                else:
                    player_lost = True
            elif self.player_assignment.tier == TIER_PRESIDENT:
                player_won_presidency = True

        # Apply outcomes to seniority roster and history
        self.seniority_tracker.apply_cycle_outcomes(
            cycle=self.current_cycle,
            nation=self.nation,
            player=self.player,
            assignments=self.assignments,
            outcomes=all_outcomes,
            name_manager=self.name_manager,
            rng=self.rng,
        )

        hist_row = build_historical_row(
            self.current_cycle,
            self.nation,
            self.player.home_state,
            self.player.home_city,
            self.player.home_district,
        )
        hist_path = os.path.join(self.data_dir, "historical_data.xlsx")
        append_historical_row(hist_row, filepath=hist_path)

        if player_lost:
            t_name = format_seat_label(self.player_assignment.seat_key)
            self.show_lose_screen(f"You were defeated in the election for {t_name}.")
            return

        if player_won_presidency:
            self.show_win_screen()
            return

        # Prepare for next cycle
        self.log_message(f"Cycle {self.current_cycle} concluded successfully.")
        self.current_cycle += 1
        self.prepare_cycle()

    # =========================================================================
    # 4. PLATFORM TWEAK DIALOG
    # =========================================================================

    def open_tweak_platform_dialog(self) -> None:
        """Modal dialog to tweak candidate coordinates within party range."""
        if not self.player or not self.nation:
            return

        win = tk.Toplevel(self)
        win.title("Tweak Platform")
        win.geometry("450x320")
        win.transient(self)
        win.grab_set()

        frm = ttk.Frame(win, padding=15)
        frm.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frm, text="Tweak Your Platform", font=("Helvetica", 12, "bold")).pack(
            anchor=tk.W, pady=(0, 6)
        )
        p_name = self.nation.parties[self.player.party_index].name
        ttk.Label(
            frm,
            text=f"Party: {p_name} | Adjust coordinates within your party bounds:",
            font=("Helvetica", 10),
        ).pack(anchor=tk.W, pady=(0, 10))

        vars_list: list[tk.DoubleVar] = []
        party_plat = self.nation.parties[self.player.party_index].platform

        for i, issue_name in enumerate(self.nation.issues):
            row = ttk.Frame(frm)
            row.pack(fill=tk.X, pady=6)

            p_side = party_plat[i]
            low, high = (0.01, 0.49) if p_side < MID_POS else (0.51, 0.99)
            side_str = "Conservative" if p_side < MID_POS else "Liberal"

            ttk.Label(row, text=f"{issue_name} ({side_str}):", width=22).pack(side=tk.LEFT)
            v = tk.DoubleVar(value=self.player.platform[i])
            vars_list.append(v)

            sp = ttk.Spinbox(
                row,
                from_=low,
                to=high,
                increment=0.01,
                textvariable=v,
                width=6,
                format="%.2f",
            )
            sp.pack(side=tk.LEFT, padx=10)
            ttk.Label(row, text=f"[{low:.2f} - {high:.2f}]", font=("Helvetica", 9, "italic")).pack(
                side=tk.LEFT
            )

        btn_row = ttk.Frame(frm)
        btn_row.pack(fill=tk.X, pady=20)

        def on_save() -> None:
            new_plat = [round(v.get(), 2) for v in vars_list]
            for i, val in enumerate(new_plat):
                p_side = party_plat[i]
                if p_side < MID_POS and not (0.01 <= val <= 0.49):
                    messagebox.showwarning("Out of Bounds", f"Value {val} must be in [0.01, 0.49].")
                    return
                if p_side > MID_POS and not (0.51 <= val <= 0.99):
                    messagebox.showwarning("Out of Bounds", f"Value {val} must be in [0.51, 0.99].")
                    return
            assert self.player is not None
            self.player.platform = new_plat
            self.update_hq_view()
            self.log_message(f"Platform updated to {[round(x, 2) for x in new_plat]}.")
            win.destroy()

        ttk.Button(btn_row, text="Cancel", command=win.destroy).pack(side=tk.LEFT)
        ttk.Button(btn_row, text="Save Platform", command=on_save).pack(side=tk.RIGHT)

    # =========================================================================
    # 5. END SCREENS: TRY AGAIN (LOSE) & WIN
    # =========================================================================

    def show_lose_screen(self, reason: str) -> None:
        """Screen: Dedicated encouraging 'try again' screen."""
        self._clear_container()

        frame = ttk.Frame(self.container, padding=40)
        frame.pack(fill=tk.BOTH, expand=True)

        lbl_head = ttk.Label(
            frame,
            text="CAMPAIGN CONCLUDED",
            style="Title.TLabel",
            foreground="#D32F2F",
            anchor="center",
        )
        lbl_head.pack(pady=(20, 15))

        lbl_reason = ttk.Label(
            frame,
            text=reason,
            font=("Helvetica", 13, "bold"),
            foreground="#333333",
            justify="center",
            anchor="center",
            wraplength=600,
        )
        lbl_reason.pack(pady=(0, 20))

        encourage_card = ttk.LabelFrame(frame, text=" A Message for the Candidate ", padding=20)
        encourage_card.pack(fill=tk.X, padx=40, pady=10)

        msg = (
            "Don't give up! Even the most storied political careers have their setbacks.\n"
            "Abraham Lincoln, Franklin D. Roosevelt, and Winston Churchill all suffered major defeats.\n"
            "Take the lessons learned, refine your ideological platform, and launch a new campaign!"
        )
        ttk.Label(
            encourage_card,
            text=msg,
            font=("Helvetica", 11, "italic"),
            justify="center",
        ).pack(anchor="center")

        stats_card = ttk.Frame(frame, padding=15)
        stats_card.pack(fill=tk.X, padx=40, pady=10)

        career_c = (self.current_cycle - self.start_cycle) if self.player else 0
        p_name = self.player.name if self.player else "Candidate"
        highest_office = (
            OFFICE_NAMES.get(self.player.current_tier, "City Council Candidate")
            if (self.player and self.player.current_tier)
            else "City Council Candidate"
        )
        ttk.Label(
            stats_card,
            text=(
                f"Candidate: {p_name} | Highest Office: {highest_office}\n"
                f"Career Duration: {career_c} cycles ({career_c * YEARS_PER_CYCLE} years)"
            ),
            font=("Helvetica", 11),
            justify="center",
        ).pack(anchor="center")

        btn_row = ttk.Frame(frame)
        btn_row.pack(pady=25)

        self.btn_cache = ttk.Button(
            btn_row,
            text="Cache / Save Data to results/",
            command=self.cache_game_data,
        )
        self.btn_cache.pack(side=tk.LEFT, padx=10, ipady=4)

        ttk.Button(
            btn_row,
            text="Restart (Try Again)",
            command=self.confirm_restart,
        ).pack(side=tk.LEFT, padx=10, ipady=4)

        ttk.Button(
            btn_row,
            text="Quit Game",
            command=self.confirm_quit,
        ).pack(side=tk.LEFT, padx=10, ipady=4)

    def show_win_screen(self) -> None:
        """Screen: Dedicated presidential victory celebration."""
        self._clear_container()

        frame = ttk.Frame(self.container, padding=40)
        frame.pack(fill=tk.BOTH, expand=True)

        lbl_head = ttk.Label(
            frame,
            text="PRESIDENTIAL VICTORY!",
            style="Title.TLabel",
            foreground="#2E7D32",
            anchor="center",
        )
        lbl_head.pack(pady=(20, 15))

        p_name = self.player.name if self.player else "Candidate"
        n_name = self.nation.name if self.nation else "the nation"
        career_c = (self.current_cycle - self.start_cycle + 1) if self.player else 0

        lbl_sub = ttk.Label(
            frame,
            text=(
                f"Congratulations, President {p_name}!\n"
                f"You have reached the pinnacle of political power and been elected President of {n_name}!\n"
                f"You accomplished this career goal in {career_c} cycles ({career_c * YEARS_PER_CYCLE} years)."
            ),
            font=("Helvetica", 13),
            justify="center",
            anchor="center",
        )
        lbl_sub.pack(pady=(0, 25))

        seal_card = ttk.LabelFrame(frame, text=" Certificate of Election ", padding=20)
        seal_card.pack(fill=tk.X, padx=40, pady=10)

        cert_text = (
            f"Be it known that {p_name}, having served with honor across local, state, and federal\n"
            f"offices, has secured the trust of the electorate of {n_name} and is duly sworn as\n"
            "Commander-in-Chief and President of the Republic."
        )
        ttk.Label(
            seal_card,
            text=cert_text,
            font=("Helvetica", 11, "italic"),
            justify="center",
        ).pack(anchor="center")

        btn_row = ttk.Frame(frame)
        btn_row.pack(pady=30)

        self.btn_cache = ttk.Button(
            btn_row,
            text="Cache / Save Data to results/",
            command=self.cache_game_data,
        )
        self.btn_cache.pack(side=tk.LEFT, padx=10, ipady=4)

        ttk.Button(
            btn_row,
            text="Restart New Career",
            command=self.confirm_restart,
        ).pack(side=tk.LEFT, padx=10, ipady=4)

        ttk.Button(
            btn_row,
            text="Quit Game",
            command=self.confirm_quit,
        ).pack(side=tk.LEFT, padx=10, ipady=4)

    def cache_game_data(self) -> None:
        """Cache results to timestamped folder in results/ and clear data/."""
        saved_dir = save_results(data_dir=self.data_dir, results_dir=self.results_dir)
        messagebox.showinfo(
            "Data Cached",
            f"Your election history and seniority rosters have been successfully cached to:\n{saved_dir}\n\nData folder has been cleared.",
        )
        if hasattr(self, "btn_cache"):
            self.btn_cache.config(state=tk.DISABLED)

    def confirm_quit(self) -> None:
        """Prompt confirmation before quitting cleanly."""
        ans = messagebox.askyesno(
            "Quit Simulation",
            "Are you sure you want to quit?\nUnsaved data in data/ will be wiped.",
        )
        if ans:
            wipe_data(self.data_dir)
            self.destroy()

    def confirm_restart(self) -> None:
        """Prompt confirmation before wiping data and restarting setup."""
        ans = messagebox.askyesno(
            "Restart Simulation",
            "Are you sure you want to restart?\nCurrent progress will be wiped.",
        )
        if ans:
            wipe_data(self.data_dir)
            self.show_welcome_screen()


def launch_gui() -> None:
    """Launch the All Politics Is Local Tkinter GUI."""
    app = AllPoliticsApp()
    app.mainloop()


if __name__ == "__main__":
    launch_gui()
