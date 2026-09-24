#!/usr/bin/env python
"""Sweep the weight of an ability feature block in the archetype clustering.

For each hero and each weight in WEIGHTS, fits archetypes with the block
added and prints k, separation, and silhouette. Blocks:

    order   when each ability reached each level, in points
    imbue   which ability each imbueable item was aimed at
    both    each of the above, separately
    joint   both blocks in the fit together

Both blocks were later rejected from the clustering (ADR 0001 for imbue, ADR
0003 for order). This script is the rough view across weights. The per-hero
comparisons behind those decisions are `compare_imbue_fits.py` and
`compare_order_fits.py`.

    python scripts/sweep_ability_features.py [--heroes A,B,...] [--block order|imbue|both|joint]
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

# The heroes from the original ability-level sweep, plus The Doorman, Rem, and
# Pocket, whose ability order varies in ways their items don't show.
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
        # Both blocks in one fit, since that's what would ship.
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
            # NaN separation means k=1, no split, which is not the same as a
            # worse split. A hero going from k=1 to a split is a new split.
            if row.isna().all():
                # k=1 at every weight.
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
