"""Interactive game runner and CLI driver for All Politics Is Local."""

import os
import random
from typing import Callable, Optional

import numpy as np

from constants import (
    CAREER_MAX_CYCLES,
    CITIES_PER_STATE,
    DATA_DIR,
    DISTRICTS_PER_CITY,
    HISTORICAL_DATA_FILE,
    LIVE_SCOPE_TITLES,
    MAX_HISTORICAL_CYCLES,
    MAX_ISSUES,
    MAX_POS,
    MID_POS,
    MIN_ISSUES,
    MIN_POS,
    NUM_STATES,
    OFFICE_NAMES,
    RESULTS_DIR,
    SENIORITY_FILE,
    SUGGESTED_ISSUES,
    TERM_LENGTH_CYCLES,
    TERM_LIMITS,
    TIER_PRESIDENT,
    WAVE_LABELS,
    YEARS_PER_CYCLE,
)
from custom_types import (
    Candidate,
    Nation,
    PlayerProfile,
    PositionVector,
    QuitGame,
    RestartGame,
)
from data_tracker import (
    NameManager,
    SeniorityTracker,
    append_historical_row,
    build_historical_row,
    get_candidate_cycles,
    get_higher_office_seat,
    get_max_cycles_for_tier,
    get_seat_population_position,
    is_player_up_for_reelection,
    load_in_party_names,
    load_out_party_names,
    load_party_names,
    run_historical_simulation,
    save_results,
    wipe_data,
)
from reporter import (
    report_historical_summary,
    run_live_elections,
    run_live_primary_race,
)
from simulator import (
    build_nation,
    find_party_for_platform,
    format_seat_label,
    get_seat_districts,
    is_valid_candidate_coordinate,
    platform_matches_party,
    run_default_election,
    sample_candidate_platform,
)


def make_prompt_fn(
    raw_input_fn: Callable[[str], str] = input,
    data_dir: str = DATA_DIR,
) -> Callable[[str], str]:
    """Wrap input reading with global Q/q (quit) and R/r (restart) hotkeys."""

    def prompt(text: str) -> str:
        response = raw_input_fn(text).strip()
        lowered = response.lower()
        if lowered == "q":
            wipe_data(data_dir)
            raise QuitGame("User requested quit.")
        if lowered == "r":
            wipe_data(data_dir)
            raise RestartGame("User requested restart.")
        return response

    return prompt


def _prompt_nonempty(
    prompt_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
    message: str,
) -> str:
    """Prompt until a non-empty string is entered."""
    while True:
        val = prompt_fn(message)
        if val:
            return val
        output_fn("Input cannot be empty. Please try again.")


def _prompt_int(
    prompt_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
    message: str,
    low: int,
    high: int,
    default: Optional[int] = None,
) -> int:
    """Prompt until an integer in [low, high] is entered (or default on blank)."""
    while True:
        raw = prompt_fn(message)
        if not raw and default is not None:
            return default
        try:
            num = int(raw)
        except ValueError:
            output_fn(f"Please enter an integer between {low} and {high}.")
            continue
        if low <= num <= high:
            return num
        output_fn(f"Value must be between {low} and {high}.")


def _prompt_yes_no(
    prompt_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
    message: str,
    default: Optional[bool] = None,
) -> bool:
    """Prompt until y/yes or n/no is entered (or default on blank)."""
    while True:
        raw = prompt_fn(message).strip().lower()
        if not raw and default is not None:
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        output_fn("Please enter 'y' or 'n'.")


