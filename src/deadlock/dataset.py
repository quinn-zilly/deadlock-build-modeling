"""Flatten cached match JSON into a compact per-purchase table.

The raw pages are large (~43 MB per 200 matches, so ~5 GB for a full pull).
Everything downstream needs only a small slice of that, so this module
distills each page to a purchase-level Parquet table and the raw JSON can then
be discarded.

Grain is one row per (match, player, purchase). Player- and match-level
attributes repeat across a player's purchases; that denormalization keeps the
confound work simple, since every wealth control is defined at the moment of a
specific buy.

`PURCHASE_COLUMNS` is the schema, in order:

- identity: `match_id`, `player_slot`, `account_id`, `hero_id`, `team`, `won`
- match-level: `average_badge`, `duration_s`
- player-level: `assigned_lane`, `final_net_worth`
- match state: `has_objectives` — False where the page predates
  `include_objectives`, so a null below means "not requested" rather than
  "never happened"
- match state (`OBJECTIVE_COLUMNS`): `slot10_unlock_s`, `slot11_unlock_s`,
  `slot12_unlock_s` — when this player's team destroyed its 1st, 2nd and 3rd
  enemy Walker, which is when it could hold a 10th, 11th and 12th item — and
  `midboss_kill_s`, the first Mid-Boss it claimed
- intent (`BUILD_COLUMNS`): `hero_build_id`, `pregame_hero_id`
- the purchase: `item_id`, `buy_time_s`, `phase`, `buy_index`, `sold`,
  `sold_time_s`
- wealth controls: `nw_at_buy`, `nw_vs_match_median`, `nw_vs_team_avg`,
  `nw_vs_enemy_avg`, `nw_rank_in_match`

The match-state and intent columns are nullable and mean **unknown**, never
zero: a match can end before three Walkers fall, and roughly 90% of matches are
never demo-analyzed. Pages cached before those fields were requested carry
neither key and convert to nulls rather than failing.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from . import assets, features, ingest

log = logging.getLogger(__name__)

# Match state attached per player row. Every one is nullable and must be read
# as "unknown", never as zero: a match can end before three Walkers fall, and
# roughly 90% of matches are never demo-analyzed.
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

# Null in the objective columns has two causes, and they are not the same
# claim: the Walker never fell, or the page was cached before
# include_objectives was requested. This boolean separates them, so a
# percentile is computed on the right denominator even while the cache holds
# pages of both vintages.
OBJECTIVES_PRESENT_COLUMN = "has_objectives"

# Only these carry through from the raw payload; everything else is dropped.
PURCHASE_COLUMNS = [
    "match_id", "player_slot", "account_id", "hero_id", "team", "won",
    "average_badge", "duration_s", "assigned_lane", "final_net_worth",
    OBJECTIVES_PRESENT_COLUMN, *OBJECTIVE_COLUMNS, *BUILD_COLUMNS,
    "item_id", "buy_time_s", "phase", "buy_index", "sold", "sold_time_s",
    "nw_at_buy", "nw_vs_match_median", "nw_vs_team_avg", "nw_vs_enemy_avg",
    "nw_rank_in_match",
]

# Build ids and hero ids are nullable, and ids in this project already exceed
# int32 and wrap negative silently, so these are pandas nullable integers
# rather than float-with-NaN.
NULLABLE_INT_COLUMNS = [*OBJECTIVE_COLUMNS, *BUILD_COLUMNS]

WALKER_PREFIX = "Tier2Lane"   # Tier1Lane is a Guardian, BarrackBoss a Base
                              # Guardian, Titan the Patron. Only Walkers
                              # grant item slots.

# Named rather than derived as "whoever is not the loser": `team` can also read
# Spectator, and a set difference would hand that team every Walker.
OPPONENT = {"Team0": "Team1", "Team1": "Team0"}


def _destroyed_at(objective: dict[str, Any]) -> int | None:
    """Destruction time, or None where the sentinel says it never happened.

    A `destroyed_time_s` of 0 or 1 means the objective survived the match
    (1,299 of 6,420 sampled Walker rows). Read as a time it drags every
    percentile below the median into nonsense.
    """
    t = objective.get("destroyed_time_s")
    if t is None or t <= 1:
        return None
    return int(t)


def team_match_state(match: dict[str, Any]) -> dict[str, dict[str, int | None]]:
    """Slot-unlock and Mid-Boss times, keyed by the team that benefits.

    `objectives.team` names the team that **LOST** the objective, so the slot
    goes to the other team and this inverts it. Confirmed by observing that a
    destroyed `Core` never belongs to the winning team. Getting this backwards
    produces a plausible, silently wrong answer rather than an error.

    Mid-Boss is not inverted: it is neutral, and `team_claimed` already names
    the team that took the souls, which disagrees with `team_killed` in ~13%
    of kills.
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
        winner = OPPONENT.get(objective.get("team"))   # the inversion
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
    """Purchase-level rows for one match, with wealth controls attached."""
    players = match.get("players") or []
    if not players:
        return []

    match_id = match["match_id"]
    badge = match.get("average_badge")
    duration = match.get("duration_s")

    # Cache per-player net-worth curves once; within-match position needs them
    # at arbitrary times and re-interpolating per purchase is wasteful.
    curves = {p["player_slot"]: features.networth_series(p) for p in players}
    teams = {p["player_slot"]: p.get("team") for p in players}

    # Objectives are match-level and purchases are player-level; the join is
    # by team. A page cached before include_objectives was requested has
    # neither key. It converts rather than failing, but its nulls mean
    # "not requested", so has_objectives records which it is.
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
        won = features.player_won(player, match)
        if won is None:
            continue  # abandon/draw/unscored: no usable label
        purchases = features.clean_purchases(player, upgrade_ids)
        if not purchases:
            continue

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
            # Within-match position, evaluated at this purchase's timestamp.
            # Same-snapshot comparison, so interpolation bias largely cancels.
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
    """Purchase-level DataFrame for a stream of matches."""
    upgrade_ids = upgrade_ids or assets.upgrade_ids()
    rows: list[dict[str, Any]] = []
    for match in matches:
        rows.extend(match_to_rows(match, upgrade_ids))
    if not rows:
        return _cast_nullable_ids(pd.DataFrame(columns=PURCHASE_COLUMNS))
    return _cast_nullable_ids(pd.DataFrame(rows)[PURCHASE_COLUMNS])


