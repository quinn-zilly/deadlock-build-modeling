"""Which ability a build points its imbueable items at.

Every purchase record has carried `imbued_ability_id` since the first pull and
nothing read it. What it says is narrow but sharp, and it is not what the item
features already say.

**Imbue is a property of an (item, ability) pair, and it is never missing.**
Only 11 of 173 shopable items can be imbued -- 9 in practice, since two are
tier 5 and nothing buys tier 5 -- and all 9 carry a target on **100%** of
purchases, because the game makes the player choose at the counter. So a hero
with a low imbue rate is not a hero with missing data:

    Silver  buys an imbueable item 21.0%   imbue rate 21%
    Billy                          22.1%              22%
    Wraith                          99.9%             100%

Those are the same number. Whether a build buys imbueable items is already in
the item features; what is new here is only the **conditional target** -- given
it bought one, which ability did it point at. Imputing a hero mean for a player
who imbued nothing would invent a statement they never made.

The three imbue types are different statements about the build:

    imbue_active            empowers or copies the ability itself
    imbue_modifier_value    buffs the ability's numbers
    imbue_active_non_ult    the same as active, but cannot target the ultimate

Grouped as active and modifier, because "I want a second Singularity" and "I
want my Singularity to last longer" are different builds while Echo Shard is
just an active imbue with a restriction. That restriction is still a signal:
buying Echo Shard over Mystic Reverb says the build is not about the ult.

Measured, this separates exactly one hero -- and it is the one items cannot
name. Dynamo's ult cluster imbues Singularity 3.6x more than its stomp cluster;
its stomp cluster imbues Kinetic Pulse 3.0x more. Dynamo is also the only hero
whose item lifts are too weak to name a cluster at all, so imbue and items
cover each other's blind spots rather than repeating each other.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from . import assets

log = logging.getLogger(__name__)

# The two feature groups. `imbue_active_non_ult` joins "active"; see above.
ACTIVE = "active"
MODIFIER = "modifier"
GROUPS = (ACTIVE, MODIFIER)
TYPE_GROUP = {
    "imbue_active": ACTIVE,
    "imbue_active_non_ult": ACTIVE,
    "imbue_modifier_value": MODIFIER,
}

N_SIGNATURE_SLOTS = 4

# A build that imbues four items is making a firmer statement than one that
# imbues a single Mystic Expansion, and shares alone flatten that. Scaled by
# this so the count lands in roughly the same range as a share.
MAX_EXPECTED_IMBUES = 4.0


def imbueable_items(shopable_only: bool = True) -> dict[int, str]:
    """Item id -> imbue type, for every item that can be imbued.

    Tier 5 items are included when asked for, but nothing buys them: zero rows
    in 5,095,598 purchases, so Frostbite Charm and Omnicharge Signet never
    appear in practice.
    """
    items = assets.shopable_items() if shopable_only else assets.load_items()
    return {i: item.imbue for i, item in items.items() if item.imbueable}


def imbue_rows(
    player: dict[str, Any],
    imbueable: dict[int, str],
    slots: dict[int, int] | None = None,
) -> list[dict[str, Any]]:
    """One row per imbued purchase for a player.

    Reads only entries whose item is imbueable *and* carries a target. Both
    conditions rather than either: a zero target on an imbueable item would
    mean the game recorded a choice that was never made, and if that ever
    starts happening it should show up as missing rows rather than as slot 0.
    """
    slots = assets.signature_slots() if slots is None else slots
    rows = []
    for entry in player.get("items") or []:
        item_id = entry.get("item_id")
        target = entry.get("imbued_ability_id")
        if item_id not in imbueable or not target:
            continue
        rows.append(
            {
                "item_id": int(item_id),
                "imbued_ability_id": int(target),
                "signature_slot": int(slots.get(int(target), -1)),
                "imbue_group": TYPE_GROUP.get(imbueable[item_id], ACTIVE),
                "game_time_s": int(entry.get("game_time_s", 0)),
            }
        )
    return rows


def conditional_features(
    df: pd.DataFrame, players: pd.MultiIndex, hero_of: pd.Series
) -> pd.DataFrame:
    """Imbue direction only, and silence from builds that bought no imbueable item.

    The question this answers is *given the build bought an imbueable item,
    which ability did it point at* -- and nothing else. Eight columns, the
    share of each group's imbues aimed at each signature slot.

    **A player who imbued nothing is placed at their hero's mean, not at zero.**
    Zero is not neutral: it is a distinct point in the feature space, so every
    non-imbuer on a hero lands on the same coordinates and k-means finds them
    as a group. Measured, that is exactly what happened -- with zeros, 27 of 33
    separating items were imbueable items, so the block was splitting heroes by
    *whether* they bought Mystic Reverb rather than by what they aimed it at.
    The item features already carry whether. Placing non-imbuers at the mean
    makes them say nothing, which is the truth about them.

    `has_imbue` and a depth count are deliberately absent for the same reason:
    both encode ownership, which is not what imbue is being asked about here.
    """
    base = imbue_features(df, players=players)
    shares = base[[c for c in base.columns if c.startswith("imb_")
                   and not c.startswith("imb_depth")]]
    imbued = base["has_imbue"] > 0

    hero = hero_of.reindex(shares.index)
    out = shares.copy()
    # Per hero, the average direction among that hero's imbuers.
    means = shares[imbued.to_numpy()].groupby(hero[imbued.to_numpy()]).mean()
    for hero_id, row in means.iterrows():
        mask = (hero == hero_id).to_numpy() & (~imbued).to_numpy()
        if mask.any():
            out.loc[mask, row.index] = row.to_numpy()
    return out


def imbue_features(df: pd.DataFrame, players: pd.MultiIndex | None = None) -> pd.DataFrame:
    """Per-player imbue features, indexed by (match_id, player_slot).

    Ten columns: `imb_active_1..4` and `imb_mod_1..4` are the share of that
    group's imbues pointed at each signature slot, `imb_depth` is how many
    imbues the build made, and `has_imbue` flags whether it made any.

    A player who imbued nothing reads all zeros with `has_imbue` 0. That is the
    honest encoding: the value is structurally undefined rather than missing,
    and the flag says so explicitly instead of leaving every non-imbuer sitting
    together at the origin looking like a playstyle.

    `players` supplies the full population to reindex over, so players who
    never imbued still get a row instead of vanishing from a later join.
    """
    keys = ["match_id", "player_slot"]
    columns = [
        f"imb_{'active' if group == ACTIVE else 'mod'}_{slot}"
        for group in GROUPS
        for slot in range(1, N_SIGNATURE_SLOTS + 1)
    ]

    valid = df[df["signature_slot"].between(1, N_SIGNATURE_SLOTS)] if len(df) else df
    index = players if players is not None else (
        df[keys].drop_duplicates().set_index(keys).index if len(df)
        else pd.MultiIndex.from_arrays([[], []], names=keys)
    )
    out = pd.DataFrame(0.0, index=index, columns=columns)
    if not len(valid):
        out["imb_depth"] = 0.0
        out["has_imbue"] = 0.0
        return out

    counts = (
        valid.groupby(keys + ["imbue_group", "signature_slot"]).size().rename("n").reset_index()
    )
    totals = counts.groupby(keys + ["imbue_group"])["n"].transform("sum")
    counts["share"] = counts["n"] / totals

    for group in GROUPS:
        prefix = "active" if group == ACTIVE else "mod"
        wide = (
            counts[counts["imbue_group"] == group]
            .pivot_table(index=keys, columns="signature_slot", values="share", aggfunc="sum")
            .reindex(columns=range(1, N_SIGNATURE_SLOTS + 1))
            .reindex(index)
            .fillna(0.0)
        )
        for slot in range(1, N_SIGNATURE_SLOTS + 1):
            out[f"imb_{prefix}_{slot}"] = wide[slot].to_numpy(float)

    depth = valid.groupby(keys).size().reindex(index).fillna(0.0)
    out["imb_depth"] = (depth / MAX_EXPECTED_IMBUES).clip(0.0, 1.0).to_numpy(float)
    out["has_imbue"] = (depth > 0).astype(float).to_numpy(float)
    return out


def target_for_item(df: pd.DataFrame, item_id: int) -> int | None:
    """The ability a population most often imbues one item into.

    What a build should say when it recommends an imbueable item. The mode
    rather than a distribution, because the export schema has one field and a
    player makes one choice.
    """
    rows = df[df["item_id"] == item_id]
    if not len(rows):
        return None
    return int(rows["imbued_ability_id"].value_counts().idxmax())


def dominant_targets(df: pd.DataFrame) -> dict[int, int]:
    """item id -> the ability that population imbues it into most often."""
    if not len(df):
        return {}
    counts = df.groupby(["item_id", "imbued_ability_id"]).size().rename("n").reset_index()
    best = counts.sort_values("n", ascending=False).drop_duplicates("item_id")
    return {int(r.item_id): int(r.imbued_ability_id) for r in best.itertuples()}
