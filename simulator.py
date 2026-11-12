"""Election simulation engine, world construction, voting math, and grudge backlash logic."""

import itertools
import math
import random
from typing import Optional

import numpy as np

from constants import (
    CITIES_PER_STATE,
    CONSERVATIVE_PLATFORM,
    DIRICHLET_KAPPA,
    DISTRICTS_PER_CITY,
    GRUDGE_BASE,
    KAPPA_CITY,
    KAPPA_STATE,
    LIBERAL_PLATFORM,
    MAX_ISSUES,
    MAX_POS,
    MID_POS,
    MIN_ISSUES,
    MIN_POS,
    NUM_STATES,
    NUM_WAVES,
    OFFICE_NAMES,
    SENATORS_PER_STATE,
    SMOOTHING_TERM,
    TIER_CITY_COUNCIL,
    TIER_GOVERNOR,
    TIER_HOUSE,
    TIER_MAYOR,
    TIER_PRESIDENT,
    TIER_SENATOR,
    TIER_STATE_LEG,
    VOTES_PER_BATCH,
)
from custom_types import (
    City,
    District,
    LiveRaceSpec,
    Nation,
    Party,
    PositionVector,
    SeatKey,
    State,
)


def clamp_and_round_position(value: float) -> float:
    """Clamp a position coordinate to [0.01, 0.99] rounded to 2 decimal places."""
    return round(min(MAX_POS, max(MIN_POS, float(value))), 2)


def is_valid_candidate_coordinate(value: float) -> bool:
    """Return True if value is in [0.01, 0.99], in 0.01 increments, and not 0.50."""
    rounded = round(value, 2)
    if abs(value - rounded) > 1e-6:
        return False
    if rounded < MIN_POS or rounded > MAX_POS:
        return False
    if abs(rounded - MID_POS) < 1e-6:
        return False
    return True


def build_parties(num_issues: int, party_names: list[str]) -> list[Party]:
    """Build 2^num_issues parties, each with a unique platform in {0.25, 0.75}^I."""
    if not (MIN_ISSUES <= num_issues <= MAX_ISSUES):
        raise ValueError(f"num_issues must be between {MIN_ISSUES} and {MAX_ISSUES}")
    num_parties = 2**num_issues
    if len(party_names) < num_parties:
        raise ValueError(
            f"Need at least {num_parties} party names, got {len(party_names)}"
        )
    platforms = list(
        itertools.product([CONSERVATIVE_PLATFORM, LIBERAL_PLATFORM], repeat=num_issues)
    )
    return [
        Party(index=idx, name=party_names[idx], platform=list(plat))
        for idx, plat in enumerate(platforms)
    ]


def sample_beta_position(
    parent_mu: float, kappa: float, rng: Optional[random.Random] = None
) -> float:
    """Sample a coordinate in [0.01, 0.99] from Beta(kappa * mu, kappa * (1 - mu))."""
    rng = rng or random.Random()
    alpha = kappa * parent_mu
    beta = kappa * (1.0 - parent_mu)
    return clamp_and_round_position(rng.betavariate(alpha, beta))