def prompt_nation_setup(
    prompt_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
    party_names: list[str],
    rng: Optional[random.Random] = None,
) -> Nation:
    """Interactive setup for nation name, up to 3 issues, and geography generation."""
    output_fn("\n=== ALL POLITICS IS LOCAL ===")
    output_fn("Global Hotkeys (usable at any prompt): Q = Quit | R = Restart")
    nation_name = _prompt_nonempty(
        prompt_fn, output_fn, "\nEnter a name for your nation: "
    )

    num_issues = _prompt_int(
        prompt_fn,
        output_fn,
        f"How many political issues to simulate ({MIN_ISSUES}-{MAX_ISSUES})? ",
        MIN_ISSUES,
        MAX_ISSUES,
    )

    output_fn("\nSuggested Issues (or type your own custom issue name):")
    for idx, issue_name in enumerate(SUGGESTED_ISSUES, start=1):
        output_fn(f"  {idx}. {issue_name}")

    chosen_issues: list[str] = []
    for i in range(1, num_issues + 1):
        while True:
            raw = _prompt_nonempty(
                prompt_fn,
                output_fn,
                f"Issue {i}/{num_issues} (enter 1-{len(SUGGESTED_ISSUES)} or custom name): ",
            )
            if raw.isdigit():
                idx = int(raw)
                if 1 <= idx <= len(SUGGESTED_ISSUES):
                    candidate_issue = SUGGESTED_ISSUES[idx - 1]
                else:
                    output_fn(f"Number must be between 1 and {len(SUGGESTED_ISSUES)}.")
                    continue
            else:
                candidate_issue = raw

            if candidate_issue in chosen_issues:
                output_fn("Issue already selected. Choose a different issue.")
                continue
            chosen_issues.append(candidate_issue)
            break

    output_fn("\nGenerating nation, 50 states, 500 cities, and 20,000 districts...")
    return build_nation(nation_name, chosen_issues, party_names, rng=rng)


def prompt_location_setup(
    prompt_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
    nation: Nation,
) -> tuple[str, int, int, int]:
    """Prompt candidate name and home state, city, and district."""
    player_name = _prompt_nonempty(
        prompt_fn, output_fn, "\nEnter your candidate name: "
    )

    output_fn("\n--- States Position Vectors ---")
    for state in nation.states:
        wave_lbl = WAVE_LABELS[state.wave]
        output_fn(
            f"  State {state.index + 1:>2} (Wave {wave_lbl}): {state.position}"
        )
    home_state = (
        _prompt_int(
            prompt_fn,
            output_fn,
            f"Choose your home state (1-{NUM_STATES}): ",
            1,
            NUM_STATES,
        )
        - 1
    )

    selected_state = nation.states[home_state]
    output_fn(f"\n--- Cities in State {home_state + 1} ---")
    for city in selected_state.cities:
        output_fn(f"  City {city.index + 1:>2}: {city.position}")
    home_city = (
        _prompt_int(
            prompt_fn,
            output_fn,
            f"Choose your home city (1-{CITIES_PER_STATE}): ",
            1,
            CITIES_PER_STATE,
        )
        - 1
    )

    selected_city = selected_state.cities[home_city]
    output_fn(f"\n--- Districts in State {home_state + 1}, City {home_city + 1} ---")
    for dist in selected_city.districts:
        output_fn(f"  District {dist.index + 1:>2}: {dist.position}")
    home_district = (
        _prompt_int(
            prompt_fn,
            output_fn,
            f"Choose your home district (1-{DISTRICTS_PER_CITY}): ",
            1,
            DISTRICTS_PER_CITY,
        )
        - 1
    )

    return player_name, home_state, home_city, home_district


def prompt_initial_platform(
    prompt_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
    nation: Nation,
    home_state: int,
    home_city: int,
    home_district: int,
) -> tuple[PositionVector, int]:
    """Prompt the player's initial ideology vector and determine their party."""
    hs = nation.states[home_state]
    hc = hs.cities[home_city]
    hd = hc.districts[home_district]

    output_fn("\n=== PLATFORM & PARTY SELECTION ===")
    output_fn("Reference Position Vectors:")
    output_fn(f"  Nation:   {nation.position}")
    output_fn(f"  State {home_state + 1}:  {hs.position}")
    output_fn(f"  City {home_city + 1}:   {hc.position}")
    output_fn(f"  District {home_district + 1}: {hd.position}")
    output_fn("\nAvailable Parties:")
    for party in nation.parties:
        output_fn(f"  [{party.index}] {party.name}: {party.platform}")

    output_fn(
        "\nEnter your position on each issue (0.01-0.49 conservative, 0.51-0.99 liberal):"
    )
    platform: PositionVector = []
    for issue in nation.issues:
        while True:
            raw = prompt_fn(f"  {issue} (0.01-0.49 or 0.51-0.99): ")
            try:
                val = float(raw)
            except ValueError:
                output_fn("Please enter a decimal number like 0.25 or 0.75.")
                continue
            if not is_valid_candidate_coordinate(val):
                output_fn(
                    f"Value must be in [{MIN_POS}, 0.49] or [0.51, {MAX_POS}] in 0.01 increments (0.50 not allowed)."
                )
                continue
            platform.append(round(val, 2))
            break

    party_idx = find_party_for_platform(platform, nation.parties)
    output_fn(
        f"\nYou joined {nation.parties[party_idx].name} (Party {party_idx}). "
        "You cannot change parties later."
    )
    return platform, party_idx


