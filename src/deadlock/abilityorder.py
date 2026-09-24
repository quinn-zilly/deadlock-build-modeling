"""Ability order: which ability gets each point.

This recommends the order, not the final levels. By match end everyone has
maxed everything (Ivy's four final means are 3.62, 3.70, 3.71, and 3.82). What
differs is which ability gets maxed first and spends most of the match at
level 4.

It uses the same backoff chain as items (`sequence.py`). `point_frame`
reshapes ability points to look like purchases, with the signature slot as
the item. There are 4 choices per step instead of 173, so the specific levels
of the chain have much more data than they do for items.

The model predicts the slot. The level follows from how many points the slot
already has.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import abilities, assets, sequence
from .state import THIN_EVIDENCE, GameState

log = logging.getLogger(__name__)

# Four signature slots with four levels each. The only rule is that a slot at
# level 4 can't take another point.
MAX_LEVEL = abilities.MAX_ABILITY_LEVEL
N_SLOTS = abilities.N_SIGNATURE_SLOTS
MAX_POINTS = N_SLOTS * MAX_LEVEL

# Cost of each level as (currency type, change), copied from `/v1/builds`.
# Unlocking costs 1 of type 2. Levels 2, 3, and 4 cost 1, 2, and 5 of type 1.
LEVEL_COST = {1: (2, -1), 2: (1, -1), 3: (1, -2), 4: (1, -5)}


@dataclass(frozen=True)
class AbilityPoint:
    """One point in a recommended order, with the backoff level and count behind it."""

    position: int
    slot: int
    ability_id: int
    ability_name: str
    level: int
    game_time_s: float
    probability: float
    n: int
    backoff_level: str

    @property
    def thin(self) -> bool:
        return self.n < THIN_EVIDENCE

    def __str__(self) -> str:
        line = (
            f"{self.position + 1:2d}. {self.ability_name:22s} -> level {self.level}  "
            f"~{int(self.game_time_s) // 60}min  p={self.probability:.3f} "
            f"(n={self.n:,}, {self.backoff_level})"
        )
        return line + "  [thin]" if self.thin else line


def point_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Ability points in the shape of a purchase table, for `sequence.fit`.

    `item_id` is the signature slot, `buy_index` the point's position, and
    `buy_time_s` its game time.

    Drops unmapped abilities (0.01% of entries, all Silver's werewolf
    abilities), since the tool can't name them. Positions are numbered after
    the drop so they have no gaps.
    """
    keys = ["match_id", "player_slot"]
    valid = df[df["signature_slot"] != abilities.UNMAPPED_SLOT]
    ordered = valid.sort_values(keys + ["game_time_s"]).copy()
    frame = pd.DataFrame(
        {
            "match_id": ordered["match_id"].to_numpy(np.int64),
            "player_slot": ordered["player_slot"].to_numpy(np.int64),
            "hero_id": ordered["hero_id"].to_numpy(np.int64),
            "item_id": ordered["signature_slot"].to_numpy(np.int64),
            "buy_index": ordered.groupby(keys).cumcount().to_numpy(np.int64),
            "buy_time_s": ordered["game_time_s"].to_numpy(np.int64),
        }
    )
    # Optional. Without it the model still fits but can't be badge-weighted.
    if "average_badge" in ordered:
        frame["average_badge"] = ordered["average_badge"].to_numpy()
    return frame


def attach_badges(df: pd.DataFrame, purchases: pd.DataFrame) -> pd.DataFrame:
    """Copy each player's badge from the purchase table onto their ability rows.

    The abilities table has no badge, so badge weighting needs this first.
    Players with no purchase row get a null badge, which `row_weights` gives
    weight 1. Filling 0 instead would give them almost no weight.
    """
    badges = (
        purchases[["match_id", "player_slot", "average_badge"]]
        .drop_duplicates(subset=["match_id", "player_slot"])
    )
    return df.drop(columns=["average_badge"], errors="ignore").merge(
        badges, on=["match_id", "player_slot"], how="left"
    )


def fit(
    df: pd.DataFrame,
    archetypes: pd.DataFrame | None = None,
    **kwargs,
) -> sequence.SequenceModel:
    """Fit the backoff chain to ability points. Takes the same options as `sequence.fit`."""
    return sequence.fit(point_frame(df), archetypes, **kwargs)


def median_timings(
    frame: pd.DataFrame,
    hero_id: int,
    archetype_id: int,
    *,
    target_badge: float | None = None,
    badge_halfwidth: float = sequence.DEFAULT_BADGE_HALFWIDTH,
) -> dict[int, float]:
    """Median game time of each ability point, by position, for one hero and archetype.

    With `target_badge`, the median is weighted toward that badge with the
    same kernel as the tables. Three backoff levels key on a time bucket, so
    timings must come from the same players as the choices. Without a badge
    column, returns the plain median.
    """
    cell = frame[frame["hero_id"] == hero_id]
    if "archetype_id" in cell:
        cell = cell[cell["archetype_id"] == archetype_id]
    if not len(cell):
        return {}
    if target_badge is None or "average_badge" not in cell:
        return cell.groupby("buy_index")["buy_time_s"].median().to_dict()

    cell = cell.assign(
        _w=sequence.row_weights(
            cell, target_badge=target_badge, badge_halfwidth=badge_halfwidth
        )
    )
    return {
        int(position): _weighted_median(
            group["buy_time_s"].to_numpy(float), group["_w"].to_numpy(float)
        )
        for position, group in cell.groupby("buy_index")
    }