def build_nation(
    name: str,
    issues: list[str],
    party_names: list[str],
    rng: Optional[random.Random] = None,
) -> Nation:
    """Construct the nation hierarchy: 50 states, 10 cities/state, 40 districts/city."""
    if not (MIN_ISSUES <= len(issues) <= MAX_ISSUES):
        raise ValueError(f"Number of issues must be between {MIN_ISSUES} and {MAX_ISSUES}")
    rng = rng or random.Random()
    num_issues = len(issues)
    parties = build_parties(num_issues, party_names)

    states: list[State] = []
    for s_idx in range(NUM_STATES):
        state_pos = [rng.randint(1, 99) / 100.0 for _ in range(num_issues)]
        cities: list[City] = []
        for c_idx in range(CITIES_PER_STATE):
            city_pos = [
                sample_beta_position(state_pos[k], KAPPA_STATE, rng=rng)
                for k in range(num_issues)
            ]
            districts: list[District] = []
            for d_idx in range(DISTRICTS_PER_CITY):
                dist_pos = [
                    sample_beta_position(city_pos[k], KAPPA_CITY, rng=rng)
                    for k in range(num_issues)
                ]
                districts.append(
                    District(
                        index=d_idx,
                        city_index=c_idx,
                        state_index=s_idx,
                        position=dist_pos,
                    )
                )
            cities.append(
                City(
                    index=c_idx,
                    state_index=s_idx,
                    position=city_pos,
                    districts=districts,
                )
            )
        states.append(
            State(
                index=s_idx,
                wave=s_idx % NUM_WAVES,
                position=state_pos,
                cities=cities,
                senator_parties=[None] * SENATORS_PER_STATE,
            )
        )

    return Nation(
        name=name,
        issues=list(issues),
        position=[MID_POS] * num_issues,
        parties=parties,
        states=states,
    )


def sample_candidate_platform(
    party_platform: PositionVector, rng: Optional[random.Random] = None
) -> PositionVector:
    """Sample a candidate position vector matching the conservative/liberal side of party."""
    rng = rng or random.Random()
    pos: PositionVector = []
    for p in party_platform:
        if p < MID_POS:
            pos.append(rng.randint(1, 49) / 100.0)
        else:
            pos.append(rng.randint(51, 99) / 100.0)
    return pos


def platform_matches_party(
    platform: PositionVector, party_platform: PositionVector
) -> bool:
    """Return True if platform has valid coordinates on the same ideological sides as party."""
    if len(platform) != len(party_platform):
        return False
    for val, party_val in zip(platform, party_platform):
        if not is_valid_candidate_coordinate(val):
            return False
        if party_val < MID_POS and val >= MID_POS:
            return False
        if party_val > MID_POS and val <= MID_POS:
            return False
    return True


def find_party_for_platform(platform: PositionVector, parties: list[Party]) -> int:
    """Return the unique party index matching a candidate's position vector."""
    for party in parties:
        if platform_matches_party(platform, party.platform):
            return party.index
    raise ValueError(
        "Platform coordinates must be in [0.01, 0.49] or [0.51, 0.99] in 0.01 steps."
    )


def euclidean_distance(a: PositionVector, b: PositionVector) -> float:
    """Compute Euclidean distance between two equal-length position vectors."""
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def compute_probabilities(
    population_pos: PositionVector,
    platforms: list[PositionVector],
    smoothing: float = SMOOTHING_TERM,
    incumbent_cycles: Optional[list[int]] = None,
) -> list[float]:
    """Convert ideological Euclidean distances (scaled by 1.06^C grudge) to probabilities."""
    cycles = incumbent_cycles if incumbent_cycles is not None else [0] * len(platforms)
    scores = [
        1.0
        / math.sqrt(
            euclidean_distance(population_pos, plat) * (GRUDGE_BASE ** max(0, cyc))
            + smoothing
        )
        for plat, cyc in zip(platforms, cycles)
    ]
    total = sum(scores)
    return [score / total for score in scores]


def run_default_election(
    population_pos: PositionVector,
    platforms: list[PositionVector],
    rng: Optional[random.Random] = None,
    incumbent_cycles: Optional[list[int]] = None,
) -> int:
    """Sample a winning index from the inverse-distance probability distribution."""
    rng = rng or random.Random()
    probs = compute_probabilities(
        population_pos, platforms, incumbent_cycles=incumbent_cycles
    )
    return rng.choices(range(len(platforms)), weights=probs, k=1)[0]