def prompt_tweak_platform(
    prompt_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
    nation: Nation,
    player: PlayerProfile,
) -> None:
    """Allow player to adjust their position vector within their party's ideological bounds."""
    party = nation.parties[player.party_index]
    output_fn(
        f"\nYour current platform: {player.platform} (Party: {party.name} {party.platform})"
    )
    if not _prompt_yes_no(
        prompt_fn,
        output_fn,
        "Would you like to tweak your platform before this election? (y/n): ",
    ):
        return

    new_platform: PositionVector = []
    for idx, issue in enumerate(nation.issues):
        party_val = party.platform[idx]
        low, high = (MIN_POS, 0.49) if party_val < MID_POS else (0.51, MAX_POS)
        while True:
            raw = prompt_fn(
                f"  {issue} (current {player.platform[idx]:.2f}, range {low:.2f}-{high:.2f}, Enter to keep): "
            )
            if not raw:
                new_platform.append(player.platform[idx])
                break
            try:
                val = float(raw)
            except ValueError:
                output_fn("Please enter a valid decimal number.")
                continue
            candidate_vec = [round(val, 2)]
            if not platform_matches_party(candidate_vec, [party_val]):
                output_fn(
                    f"Value must remain within your party's range [{low:.2f}, {high:.2f}] in 0.01 steps."
                )
                continue
            new_platform.append(round(val, 2))
            break

    player.platform = new_platform
    output_fn(f"Updated platform: {player.platform}")


