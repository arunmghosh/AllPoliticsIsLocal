"""Name management, seniority/vacancy tracking, and Excel data storage."""

from datetime import datetime
import os
import random
import shutil
from typing import Optional

from openpyxl import Workbook, load_workbook

from constants import (
    ALL_TIERS,
    CITIES_PER_STATE,
    DATA_DIR,
    DISTRICTS_PER_CITY,
    HISTORICAL_DATA_FILE,
    HISTORICAL_HEADERS,
    IN_PARTY_FILE,
    NUM_STATES,
    OUT_PARTIES_FILE,
    PARTIES_FILE,
    RESULTS_DIR,
    SENATORS_PER_STATE,
    SENIORITY_FILE,
    SENIORITY_HEADERS,
    TIER_CITY_COUNCIL,
    TIER_GOVERNOR,
    TIER_HOUSE,
    TIER_MAYOR,
    TIER_PRESIDENT,
    TIER_SENATOR,
    TIER_STATE_LEG,
    YEARS_PER_CYCLE,
)
from custom_types import (
    Candidate,
    ElectionAssignment,
    LiveRaceSpec,
    Nation,
    PlayerProfile,
    SeatKey,
)
from simulator import (
    format_seat_label,
    get_seat_districts,
    get_seat_wave,
    is_election_cycle,
    run_default_election,
    sample_candidate_platform,
)


def load_name_list(filepath: str) -> list[str]:
    """Load non-empty stripped lines from a text file."""
    with open(filepath, "r", encoding="utf-8") as handle:
        return [line.strip() for line in handle if line.strip()]


def load_party_names(filepath: str = PARTIES_FILE) -> list[str]:
    """Load party names from names/parties.txt."""
    return load_name_list(filepath)


def load_in_party_names(filepath: str = IN_PARTY_FILE) -> list[str]:
    """Load in-party candidate names from names/in_party.txt."""
    return load_name_list(filepath)


def load_out_party_names(filepath: str = OUT_PARTIES_FILE) -> list[str]:
    """Load opposing-party candidate names from names/out_parties.txt."""
    return load_name_list(filepath)


class NameManager:
    """Manages shuffled sequential candidate name drawing and in-party recycling."""

    def __init__(
        self,
        in_party_names: list[str],
        out_party_names: list[str],
        player_name: str = "",
        rng: Optional[random.Random] = None,
    ) -> None:
        if not in_party_names:
            raise ValueError("in_party_names cannot be empty.")
        if not out_party_names:
            raise ValueError("out_party_names cannot be empty.")
        self.rng = rng or random.Random()
        self.player_name = player_name.strip()

        self.in_party_pool = list(in_party_names)
        self.out_party_pool = list(out_party_names)
        self.rng.shuffle(self.in_party_pool)
        self.rng.shuffle(self.out_party_pool)

        self.in_ptr = 0
        self.in_suffix = 1
        self.out_ptr = 0

    def draw_in_party_name(self, active_names: Optional[set[str]] = None) -> str:
        """Draw the next in-party name, recycling with numeric suffix 2, 3, ... on wrap."""
        blocked = set(active_names or ())
        if self.player_name:
            blocked.add(self.player_name)

        max_attempts = len(self.in_party_pool) * 10
        for _ in range(max_attempts):
            base = self.in_party_pool[self.in_ptr]
            suffix = self.in_suffix
            self.in_ptr += 1
            if self.in_ptr >= len(self.in_party_pool):
                self.in_ptr = 0
                self.in_suffix += 1
            candidate_name = base if suffix == 1 else f"{base} {suffix}"
            if candidate_name not in blocked:
                return candidate_name
        raise RuntimeError("Unable to draw a unique in-party candidate name.")

    def draw_out_party_name(self, active_names: Optional[set[str]] = None) -> str:
        """Draw the next opposing-party name sequentially without recycling."""
        blocked = set(active_names or ())
        if self.player_name:
            blocked.add(self.player_name)

        while self.out_ptr < len(self.out_party_pool):
            candidate_name = self.out_party_pool[self.out_ptr]
            self.out_ptr += 1
            if candidate_name not in blocked:
                return candidate_name
        raise RuntimeError("Exhausted opposing-party names pool.")