def _cast_nullable_ids(df: pd.DataFrame) -> pd.DataFrame:
    """Nullable integers for the columns that carry ids and may be missing."""
    for column in NULLABLE_INT_COLUMNS:
        missing = df[column].isna()
        df[column] = df[column].astype("object").where(~missing).astype("Int64")
    return df


def add_networth_quintiles(df: pd.DataFrame) -> pd.DataFrame:
    """Population net-worth quintile within each phase.

    Quintiles, not deciles: the reconstruction agrees with reported values
    54-60% of the time at quintile granularity but 95-98% within one quintile,
    so finer buckets would imply precision the measurement does not support.
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
    """Stream cached pages into one Parquet file, in chunks to bound memory."""
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

    # A cache of mixed vintage is the expected state during a partial re-pull,
    # and the stale share is invisible in the file itself unless someone
    # filters on has_objectives. Say it out loud at build time.
    if OBJECTIVES_PRESENT_COLUMN in df.columns and len(df):
        stale = float((~df[OBJECTIVES_PRESENT_COLUMN].astype(bool)).mean())
        if stale:
            log.warning(
                "%.1f%% of purchase rows come from pages cached before "
                "include_objectives; their objective columns are null meaning "
                "'not requested', not 'never happened'. Filter on %s before "
                "measuring anything from them.",
                stale * 100, OBJECTIVES_PRESENT_COLUMN,
            )
    return out_path
