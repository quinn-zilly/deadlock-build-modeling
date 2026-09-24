"""Convert cached match JSON into one purchase table (Parquet).

The raw pages are large and downstream code needs little of them, so this
keeps only the columns below.

One row per (match, player, purchase). Match and player columns repeat on
each of a player's purchases.

`PURCHASE_COLUMNS`, in order:

- identity: `match_id`, `player_slot`, `account_id`, `hero_id`, `team`, `won`
- match: `average_badge`, `duration_s`
- player: `assigned_lane`, `final_net_worth`
- `has_objectives`: False if the page was cached before objectives were
  requested
- `OBJECTIVE_COLUMNS`: `slot10_unlock_s`, `slot11_unlock_s`, and
  `slot12_unlock_s` are when the player's team destroyed its 1st, 2nd, and
  3rd enemy Walker, which unlocks the 10th, 11th, and 12th item slot.
  `midboss_kill_s` is the first Mid-Boss the team claimed.
- `BUILD_COLUMNS`: `hero_build_id`, `pregame_hero_id`
- the purchase: `item_id`, `buy_time_s`, `phase`, `buy_index`, `sold`,
  `sold_time_s`
- net worth: `nw_at_buy`, `nw_vs_match_median`, `nw_vs_team_avg`,
  `nw_vs_enemy_avg`, `nw_rank_in_match`

In the six columns below, null has a specific meaning and is never zero.
Measured per player-match on the current table (296,478 player-matches over
24,999 matches, all with `has_objectives`):

| Column | Present | Median | Null means |
| --- | ---: | ---: | --- |
| `slot10_unlock_s` | 96.8% | 1,117s | that team never took an enemy Walker |
| `slot11_unlock_s` | 86.6% | 1,400s | it never took a second |
| `slot12_unlock_s` | 70.7% | 1,669s | it never took a third, so it held 11 slots at most |
| `midboss_kill_s` | 66.9% | 1,584s | that team claimed no Mid-Boss |
| `hero_build_id` | 0.21% | - | the match hasn't been analyzed yet, not "no build selected" |
| `pregame_hero_id` | 0.35% | - | the same |

Only the team that destroys a Walker gets the slot, so most teams never reach
12 slots. The 70.7% is real, not missing data. The two build columns are
nearly empty because the pull covers the newest few days and match analysis
runs weeks behind. `scripts/pull_data.py` explains what to do about that.

Pages cached before objectives were requested have no objective data, and
those columns come out null. `has_objectives` is False on those rows, so a
null there means "not requested", not "never happened".
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from . import assets, features, ingest

log = logging.getLogger(__name__)

# Per-team match events. All nullable, and null never means zero: a match can
# end before three Walkers fall, and most matches are never analyzed.
SLOT_COLUMNS = [
    "slot10_unlock_s",   # the player's team's 1st enemy Walker kill
    "slot11_unlock_s",   # its 2nd
    "slot12_unlock_s",   # its 3rd
]
OBJECTIVE_COLUMNS = [
    *SLOT_COLUMNS,
    "midboss_kill_s",    # first Mid-Boss the player's team claimed
]
BUILD_COLUMNS = [
    "hero_build_id",     # community build selected at match start
    "pregame_hero_id",   # hero locked before the swap window
]

# A null objective column means either the Walker never fell or the page was
# cached before objectives were requested. This column tells the two apart.
OBJECTIVES_PRESENT_COLUMN = "has_objectives"

# The output columns. Everything else in the raw data is dropped.
PURCHASE_COLUMNS = [
    "match_id", "player_slot", "account_id", "hero_id", "team", "won",
    "average_badge", "duration_s", "assigned_lane", "final_net_worth",
    OBJECTIVES_PRESENT_COLUMN, *OBJECTIVE_COLUMNS, *BUILD_COLUMNS,
    "item_id", "buy_time_s", "phase", "buy_index", "sold", "sold_time_s",
    "nw_at_buy", "nw_vs_match_median", "nw_vs_team_avg", "nw_vs_enemy_avg",
    "nw_rank_in_match",
]

# Stored as pandas Int64 so they can be null and still be integers. Don't
# narrow them to int32: some ids in this project don't fit and wrap negative
# without an error.
NULLABLE_INT_COLUMNS = [*OBJECTIVE_COLUMNS, *BUILD_COLUMNS]

# Walkers are "Tier2Lane" objectives. Tier1Lane is a Guardian, BarrackBoss a
# Base Guardian, and Titan the Patron. Only Walkers unlock item slots.
WALKER_PREFIX = "Tier2Lane"

# Written out because `team` can also be "Spectator", which must not get any
# Walkers.
OPPONENT = {"Team0": "Team1", "Team1": "Team0"}


def _destroyed_at(objective: dict[str, Any]) -> int | None:
    """The objective's destruction time, or None if it was never destroyed.

    A `destroyed_time_s` of 0 or 1 means the objective survived the match
    (1,299 of 6,420 sampled Walker rows).
    """
    t = objective.get("destroyed_time_s")
    if t is None or t <= 1:
        return None
    return int(t)


def team_match_state(match: dict[str, Any]) -> dict[str, dict[str, int | None]]:
    """Slot-unlock and Mid-Boss times for each team.

    `objectives.team` is the team that lost the objective, so each Walker
    kill goes to the other team. (A destroyed `Core` is never on the winning
    team, which confirms this.) Getting it backwards raises no error, just
    wrong numbers.

    Mid-Boss is neutral. `team_claimed` is the team that got the souls, and
    it differs from `team_killed` in about 13% of kills.
    """
    teams = {p.get("team") for p in (match.get("players") or [])}
    teams.discard(None)
    state = {team: {col: None for col in OBJECTIVE_COLUMNS} for team in teams}

    kills: dict[str, list[int]] = {team: [] for team in teams}
    for objective in match.get("objectives") or []:
        if not str(objective.get("team_objective") or "").startswith(WALKER_PREFIX):
            continue
        destroyed = _destroyed_at(objective)
        if destroyed is None:
            continue
        winner = OPPONENT.get(objective.get("team"))   # the team that killed it
        if winner in kills:
            kills[winner].append(destroyed)

    for team, times in kills.items():
        for column, t in zip(SLOT_COLUMNS, sorted(times)):
            state[team][column] = t

    for boss in match.get("mid_boss") or []:
        destroyed = _destroyed_at(boss)
        claimant = boss.get("team_claimed") or boss.get("team_killed")
        if destroyed is None or claimant not in state:
            continue
        current = state[claimant]["midboss_kill_s"]
        if current is None or destroyed < current:
            state[claimant]["midboss_kill_s"] = destroyed

    return state


def _optional_id(value: Any) -> int | None:
    """An id, or None where the API omitted it or sent 0 for "none"."""
    if value is None or value == 0:
        return None
    return int(value)


def match_to_rows(
    match: dict[str, Any], upgrade_ids: frozenset[int]
) -> list[dict[str, Any]]:
    """One row per purchase for every in-scope player in a match."""
    players = match.get("players") or []
    if not players:
        return []

    match_id = match["match_id"]
    badge = match.get("average_badge")
    duration = match.get("duration_s")

    # Every purchase compares against every player's net worth, so build each
    # player's series once.
    curves = {p["player_slot"]: features.networth_series(p) for p in players}
    teams = {p["player_slot"]: p.get("team") for p in players}

    # Objectives are per team, so each player gets their team's values.
    state = team_match_state(match)
    empty_state = {col: None for col in OBJECTIVE_COLUMNS}
    has_objectives = "objectives" in match

    def nw_of(slot: int, t: float) -> float:
        times, worths = curves[slot]
        if times.size == 0:
            return 0.0
        return float(np.interp(t, times, worths))

    rows: list[dict[str, Any]] = []
    for player in players:
        slot = player["player_slot"]
        if not features.in_scope(player, match, upgrade_ids):
            continue  # unknown outcome, or bought nothing
        won = features.player_won(player, match)
        purchases = features.clean_purchases(player, upgrade_ids)

        player_state = state.get(teams[slot], empty_state)
        build_state = {
            "hero_build_id": _optional_id(player.get("hero_build_id")),
            "pregame_hero_id": _optional_id(player.get("pregame_hero_id")),
        }

        buy_times = np.array([p["game_time_s"] for p in purchases], dtype=float)
        own_nw = features.networth_at(player, buy_times)
        phases = features.phase_of(buy_times)

        for idx, (purchase, t, nw, phase) in enumerate(
            zip(purchases, buy_times, own_nw, phases)
        ):
            # Net worth relative to the other players at this moment. Everyone
            # is interpolated the same way, so the overshoot mostly cancels.
            others = [nw_of(s, t) for s in curves]
            same = [nw_of(s, t) for s, tm in teams.items() if tm == teams[slot]]
            enemy = [nw_of(s, t) for s, tm in teams.items() if tm != teams[slot]]
            median = float(np.median(others)) or 1.0
            team_avg = float(np.mean(same)) if same else 1.0
            enemy_avg = float(np.mean(enemy)) if enemy else 1.0

            sold_time = purchase.get("sold_time_s") or 0
            rows.append(
                {
                    "match_id": match_id,
                    "player_slot": slot,
                    "account_id": player.get("account_id"),
                    "hero_id": player.get("hero_id"),
                    "team": teams[slot],
                    "won": won,
                    "average_badge": badge,
                    "duration_s": duration,
                    "assigned_lane": player.get("assigned_lane"),
                    "final_net_worth": player.get("net_worth"),
                    OBJECTIVES_PRESENT_COLUMN: has_objectives,
                    **player_state,
                    **build_state,
                    "item_id": purchase["item_id"],
                    "buy_time_s": int(t),
                    "phase": int(phase),
                    "buy_index": idx,
                    "sold": bool(sold_time),
                    "sold_time_s": int(sold_time),
                    "nw_at_buy": float(nw),
                    "nw_vs_match_median": float(nw / median),
                    "nw_vs_team_avg": float(nw / (team_avg or 1.0)),
                    "nw_vs_enemy_avg": float(nw / (enemy_avg or 1.0)),
                    "nw_rank_in_match": float(
                        sum(1 for o in others if o < nw) / max(len(others) - 1, 1)
                    ),
                }
            )
    return rows


def build_purchase_table(
    matches: Iterable[dict[str, Any]], upgrade_ids: frozenset[int] | None = None
) -> pd.DataFrame:
    """The purchase table for a stream of matches."""
    upgrade_ids = upgrade_ids or assets.upgrade_ids()
    rows: list[dict[str, Any]] = []
    for match in matches:
        rows.extend(match_to_rows(match, upgrade_ids))
    if not rows:
        return _cast_nullable_ids(pd.DataFrame(columns=PURCHASE_COLUMNS))
    return _cast_nullable_ids(pd.DataFrame(rows)[PURCHASE_COLUMNS])


def _cast_nullable_ids(df: pd.DataFrame) -> pd.DataFrame:
    """Convert NULLABLE_INT_COLUMNS to pandas Int64."""
    for column in NULLABLE_INT_COLUMNS:
        missing = df[column].isna()
        df[column] = df[column].astype("object").where(~missing).astype("Int64")
    return df


def add_networth_quintiles(df: pd.DataFrame) -> pd.DataFrame:
    """Add `nw_quintile`: each purchase's net-worth quintile within its phase.

    The rebuilt net worth lands in the right quintile 54-60% of the time and
    within one quintile 95-98% of the time, so finer buckets would be noise.
    """
    df = df.copy()
    df["nw_quintile"] = (
        df.groupby("phase")["nw_at_buy"]
        .transform(lambda s: pd.qcut(s.rank(method="first"), 5, labels=False))
        .astype("int8")
    )
    return df


def convert_pages(
    pages: list[Path], out_path: Path, chunk_size: int = 2_000
) -> Path:
    """Convert cached pages into one Parquet file, `chunk_size` matches at a time."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    upgrade_ids = assets.upgrade_ids()

    frames: list[pd.DataFrame] = []
    buffer: list[dict[str, Any]] = []
    total = 0

    for match in ingest.iter_matches(pages):
        buffer.append(match)
        if len(buffer) >= chunk_size:
            frames.append(build_purchase_table(buffer, upgrade_ids))
            total += len(buffer)
            log.info("converted %d matches", total)
            buffer.clear()

    if buffer:
        frames.append(build_purchase_table(buffer, upgrade_ids))
        total += len(buffer)

    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    df = add_networth_quintiles(df)
    df.to_parquet(out_path, index=False)
    log.info("wrote %s (%d purchases from %d matches)", out_path, len(df), total)

    # Warn if some pages predate objectives, which happens during a partial
    # re-pull. Nothing in the file shows it unless you check has_objectives.
    if OBJECTIVES_PRESENT_COLUMN in df.columns and len(df):
        stale = float((~df[OBJECTIVES_PRESENT_COLUMN].astype(bool)).mean())
        if stale:
            log.warning(
                "%.1f%% of purchase rows come from pages cached before objectives "
                "were requested. In those rows a null objective column means the "
                "data wasn't requested, not that the objective never fell. Filter "
                "on %s before measuring objectives.",
                stale * 100, OBJECTIVES_PRESENT_COLUMN,
            )
    return out_path