def write_historical_data(
    rows: list[dict], filepath: str = HISTORICAL_DATA_FILE
) -> None:
    """Write historical election cycle rows to historical_data.xlsx."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "Historical Data"
    ws.append(HISTORICAL_HEADERS)
    for row in rows:
        ws.append([row[col] for col in HISTORICAL_HEADERS])
    wb.save(filepath)


def append_historical_row(row: dict, filepath: str = HISTORICAL_DATA_FILE) -> None:
    """Append a single cycle row to historical_data.xlsx (creating if absent)."""
    if not os.path.exists(filepath):
        write_historical_data([row], filepath=filepath)
        return
    wb = load_workbook(filepath)
    ws = wb.active
    ws.append([row[col] for col in HISTORICAL_HEADERS])
    wb.save(filepath)


def read_historical_data(filepath: str = HISTORICAL_DATA_FILE) -> list[dict]:
    """Read historical_data.xlsx rows as a list of dictionaries keyed by header."""
    if not os.path.exists(filepath):
        return []
    wb = load_workbook(filepath, data_only=True)
    ws = wb.active
    iterator = ws.iter_rows(values_only=True)
    try:
        headers = list(next(iterator))
    except StopIteration:
        return []
    rows: list[dict] = []
    for values in iterator:
        if all(v is None for v in values):
            continue
        rows.append(dict(zip(headers, values)))
    return rows


def count_consecutive_years(
    rows: list[dict], column: str, party_index: int
) -> int:
    """Count consecutive years (2 per cycle) ending now that party_index held column."""
    consecutive_cycles = 0
    for row in reversed(rows):
        if row.get(column) == party_index:
            consecutive_cycles += 1
        else:
            break
    return consecutive_cycles * YEARS_PER_CYCLE


def get_seat_party(nation: Nation, seat_key: SeatKey) -> Optional[int]:
    """Read the current incumbent party index for seat_key on nation."""
    tier, coords = seat_key
    if tier == TIER_PRESIDENT:
        return nation.president_party
    if tier == TIER_GOVERNOR:
        return nation.states[coords[0]].governor_party
    if tier == TIER_SENATOR:
        return nation.states[coords[0]].senator_parties[coords[1]]
    if tier == TIER_HOUSE:
        return nation.states[coords[0]].cities[coords[1]].house_party
    if tier == TIER_MAYOR:
        return nation.states[coords[0]].cities[coords[1]].mayor_party
    if tier == TIER_STATE_LEG:
        return (
            nation.states[coords[0]]
            .cities[coords[1]]
            .districts[coords[2]]
            .state_leg_party
        )
    if tier == TIER_CITY_COUNCIL:
        return (
            nation.states[coords[0]]
            .cities[coords[1]]
            .districts[coords[2]]
            .city_council_party
        )
    raise ValueError(f"Unknown tier: {tier}")


def set_seat_party(
    nation: Nation, seat_key: SeatKey, party_index: int, cycle: Optional[int] = None
) -> None:
    """Update the incumbent party index for seat_key on nation."""
    tier, coords = seat_key
    if tier == TIER_PRESIDENT:
        nation.president_party = party_index
        if cycle is not None:
            nation.president_term_start_cycle = cycle
    elif tier == TIER_GOVERNOR:
        nation.states[coords[0]].governor_party = party_index
    elif tier == TIER_SENATOR:
        nation.states[coords[0]].senator_parties[coords[1]] = party_index
    elif tier == TIER_HOUSE:
        nation.states[coords[0]].cities[coords[1]].house_party = party_index
    elif tier == TIER_MAYOR:
        nation.states[coords[0]].cities[coords[1]].mayor_party = party_index
    elif tier == TIER_STATE_LEG:
        nation.states[coords[0]].cities[coords[1]].districts[
            coords[2]
        ].state_leg_party = party_index
    elif tier == TIER_CITY_COUNCIL:
        nation.states[coords[0]].cities[coords[1]].districts[
            coords[2]
        ].city_council_party = party_index
    else:
        raise ValueError(f"Unknown tier: {tier}")


def get_seat_population_position(nation: Nation, seat_key: SeatKey) -> list[float]:
    """Return the population position vector used for default-mode elections of seat_key."""
    tier, coords = seat_key
    if tier == TIER_PRESIDENT:
        return nation.position
    if tier in (TIER_GOVERNOR, TIER_SENATOR):
        return nation.states[coords[0]].position
    if tier in (TIER_HOUSE, TIER_MAYOR):
        return nation.states[coords[0]].cities[coords[1]].position
    if tier in (TIER_STATE_LEG, TIER_CITY_COUNCIL):
        return nation.states[coords[0]].cities[coords[1]].districts[coords[2]].position
    raise ValueError(f"Unknown tier: {tier}")


def get_historical_tracked_keys(
    home_state: int, home_city: int, home_district: int
) -> list[SeatKey]:
    """Return all seat keys tracked during historical simulation (301 seats total)."""
    keys: list[SeatKey] = [(TIER_PRESIDENT, ())]
    for s in range(NUM_STATES):
        keys.append((TIER_GOVERNOR, (s,)))
    for s in range(NUM_STATES):
        for w in range(SENATORS_PER_STATE):
            keys.append((TIER_SENATOR, (s, w)))
    for c in range(CITIES_PER_STATE):
        keys.append((TIER_HOUSE, (home_state, c)))
    for c in range(CITIES_PER_STATE):
        keys.append((TIER_MAYOR, (home_state, c)))
    for d in range(DISTRICTS_PER_CITY):
        keys.append((TIER_STATE_LEG, (home_state, home_city, d)))
    keys.append((TIER_CITY_COUNCIL, (home_state, home_city, home_district)))
    return keys


def build_historical_row(
    cycle: int, nation: Nation, home_state: int, home_city: int, home_district: int
) -> dict:
    """Construct a historical_data.xlsx row dictionary from current nation incumbents."""
    hs = nation.states[home_state]
    hc = hs.cities[home_city]
    hd = hc.districts[home_district]
    return {
        "Cycle": cycle,
        "President": nation.president_party,
        "Senator 1": hs.senator_parties[0],
        "Senator 2": hs.senator_parties[1],
        "Senator 3": hs.senator_parties[2],
        "House": hc.house_party,
        "Governor": hs.governor_party,
        "State Legislature": hd.state_leg_party,
        "Mayor": hc.mayor_party,
        "City Council": hd.city_council_party,
    }


def run_historical_simulation(
    nation: Nation,
    home_state: int,
    home_city: int,
    home_district: int,
    num_cycles: int,
    filepath: str = HISTORICAL_DATA_FILE,
    rng: Optional[random.Random] = None,
) -> tuple[list[dict], dict[SeatKey, tuple[Optional[int], int]]]:
    """Simulate 0..50 historical cycles, track streaks, and write historical_data.xlsx."""
    rng = rng or random.Random()
    party_platforms = [p.platform for p in nation.parties]
    tracked_keys = get_historical_tracked_keys(home_state, home_city, home_district)

    # Initialize Cycle 0 incumbents so non-Cycle-1 seats already have valid incumbents
    streaks: dict[SeatKey, tuple[Optional[int], int]] = {}
    for sk in tracked_keys:
        pop_pos = get_seat_population_position(nation, sk)
        winner = run_default_election(pop_pos, party_platforms, rng=rng)
        set_seat_party(nation, sk, winner, cycle=0)
        streaks[sk] = (winner, 0)

    rows: list[dict] = []
    num_parties = len(nation.parties)
    for cycle in range(1, num_cycles + 1):
        for sk in tracked_keys:
            tier = sk[0]
            wave = get_seat_wave(sk, nation)
            if is_election_cycle(tier, cycle, wave):
                pop_pos = get_seat_population_position(nation, sk)
                prev_party, prev_streak = streaks[sk]
                inc_cycles = [
                    prev_streak if (p == prev_party and prev_streak > 0) else 0
                    for p in range(num_parties)
                ]
                winner = run_default_election(
                    pop_pos,
                    party_platforms,
                    rng=rng,
                    incumbent_cycles=inc_cycles,
                )
                set_seat_party(nation, sk, winner, cycle=cycle)

            current_party = get_seat_party(nation, sk)
            prev_party, prev_streak = streaks[sk]
            if current_party == prev_party and prev_streak > 0:
                streaks[sk] = (current_party, prev_streak + 1)
            else:
                streaks[sk] = (current_party, 1)

        rows.append(
            build_historical_row(cycle, nation, home_state, home_city, home_district)
        )

    write_historical_data(rows, filepath=filepath)
    return rows, streaks


def write_seniority_data(
    candidates: list[Candidate], filepath: str = SENIORITY_FILE
) -> None:
    """Write the sorted in-party seniority roster to seniority.xlsx."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "Seniority"
    ws.append(SENIORITY_HEADERS)
    ordered = sorted(
        candidates,
        key=lambda c: (c.tier, -c.seniority, -c.victory_size, c.name),
    )
    for cand in ordered:
        ws.append([cand.name, cand.tier, cand.seniority, round(cand.victory_size, 2)])
    wb.save(filepath)


