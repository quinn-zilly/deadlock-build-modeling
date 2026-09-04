"""Purchase cleaning, net-worth reconstruction, and the design matrix.

Three data defects in the source must be corrected here. Each was measured on
live data (2026-09-03) and each has a regression test in tests/test_features.py:

1. ~46% of entries in a player's `items` array are ability-point spends, not
   item purchases. Filter against the asset upgrade ids.
2. 11.5% of players have `items` arrays that are not sorted by game_time_s, so
   purchase order requires an explicit sort rather than array position.
3. 9.0% of purchases report `net_worth_at_buy` equal to the player's *final*
   net worth. The corruption concentrates in the early game (26,027 of 26,054
   bad entries occur before t=600s), which is exactly where a recommender is
   most useful. The field is never read; net worth is reconstructed from the
   `stats` series instead.

On the reconstruction's accuracy: interpolating the 180s net-worth series does
NOT recover absolute souls (median relative error 21%; a systematic overshoot
of ~1.34x early decaying to ~1.07x late, because net worth is a step function
sampled coarsely). It does preserve *rank* almost exactly (Pearson 0.983, rank
correlation 0.987; within-phase quintile agreement 54-60% exact, 95-98% within
one quintile). So these values are only ever used for relative position, and
only bucketed into quintiles — deciles would imply precision we do not have.
"""

from __future__ import annotations

from typing import Any

import numpy as np

PHASE_INTERVAL_S = 600
N_PHASES = 4


def player_won(player: dict[str, Any], match: dict[str, Any]) -> bool | None:
    """Whether this player won.

    The metadata endpoint carries no per-player `won` boolean -- that exists
    only on the SQL table -- so read `player_match_outcome` and fall back to
    comparing the player's team against the match winner. Returns None when
    the outcome is genuinely unknown (abandons, draws, errored matches) so
    those rows can be dropped rather than silently counted as losses.
    """
    outcome = player.get("player_match_outcome")
    if outcome == "Win":
        return True
    if outcome == "Loss":
        return False
    if outcome in {"Penalized", "PenalizedParty"}:
        # Penalized players are recorded on the losing side.
        return False
    if outcome in {"Invalid", "NotScored"}:
        return None

    winner = match.get("winning_team")
    team = player.get("team")
    if winner in {None, "Spectator"} or team is None:
        return None
    if match.get("match_outcome") not in {None, "TeamWin"}:
        return None  # draws and errors are not usable labels
    return team == winner


def clean_purchases(
    player: dict[str, Any], upgrade_ids: frozenset[int]
) -> list[dict[str, Any]]:
    """Real item purchases for one player, in true chronological order.

    Drops ability-point spends and sorts by game_time_s (array order is not
    reliable). `sold_time_s` is preserved rather than filtered: ~33.6% of
    purchases are later sold, and "bought" vs "held to the end" are different
    questions, so the caller decides.
    """
    purchases = [
        item
        for item in player.get("items") or []
        if item.get("item_id") in upgrade_ids
    ]
    purchases.sort(key=lambda item: item["game_time_s"])
    return purchases


def networth_series(player: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    """The player's (time, net_worth) samples, anchored at the origin.

    The (0, 0) anchor matters: 8.8% of purchases happen before the first 180s
    snapshot, and without it np.interp flat-extrapolates the first sample
    backwards, crediting a 13-second purchase with ~1,700 souls.
    """
    stats = player.get("stats") or []
    times = np.fromiter((s["time_stamp_s"] for s in stats), dtype=float, count=len(stats))
    worths = np.fromiter((s["net_worth"] for s in stats), dtype=float, count=len(stats))

    order = np.argsort(times)
    times, worths = times[order], worths[order]

    if times.size == 0 or times[0] > 0:
        times = np.concatenate(([0.0], times))
        worths = np.concatenate(([0.0], worths))
    return times, worths


def networth_at(player: dict[str, Any], at_times: np.ndarray) -> np.ndarray:
    """Reconstructed net worth at arbitrary times. RELATIVE USE ONLY.

    Absolute values carry a systematic overshoot (see module docstring); only
    the ordering these induce is trustworthy.
    """
    at_times = np.asarray(at_times, dtype=float)
    if at_times.size == 0:
        return np.empty(0, dtype=float)
    times, worths = networth_series(player)
    if times.size == 0:
        return np.zeros_like(at_times)
    return np.interp(at_times, times, worths)


def phase_of(game_time_s: np.ndarray | float) -> np.ndarray | int:
    """Match phase index (0..N_PHASES-1) for a purchase time."""
    idx = np.asarray(game_time_s, dtype=float) // PHASE_INTERVAL_S
    return np.clip(idx, 0, N_PHASES - 1).astype(int)


def within_match_position(
    match: dict[str, Any], at_time: float
) -> dict[int, dict[str, float]]:
    """Each player's net worth at `at_time` relative to their own match.

    This is the more reliable of the two wealth measures. Every value is read
    from the same 180s snapshot, so the interpolation overshoot is common-mode
    and largely cancels in the ratios. It also encodes the question that
    actually drives buy decisions -- am I ahead right now? -- rather than an
    abstract population rank.
    """
    players = match.get("players") or []
    if not players:
        return {}

    slots = [p["player_slot"] for p in players]
    worths = np.array(
        [float(networth_at(p, np.array([at_time]))[0]) for p in players]
    )
    teams = [p.get("team") for p in players]

    median = float(np.median(worths)) or 1.0
    out: dict[int, dict[str, float]] = {}
    for i, slot in enumerate(slots):
        same_team = [w for w, t in zip(worths, teams) if t == teams[i]]
        enemy = [w for w, t in zip(worths, teams) if t != teams[i]]
        team_avg = float(np.mean(same_team)) if same_team else 1.0
        enemy_avg = float(np.mean(enemy)) if enemy else 1.0
        out[slot] = {
            "nw_vs_match_median": worths[i] / median,
            "nw_vs_team_avg": worths[i] / (team_avg or 1.0),
            "nw_vs_enemy_avg": worths[i] / (enemy_avg or 1.0),
            "nw_rank_in_match": float((worths < worths[i]).sum()) / max(len(worths) - 1, 1),
        }
    return out
