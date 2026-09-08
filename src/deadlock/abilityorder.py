"""Where the ability points go, and in what order.

The other half of a build. The tool has always answered "what do I buy"; this
answers "where do my points go", which a player cannot look up and which
changes how a hero plays more than a mid-tier item does.

**Order, not final allocation.** By the end of a match everyone has maxed
everything -- measured on Ivy the four final means are 3.62/3.70/3.71/3.82 --
so the allocation says nothing. The ability maxed first is maxed for most of
the match; the one maxed last is maxed for a few minutes. `CONTEXT.md` makes
the same point about items: a build is a sequence, not an inventory.

This module owns no model. An ability order is a sequence conditioned on hero
and archetype, which is exactly the problem `sequence.py` already solves, so
the frame here is shaped like a purchase table and handed to the same backoff
chain. Four outcomes per step instead of 173, so the deep levels are dense and
fire far more often than they do for items -- but every recommendation still
names its table row, its raw count, and its backoff level, because a number
with no recourse is what this project was burned by.

The outcome is the *signature slot*, not the level it reaches. Which level a
point takes a slot to is determined by how many points already went there, so
predicting the slot is the whole decision.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import abilities, assets, sequence
from .state import THIN_EVIDENCE, GameState

log = logging.getLogger(__name__)

# Four signature slots, four levels each. A slot at level 4 cannot take another
# point, which is the only hard constraint in an ability order.
MAX_LEVEL = abilities.MAX_ABILITY_LEVEL
N_SLOTS = abilities.N_SIGNATURE_SLOTS
MAX_POINTS = N_SLOTS * MAX_LEVEL

# What each level costs, read off `/v1/builds`: unlocking an ability spends one
# point of currency type 2, and levels 2, 3 and 4 spend 1, 2 and 5 of type 1.
# The game charges more for later levels, which is why maxing an ability early
# is a real commitment rather than a preference.
LEVEL_COST = {1: (2, -1), 2: (1, -1), 3: (1, -2), 4: (1, -5)}


@dataclass(frozen=True)
class AbilityPoint:
    """One point in a recommended order, with the evidence behind it."""

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
    """Ability points shaped like a purchase table, for `sequence.fit`.

    `item_id` carries the signature slot, `buy_index` the ordinal position of
    the point and `buy_time_s` its clock time, so every level key in the chain
    means for abilities what it means for items.

    Unmapped abilities are dropped rather than modelled. They are 0.01% of
    entries -- Silver's reworked werewolf abilities, absent from the asset
    signature map -- and a recommendation the tool cannot name is not advice.
    Positions are assigned after the drop, so the sequence stays contiguous.
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
    # Carried through rather than required, so an abilities table without one
    # still fits -- it simply cannot be badge-weighted.
    if "average_badge" in ordered:
        frame["average_badge"] = ordered["average_badge"].to_numpy()
    return frame


def attach_badges(df: pd.DataFrame, purchases: pd.DataFrame) -> pd.DataFrame:
    """Copy each player's match badge onto their ability rows.

    Badge is recorded on purchases and not on abilities, so weighting the
    ability order toward a bracket needs this join first. Players with no
    purchase row keep a null badge, which the kernel reads as neutral: a filled
    zero would sit at the far tail and drop them out of every table, and the
    badge is Ranked-only, so those rows are not rare.
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
    """Fit the backoff chain to ability orders. Same model, different sequence."""
    return sequence.fit(point_frame(df), archetypes, **kwargs)


def median_timings(
    frame: pd.DataFrame,
    hero_id: int,
    archetype_id: int,
    *,
    target_badge: float | None = None,
    badge_halfwidth: float = sequence.DEFAULT_BADGE_HALFWIDTH,
) -> dict[int, float]:
    """Median clock time of the nth ability point, for one hero-archetype.

    Population medians, the same basis the item timings use. A player levels
    when they level up, not by the clock, so these orient rather than instruct.

    `target_badge` moves the median toward a bracket, using the same kernel
    that weights the tables. It has to, because the clock is not decoration
    here: three of the six backoff levels key on a time bucket, so a build
    whose *choices* come from strong players and whose *timings* come from the
    whole population is conditioned on a pace its own players do not keep.
    A weighted median rather than a filtered one, for the same reason the
    tables weight rather than filter -- the thin cells cannot spare the rows.

    A frame with no badge column answers with the plain median, since the
    abilities table carries no badge of its own until one is joined on.
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
    """The value at which half the weight lies below."""
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
    """Ranked next ability points for a state.

    `levels` is the current level of each slot; a slot already at 4 is dropped,
    since it cannot take another point. Note `mask_owned=False`: unlike items,
    which are never bought twice, a slot takes four points, so the ownership
    mask that protects the item path would be wrong here.
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
    """The full recommended ability order for one hero-archetype.

    A greedy roll-forward: take the most likely legal slot, advance the state,
    repeat. Greedy rather than a beam search because the constraint set is one
    rule -- a slot stops at level 4 -- and there is nothing for a search to
    recover from.

    **The frame is required because the clock is part of the context.** Three
    of the six levels key on `time_bucket`, so rolling forward without
    advancing the clock asks every level for the first five minutes of a match
    and gets a confident wrong answer rather than a miss -- measured: a
    16-point order generated at a frozen clock diverges at the seventh point
    and reports p=0.892 for it. Passing the population's own timings is what
    makes the context real, so they are read from `frame` unless overridden.

    `target_badge` moves those timings to the same bracket the model was
    weighted toward. Without it a build asked for strong players takes its
    choices from them and its clock from everybody.
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
            f"no ability-point timings for hero {hero_id} archetype {archetype_id}; "
            "the time bucket is part of every deep context, so an order "
            "generated without one is conditioned on the first five minutes"
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
    """The point list a player reads, with a priority summary on top.

    The summary is what most players want -- which ability to rush -- and the
    list is what they follow. Printing only the summary would discard the
    interleaving, and real orders interleave.
    """
    if not order:
        return "no ability order available"
    maxed = [point.ability_name for point in order if point.level == MAX_LEVEL]
    lines = []
    if maxed:
        lines.append("max order: " + " > ".join(maxed))
    lines.extend(str(point) for point in order)
    return "\n".join(lines)