def is_election_cycle(tier: int, cycle: int, wave: int = 0) -> bool:
    """Return True if an office at the given tier and wave holds an election in cycle."""
    if tier == TIER_PRESIDENT:
        return (cycle - 1) % 4 == 0
    if tier in (TIER_GOVERNOR, TIER_SENATOR):
        return (cycle - 1) % NUM_WAVES == wave
    if tier == TIER_HOUSE:
        return cycle % 2 == 0
    if tier == TIER_MAYOR:
        return cycle % 2 == 1
    if tier in (TIER_STATE_LEG, TIER_CITY_COUNCIL):
        return True
    raise ValueError(f"Unknown tier: {tier}")


def get_seat_wave(seat_key: SeatKey, nation: Nation) -> int:
    """Return the 0/1/2 election wave for Governor or Senator seats (0 otherwise)."""
    tier, coords = seat_key
    if tier == TIER_GOVERNOR:
        return nation.states[coords[0]].wave
    if tier == TIER_SENATOR:
        return coords[1]
    return 0


def get_seat_districts(seat_key: SeatKey, nation: Nation) -> list[District]:
    """Return all District objects participating in elections for seat_key."""
    tier, coords = seat_key
    if tier == TIER_PRESIDENT:
        return [
            d
            for state in nation.states
            for city in state.cities
            for d in city.districts
        ]
    if tier in (TIER_GOVERNOR, TIER_SENATOR):
        state = nation.states[coords[0]]
        return [d for city in state.cities for d in city.districts]
    if tier in (TIER_HOUSE, TIER_MAYOR):
        city = nation.states[coords[0]].cities[coords[1]]
        return list(city.districts)
    if tier in (TIER_STATE_LEG, TIER_CITY_COUNCIL):
        district = nation.states[coords[0]].cities[coords[1]].districts[coords[2]]
        return [district]
    raise ValueError(f"Unknown tier: {tier}")


def format_seat_label(seat_key: SeatKey) -> str:
    """Return a human-readable label for an office seat key."""
    tier, coords = seat_key
    office = OFFICE_NAMES[tier]
    if tier == TIER_PRESIDENT:
        return office
    if tier == TIER_GOVERNOR:
        return f"{office} - State {coords[0] + 1}"
    if tier == TIER_SENATOR:
        return f"{office} {coords[1] + 1} - State {coords[0] + 1}"
    if tier in (TIER_HOUSE, TIER_MAYOR):
        return f"{office} - State {coords[0] + 1}, City {coords[1] + 1}"
    return (
        f"{office} - State {coords[0] + 1}, City {coords[1] + 1}, "
        f"District {coords[2] + 1}"
    )


def num_voting_rounds(num_parties: int) -> int:
    """Compute ranked-choice simulated rounds R(P) = floor(P / 2)."""
    return math.floor(num_parties / 2)


def allocate_batch_votes(
    shares: list[float], total_votes: int = VOTES_PER_BATCH
) -> list[int]:
    """Allocate integer votes summing to total_votes via largest-remainder rounding."""
    exact = [share * total_votes for share in shares]
    floors = [int(math.floor(x)) for x in exact]
    remainder = total_votes - sum(floors)
    if remainder > 0:
        order = sorted(
            range(len(shares)),
            key=lambda idx: (exact[idx] - floors[idx], shares[idx]),
            reverse=True,
        )
        for idx in order[:remainder]:
            floors[idx] += 1
    return floors


def simulate_district_batch(
    district_probs: list[float],
    rng: Optional[random.Random] = None,
    kappa: float = DIRICHLET_KAPPA,
) -> list[float]:
    """Sample one district batch share vector from Dirichlet(kappa * district_probs)."""
    rng = rng or random.Random()
    gammas = [
        rng.gammavariate(kappa * pr, 1.0) if pr > 0.0 else 0.0
        for pr in district_probs
    ]
    total = sum(gammas)
    if total <= 0.0:
        return [1.0 / len(district_probs)] * len(district_probs)
    return [g / total for g in gammas]


