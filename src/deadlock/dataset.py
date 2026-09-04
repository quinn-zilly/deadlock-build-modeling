"""Flatten cached match JSON into a compact per-purchase table.

The raw pages are large (~43 MB per 200 matches, so ~5 GB for a full pull).
Everything downstream needs only a small slice of that, so this module
distills each page to a purchase-level Parquet table and the raw JSON can then
be discarded.

Grain is one row per (match, player, purchase). Player- and match-level
attributes repeat across a player's purchases; that denormalization keeps the
confound work simple, since every wealth control is defined at the moment of a
specific buy.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from . import assets, features, ingest

log = logging.getLogger(__name__)

# Only these carry through from the raw payload; everything else is dropped.
PURCHASE_COLUMNS = [
    "match_id", "player_slot", "account_id", "hero_id", "team", "won",
    "average_badge", "duration_s", "assigned_lane", "final_net_worth",
    "item_id", "buy_time_s", "phase", "buy_index", "sold", "sold_time_s",
    "nw_at_buy", "nw_vs_match_median", "nw_vs_team_avg", "nw_vs_enemy_avg",
    "nw_rank_in_match",
]


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
        return pd.DataFrame(columns=PURCHASE_COLUMNS)
    return pd.DataFrame(rows)[PURCHASE_COLUMNS]


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
    return out_path
