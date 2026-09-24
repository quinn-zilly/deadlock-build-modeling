"""Ability points: the entries in a player's `items` list that aren't purchases.

`features.clean_purchases` keeps the entries whose id is an upgrade. This
module keeps the rest, about 46% of entries. The two stay separate functions
so `reconcile` can check that together they account for every entry.

Each ability-point entry has three useful fields:

    item_id       the ability id, which maps to a signature slot
    game_time_s   when the point was spent
    upgrade_info  the level reached, in the high 16 bits

Read the level from `upgrade_info`, not by counting rows. The high 16 bits are
1, 3, 7, or 15 for levels 1 to 4. 7.9% of players are missing a level row, and
counting rows would give them the wrong levels.

Ability levels say little about a player's archetype early in a match. From
the first point (around 13s) they predict it with AUC 0.607, and by 480-600s,
when they become useful, purchases predict it better (0.854). Final levels say
nothing, because everyone maxes everything.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from . import assets

log = logging.getLogger(__name__)

# Maps upgrade_info >> 16 to ability level. The value is a bitmask with one
# bit per level reached.
LEVEL_BITS = {1: 1, 3: 2, 7: 3, 15: 4}

MAX_ABILITY_LEVEL = 4
N_SIGNATURE_SLOTS = 4

# When `ability_features` reads ability levels. At 8 minutes players still
# differ; by match end everyone is maxed.
ARCHETYPE_READ_TIME_S = 480.0

# Slot for ability ids that don't map to a signature slot. These rows are kept,
# not dropped, so row counts still match the raw data.
UNMAPPED_SLOT = -1


def ability_level(upgrade_info: int) -> int:
    """The ability level stored in the high 16 bits of `upgrade_info`.

    Returns 0 for an unknown value, so if a patch changes the format the
    levels show up as zeros instead of believable wrong numbers.
    """
    return LEVEL_BITS.get(int(upgrade_info) >> 16, 0)


def clean_ability_points(
    player: dict[str, Any], upgrade_ids: frozenset[int]
) -> list[dict[str, Any]]:
    """One player's ability points, sorted by time.

    Everything in `items` that `features.clean_purchases` drops.
    """
    spends = [
        entry
        for entry in player.get("items") or []
        if entry.get("item_id") not in upgrade_ids
    ]
    spends.sort(key=lambda entry: entry.get("game_time_s", 0))
    return spends


def ability_rows(
    player: dict[str, Any],
    upgrade_ids: frozenset[int],
    slots: dict[int, int] | None = None,
) -> list[dict[str, Any]]:
    """One player's ability points as rows: ability_id, signature_slot, level, game_time_s."""
    slots = assets.signature_slots() if slots is None else slots
    rows = []
    for entry in clean_ability_points(player, upgrade_ids):
        ability_id = entry.get("item_id")
        rows.append(
            {
                "ability_id": ability_id,
                "signature_slot": slots.get(ability_id, UNMAPPED_SLOT),
                "level": ability_level(entry.get("upgrade_info", 0)),
                "game_time_s": int(entry.get("game_time_s", 0)),
            }
        )
    return rows


def ability_state_at(rows: pd.DataFrame, at_time: float) -> dict[int, int]:
    """One player's level in each signature slot at `at_time`.

    Uses the highest level reached, not the last row, so a missing level row
    doesn't make a level go backwards.
    """
    state = {slot: 0 for slot in range(1, N_SIGNATURE_SLOTS + 1)}
    if rows.empty:
        return state
    seen = rows[rows["game_time_s"] <= at_time]
    if seen.empty:
        return state
    for slot, level in seen.groupby("signature_slot")["level"].max().items():
        if slot in state:
            state[slot] = int(level)
    return state


def ability_features(
    df: pd.DataFrame, at_time: float = ARCHETYPE_READ_TIME_S
) -> pd.DataFrame:
    """Each player's ability levels at `at_time`, indexed by (match_id, player_slot).

    Columns are `lvl_1` to `lvl_4`, the level of each signature slot, and
    `first_slot`, the slot that got the first point.

    The default time is mid-match because final levels are all nearly the
    same. On Ivy the four final means are 3.62, 3.70, 3.71, and 3.82.
    """
    keys = ["match_id", "player_slot"]
    valid = df[df["signature_slot"] != UNMAPPED_SLOT]
    early = valid[valid["game_time_s"] <= at_time]

    levels = (
        early.groupby(keys + ["signature_slot"])["level"]
        .max()
        .unstack("signature_slot")
        .reindex(columns=range(1, N_SIGNATURE_SLOTS + 1))
    )
    levels.columns = [f"lvl_{c}" for c in levels.columns]

    first = (
        valid.sort_values("game_time_s")
        .groupby(keys)["signature_slot"]
        .first()
        .rename("first_slot")
    )

    # Include every player, so one whose abilities are all unmapped gets zeros
    # instead of disappearing.
    everyone = df[keys].drop_duplicates().set_index(keys).index
    out = levels.reindex(everyone).fillna(0.0)
    out["first_slot"] = first.reindex(everyone).fillna(0).astype(int)
    return out


