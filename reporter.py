"""Live election night reporting and historical data presentation."""

import random
from typing import Callable, Optional

import numpy as np

from constants import LIVE_BATCHES, VOTES_PER_DISTRICT
from custom_types import (
    LiveBatchResult,
    LiveRaceSnapshot,
    LiveRaceSpec,
    Party,
    SeatKey,
)
from simulator import compute_rcv_percentages, precompute_race_probabilities, simulate_live_batch


def report_historical_summary(
    rows: list[dict],
    parties: list[Party],
    output_fn: Callable[[str], None] = print,
) -> None:
    """Print a readable summary of simulated historical election data."""
    output_fn("\n=== HISTORICAL ELECTION DATA ===")
    output_fn("Party Index Legend:")
    for party in parties:
        output_fn(f"  [{party.index}] {party.name} (Platform: {party.platform})")

    if not rows:
        output_fn("No historical cycles were simulated.")
        return

    cols = [
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
    output_fn(f"\nSimulated {len(rows)} historical cycle(s) (Cycles {rows[0]['Cycle']}..{rows[-1]['Cycle']}):")
    header_line = "Cycle | " + " | ".join(f"{c[:9]:>9}" for c in cols)
    output_fn(header_line)
    output_fn("-" * len(header_line))
    for row in rows:
        vals = " | ".join(f"{str(row[c]):>9}" for c in cols)
        output_fn(f"{row['Cycle']:>5} | {vals}")

    output_fn("\nParty Win Share Summary across Simulated Cycles:")
    for col in cols:
        counts = {p.index: 0 for p in parties}
        for row in rows:
            idx = row[col]
            if idx in counts:
                counts[idx] += 1
        summary = ", ".join(
            f"P{p.index}={counts[p.index]}" for p in parties
        )
        output_fn(f"  {col:<18}: {summary}")


def format_batch_report(
    batch_result: LiveBatchResult,
    races: list[LiveRaceSpec],
    parties: list[Party],
    player_party: int,
) -> str:
    """Format a live election batch report string."""
    lines: list[str] = [
        f"\n=== ELECTION NIGHT LIVE: Batch {batch_result.batch_num}/{batch_result.total_batches} ==="
    ]
    race_by_key = {race.seat_key: race for race in races}
    show_all_details = len(races) <= 3

    for snap in batch_result.race_snapshots:
        race = race_by_key[snap.seat_key]
        cand_by_party = {c.party_index: c for c in race.candidates}
        pct_reporting = int((snap.votes_reported / snap.total_votes) * 100)
        tag = " [YOUR RACE]" if snap.has_player else ""

        if show_all_details or snap.has_player:
            lines.append(
                f"\n{snap.label}{tag} ({snap.votes_reported:,}/{snap.total_votes:,} votes, {pct_reporting}% reporting):"
            )
            sorted_parties = sorted(
                snap.candidate_votes.keys(),
                key=lambda p: (snap.candidate_votes[p], -p),
                reverse=True,
            )
            for p_idx in sorted_parties:
                cand = cand_by_party[p_idx]
                votes = snap.candidate_votes[p_idx]
                pct = snap.candidate_shares[p_idx]
                you_mark = " *" if cand.is_player else ""
                lines.append(
                    f"  - {cand.name}{you_mark} ({parties[p_idx].name}): {votes:,} votes ({pct:.2f}%)"
                )
        else:
            sorted_parties = sorted(
                snap.candidate_votes.keys(),
                key=lambda p: (snap.candidate_votes[p], -p),
                reverse=True,
            )
            leader = sorted_parties[0]
            leader_cand = cand_by_party[leader]
            leader_pct = snap.candidate_shares[leader]
            summary = (
                f"  {snap.label} ({pct_reporting}%): "
                f"{leader_cand.name} ({parties[leader].name}) leads {leader_pct:.2f}%"
            )
            if len(sorted_parties) > 1:
                runner = sorted_parties[1]
                runner_cand = cand_by_party[runner]
                runner_pct = snap.candidate_shares[runner]
                summary += f" | {runner_cand.name} ({parties[runner].name}) {runner_pct:.2f}%"
            if player_party not in (leader, sorted_parties[1] if len(sorted_parties) > 1 else -1):
                in_cand = cand_by_party[player_party]
                summary += f" | {in_cand.name} ({parties[player_party].name}) {snap.candidate_shares[player_party]:.2f}%"
            lines.append(summary)

    return "\n".join(lines)


def format_final_results(
    final_batch: LiveBatchResult,
    races: list[LiveRaceSpec],
    parties: list[Party],
) -> str:
    """Format final called winners after all 10 live batches complete."""
    lines = ["\n=== FINAL CALLED ELECTION RESULTS ==="]
    race_by_key = {race.seat_key: race for race in races}
    for snap in final_batch.race_snapshots:
        race = race_by_key[snap.seat_key]
        cand_by_party = {c.party_index: c for c in race.candidates}
        winner = cand_by_party[snap.leader_party]
        win_pct = snap.candidate_shares[snap.leader_party]
        tag = " [YOUR RACE]" if snap.has_player else ""
        lines.append(
            f"  {snap.label}{tag}: {winner.name} ({parties[snap.leader_party].name}) WINS with {win_pct:.2f}%"
        )
    return "\n".join(lines)


def run_live_elections(
    races: list[LiveRaceSpec],
    parties: list[Party],
    player_party: int,
    input_fn: Callable[[str], str],
    output_fn: Callable[[str], None] = print,
    rng: Optional[random.Random] = None,
    np_rng: Optional[np.random.Generator] = None,
) -> tuple[dict[SeatKey, tuple[int, float]], list[LiveBatchResult]]:
    """Run 10 batches of 1000 votes/district, reporting and prompting per batch."""
    if not races:
        output_fn("\nNo elections in your live scope this cycle.")
        return {}, []

    prob_matrices = [precompute_race_probabilities(race) for race in races]
    cumulative_votes: dict[SeatKey, dict[int, int]] = {
        race.seat_key: {cand.party_index: 0 for cand in race.candidates}
        for race in races
    }
    num_parties = len(parties)
    batch_results: list[LiveBatchResult] = []

    for batch_num in range(1, LIVE_BATCHES + 1):
        snapshots: list[LiveRaceSnapshot] = []
        for race, prob_mat in zip(races, prob_matrices):
            batch_counts = simulate_live_batch(
                race, prob_matrix=prob_mat, rng=rng, np_rng=np_rng
            )
            race_totals = cumulative_votes[race.seat_key]
            for cand, count in zip(race.candidates, batch_counts):
                race_totals[cand.party_index] += count

            rcv_shares = compute_rcv_percentages(race_totals, num_parties)
            leader_party = max(
                race_totals.keys(),
                key=lambda p: (race_totals[p], -p),
            )
            num_dist = len(race.districts)
            snapshots.append(
                LiveRaceSnapshot(
                    seat_key=race.seat_key,
                    tier=race.tier,
                    label=race.label,
                    has_player=race.has_player,
                    votes_reported=batch_num * (VOTES_PER_DISTRICT // LIVE_BATCHES) * num_dist,
                    total_votes=VOTES_PER_DISTRICT * num_dist,
                    candidate_votes=dict(race_totals),
                    candidate_shares=rcv_shares,
                    leader_party=leader_party,
                )
            )

        batch_result = LiveBatchResult(
            batch_num=batch_num,
            total_batches=LIVE_BATCHES,
            race_snapshots=snapshots,
        )
        batch_results.append(batch_result)
        output_fn(format_batch_report(batch_result, races, parties, player_party))
        input_fn(
            f"\nBatch {batch_num}/{LIVE_BATCHES} complete. Press Enter to continue (Q=quit, R=restart): "
        )

    final_batch = batch_results[-1]
    output_fn(format_final_results(final_batch, races, parties))

    outcomes: dict[SeatKey, tuple[int, float]] = {}
    for snap in final_batch.race_snapshots:
        outcomes[snap.seat_key] = (
            snap.leader_party,
            snap.candidate_shares[snap.leader_party],
        )
    return outcomes, batch_results