def read_seniority_data(filepath: str = SENIORITY_FILE) -> list[dict]:
    """Read seniority.xlsx rows as dictionaries keyed by SENIORITY_HEADERS."""
    if not os.path.exists(filepath):
        return []
    wb = load_workbook(filepath, data_only=True)
    ws = wb.active
    iterator = ws.iter_rows(values_only=True)
    try:
        headers = list(next(iterator))
    except StopIteration:
        return []
    rows: list[dict] = []
    for values in iterator:
        if all(v is None for v in values):
            continue
        rows.append(dict(zip(headers, values)))
    return rows


def _seat_matches_scope(
    candidate_seat: Optional[SeatKey],
    dest_tier: int,
    dest_coords: tuple[int, ...],
) -> bool:
    """Check geographical eligibility for promoting candidate_seat to dest_tier."""
    if candidate_seat is None:
        return False
    _, src_coords = candidate_seat
    if dest_tier == TIER_PRESIDENT:
        return True
    if dest_tier in (TIER_GOVERNOR, TIER_SENATOR, TIER_HOUSE):
        return len(src_coords) >= 1 and src_coords[0] == dest_coords[0]
    if dest_tier == TIER_MAYOR:
        return (
            len(src_coords) >= 2
            and src_coords[0] == dest_coords[0]
            and src_coords[1] == dest_coords[1]
        )
    if dest_tier == TIER_STATE_LEG:
        return (
            len(src_coords) >= 3
            and src_coords[0] == dest_coords[0]
            and src_coords[1] == dest_coords[1]
            and src_coords[2] == dest_coords[2]
        )
    return False