def precompute_race_probabilities(race: LiveRaceSpec) -> np.ndarray:
    """Precompute (num_districts, num_candidates) probability matrix for a live race."""
    dist_positions = np.asarray([d.position for d in race.districts], dtype=np.float64)
    cand_platforms = np.asarray([c.platform for c in race.candidates], dtype=np.float64)
    # Shape: (D, P, I) -> Euclidean distances (D, P)
    diff = dist_positions[:, None, :] - cand_platforms[None, :, :]
    dists = np.sqrt(np.sum(diff * diff, axis=2))

    grudge = np.ones(len(race.candidates), dtype=np.float64)
    if race.incumbent_party is not None and race.incumbent_cycles > 0:
        factor = GRUDGE_BASE ** race.incumbent_cycles
        for idx, cand in enumerate(race.candidates):
            if cand.party_index == race.incumbent_party:
                grudge[idx] = factor

    effective_dists = dists * grudge[None, :]
    scores = 1.0 / np.sqrt(effective_dists + SMOOTHING_TERM)
    return scores / scores.sum(axis=1, keepdims=True)


def simulate_live_batch(
    race: LiveRaceSpec,
    prob_matrix: Optional[np.ndarray] = None,
    rng: Optional[random.Random] = None,
    np_rng: Optional[np.random.Generator] = None,
    kappa: float = DIRICHLET_KAPPA,
) -> list[int]:
    """Simulate one 1000-vote batch per district for a race and return per-candidate votes."""
    p_count = len(race.candidates)
    if len(race.districts) == 1 and rng is not None:
        if prob_matrix is not None:
            probs = prob_matrix[0].tolist()
        else:
            inc_cycles = [
                race.incumbent_cycles
                if (race.incumbent_party is not None and c.party_index == race.incumbent_party)
                else 0
                for c in race.candidates
            ]
            probs = compute_probabilities(
                race.districts[0].position,
                [c.platform for c in race.candidates],
                incumbent_cycles=inc_cycles,
            )
        shares = simulate_district_batch(probs, rng=rng, kappa=kappa)
        return allocate_batch_votes(shares, VOTES_PER_BATCH)

    if prob_matrix is None:
        prob_matrix = precompute_race_probabilities(race)

    if np_rng is None:
        if rng is not None:
            np_rng = np.random.default_rng(rng.randrange(0, 2**32))
        else:
            np_rng = np.random.default_rng()

    alphas = prob_matrix * kappa
    gammas = np.where(
        alphas > 0.0,
        np_rng.gamma(np.maximum(alphas, 1e-12), 1.0),
        0.0,
    )
    row_sums = gammas.sum(axis=1, keepdims=True)
    safe_sums = np.where(row_sums > 0.0, row_sums, 1.0)
    shares = np.where(row_sums > 0.0, gammas / safe_sums, 1.0 / p_count)

    # Vectorized largest-remainder allocation per district row
    exact = shares * VOTES_PER_BATCH
    floors = np.floor(exact).astype(np.int64)
    remainders = VOTES_PER_BATCH - floors.sum(axis=1)
    fracs = exact - floors
    if np.any(remainders > 0):
        rank_order = np.argsort(-fracs, axis=1, kind="mergesort")
        for row_idx in np.flatnonzero(remainders > 0):
            rem = int(remainders[row_idx])
            floors[row_idx, rank_order[row_idx, :rem]] += 1

    totals = floors.sum(axis=0)
    return [int(v) for v in totals]


def compute_rcv_percentages(
    candidate_votes: dict[int, int], num_parties: int
) -> dict[int, float]:
    """Convert cumulative vote counts into RCV-adjusted percentages (winner >= 50%)."""
    total = sum(candidate_votes.values())
    if total <= 0:
        return {p: 0.0 for p in candidate_votes}
    rounds = num_voting_rounds(num_parties)
    return {
        party_idx: (votes / total) * rounds * 100.0
        for party_idx, votes in candidate_votes.items()
    }
