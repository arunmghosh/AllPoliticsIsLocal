"""Hyperparameters and global constants for All Politics Is Local."""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
NAMES_DIR = os.path.join(BASE_DIR, "names")
DATA_DIR = os.path.join(BASE_DIR, "data")
RESULTS_DIR = os.path.join(BASE_DIR, "results")

PARTIES_FILE = os.path.join(NAMES_DIR, "parties.txt")
IN_PARTY_FILE = os.path.join(NAMES_DIR, "in_party.txt")
OUT_PARTIES_FILE = os.path.join(NAMES_DIR, "out_parties.txt")

HISTORICAL_DATA_FILE = os.path.join(DATA_DIR, "historical_data.xlsx")
SENIORITY_FILE = os.path.join(DATA_DIR, "seniority.xlsx")

EXPECTED_PARTIES_COUNT = 8
EXPECTED_IN_PARTY_COUNT = 500
EXPECTED_OUT_PARTIES_COUNT = 2500

# Geography & government structure
NUM_STATES = 50
CITIES_PER_STATE = 10
DISTRICTS_PER_CITY = 40
SENATORS_PER_STATE = 3
NUM_WAVES = 3
WAVE_LABELS = ("A", "B", "C")

# Office tiers (1 = highest, 7 = lowest)
TIER_PRESIDENT = 1
TIER_GOVERNOR = 2
TIER_SENATOR = 3
TIER_HOUSE = 4
TIER_MAYOR = 5
TIER_STATE_LEG = 6
TIER_CITY_COUNCIL = 7
ALL_TIERS = (
    TIER_PRESIDENT,
    TIER_GOVERNOR,
    TIER_SENATOR,
    TIER_HOUSE,
    TIER_MAYOR,
    TIER_STATE_LEG,
    TIER_CITY_COUNCIL,
)

OFFICE_NAMES = {
    TIER_PRESIDENT: "President",
    TIER_GOVERNOR: "Governor",
    TIER_SENATOR: "Senator",
    TIER_HOUSE: "House",
    TIER_MAYOR: "Mayor",
    TIER_STATE_LEG: "State Legislature",
    TIER_CITY_COUNCIL: "City Council",
}

LIVE_SCOPE_TITLES = {
    TIER_PRESIDENT: "Presidential Election",
    TIER_GOVERNOR: "Gubernatorial Elections",
    TIER_SENATOR: "Senate Election In Your State",
    TIER_HOUSE: "House Elections In Your State",
    TIER_MAYOR: "Mayoral Elections In Your State",
    TIER_STATE_LEG: "State Legislature Elections In Your City",
    TIER_CITY_COUNCIL: "City Council Elections In Your City",
}

TERM_LENGTH_CYCLES = {
    TIER_PRESIDENT: 4,
    TIER_GOVERNOR: 3,
    TIER_SENATOR: 3,
    TIER_HOUSE: 2,
    TIER_MAYOR: 2,
    TIER_STATE_LEG: 1,
    TIER_CITY_COUNCIL: 1,
}

# Political representation
MIN_ISSUES = 1
MAX_ISSUES = 3
MIN_POS = 0.01
MAX_POS = 0.99
POS_STEP = 0.01
MID_POS = 0.50
CONSERVATIVE_PLATFORM = 0.25
LIBERAL_PLATFORM = 0.75
SMOOTHING_TERM = 0.01
GRUDGE_BASE = 1.06
KAPPA_STATE = 4
KAPPA_CITY = 10

SUGGESTED_ISSUES = [
    "Economic Policy",
    "Social Policy",
    "Foreign Policy",
    "Healthcare",
    "Environment",
    "Education",
    "Immigration",
    "Criminal Justice",
]

# Simulation & career rules
YEARS_PER_CYCLE = 2
MAX_HISTORICAL_CYCLES = 50
CAREER_MAX_CYCLES = 25
PRESIDENT_TERM_LIMIT = 1

# Live voting simulation
LIVE_BATCHES = 10
VOTES_PER_BATCH = 1000
VOTES_PER_DISTRICT = LIVE_BATCHES * VOTES_PER_BATCH
DIRICHLET_KAPPA = 20.0

# Spreadsheet schemas
HISTORICAL_HEADERS = [
    "Cycle",
    "President",
    "Senator 1",
    "Senator 2",
    "Senator 3",
    "House",
    "Governor",
    "State Legislature",
    "Mayor",
    "City Council",
]

SENIORITY_HEADERS = [
    "Name",
    "Level of Office",
    "Seniority",
    "Victory Size",
]