class SeniorityTracker:
    """Maintains active in-party politicians, vacancies, seniority advancement, and opponents."""

    def __init__(self, filepath: str = SENIORITY_FILE) -> None:
        self.filepath = filepath
        self.roster: dict[SeatKey, Candidate] = {}
        self.opponent_cache: dict[SeatKey, dict[int, Candidate]] = {}
        self.cached_opponent_tier: Optional[int] = None
        self.seat_streaks: dict[SeatKey, tuple[Optional[int], int]] = {}

    def active_names(self) -> set[str]:
        """Return all currently active in-party and cached opponent names."""
        names = {cand.name for cand in self.roster.values()}
        for seat_opponents in self.opponent_cache.values():
            for cand in seat_opponents.values():
                names.add(cand.name)
        return names

    def initialize_starting_roster(
        self,
        nation: Nation,
        home_state: int,
        home_city: int,
        player_party: int,
        name_manager: NameManager,
        historical_rows: list[dict],
        streaks: dict[SeatKey, tuple[Optional[int], int]],
        rng: Optional[random.Random] = None,
    ) -> None:
        """Populate initial in-party officeholders from historical data and write seniority.xlsx."""
        rng = rng or random.Random()
        self.roster.clear()
        self.seat_streaks = dict(streaks)
        party_platform = nation.parties[player_party].platform

        # Exclude City Council in home city (vacant at start)
        candidates_seats: list[SeatKey] = [(TIER_PRESIDENT, ())]
        candidates_seats.extend((TIER_GOVERNOR, (s,)) for s in range(NUM_STATES))
        candidates_seats.extend(
            (TIER_SENATOR, (s, w))
            for s in range(NUM_STATES)
            for w in range(SENATORS_PER_STATE)
        )
        candidates_seats.extend((TIER_HOUSE, (home_state, c)) for c in range(CITIES_PER_STATE))
        candidates_seats.extend((TIER_MAYOR, (home_state, c)) for c in range(CITIES_PER_STATE))
        candidates_seats.extend(
            (TIER_STATE_LEG, (home_state, home_city, d))
            for d in range(DISTRICTS_PER_CITY)
        )

        home_history_col_map: dict[SeatKey, str] = {
            (TIER_PRESIDENT, ()): "President",
            (TIER_GOVERNOR, (home_state,)): "Governor",
            (TIER_SENATOR, (home_state, 0)): "Senator 1",
            (TIER_SENATOR, (home_state, 1)): "Senator 2",
            (TIER_SENATOR, (home_state, 2)): "Senator 3",
            (TIER_HOUSE, (home_state, home_city)): "House",
            (TIER_MAYOR, (home_state, home_city)): "Mayor",
        }

        for sk in candidates_seats:
            incumbent_party = get_seat_party(nation, sk)
            if incumbent_party != player_party:
                continue
            if sk in home_history_col_map and historical_rows:
                seniority_years = count_consecutive_years(
                    historical_rows, home_history_col_map[sk], player_party
                )
            else:
                streak_party, streak_cycles = streaks.get(sk, (None, 0))
                seniority_years = (
                    streak_cycles * YEARS_PER_CYCLE
                    if streak_party == player_party
                    else 0
                )

            name = name_manager.draw_in_party_name(self.active_names())
            plat = sample_candidate_platform(party_platform, rng=rng)
            self.roster[sk] = Candidate(
                name=name,
                party_index=player_party,
                platform=plat,
                tier=sk[0],
                seat_id=sk,
                seniority=seniority_years,
                victory_size=0.0,
                is_player=False,
                cycles_in_office=seniority_years // YEARS_PER_CYCLE,
            )

        self.save()

    def save(self) -> None:
        """Persist current roster to seniority.xlsx."""
        write_seniority_data(list(self.roster.values()), filepath=self.filepath)

    def _get_scheduled_seats_for_tier(
        self,
        tier: int,
        cycle: int,
        nation: Nation,
        home_state: int,
        home_city: int,
        home_district: int,
        player_tier: Optional[int],
    ) -> list[SeatKey]:
        """Return tracked seat keys at tier that hold elections in cycle."""
        if tier == TIER_PRESIDENT:
            return [(TIER_PRESIDENT, ())] if is_election_cycle(tier, cycle) else []
        if tier == TIER_GOVERNOR:
            return [
                (TIER_GOVERNOR, (s,))
                for s in range(NUM_STATES)
                if is_election_cycle(TIER_GOVERNOR, cycle, nation.states[s].wave)
            ]
        if tier == TIER_SENATOR:
            return [
                (TIER_SENATOR, (s, w))
                for s in range(NUM_STATES)
                for w in range(SENATORS_PER_STATE)
                if is_election_cycle(TIER_SENATOR, cycle, w)
            ]
        if tier == TIER_HOUSE:
            if not is_election_cycle(TIER_HOUSE, cycle):
                return []
            return [(TIER_HOUSE, (home_state, c)) for c in range(CITIES_PER_STATE)]
        if tier == TIER_MAYOR:
            if not is_election_cycle(TIER_MAYOR, cycle):
                return []
            return [(TIER_MAYOR, (home_state, c)) for c in range(CITIES_PER_STATE)]
        if tier == TIER_STATE_LEG:
            if player_tier is None or player_tier >= TIER_STATE_LEG:
                return [
                    (TIER_STATE_LEG, (home_state, home_city, d))
                    for d in range(DISTRICTS_PER_CITY)
                ]
            return [(TIER_STATE_LEG, (home_state, home_city, home_district))]
        if tier == TIER_CITY_COUNCIL:
            if player_tier is None or player_tier >= TIER_STATE_LEG:
                return [
                    (TIER_CITY_COUNCIL, (home_state, home_city, d))
                    for d in range(DISTRICTS_PER_CITY)
                ]
            return [(TIER_CITY_COUNCIL, (home_state, home_city, home_district))]
        raise ValueError(f"Unknown tier: {tier}")

    def _pop_best_candidate(
        self,
        dest_tier: int,
        dest_coords: tuple[int, ...],
        strict_lower_tier_only: bool = False,
    ) -> Optional[Candidate]:
        """Find and remove the most senior eligible candidate from lower tiers."""
        start_tier = dest_tier + 1
        end_tier = start_tier if strict_lower_tier_only else TIER_CITY_COUNCIL
        for src_tier in range(start_tier, end_tier + 1):
            pool = [
                cand
                for sk, cand in self.roster.items()
                if sk[0] == src_tier and _seat_matches_scope(sk, dest_tier, dest_coords)
            ]
            if pool:
                pool.sort(
                    key=lambda c: (c.seniority, c.victory_size, 1 if c.is_player else 0),
                    reverse=True,
                )
                chosen = pool[0]
                if chosen.seat_id is not None:
                    self.roster.pop(chosen.seat_id, None)
                    self.seat_streaks.pop(chosen.seat_id, None)
                return chosen
        return None

    def resolve_cycle_assignments(
        self,
        cycle: int,
        nation: Nation,
        player: PlayerProfile,
    ) -> tuple[dict[SeatKey, ElectionAssignment], Optional[ElectionAssignment]]:
        """Resolve all vacancies and nominations top-down (Tier 1 -> Tier 7) for cycle."""
        # Term-limit outgoing President when a Presidential election cycle starts
        if is_election_cycle(TIER_PRESIDENT, cycle):
            self.roster.pop((TIER_PRESIDENT, ()), None)
            self.seat_streaks.pop((TIER_PRESIDENT, ()), None)

        assignments: dict[SeatKey, ElectionAssignment] = {}
        player_assignment: Optional[ElectionAssignment] = None

        for tier in ALL_TIERS:
            scheduled = self._get_scheduled_seats_for_tier(
                tier=tier,
                cycle=cycle,
                nation=nation,
                home_state=player.home_state,
                home_city=player.home_city,
                home_district=player.home_district,
                player_tier=player.current_tier,
            )
            if not scheduled:
                continue

            vacant_seats: list[SeatKey] = []
            for sk in scheduled:
                if sk in self.roster:
                    incumbent = self.roster[sk]
                    assignment = ElectionAssignment(
                        seat_key=sk,
                        tier=tier,
                        candidate=incumbent,
                        is_promotion=False,
                        is_reelection=True,
                    )
                    assignments[sk] = assignment
                    if incumbent.is_player:
                        player_assignment = assignment
                else:
                    vacant_seats.append(sk)

            if not vacant_seats:
                continue

            # Tier 4 (House) competes across all V vacant seats in home_state as one pool
            if tier == TIER_HOUSE:
                selected_pool: list[Candidate] = []
                for _ in vacant_seats:
                    chosen = self._pop_best_candidate(
                        TIER_HOUSE, (player.home_state,)
                    )
                    if chosen is None:
                        break
                    selected_pool.append(chosen)

                unmatched_seats = list(vacant_seats)
                unmatched_cands: list[Candidate] = []
                # Prefer matching a Mayor to their own city's House seat (especially player)
                for cand in selected_pool:
                    if cand.seat_id is not None and len(cand.seat_id[1]) >= 2:
                        own_house_key = (TIER_HOUSE, (player.home_state, cand.seat_id[1][1]))
                        if own_house_key in unmatched_seats:
                            unmatched_seats.remove(own_house_key)
                            assignment = ElectionAssignment(
                                seat_key=own_house_key,
                                tier=TIER_HOUSE,
                                candidate=cand,
                                is_promotion=True,
                                is_reelection=False,
                            )
                            assignments[own_house_key] = assignment
                            if cand.is_player:
                                player_assignment = assignment
                            continue
                    unmatched_cands.append(cand)

                for sk, cand in zip(unmatched_seats, unmatched_cands):
                    assignment = ElectionAssignment(
                        seat_key=sk,
                        tier=TIER_HOUSE,
                        candidate=cand,
                        is_promotion=True,
                        is_reelection=False,
                    )
                    assignments[sk] = assignment
                    if cand.is_player:
                        player_assignment = assignment

                for sk in vacant_seats:
                    if sk not in assignments:
                        assignments[sk] = ElectionAssignment(
                            seat_key=sk,
                            tier=TIER_HOUSE,
                            candidate=None,
                            is_promotion=False,
                            is_reelection=False,
                        )
                continue

            # Tier 7: First cycle places player into their chosen home district City Council
            for sk in vacant_seats:
                if (
                    tier == TIER_CITY_COUNCIL
                    and player.current_tier is None
                    and sk[1] == (player.home_state, player.home_city, player.home_district)
                ):
                    player_cand = Candidate(
                        name=player.name,
                        party_index=player.party_index,
                        platform=list(player.platform),
                        tier=TIER_CITY_COUNCIL,
                        seat_id=sk,
                        seniority=0,
                        victory_size=0.0,
                        is_player=True,
                    )
                    assignment = ElectionAssignment(
                        seat_key=sk,
                        tier=TIER_CITY_COUNCIL,
                        candidate=player_cand,
                        is_promotion=False,
                        is_reelection=False,
                    )
                    assignments[sk] = assignment
                    player_assignment = assignment
                    continue

                strict = tier == TIER_STATE_LEG
                chosen = (
                    self._pop_best_candidate(
                        tier, sk[1], strict_lower_tier_only=strict
                    )
                    if tier < TIER_CITY_COUNCIL
                    else None
                )
                assignment = ElectionAssignment(
                    seat_key=sk,
                    tier=tier,
                    candidate=chosen,
                    is_promotion=chosen is not None,
                    is_reelection=False,
                )
                assignments[sk] = assignment
                if chosen is not None and chosen.is_player:
                    player_assignment = assignment

        return assignments, player_assignment

    def get_live_seat_keys(
        self,
        live_tier: int,
        cycle: int,
        nation: Nation,
        home_state: int,
        home_city: int,
    ) -> list[SeatKey]:
        """Return the list of seat keys monitored live for the player's active tier."""
        if live_tier == TIER_PRESIDENT:
            return [(TIER_PRESIDENT, ())] if is_election_cycle(TIER_PRESIDENT, cycle) else []
        if live_tier == TIER_GOVERNOR:
            return [
                (TIER_GOVERNOR, (s,))
                for s in range(NUM_STATES)
                if is_election_cycle(TIER_GOVERNOR, cycle, nation.states[s].wave)
            ]
        if live_tier == TIER_SENATOR:
            return [
                (TIER_SENATOR, (home_state, w))
                for w in range(SENATORS_PER_STATE)
                if is_election_cycle(TIER_SENATOR, cycle, w)
            ]
        if live_tier == TIER_HOUSE:
            if not is_election_cycle(TIER_HOUSE, cycle):
                return []
            return [(TIER_HOUSE, (home_state, c)) for c in range(CITIES_PER_STATE)]
        if live_tier == TIER_MAYOR:
            if not is_election_cycle(TIER_MAYOR, cycle):
                return []
            return [(TIER_MAYOR, (home_state, c)) for c in range(CITIES_PER_STATE)]
        if live_tier == TIER_STATE_LEG:
            return [
                (TIER_STATE_LEG, (home_state, home_city, d))
                for d in range(DISTRICTS_PER_CITY)
            ]
        if live_tier == TIER_CITY_COUNCIL:
            return [
                (TIER_CITY_COUNCIL, (home_state, home_city, d))
                for d in range(DISTRICTS_PER_CITY)
            ]
        raise ValueError(f"Unknown tier: {live_tier}")

    def get_incumbent_grudge(
        self,
        seat_key: SeatKey,
        assignment: Optional[ElectionAssignment],
        player_party: int,
    ) -> tuple[Optional[int], int]:
        """Return (incumbent_party, consecutive_cycles) currently holding seat_key."""
        if assignment is not None:
            if assignment.is_reelection and assignment.candidate is not None:
                return player_party, assignment.candidate.cycles_in_office
            streak_party, streak_cycles = self.seat_streaks.get(seat_key, (None, 0))
            if streak_party is not None and streak_party != player_party and streak_cycles > 0:
                return streak_party, streak_cycles
            return None, 0

        if seat_key in self.roster:
            return player_party, self.roster[seat_key].cycles_in_office
        streak_party, streak_cycles = self.seat_streaks.get(seat_key, (None, 0))
        if streak_party is not None and streak_cycles > 0:
            return streak_party, streak_cycles
        return None, 0

    def build_live_races(
        self,
        live_tier: int,
        cycle: int,
        nation: Nation,
        player: PlayerProfile,
        assignments: dict[SeatKey, ElectionAssignment],
        name_manager: NameManager,
        rng: Optional[random.Random] = None,
    ) -> list[LiveRaceSpec]:
        """Build LiveRaceSpec entries, drawing fresh opponents only upon leveling up."""
        rng = rng or random.Random()
        if self.cached_opponent_tier != live_tier:
            self.opponent_cache.clear()
            self.cached_opponent_tier = live_tier

        seat_keys = self.get_live_seat_keys(
            live_tier=live_tier,
            cycle=cycle,
            nation=nation,
            home_state=player.home_state,
            home_city=player.home_city,
        )
        races: list[LiveRaceSpec] = []
        player_party = player.party_index

        for sk in seat_keys:
            assignment = assignments.get(sk)
            in_cand = assignment.candidate if assignment is not None else None
            if in_cand is None:
                in_name = name_manager.draw_in_party_name(self.active_names())
                in_plat = sample_candidate_platform(
                    nation.parties[player_party].platform, rng=rng
                )
                in_cand = Candidate(
                    name=in_name,
                    party_index=player_party,
                    platform=in_plat,
                    tier=sk[0],
                    seat_id=sk,
                    seniority=0,
                    victory_size=0.0,
                    is_player=False,
                )
                if assignment is not None:
                    assignment.candidate = in_cand
            elif in_cand.is_player:
                in_cand.platform = list(player.platform)

            seat_opponents = self.opponent_cache.setdefault(sk, {})
            candidates: list[Candidate] = []
            for party in nation.parties:
                if party.index == player_party:
                    candidates.append(in_cand)
                else:
                    opp = seat_opponents.get(party.index)
                    if opp is None:
                        opp_name = name_manager.draw_out_party_name(self.active_names())
                        opp_plat = sample_candidate_platform(party.platform, rng=rng)
                        opp = Candidate(
                            name=opp_name,
                            party_index=party.index,
                            platform=opp_plat,
                            tier=sk[0],
                            seat_id=sk,
                            is_player=False,
                        )
                        seat_opponents[party.index] = opp
                    candidates.append(opp)

            inc_party, inc_cycles = self.get_incumbent_grudge(
                sk, assignment, player_party
            )
            races.append(
                LiveRaceSpec(
                    seat_key=sk,
                    tier=sk[0],
                    label=format_seat_label(sk),
                    districts=get_seat_districts(sk, nation),
                    candidates=candidates,
                    has_player=in_cand.is_player,
                    incumbent_party=inc_party,
                    incumbent_cycles=inc_cycles,
                )
            )
        return races

    def apply_cycle_outcomes(
        self,
        cycle: int,
        nation: Nation,
        player: PlayerProfile,
        assignments: dict[SeatKey, ElectionAssignment],
        outcomes: dict[SeatKey, tuple[int, float]],
        name_manager: NameManager,
        rng: Optional[random.Random] = None,
    ) -> None:
        """Update Nation incumbents, SeniorityTracker roster, and seniority.xlsx."""
        rng = rng or random.Random()
        player_party = player.party_index

        # Candidates not up for election this cycle gain +2 years seniority and +1 cycle
        elected_keys = set(outcomes.keys())
        for sk, cand in list(self.roster.items()):
            if sk not in elected_keys:
                cand.seniority += YEARS_PER_CYCLE
                cand.cycles_in_office += 1
        for sk, (streak_party, streak_count) in list(self.seat_streaks.items()):
            if sk not in elected_keys and streak_party is not None:
                self.seat_streaks[sk] = (streak_party, streak_count + 1)

        for sk, (winner_party, victory_size) in outcomes.items():
            set_seat_party(nation, sk, winner_party, cycle=cycle)
            assignment = assignments.get(sk)
            nominee = assignment.candidate if assignment is not None else None

            if winner_party == player_party:
                if nominee is None:
                    nominee = Candidate(
                        name=name_manager.draw_in_party_name(self.active_names()),
                        party_index=player_party,
                        platform=sample_candidate_platform(
                            nation.parties[player_party].platform, rng=rng
                        ),
                        tier=sk[0],
                        seat_id=sk,
                        seniority=0,
                        victory_size=victory_size,
                        is_player=False,
                        cycles_in_office=1,
                    )
                else:
                    nominee.tier = sk[0]
                    nominee.seat_id = sk
                    nominee.victory_size = victory_size
                    if assignment is not None and assignment.is_reelection:
                        nominee.seniority += YEARS_PER_CYCLE
                        nominee.cycles_in_office += 1
                    else:
                        nominee.seniority = 0
                        nominee.cycles_in_office = 1

                self.roster[sk] = nominee
                self.seat_streaks[sk] = (player_party, nominee.cycles_in_office)
                if nominee.is_player:
                    player.current_tier = sk[0]
                    player.current_seat = sk
                    player.elected_cycle = cycle
            else:
                # If an incumbent from player's party lost reelection, remove from roster
                if sk in self.roster and self.roster[sk].party_index == player_party:
                    self.roster.pop(sk, None)
                prev_party, prev_count = self.seat_streaks.get(sk, (None, 0))
                if prev_party == winner_party and prev_count > 0:
                    self.seat_streaks[sk] = (winner_party, prev_count + 1)
                else:
                    self.seat_streaks[sk] = (winner_party, 1)

            # Keep winning opposing candidate's platform; redraw losing opposing candidates' platforms
            seat_opponents = self.opponent_cache.get(sk)
            if seat_opponents is not None:
                for opp_party, opp_cand in seat_opponents.items():
                    if opp_party != winner_party:
                        opp_cand.platform = sample_candidate_platform(
                            nation.parties[opp_party].platform, rng=rng
                        )

        self.save()