def _weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    """The value with half the total weight below it."""
    order = np.argsort(values)
    values, weights = values[order], weights[order]
    total = weights.sum()
    if total <= 0:
        return float(np.median(values))
    index = int(np.searchsorted(np.cumsum(weights), total / 2.0))
    return float(values[min(index, len(values) - 1)])


def recommend(
    model: sequence.SequenceModel,
    state: GameState,
    *,
    levels: dict[int, int] | None = None,
    top: int = N_SLOTS,
) -> list[AbilityPoint]:
    """The top next ability points for a state.

    `levels` is each slot's current level. Slots at level 4 are skipped. The
    model is called with `mask_owned=False` because a slot takes four points,
    unlike an item, which is bought once.
    """
    levels = dict(levels or {})
    signatures = assets.hero_signatures().get(int(state.hero_id), {})
    ids, probability = model.distribution(state, mask_owned=False)
    if not len(ids):
        return []

    out: list[AbilityPoint] = []
    for index in np.argsort(-probability):
        slot = int(ids[index])
        current = levels.get(slot, 0)
        if current >= MAX_LEVEL or slot not in signatures:
            continue
        trace = model.evidence(state, slot)
        out.append(
            AbilityPoint(
                position=len(state.purchased),
                slot=slot,
                ability_id=signatures[slot].id,
                ability_name=signatures[slot].name,
                level=current + 1,
                game_time_s=state.game_time_s,
                probability=float(probability[index]),
                n=trace.n if trace else 0,
                backoff_level=trace.level if trace else model.levels[-1].name,
            )
        )
        if len(out) >= top:
            break
    return out


def generate_order(
    model: sequence.SequenceModel,
    frame: pd.DataFrame,
    hero_id: int,
    archetype_id: int,
    *,
    timings: dict[int, float] | None = None,
    target_badge: float | None = None,
    badge_halfwidth: float = sequence.DEFAULT_BADGE_HALFWIDTH,
    n_points: int = MAX_POINTS,
) -> list[AbilityPoint]:
    """The full recommended ability order for one hero and archetype.

    Greedy: take the most likely slot that isn't maxed, update the state,
    repeat. The only rule is that slots stop at level 4, so a search wouldn't
    find anything better.

    `frame` supplies the game time of each point. Three backoff levels key on
    the time bucket, so without advancing the clock every point would be
    predicted as if it were in the first five minutes. When measured, a
    16-point order with the clock stuck at zero went wrong at the seventh
    point, with p=0.892.

    `target_badge` takes the timings from the same badge the model was
    weighted toward.
    """
    if timings is None:
        timings = median_timings(
            frame,
            hero_id,
            archetype_id,
            target_badge=target_badge,
            badge_halfwidth=badge_halfwidth,
        )
    if not timings:
        raise ValueError(
            f"no ability-point timings for hero {hero_id} archetype {archetype_id}. "
            "Without them every point would be predicted as if it were bought "
            "in the first five minutes"
        )
    levels = {slot: 0 for slot in range(1, N_SLOTS + 1)}
    state = GameState(
        hero_id=int(hero_id),
        game_time_s=float(timings.get(0, 0.0)),
        souls_available=0,
        archetype_posterior={int(archetype_id): 1.0},
    )

    order: list[AbilityPoint] = []
    for position in range(min(n_points, MAX_POINTS)):
        if all(level >= MAX_LEVEL for level in levels.values()):
            break
        ranked = recommend(model, state, levels=levels, top=1)
        if not ranked:
            break
        best = ranked[0]
        levels[best.slot] += 1
        order.append(
            AbilityPoint(
                position=position,
                slot=best.slot,
                ability_id=best.ability_id,
                ability_name=best.ability_name,
                level=levels[best.slot],
                game_time_s=float(timings.get(position, state.game_time_s)),
                probability=best.probability,
                n=best.n,
                backoff_level=best.backoff_level,
            )
        )
        state = state.with_purchase(
            best.slot, game_time_s=float(timings.get(position + 1, state.game_time_s))
        )
    return order


def format_order(order: list[AbilityPoint]) -> str:
    """The order as text: the max order on the first line, then every point."""
    if not order:
        return "no ability order available"
    maxed = [point.ability_name for point in order if point.level == MAX_LEVEL]
    lines = []
    if maxed:
        lines.append("max order: " + " > ".join(maxed))
    lines.extend(str(point) for point in order)
    return "\n".join(lines)
