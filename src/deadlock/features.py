"""Per-player helpers: match outcome, purchase cleaning, and net worth.

The source data has three defects, fixed here. Each was measured on
2026-09-03 and has a test in tests/test_features.py:

1. About 46% of entries in a player's `items` list are ability-point spends,
   not purchases. `clean_purchases` keeps only shop item ids.
2. 11.5% of players have an `items` list out of time order.
   `clean_purchases` sorts by game_time_s.
3. 9.0% of purchases report the player's final net worth as
   `net_worth_at_buy`, almost all of them before 10 minutes. We never read
   that field. `networth_at` rebuilds net worth from the `stats` series.

The rebuilt net worth is wrong in absolute terms. The series is sampled every
180s, so interpolating it overshoots by about 1.34x early and 1.07x late
(median error 21%). It gets the order of players right, with rank correlation
0.987 against the true values. Use it to compare players, and bucket it no
finer than quintiles.
"""

from __future__ import annotations

from typing import Any

import numpy as np

PHASE_INTERVAL_S = 600
N_PHASES = 4


def player_won(player: dict[str, Any], match: dict[str, Any]) -> bool | None:
    """Whether this player won, or None if the outcome is unknown.

    The metadata endpoint has no per-player `won` field, so this reads
    `player_match_outcome` and falls back to comparing the player's team with
    the winning team. Abandons, draws, and errored matches return None, so
    callers drop them instead of counting them as losses.
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
        return None  # a draw or an error
    return team == winner


def in_scope(
    player: dict[str, Any], match: dict[str, Any], upgrade_ids: frozenset[int]
) -> bool:
    """Whether this player belongs in the per-player tables ("in scope" in CONTEXT.md).

    A player is in scope if the outcome is known and they bought at least one
    item. Every table builder uses this. When each table decided for itself,
    the imbue table kept players the purchase table dropped, and three heroes
    ended up with imbue rates above 1.0 (#41).
    """
    if player_won(player, match) is None:
        return False
    return any(item.get("item_id") in upgrade_ids for item in player.get("items") or [])


def clean_purchases(
    player: dict[str, Any], upgrade_ids: frozenset[int]
) -> list[dict[str, Any]]:
    """One player's item purchases, sorted by game_time_s.

    Drops ability-point spends. Keeps sold items and their `sold_time_s`,
    because about 33.6% of purchases are later sold and some callers want
    everything bought while others want what was held at the end.
    """
    purchases = [
        item
        for item in player.get("items") or []
        if item.get("item_id") in upgrade_ids
    ]
    purchases.sort(key=lambda item: item["game_time_s"])
    return purchases


def networth_series(player: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    """The player's (time, net_worth) samples, starting at (0, 0).

    8.8% of purchases happen before the first sample at 180s. Without the
    (0, 0) point, np.interp would give a purchase at 13 seconds the 180s value
    of about 1,700 souls.
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
    """Rebuilt net worth at the given times.

    The values run high (see the module docstring). Only compare them with
    each other.
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
    """Each player's net worth at `at_time`, relative to the others in the match.

    Every player's value comes from the same interpolation, so the overshoot
    mostly cancels out in these ratios.
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