def wipe_data(data_dir: str = DATA_DIR) -> None:
    """Remove all contents inside data_dir while ensuring data_dir exists."""
    os.makedirs(data_dir, exist_ok=True)
    for entry in os.listdir(data_dir):
        full_path = os.path.join(data_dir, entry)
        if os.path.isdir(full_path):
            shutil.rmtree(full_path)
        else:
            os.remove(full_path)


def save_results(
    data_dir: str = DATA_DIR,
    results_dir: str = RESULTS_DIR,
    timestamp: Optional[str] = None,
) -> str:
    """Move contents of data_dir into a timestamped subfolder in results_dir and wipe data_dir."""
    os.makedirs(results_dir, exist_ok=True)
    os.makedirs(data_dir, exist_ok=True)

    base_stamp = timestamp or datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    dest_dir = os.path.join(results_dir, base_stamp)
    counter = 1
    while os.path.exists(dest_dir):
        dest_dir = os.path.join(results_dir, f"{base_stamp}_{counter}")
        counter += 1
    os.makedirs(dest_dir, exist_ok=True)

    for entry in os.listdir(data_dir):
        src_path = os.path.join(data_dir, entry)
        shutil.move(src_path, os.path.join(dest_dir, entry))

    wipe_data(data_dir)
    return dest_dir
