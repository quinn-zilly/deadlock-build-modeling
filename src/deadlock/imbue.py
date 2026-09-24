"""Imbues: which ability a player points each imbueable item at.

Each purchase row has an `imbued_ability_id`. An imbue is an (item, ability)
pair.

An imbue is never missing. Only 9 shop items can be imbued in practice (11
are marked imbueable, but two are tier 5, which nobody buys). The game makes
the player pick a target when buying, so all 9 have a target on 100% of
purchases. A hero's imbue rate is just how often its players buy those items:

    Silver  buys an imbueable item 20.2%   imbue rate 20.2%
    Billy                          24.8%              24.8%
    Wraith                         99.8%              99.8%

The item features already capture whether a player bought an imbueable item.
The new information here is only which ability they chose.

There are three imbue types:

    imbue_active            empowers or copies the ability
    imbue_modifier_value    raises the ability's numbers
    imbue_active_non_ult    like active, but can't target the ultimate

We group them into active and modifier. "A second Singularity" and "a longer
Singularity" are different builds, while Echo Shard (the non-ult one) is an
active imbue with a restriction.

Imbue separates the archetypes of one hero that items can't: Dynamo. Dynamo's
ult archetype imbues Singularity 3.6x more than its stomp archetype, and the
stomp archetype imbues Kinetic Pulse 3.0x more.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from . import assets
from .state import THIN_EVIDENCE

log = logging.getLogger(__name__)

# The two imbue groups. `imbue_active_non_ult` counts as active.
ACTIVE = "active"
MODIFIER = "modifier"
GROUPS = (ACTIVE, MODIFIER)
TYPE_GROUP = {
    "imbue_active": ACTIVE,
    "imbue_active_non_ult": ACTIVE,
    "imbue_modifier_value": MODIFIER,
}

N_SIGNATURE_SLOTS = 4

# `imb_depth` is the imbue count divided by this, capped at 1, so it falls in
# the same 0-1 range as the share columns.
MAX_EXPECTED_IMBUES = 4.0

# A most-common target chosen by less than this share of players is marked
# [split]. For example, Ivy's spirit build aims Compress Cooldown at Air Drop
# 39% of the time. That is the most common target, but it is not most players.
MAJORITY = 0.5


def imbueable_items(shopable_only: bool = True) -> dict[int, str]:
    """Map item id to imbue type, for every item that can be imbued.

    With `shopable_only=False` this includes the tier 5 items Frostbite Charm
    and Omnicharge Signet, which nobody buys.
    """
    items = assets.shopable_items() if shopable_only else assets.load_items()
    return {i: item.imbue for i, item in items.items() if item.imbueable}


def imbue_rows(
    player: dict[str, Any],
    imbueable: dict[int, str],
    slots: dict[int, int] | None = None,
) -> list[dict[str, Any]]:
    """One row per imbued purchase for a player.

    Keeps entries whose item is imbueable and whose target is nonzero. If the
    game ever records an imbueable purchase with no target, it shows up as a
    missing row, not as slot 0.
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
    """Which slot each player aimed their imbues at, with non-imbuers at the hero mean.

    Not used by the shipped model. Kept so `scripts/compare_imbue_fits.py` can
    rerun the experiment in `docs/adr/0001-imbue-out-of-the-clustering.md`.

    Eight columns: for each group (active, modifier), the share of imbues aimed
    at each signature slot.

    Players who imbued nothing get their hero's mean, not zeros. With zeros,
    every non-imbuer sat on the same point and k-means grouped them, so the
    clusters split on whether players bought an imbueable item (27 of 33
    separating items were imbueable). `has_imbue` and `imb_depth` are left out
    for the same reason.

    It still didn't work. With this block, 24 of 29 split heroes separated on
    an imbueable item, against 2 of 28 with build families alone, and nine
    heroes lost a split. Only players who buy imbueable items can differ from
    the mean, so the block still groups them apart from everyone else.
    """
    base = imbue_features(df, players=players)
    shares = base[[c for c in base.columns if c.startswith("imb_")
                   and not c.startswith("imb_depth")]]
    imbued = base["has_imbue"] > 0

    hero = hero_of.reindex(shares.index)
    out = shares.copy()
    # Each hero's mean shares, over the players who imbued.
    means = shares[imbued.to_numpy()].groupby(hero[imbued.to_numpy()]).mean()
    for hero_id, row in means.iterrows():
        mask = (hero == hero_id).to_numpy() & (~imbued).to_numpy()
        if mask.any():
            out.loc[mask, row.index] = row.to_numpy()
    return out