def run_single_game(
    raw_input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
    data_dir: str = DATA_DIR,
    results_dir: str = RESULTS_DIR,
    rng: Optional[random.Random] = None,
    np_rng: Optional[np.random.Generator] = None,
) -> str:
    """Run one complete playthrough and return outcome ('won', 'lost_election', 'lost_timeout')."""
    rng = rng or random.Random()
    if np_rng is None:
        np_rng = np.random.default_rng(rng.randrange(0, 2**32))

    wipe_data(data_dir)
    prompt_fn = make_prompt_fn(raw_input_fn=raw_input_fn, data_dir=data_dir)

    party_names = load_party_names()
    in_party_names = load_in_party_names()
    out_party_names = load_out_party_names()

    nation = prompt_nation_setup(prompt_fn, output_fn, party_names, rng=rng)
    player_name, home_state, home_city, home_district = prompt_location_setup(
        prompt_fn, output_fn, nation
    )

    historical_filepath = os.path.join(data_dir, os.path.basename(HISTORICAL_DATA_FILE))
    seniority_filepath = os.path.join(data_dir, os.path.basename(SENIORITY_FILE))

    num_historical_cycles = 0
    if _prompt_yes_no(
        prompt_fn,
        output_fn,
        "\nWould you like to simulate prior historical election data? (y/n): ",
    ):
        num_historical_cycles = _prompt_int(
            prompt_fn,
            output_fn,
            f"How many cycles to simulate (1-{MAX_HISTORICAL_CYCLES})? [default {MAX_HISTORICAL_CYCLES}]: ",
            1,
            MAX_HISTORICAL_CYCLES,
            default=MAX_HISTORICAL_CYCLES,
        )

    historical_rows, streaks = run_historical_simulation(
        nation=nation,
        home_state=home_state,
        home_city=home_city,
        home_district=home_district,
        num_cycles=num_historical_cycles,
        filepath=historical_filepath,
        rng=rng,
    )
    if num_historical_cycles > 0:
        report_historical_summary(historical_rows, nation.parties, output_fn=output_fn)
        output_fn(f"\nHistorical data saved to {historical_filepath}")

    player_platform, player_party = prompt_initial_platform(
        prompt_fn, output_fn, nation, home_state, home_city, home_district
    )
    player = PlayerProfile(
        name=player_name,
        home_state=home_state,
        home_city=home_city,
        home_district=home_district,
        party_index=player_party,
        platform=player_platform,
    )

    name_manager = NameManager(
        in_party_names=in_party_names,
        out_party_names=out_party_names,
        player_name=player_name,
        rng=rng,
    )
    seniority_tracker = SeniorityTracker(filepath=seniority_filepath)
    seniority_tracker.initialize_starting_roster(
        nation=nation,
        home_state=home_state,
        home_city=home_city,
        player_party=player_party,
        name_manager=name_manager,
        historical_rows=historical_rows,
        streaks=streaks,
        rng=rng,
    )
    output_fn(f"Initial seniority roster saved to {seniority_filepath}")

    start_cycle = num_historical_cycles + 1
    end_cycle = num_historical_cycles + CAREER_MAX_CYCLES
    party_platforms = [p.platform for p in nation.parties]
    outcome = "lost_timeout"

    for cycle in range(start_cycle, end_cycle + 1):
        career_num = cycle - start_cycle + 1
        output_fn(
            f"\n========================================\n"
            f"CYCLE {cycle} (Year {cycle * YEARS_PER_CYCLE}, Career Cycle {career_num}/{CAREER_MAX_CYCLES})"
        )

        assignments, player_assignment = seniority_tracker.resolve_cycle_assignments(
            cycle=cycle, nation=nation, player=player
        )

        player_was_promoted = (
            player_assignment is not None and player_assignment.is_promotion
        )
        is_term_limited = False
        if player.current_tier is not None:
            max_cyc = get_max_cycles_for_tier(player.current_tier)
            cyc_count = 0
            if player.current_seat in seniority_tracker.roster:
                cyc_count = get_candidate_cycles(
                    seniority_tracker.roster[player.current_seat]
                )
            elif player.current_seat in seniority_tracker.seat_streaks:
                streak_p, streak_c = seniority_tracker.seat_streaks[player.current_seat]
                if streak_p == player.party_index:
                    cyc_count = streak_c
            if cyc_count >= max_cyc:
                is_term_limited = True

        is_up_for_reelection = (
            is_player_up_for_reelection(player, cycle, nation) or is_term_limited
        )
        player_in_general_no_stakes = False
        issued_primary_challenge = False
        faced_retaliatory_primary = False

        higher_sk = get_higher_office_seat(player, cycle, nation)
        can_issue_primary = (
            player.current_tier is not None
            and not player_was_promoted
            and not player.pending_party_challenge
            and higher_sk is not None
        )
        target_nominee = None
        if can_issue_primary and higher_sk is not None:
            higher_assign = assignments.get(higher_sk)
            if higher_assign is not None and higher_assign.candidate is not None:
                if not higher_assign.candidate.is_player:
                    target_nominee = higher_assign.candidate
                else:
                    can_issue_primary = False
            else:
                can_issue_primary = False

        if can_issue_primary and target_nominee is not None and higher_sk is not None:
            has_stakes = is_up_for_reelection
            output_fn(
                f"\nYou were not selected to advance to {format_seat_label(higher_sk)}."
            )
            output_fn(
                f"{target_nominee.name} is currently assigned by your party to run for this seat."
            )
            if has_stakes:
                output_fn(
                    "STAKES: You are up for re-election (or term-limited). If you challenge and lose, you will be eliminated from the game!"
                )
            else:
                output_fn(
                    "NO STAKES: You are not up for re-election this cycle. If you challenge and lose, you retain your current office."
                )

            want_challenge = _prompt_yes_no(
                prompt_fn,
                output_fn,
                f"Would you like to issue a primary challenge against {target_nominee.name} for {format_seat_label(higher_sk)}? (y/n): ",
                default=False,
            )
            if want_challenge:
                issued_primary_challenge = True
                player.pending_party_challenge = True
                prompt_tweak_platform(prompt_fn, output_fn, nation, player)
                player_cand = Candidate(
                    name=player.name,
                    party_index=player.party_index,
                    platform=list(player.platform),
                    tier=higher_sk[0],
                    seat_id=higher_sk,
                    seniority=0,
                    victory_size=0.0,
                    is_player=True,
                )
                winner_cand, win_pct = run_live_primary_race(
                    seat_key=higher_sk,
                    tier=higher_sk[0],
                    label=format_seat_label(higher_sk),
                    districts=get_seat_districts(higher_sk, nation),
                    player_cand=player_cand,
                    opponent_cand=target_nominee,
                    party=nation.parties[player.party_index],
                    input_fn=prompt_fn,
                    output_fn=output_fn,
                    rng=rng,
                    np_rng=np_rng,
                )
                if winner_cand.is_player:
                    output_fn(
                        f"\nPRIMARY VICTORY: You defeated {target_nominee.name} with {win_pct:.2f}% of the vote! "
                        f"You are now the nominee for {format_seat_label(higher_sk)}!"
                    )
                    higher_assign = assignments[higher_sk]
                    higher_assign.candidate = player_cand
                    higher_assign.is_promotion = True
                    player_assignment = higher_assign
                    player_in_general_no_stakes = not has_stakes
                    if (
                        has_stakes
                        and player.current_seat is not None
                        and player.current_seat in assignments
                    ):
                        old_assign = assignments[player.current_seat]
                        if (
                            old_assign.candidate is not None
                            and old_assign.candidate.is_player
                        ):
                            old_assign.candidate = None
                            old_assign.is_reelection = False
                else:
                    output_fn(
                        f"\nPRIMARY DEFEAT: You were defeated by {target_nominee.name} with {win_pct:.2f}% of the vote."
                    )
                    if has_stakes:
                        output_fn(
                            f"\nDEFEAT: You lost the primary challenge while up for re-election. Game Over!"
                        )
                        outcome = "lost_election"
                        break
                    else:
                        output_fn(
                            f"\nYou retain your current office as {OFFICE_NAMES[player.current_tier]}. You will watch the general election."
                        )
                        player_assignment = None

        if (
            not issued_primary_challenge
            and player_assignment is not None
            and player.pending_party_challenge
        ):
            faced_retaliatory_primary = True
            output_fn(f"\n=== RETALIATORY PRIMARY CHALLENGE ===")
            output_fn(
                f"Because you defied your party manager with a prior primary challenge, "
                f"the party manager has entered a challenger against you for {format_seat_label(player_assignment.seat_key)}!"
            )
            chal_name = name_manager.draw_in_party_name(seniority_tracker.active_names())
            chal_plat = sample_candidate_platform(
                nation.parties[player.party_index].platform, rng=rng
            )
            chal_cand = Candidate(
                name=chal_name,
                party_index=player.party_index,
                platform=chal_plat,
                tier=player_assignment.tier,
                seat_id=player_assignment.seat_key,
                is_player=False,
            )
            prompt_tweak_platform(prompt_fn, output_fn, nation, player)
            if player_assignment.candidate is not None:
                player_assignment.candidate.platform = list(player.platform)

            winner_cand, win_pct = run_live_primary_race(
                seat_key=player_assignment.seat_key,
                tier=player_assignment.tier,
                label=format_seat_label(player_assignment.seat_key),
                districts=get_seat_districts(player_assignment.seat_key, nation),
                player_cand=player_assignment.candidate,
                opponent_cand=chal_cand,
                party=nation.parties[player.party_index],
                input_fn=prompt_fn,
                output_fn=output_fn,
                rng=rng,
                np_rng=np_rng,
            )
            if winner_cand.is_player:
                output_fn(
                    f"\nPRIMARY VICTORY: You survived the retaliatory primary challenge against {chal_name} with {win_pct:.2f}%!"
                )
                player.pending_party_challenge = False
            else:
                output_fn(
                    f"\nDEFEAT: You lost the primary challenge to {chal_name} ({win_pct:.2f}%). Game Over!"
                )
                outcome = "lost_election"
                break

        if player_assignment is None and is_term_limited:
            output_fn(
                f"\nDEFEAT: You reached your term limit as {OFFICE_NAMES[player.current_tier]} "
                "and were not able to advance to higher office. Game Over!"
            )
            outcome = "lost_election"
            break

        if player_assignment is not None:
            live_tier = player_assignment.tier
            if not issued_primary_challenge and not faced_retaliatory_primary:
                action_word = (
                    "advanced to run for"
                    if player_assignment.is_promotion
                    else (
                        "running for reelection for"
                        if player_assignment.is_reelection
                        else "running for"
                    )
                )
                output_fn(
                    f"You are {action_word} {format_seat_label(player_assignment.seat_key)}!"
                )
                prompt_tweak_platform(prompt_fn, output_fn, nation, player)
                if player_assignment.candidate is not None:
                    player_assignment.candidate.platform = list(player.platform)
        else:
            assert player.current_tier is not None
            live_tier = player.current_tier
            output_fn(
                f"You are not up for election this cycle (currently {OFFICE_NAMES[player.current_tier]})."
            )
            output_fn(f"Live coverage: {LIVE_SCOPE_TITLES[live_tier]}")

        live_races = seniority_tracker.build_live_races(
            live_tier=live_tier,
            cycle=cycle,
            nation=nation,
            player=player,
            assignments=assignments,
            name_manager=name_manager,
            rng=rng,
        )
        live_outcomes, _ = run_live_elections(
            races=live_races,
            parties=nation.parties,
            player_party=player.party_index,
            input_fn=prompt_fn,
            output_fn=output_fn,
            rng=rng,
            np_rng=np_rng,
        )

        default_outcomes: dict = {}
        num_parties = len(nation.parties)
        for sk, assignment in assignments.items():
            if sk in live_outcomes:
                continue
            pop_pos = get_seat_population_position(nation, sk)
            inc_party, inc_cycles_val = seniority_tracker.get_incumbent_grudge(
                sk, assignment, player.party_index
            )
            inc_cycles = [
                inc_cycles_val if (p == inc_party and inc_cycles_val > 0) else 0
                for p in range(num_parties)
            ]
            winner = run_default_election(
                pop_pos,
                party_platforms,
                rng=rng,
                incumbent_cycles=inc_cycles,
            )
            default_outcomes[sk] = (winner, 0.0)

        all_outcomes = {**default_outcomes, **live_outcomes}

        # Check player's election outcome BEFORE updating roster/history
        player_lost = False
        player_won_presidency = False
        if player_assignment is not None:
            win_party, win_pct = all_outcomes[player_assignment.seat_key]
            if win_party != player.party_index:
                if player_in_general_no_stakes:
                    output_fn(
                        f"\nYou lost the general election for {format_seat_label(player_assignment.seat_key)} ({win_pct:.2f}%). "
                        f"However, since you were not up for re-election as {OFFICE_NAMES[player.current_tier]}, you retain your current office!"
                    )
                    player_lost = False
                else:
                    player_lost = True
            elif player_assignment.tier == TIER_PRESIDENT:
                player_won_presidency = True

        seniority_tracker.apply_cycle_outcomes(
            cycle=cycle,
            nation=nation,
            player=player,
            assignments=assignments,
            outcomes=all_outcomes,
            name_manager=name_manager,
            rng=rng,
        )
        hist_row = build_historical_row(
            cycle, nation, home_state, home_city, home_district
        )
        append_historical_row(hist_row, filepath=historical_filepath)

        if player_lost:
            output_fn(
                f"\nDEFEAT: You lost the election for {format_seat_label(player_assignment.seat_key)}. Game Over!"
            )
            outcome = "lost_election"
            break

        if player_won_presidency:
            output_fn(
                f"\nVICTORY! Congratulations {player.name}, you have been elected President of {nation.name}!"
            )
            outcome = "won"
            break
    else:
        output_fn(
            f"\nTIME LIMIT REACHED: {CAREER_MAX_CYCLES} cycles ({CAREER_MAX_CYCLES * YEARS_PER_CYCLE} years) "
            "elapsed without winning the Presidency. Game Over!"
        )

    if _prompt_yes_no(
        prompt_fn,
        output_fn,
        "\nWould you like to save the simulation spreadsheets to results/? (y/n): ",
    ):
        saved_dir = save_results(data_dir=data_dir, results_dir=results_dir)
        output_fn(f"Results saved to {saved_dir}. Data folder cleared.")
    else:
        wipe_data(data_dir)
        output_fn("Results discarded. Data folder cleared.")

    return outcome


def main(
    raw_input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
    data_dir: str = DATA_DIR,
    results_dir: str = RESULTS_DIR,
) -> Optional[str]:
    """Top-level driver loop supporting global Restart (R) and Quit (Q) hotkeys."""
    while True:
        try:
            return run_single_game(
                raw_input_fn=raw_input_fn,
                output_fn=output_fn,
                data_dir=data_dir,
                results_dir=results_dir,
            )
        except RestartGame:
            output_fn("\nRestarting game... Data folder wiped.")
            continue
        except QuitGame:
            output_fn("\nExiting game. Data folder wiped. Goodbye!")
            return None


if __name__ == "__main__":
    main()

