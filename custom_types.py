"""Custom data types and domain structures for All Politics Is Local."""

from dataclasses import dataclass, field
from typing import Optional

PositionVector = list[float]
SeatKey = tuple[int, tuple[int, ...]]


class QuitGame(Exception):
    """Raised when the user presses Q/q to quit the game."""


class RestartGame(Exception):
    """Raised when the user presses R/r to restart the game."""


@dataclass
class Party:
    """Represents a political party with a unique conservative/liberal platform."""

    index: int
    name: str
    platform: PositionVector


@dataclass
class Candidate:
    """Represents a political candidate or sitting incumbent."""

    name: str
    party_index: int
    platform: PositionVector
    tier: int
    seat_id: Optional[SeatKey] = None
    seniority: int = 0
    victory_size: float = 0.0
    is_player: bool = False
    cycles_in_office: int = 0


@dataclass
class District:
    """Lowest geographical unit (40 per city, 20,000 total)."""

    index: int
    city_index: int
    state_index: int
    position: PositionVector
    state_leg_party: Optional[int] = None
    city_council_party: Optional[int] = None


@dataclass
class City:
    """Mid-level geographical unit (10 per state, 500 total)."""

    index: int
    state_index: int
    position: PositionVector
    districts: list[District] = field(default_factory=list)
    house_party: Optional[int] = None
    mayor_party: Optional[int] = None


@dataclass
class State:
    """State unit (50 per nation), assigned to election wave A/B/C (0/1/2)."""

    index: int
    wave: int
    position: PositionVector
    cities: list[City] = field(default_factory=list)
    governor_party: Optional[int] = None
    senator_parties: list[Optional[int]] = field(default_factory=lambda: [None, None, None])


@dataclass
class Nation:
    """Top-level nation container holding issues, parties, and 50 states."""

    name: str
    issues: list[str]
    position: PositionVector
    parties: list[Party]
    states: list[State]
    president_party: Optional[int] = None
    president_term_start_cycle: Optional[int] = None


@dataclass
class PlayerProfile:
    """Tracks the player's identity, home geography, party, and career state."""

    name: str
    home_state: int
    home_city: int
    home_district: int
    party_index: int
    platform: PositionVector
    current_tier: Optional[int] = None
    current_seat: Optional[SeatKey] = None
    elected_cycle: Optional[int] = None


@dataclass
class ElectionAssignment:
    """Describes the player party's nominee for a specific seat in a cycle."""

    seat_key: SeatKey
    tier: int
    candidate: Optional[Candidate]
    is_promotion: bool
    is_reelection: bool


@dataclass
class LiveRaceSpec:
    """Specification for a single race reported in live election mode."""

    seat_key: SeatKey
    tier: int
    label: str
    districts: list[District]
    candidates: list[Candidate]
    has_player: bool = False
    incumbent_party: Optional[int] = None
    incumbent_cycles: int = 0


@dataclass
class LiveRaceSnapshot:
    """Cumulative batch results for one live race."""

    seat_key: SeatKey
    tier: int
    label: str
    has_player: bool
    votes_reported: int
    total_votes: int
    candidate_votes: dict[int, int]
    candidate_shares: dict[int, float]
    leader_party: int


@dataclass
class LiveBatchResult:
    """Aggregated snapshots across all live races after a reporting batch."""

    batch_num: int
    total_batches: int
    race_snapshots: list[LiveRaceSnapshot]