def order_index(df: pd.DataFrame) -> pd.DataFrame:
    """For each slot, whether it was unlocked 1st, 2nd, 3rd, or 4th (0 if never)."""
    keys = ["match_id", "player_slot"]
    firsts = (
        df[(df["level"] == 1) & (df["signature_slot"] != UNMAPPED_SLOT)]
        .sort_values("game_time_s")
        .groupby(keys + ["signature_slot"], as_index=False)
        .first()
    )
    firsts["order"] = firsts.groupby(keys)["game_time_s"].rank(method="first")
    wide = (
        firsts.pivot_table(
            index=keys, columns="signature_slot", values="order", aggfunc="first"
        )
        .reindex(columns=range(1, N_SIGNATURE_SLOTS + 1))
    )
    wide.columns = [f"order_{c}" for c in wide.columns]
    return wide.fillna(0.0)


def point_order_features(
    df: pd.DataFrame, levels: tuple[int, ...] = (2, 3, 4)
) -> pd.DataFrame:
    """When each slot reached each level, as a fraction of the player's points.

    Twelve columns, `pt_1_l2` to `pt_4_l4`. `pt_s_lL` is the point at which
    slot s reached level L, divided by the player's total ability points. A
    slot that never reached the level gets 1.0, which sorts after every slot
    that did.

    Position is counted in points, not seconds, because players level at
    different speeds.

    Order separates a hero's archetypes better than levels at a fixed time
    do. On Ivy, 67% of one archetype maxes Stone Form first against 9% of
    another, while the biggest gap in levels at 480s was 0.48. Even so, order
    was tested as a clustering input and rejected (ADR 0003), so these columns
    are for describing and naming archetypes, not finding them.

    Level L is reached at the first point where the recorded level is at
    least L. Requiring exactly L would miss the 7.9% of players with a missing
    level row.
    """
    keys = ["match_id", "player_slot"]
    ordered = df.sort_values(keys + ["game_time_s"]).copy()
    ordered["pt_index"] = ordered.groupby(keys).cumcount()
    totals = ordered.groupby(keys).size().rename("n_points")

    everyone = ordered[keys].drop_duplicates().set_index(keys).index
    valid = ordered[ordered["signature_slot"] != UNMAPPED_SLOT]

    out = pd.DataFrame(index=everyone)
    for level in levels:
        reached = (
            valid[valid["level"] >= level]
            .groupby(keys + ["signature_slot"])["pt_index"]
            .min()
            .unstack("signature_slot")
            .reindex(columns=range(1, N_SIGNATURE_SLOTS + 1))
            .reindex(everyone)
        )
        scaled = reached.div(totals.reindex(everyone), axis=0)
        for slot in range(1, N_SIGNATURE_SLOTS + 1):
            out[f"pt_{slot}_l{level}"] = scaled[slot].fillna(1.0).clip(0.0, 1.0)
    return out


def residual_point_order_features(
    df: pd.DataFrame,
    *,
    form: str = "mean",
    levels: tuple[int, ...] = (2, 3, 4),
) -> pd.DataFrame:
    """`point_order_features` relative to the average for the player's hero.

    Most players on a hero level abilities in the same order, so the raw
    columns mostly identify the hero. Clustering already runs one hero at a
    time, so only the difference from the hero's average is useful.

    `form` picks how the difference is taken:

        mean    the value minus the hero's mean. Stays in the raw units, a
                fraction of the player's points.
        rank    the value's percentile within the hero, minus 0.5. Not pulled
                around by the many ties at 1.0 ("never reached"), which drag
                the mean.

    Each column now averages about 0 per hero, so `scale_block` scales by
    how far players spread from their hero's habit.
    """
    if form not in {"mean", "rank"}:
        raise ValueError(f"unknown residual form {form!r}; want 'mean' or 'rank'")
    raw = point_order_features(df, levels=levels)
    keys = ["match_id", "player_slot"]
    heroes = (
        df[keys + ["hero_id"]]
        .drop_duplicates(subset=keys)
        .set_index(keys)["hero_id"]
        .reindex(raw.index)
    )
    grouped = raw.groupby(heroes)
    if form == "mean":
        return raw - grouped.transform("mean")
    return grouped.rank(pct=True) - 0.5


def first_maxed_slot(df: pd.DataFrame) -> pd.Series:
    """The signature slot each player took to level 4 first, or 0 if none.

    This is the one-line summary of an ability order that players recognize.
    Review sheets and archetype naming use it.
    """
    keys = ["match_id", "player_slot"]
    valid = df[df["signature_slot"] != UNMAPPED_SLOT]
    maxed = (
        valid[valid["level"] >= MAX_ABILITY_LEVEL]
        .sort_values("game_time_s")
        .groupby(keys)["signature_slot"]
        .first()
    )
    everyone = df[keys].drop_duplicates().set_index(keys).index
    return maxed.reindex(everyone).fillna(0).astype(int).rename("first_maxed")


def reconcile(
    n_purchases: int, n_abilities: int, n_raw: int
) -> tuple[bool, str]:
    """Check that purchases plus ability points equals the raw entry count.

    Every `items` entry is one or the other, so a mismatch means one path is
    dropping entries. Returns (ok, message).
    """
    total = n_purchases + n_abilities
    ok = total == n_raw
    return ok, (
        f"{n_purchases:,} purchases plus {n_abilities:,} ability points make "
        f"{total:,}, against {n_raw:,} raw entries "
        f"({'exact' if ok else f'off by {total - n_raw:+,}'})"
    )
