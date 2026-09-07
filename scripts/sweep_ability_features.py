#!/usr/bin/env python
"""Do the ability features earn a place in the archetype clustering?

`archetype.py` records that ability features were tried and removed: adding
ability *levels* monotonically degraded the fit, with Ivy falling 0.508 ->
0.421 -> 0.361 -> 0.274 as the weight went 0 -> 0.25 -> 0.5 -> 1.0. That
measurement stands, and it is why the prior here is against these features.

But what it measured was ability state at a fixed instant. Two features were
never tried:

    point order   how far into a player's spending each ability reached each
                  level -- a sequence, where levels at 480s are an inventory
    imbue         which ability the build points its imbueable items at

So this runs the same sweep on the same criterion, and the same rule applies:
if separation falls monotonically, the feature goes back to naming only.

    python scripts/sweep_ability_features.py [--heroes N] [--block order|imbue|both]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from deadlock import abilities, archetype, assets, imbue  # noqa: E402

PURCHASES = Path("data/processed/purchases.parquet")
ABILITIES = Path("data/processed/abilities.parquet")
IMBUES = Path("data/processed/imbues.parquet")

WEIGHTS = (0.0, 0.25, 0.5, 1.0)

# The heroes the original ability sweep reported on, plus the ones this work
# predicts should gain: Doorman, Rem and Pocket all show order structure that
# the item features cannot see.
DEFAULT_HEROES = (
    "Ivy", "Haze", "Dynamo", "Bebop", "Wraith",
    "Holliday", "Lady Geist", "Paradox", "The Doorman", "Rem", "Pocket",
)


def blocks(hero_players: pd.MultiIndex) -> dict[str, pd.DataFrame]:
    """The two candidate feature blocks, unscaled."""
    out: dict[str, pd.DataFrame] = {}
    if ABILITIES.exists():
        ability_rows = pd.read_parquet(ABILITIES)
        out["order"] = abilities.point_order_features(ability_rows)
    if IMBUES.exists():
        imbue_rows = pd.read_parquet(IMBUES)
        out["imbue"] = imbue.imbue_features(imbue_rows, players=hero_players)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--heroes", type=str, default=",".join(DEFAULT_HEROES))
    parser.add_argument(
        "--block", choices=("order", "imbue", "both", "joint"), default="both"
    )
    args = parser.parse_args()

    purchases = pd.read_parquet(
        PURCHASES,
        columns=["match_id", "player_slot", "hero_id", "item_id", "buy_index"],
    )
    players = (
        purchases[["match_id", "player_slot"]]
        .drop_duplicates()
        .set_index(["match_id", "player_slot"])
        .index
    )
    available = blocks(players)
    if not available:
        print("no ability or imbue table built; nothing to sweep")
        return 1

    if args.block == "joint":
        # What would actually ship: both blocks in the fit together. Sweeping
        # them separately says whether each can help; only this says whether
        # they help at the same time.
        joint = [
            archetype.scale_block(available[name], 1.0)
            for name in ("order", "imbue")
            if name in available
        ]
        available["joint"] = pd.concat(joint, axis=1)
        wanted = ("joint",)
    else:
        wanted = ("order", "imbue") if args.block == "both" else (args.block,)
        wanted = tuple(name for name in wanted if name in available)

    heroes = {h.name.lower(): i for i, h in assets.playable_heroes().items()}
    names = [n.strip() for n in args.heroes.split(",") if n.strip()]

    rows = []
    for name in names:
        hero_id = heroes.get(name.lower())
        if hero_id is None:
            print(f"  (no hero {name!r})")
            continue
        group = purchases[purchases["hero_id"] == hero_id]
        for block_name in wanted:
            for weight in WEIGHTS:
                extra = archetype.scale_block(available[block_name], weight)
                fit = archetype.fit_hero(
                    group, hero_id=hero_id, hero_name=name, extra=extra
                )
                rows.append(
                    {
                        "hero": name,
                        "block": block_name,
                        "weight": weight,
                        "k": fit.k,
                        "separation": fit.separation,
                        "silhouette": fit.silhouette,
                    }
                )
                print(
                    f"  {name:12s} {block_name:6s} w={weight:<5} "
                    f"k={fit.k} sep={fit.separation:.3f} sil={fit.silhouette:.3f}"
                )

    out = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    for block_name in wanted:
        block = out[out["block"] == block_name]
        table = block.pivot_table(index="hero", columns="weight", values="separation")
        print(f"\nseparation by {block_name} weight")
        print(table.round(3).to_string())
        ks = block.pivot_table(index="hero", columns="weight", values="k")
        print(f"\nk by {block_name} weight")
        print(ks.astype(int).to_string())
        print("\nverdict per hero (vs weight 0):")
        for hero in table.index:
            row = table.loc[hero]
            base_k = int(ks.loc[hero, 0.0])
            best_weight = row.idxmax()
            best_k = int(ks.loc[hero, best_weight])
            # A hero that was k=1 has no separation to compare against. NaN
            # there means "there was no split", not "the split got worse", and
            # reporting it as a degradation buries the most interesting result
            # available: a playstyle the item features could not see.
            if row.isna().all():
                # k=1 at every weight: the hero has one build and the feature
                # did not invent a second. Not a degradation.
                print(f"  {hero:12s} no split at any weight")
                continue
            if base_k == 1 and best_k > 1 and row.max() >= archetype.MIN_SEPARATION:
                print(
                    f"  {hero:12s} best w={best_weight:<5} "
                    f"k {base_k}->{best_k} sep={row.max():.3f}  NEW SPLIT"
                )
                continue
            delta = row.max() - row[0.0]
            verdict = "gains" if delta > 0.01 else ("flat" if delta > -0.01 else "degrades")
            suffix = f"  (k {base_k}->{best_k})" if best_k != base_k else ""
            print(f"  {hero:12s} best w={best_weight:<5} {delta:+.3f}  {verdict}{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
