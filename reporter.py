"""Live election night reporting and historical data presentation."""

import random
from typing import Callable, Optional

import numpy as np

from constants import LIVE_BATCHES, VOTES_PER_DISTRICT
from custom_types import (
    Candidate,
    District,
    LiveBatchResult,
    LiveRaceSnapshot,
    LiveRaceSpec,
    Party,
    SeatKey,
)
from simulator import compute_vote_percentages, precompute_race_probabilities, simulate_live_batch


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
    title: str = "ELECTION NIGHT LIVE",
) -> str:
    """Format a live election batch report string."""
    lines: list[str] = [
        f"\n=== {title}: Batch {batch_result.batch_num}/{batch_result.total_batches} ==="
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
            if (
                player_party in cand_by_party
                and player_party not in (leader, sorted_parties[1] if len(sorted_parties) > 1 else -1)
            ):
                in_cand = cand_by_party[player_party]
                summary += f" | {in_cand.name} ({parties[player_party].name}) {snap.candidate_shares[player_party]:.2f}%"
            lines.append(summary)

    return "\n".join(lines)


def format_final_results(
    final_batch: LiveBatchResult,
    races: list[LiveRaceSpec],
    parties: list[Party],
    title: str = "FINAL CALLED ELECTION RESULTS",
) -> str:
    """Format final called winners after all live batches complete."""
    lines = [f"\n=== {title} ==="]
    race_by_key = {race.seat_key: race for race in races}
    for snap in final_batch.race_snapshots:
        race = race_by_key[snap.seat_key]
        cand_by_party = {c.party_index: c for c in race.candidates}
        winner = cand_by_party[snap.leader_party]
        win_pct = snap.candidate_shares[snap.leader_party]
        tag = " [YOUR RACE]" if (snap.has_player or race.has_player) else ""
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
    """Run 10 batches of 1000 votes/district. If leader < 50%, top 2 advance to runoff."""
    if not races:
        output_fn("\nNo elections in your live scope this cycle.")
        return {}, []

    prob_matrices = [precompute_race_probabilities(race) for race in races]
    cumulative_votes: dict[SeatKey, dict[int, int]] = {
        race.seat_key: {cand.party_index: 0 for cand in race.candidates}
        for race in races
    }
    batch_results: list[LiveBatchResult] = []

    # Round 1: 10 batches
    for batch_num in range(1, LIVE_BATCHES + 1):
        snapshots: list[LiveRaceSnapshot] = []
        for race, prob_mat in zip(races, prob_matrices):
            batch_counts = simulate_live_batch(
                race, prob_matrix=prob_mat, rng=rng, np_rng=np_rng
            )
            race_totals = cumulative_votes[race.seat_key]
            for cand, count in zip(race.candidates, batch_counts):
                race_totals[cand.party_index] += count

            actual_shares = compute_vote_percentages(race_totals)
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
                    candidate_shares=actual_shares,
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

    round1_final_batch = batch_results[-1]

    # Evaluate Round 1 results: check which races require a runoff
    decided_outcomes: dict[SeatKey, tuple[int, float]] = {}
    runoff_specs: list[LiveRaceSpec] = []
    runoff_top_two: dict[SeatKey, list[Candidate]] = {}

    for race in races:
        race_totals = cumulative_votes[race.seat_key]
        total_votes = sum(race_totals.values())
        sorted_cands = sorted(
            race.candidates,
            key=lambda c: (race_totals[c.party_index], -c.party_index),
            reverse=True,
        )
        leader = sorted_cands[0]
        leader_pct = (
            (race_totals[leader.party_index] / total_votes) * 100.0
            if total_votes > 0
            else 0.0
        )

        if len(race.candidates) <= 2 or leader_pct >= 50.0:
            decided_outcomes[race.seat_key] = (leader.party_index, leader_pct)
        else:
            top_two = [sorted_cands[0], sorted_cands[1]]
            runoff_top_two[race.seat_key] = top_two
            runoff_specs.append(
                LiveRaceSpec(
                    seat_key=race.seat_key,
                    tier=race.tier,
                    label=race.label,
                    districts=race.districts,
                    candidates=top_two,
                    has_player=any(c.is_player for c in top_two),
                    incumbent_party=race.incumbent_party,
                    incumbent_cycles=race.incumbent_cycles,
                )
            )

    if not runoff_specs:
        output_fn(format_final_results(round1_final_batch, races, parties))
        return decided_outcomes, batch_results

    # Announce Round 1 outcomes
    output_fn("\n=== ROUND 1 ELECTION RESULTS ===")
    race_by_key = {r.seat_key: r for r in races}
    for snap in round1_final_batch.race_snapshots:
        race = race_by_key[snap.seat_key]
        cand_by_party = {c.party_index: c for c in race.candidates}
        tag = " [YOUR RACE]" if snap.has_player else ""
        if snap.seat_key in decided_outcomes:
            winner_party, win_pct = decided_outcomes[snap.seat_key]
            winner = cand_by_party[winner_party]
            output_fn(
                f"  {snap.label}{tag}: {winner.name} ({parties[winner_party].name}) WINS outright with {win_pct:.2f}%"
            )
        else:
            top_two = runoff_top_two[snap.seat_key]
            c1, c2 = top_two[0], top_two[1]
            pct1 = snap.candidate_shares[c1.party_index]
            pct2 = snap.candidate_shares[c2.party_index]
            output_fn(
                f"  {snap.label}{tag}: No candidate reached 50%. RUNOFF: "
                f"{c1.name} ({parties[c1.party_index].name}) {pct1:.2f}% vs. "
                f"{c2.name} ({parties[c2.party_index].name}) {pct2:.2f}%"
            )

    input_fn(
        f"\nRound 1 complete. Press Enter for Runoff Batch 1/{LIVE_BATCHES} (Q=quit, R=restart): "
    )

    # Runoff round: 10 batches for the top 2 in each advancing race
    runoff_prob_matrices = [precompute_race_probabilities(r) for r in runoff_specs]
    runoff_cumulative_votes: dict[SeatKey, dict[int, int]] = {
        r.seat_key: {c.party_index: 0 for c in r.candidates}
        for r in runoff_specs
    }

    runoff_final_batch: Optional[LiveBatchResult] = None
    for batch_num in range(1, LIVE_BATCHES + 1):
        runoff_snapshots: list[LiveRaceSnapshot] = []
        for r_spec, r_prob_mat in zip(runoff_specs, runoff_prob_matrices):
            batch_counts = simulate_live_batch(
                r_spec, prob_matrix=r_prob_mat, rng=rng, np_rng=np_rng
            )
            r_totals = runoff_cumulative_votes[r_spec.seat_key]
            for cand, count in zip(r_spec.candidates, batch_counts):
                r_totals[cand.party_index] += count

            actual_shares = compute_vote_percentages(r_totals)
            leader_party = max(
                r_totals.keys(),
                key=lambda p: (r_totals[p], -p),
            )
            num_dist = len(r_spec.districts)
            runoff_snapshots.append(
                LiveRaceSnapshot(
                    seat_key=r_spec.seat_key,
                    tier=r_spec.tier,
                    label=r_spec.label,
                    has_player=r_spec.has_player,
                    votes_reported=batch_num * (VOTES_PER_DISTRICT // LIVE_BATCHES) * num_dist,
                    total_votes=VOTES_PER_DISTRICT * num_dist,
                    candidate_votes=dict(r_totals),
                    candidate_shares=actual_shares,
                    leader_party=leader_party,
                )
            )

        runoff_batch_result = LiveBatchResult(
            batch_num=batch_num,
            total_batches=LIVE_BATCHES,
            race_snapshots=runoff_snapshots,
        )
        batch_results.append(runoff_batch_result)
        runoff_final_batch = runoff_batch_result
        output_fn(
            format_batch_report(
                runoff_batch_result,
                runoff_specs,
                parties,
                player_party,
                title="RUNOFF ELECTION NIGHT LIVE",
            )
        )
        input_fn(
            f"\nRunoff Batch {batch_num}/{LIVE_BATCHES} complete. Press Enter to continue (Q=quit, R=restart): "
        )

    assert runoff_final_batch is not None
    for snap in runoff_final_batch.race_snapshots:
        decided_outcomes[snap.seat_key] = (
            snap.leader_party,
            snap.candidate_shares[snap.leader_party],
        )

    # Combine final snapshots for all races into one final report
    runoff_final_by_key = {s.seat_key: s for s in runoff_final_batch.race_snapshots}
    round1_final_by_key = {s.seat_key: s for s in round1_final_batch.race_snapshots}
    combined_final_snaps: list[LiveRaceSnapshot] = []
    for race in races:
        if race.seat_key in runoff_final_by_key:
            snap = runoff_final_by_key[race.seat_key]
            combined_final_snaps.append(
                LiveRaceSnapshot(
                    seat_key=race.seat_key,
                    tier=race.tier,
                    label=race.label,
                    has_player=race.has_player,
                    votes_reported=snap.votes_reported,
                    total_votes=snap.total_votes,
                    candidate_votes=snap.candidate_votes,
                    candidate_shares=snap.candidate_shares,
                    leader_party=snap.leader_party,
                )
            )
        else:
            combined_final_snaps.append(round1_final_by_key[race.seat_key])

    final_batch = LiveBatchResult(
        batch_num=LIVE_BATCHES,
        total_batches=LIVE_BATCHES,
        race_snapshots=combined_final_snaps,
    )
    output_fn(format_final_results(final_batch, races, parties))

    return decided_outcomes, batch_results


def run_live_primary_race(
    seat_key: SeatKey,
    tier: int,
    label: str,
    districts: list[District],
    player_cand: Candidate,
    opponent_cand: Candidate,
    party: Party,
    input_fn: Callable[[str], str],
    output_fn: Callable[[str], None] = print,
    rng: Optional[random.Random] = None,
    np_rng: Optional[np.random.Generator] = None,
) -> tuple[Candidate, float]:
    """Run a 10-batch live primary election between player and an in-party opponent."""
    race = LiveRaceSpec(
        seat_key=seat_key,
        tier=tier,
        label=f"PRIMARY: {label}",
        districts=districts,
        candidates=[player_cand, opponent_cand],
        has_player=True,
    )
    prob_mat = precompute_race_probabilities(race)
    cand_votes = [0, 0]
    num_dist = len(districts)
    total_votes = VOTES_PER_DISTRICT * num_dist

    output_fn(f"\n========================================")
    output_fn(f"LIVE PRIMARY ELECTION: {label}")
    output_fn(f"Contenders: {player_cand.name} * (You) vs. {opponent_cand.name} ({party.name})")
    output_fn(f"========================================")

    for batch_num in range(1, LIVE_BATCHES + 1):
        batch_counts = simulate_live_batch(
            race, prob_matrix=prob_mat, rng=rng, np_rng=np_rng
        )
        cand_votes[0] += batch_counts[0]
        cand_votes[1] += batch_counts[1]
        reported_votes = batch_num * (VOTES_PER_DISTRICT // LIVE_BATCHES) * num_dist
        pct_rep = int((reported_votes / total_votes) * 100)

        tot = cand_votes[0] + cand_votes[1]
        p0_pct = (cand_votes[0] / tot) * 100.0 if tot > 0 else 50.0
        p1_pct = (cand_votes[1] / tot) * 100.0 if tot > 0 else 50.0

        output_fn(
            f"\n=== PRIMARY ELECTION LIVE: Batch {batch_num}/{LIVE_BATCHES} ({pct_rep}% reporting) ===\n"
            f"{label}:\n"
            f"  - {player_cand.name} * ({party.name}): {cand_votes[0]:,} votes ({p0_pct:.2f}%)\n"
            f"  - {opponent_cand.name} ({party.name}): {cand_votes[1]:,} votes ({p1_pct:.2f}%)"
        )
        input_fn(
            f"\nPrimary Batch {batch_num}/{LIVE_BATCHES} complete. Press Enter to continue (Q=quit, R=restart): "
        )

    tot = cand_votes[0] + cand_votes[1]
    p0_pct = (cand_votes[0] / tot) * 100.0 if tot > 0 else 50.0
    p1_pct = (cand_votes[1] / tot) * 100.0 if tot > 0 else 50.0

    if cand_votes[0] >= cand_votes[1]:
        winner = player_cand
        win_pct = p0_pct
    else:
        winner = opponent_cand
        win_pct = p1_pct

    output_fn(f"\n=== FINAL PRIMARY ELECTION RESULTS ===")
    you_tag = " *" if winner.is_player else ""
    output_fn(
        f"  {label}: {winner.name}{you_tag} ({party.name}) WINS PRIMARY with {win_pct:.2f}%!\n"
    )
    return winner, win_pct


