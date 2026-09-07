"""Ability leveling: the half of the `items` array the purchase path discards.

`features.clean_purchases` keeps entries whose id is a known upgrade. This
module is its exact complement -- same input, opposite filter -- and recovers
the ~46% of entries that are ability level-ups. Keeping them separate rather
than generalizing `clean_purchases` is deliberate: that function's behaviour is
pinned by regression tests and the whole purchase path depends on it, so the
two paths prove each other by staying distinct.

Each level-up entry carries three usable fields:

    item_id       the ability id, joinable to a hero signature slot
    game_time_s   when the point was spent
    upgrade_info  the level, in its high 16 bits

**Read the level from `upgrade_info`, never from a running count.** The high
word takes exactly four values -- 1, 3, 7, 15 -- for levels 1 through 4, and
7.9% of players have a missing level row. Counting rows would silently
mis-level every one of them.

What this data is for: distinguishing how a hero is being played. But note the
measured limit -- ability state predicts a player's build archetype poorly
early (AUC 0.607 from the first ability, at ~13s) and only becomes informative
around 480-600s, by which point their purchases say more (0.854). Final levels
are useless for this: everyone maxes everything. So these features are read at
a mid-match instant, and they support clustering rather than in-match
inference.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from . import assets

log = logging.getLogger(__name__)

# upgrade_info >> 16 -> ability level. A bitmask of levels reached, so each
# value is the previous one with another bit set.
LEVEL_BITS = {1: 1, 3: 2, 7: 3, 15: 4}

MAX_ABILITY_LEVEL = 4
N_SIGNATURE_SLOTS = 4

# When to read ability state for archetype features. Levels vary meaningfully
# here; by match end they are saturated and carry almost no signal.
ARCHETYPE_READ_TIME_S = 480.0

# Ability ids with no signature slot in the hero assets get this, rather than
# being dropped, so row counts reconcile against the raw array and the gap
# stays visible.
UNMAPPED_SLOT = -1


def ability_level(upgrade_info: int) -> int:
    """Ability level encoded in the high word of `upgrade_info`.

    Returns 0 for an unrecognized encoding rather than guessing, so a patch
    that changes the format shows up as zeros instead of plausible-looking
    wrong levels.
    """
    return LEVEL_BITS.get(int(upgrade_info) >> 16, 0)


def clean_ability_points(
    player: dict[str, Any], upgrade_ids: frozenset[int]
) -> list[dict[str, Any]]:
    """Ability level-ups for one player, in true chronological order.

    The complement of `features.clean_purchases`: everything in the `items`
    array that is not a purchasable upgrade. Sorted by time, since array order
    is not reliable in the source data.
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
    """Flatten one player's ability spends into table rows."""
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
    """Level of each signature slot as of `at_time`, for one player.

    Takes the maximum level reached rather than the last row, because a
    player's missing level rows would otherwise make their state jump around.
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
    """Per-player ability state, indexed by (match_id, player_slot).

    Columns are `lvl_1` .. `lvl_4` -- the level of each signature slot at
    `at_time` -- plus `first_slot`, which slot the player invested in first.

    Read at a mid-match instant by default. Final levels do not discriminate:
    measured on Ivy the four means are 3.62/3.70/3.71/3.82, because everyone
    eventually maxes everything.
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

    # Reindex over every player present, so a player whose abilities are all
    # unmapped still appears with zeros rather than vanishing from the join.
    everyone = df[keys].drop_duplicates().set_index(keys).index
    out = levels.reindex(everyone).fillna(0.0)
    out["first_slot"] = first.reindex(everyone).fillna(0).astype(int)
    return out


def order_index(df: pd.DataFrame) -> pd.DataFrame:
    """Ordinal position at which each slot first reached level 1.

    The leveling *order*, which is what carries playstyle information --
    unlike the final allocation, which saturates.
    """
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
    """How far into a player's spending each slot reached each level.

    Twelve columns, `pt_1_l2` .. `pt_4_l4`: the point at which signature slot
    *s* reached level *L*, as a fraction of that player's total ability points.
    A slot never reaching a level reads 1.0, which sorts after every slot that
    did -- "not by the end" is the honest reading, and it keeps the column
    ordered rather than punching a hole in it.

    **This is the ability feature that carries playstyle, and it is not
    `ability_features`.** That one reads levels at a fixed instant, which is a
    snapshot of state; `CONTEXT.md` says of items that a build is a sequence and
    not an inventory, and the same holds here. State was measured and rejected
    for the archetype clustering (see the module docstring in `archetype.py`),
    but what was measured was state. Order was never tried, and it separates
    clusters state could not -- on Ivy, 67% of one cluster maxes Stone Form
    first against 9% of another, where the largest gap in levels at 480s was
    0.48 of 4.

    Ordering by point rather than by clock because players level at different
    speeds; the fifth point is the fifth decision whenever it was taken.

    Level *L* is read as the first point where the recorded level is **at least**
    L, not exactly L. 7.9% of players have a missing level row, and exact
    matching would report those slots as never reaching a level they plainly
    reached.
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


def first_maxed_slot(df: pd.DataFrame) -> pd.Series:
    """Which signature slot each player took to level 4 first.

    The single most legible summary of an ability order, and the one a player
    would recognise: the ability maxed first is maxed for most of the match,
    the one maxed last for a few minutes. Reported for review sheets and
    archetype naming rather than fed to the clustering, which reads the full
    `point_order_features` instead.

    Players who max nothing get 0.
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
    """Check that the two paths together account for every raw entry.

    The single most valuable check in the ability pipeline: purchases and
    abilities partition the `items` array, so any drift means one path is
    silently dropping records.
    """
    total = n_purchases + n_abilities
    ok = total == n_raw
    return ok, (
        f"purchases {n_purchases:,} + abilities {n_abilities:,} "
        f"= {total:,} vs raw {n_raw:,} "
        f"({'exact' if ok else f'MISMATCH {total - n_raw:+,}'})"
    )