def imbue_features(df: pd.DataFrame, players: pd.MultiIndex | None = None) -> pd.DataFrame:
    """Per-player imbue features, indexed by (match_id, player_slot).

    Ten columns. `imb_active_1` to `imb_active_4` and `imb_mod_1` to
    `imb_mod_4` are the share of that group's imbues aimed at each signature
    slot. `imb_depth` is the imbue count scaled by MAX_EXPECTED_IMBUES, and
    `has_imbue` is 1 if the player imbued anything.

    A player who imbued nothing gets all zeros. Pass `players` to give a row
    to every player, including those with no imbues.
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
    """The ability players most often imbue this item into, or None if nobody did."""
    rows = df[df["item_id"] == item_id]
    if not len(rows):
        return None
    return int(rows["imbued_ability_id"].value_counts().idxmax())


def dominant_targets(df: pd.DataFrame) -> dict[int, int]:
    """Map item id to the ability players most often imbue it into.

    Built on `targets_for_build` so ties break the same way everywhere. With
    two separate implementations, the CLI and `generate_builds.py` could
    export different targets for the same build.
    """
    if not len(df):
        return {}
    return {
        target.item_id: target.ability_id
        for target in targets_for_build(df, df["item_id"].unique())
        if target.ability_id is not None
    }


@dataclass(frozen=True)
class ImbueTarget:
    """The most common imbue target for one item, with its share and count.

    `ability_id` is None when no player in the table passed to
    `targets_for_build` bought this item. Every
    purchase of an imbueable item has a target, so None means no data, not
    that players chose nothing.
    """

    item_id: int
    item_name: str
    ability_id: int | None
    ability_name: str
    n: int
    share: float

    @property
    def split(self) -> bool:
        """True when the most common target has less than MAJORITY of imbues."""
        return self.ability_id is not None and self.share < MAJORITY

    @property
    def thin(self) -> bool:
        """True when fewer than THIN_EVIDENCE imbues back this target."""
        return self.ability_id is not None and self.n < THIN_EVIDENCE

    def __str__(self) -> str:
        if self.ability_id is None:
            return f"{self.item_name:26s} -> (no imbue seen in this cell)"
        line = (
            f"{self.item_name:26s} -> {self.ability_name:22s} "
            f"{self.share:.0%} of {self.n:,} imbues"
        )
        if self.split:
            line += "  [split]"
        if self.thin:
            line += "  [thin]"
        return line


def targets_for_build(
    df: pd.DataFrame,
    item_ids: Iterable[int],
    *,
    item_names: dict[int, str] | None = None,
    ability_names: dict[int, str] | None = None,
    imbueable: dict[int, str] | None = None,
) -> list[ImbueTarget]:
    """The imbue target for each imbueable item in a build, in build order.

    Items that can't be imbued are left out.
    """
    imbueable = imbueable_items() if imbueable is None else imbueable
    if item_names is None:
        item_names = {i: item.name for i, item in assets.load_items().items()}
    if ability_names is None:
        ability_names = {i: a.name for i, a in assets.load_abilities().items()}

    counts = (
        df.groupby(["item_id", "imbued_ability_id"]).size() if len(df)
        else pd.Series(dtype=int)
    )
    out: list[ImbueTarget] = []
    for item_id in dict.fromkeys(int(i) for i in item_ids):
        if item_id not in imbueable:
            continue
        rows = counts[item_id] if item_id in counts.index.get_level_values(0) else None
        if rows is None or not len(rows):
            out.append(
                ImbueTarget(item_id, item_names.get(item_id, str(item_id)), None, "", 0, 0.0)
            )
            continue
        ability_id = int(rows.idxmax())
        total = int(rows.sum())
        out.append(
            ImbueTarget(
                item_id=item_id,
                item_name=item_names.get(item_id, str(item_id)),
                ability_id=ability_id,
                ability_name=ability_names.get(ability_id, str(ability_id)),
                n=total,
                share=int(rows.max()) / total,
            )
        )
    return out
