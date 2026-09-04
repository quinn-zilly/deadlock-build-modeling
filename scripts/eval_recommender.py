#!/usr/bin/env python
"""Evaluate the recommender against the popularity floor.

The test is paired within a lane: for each held-out lane, does the winning
side hold items our table scores higher than the losing side does? Comparing
inside a lane means both sides played the same match, so the comparison is not
contaminated by match quality.

The floor matters. A recommender that cannot beat "buy what everyone else
buys" has not earned its complexity.

Usage:  python scripts/eval_recommender.py [purchases.parquet]
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from deadlock import assets, confound, paired, recommend


def paired_separation(sides: pd.DataFrame, column: str) -> tuple[float, float]:
    """Winner-minus-loser score within each lane, and its standard error."""
    pivot = sides.reset_index().pivot_table(
        index=["match_id", "lane"], columns="won", values=column
    )
    pivot = pivot.dropna()
    if pivot.empty or True not in pivot or False not in pivot:
        return float("nan"), float("nan")
    diff = pivot[True] - pivot[False]
    return float(diff.mean()), float(diff.std() / np.sqrt(len(diff)))


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/processed/purchases.parquet")

    df = pd.read_parquet(path)
    early = df[df.phase <= 1]
    train, test = confound.split_by_match(early)

    # Fitted on train only -- the table is learned from outcomes.
    advantages = recommend.item_advantage(train)
    popularity = train.item_id.value_counts()

    sides = paired.lane_sides(test)
    buys = test[["match_id", "player_slot", "item_id"]].drop_duplicates()
    held = buys.merge(
        sides[["match_id", "player_slot", "lane", "team", "won"]],
        on=["match_id", "player_slot"],
    )
    held["advantage"] = held["item_id"].map(advantages["advantage"])
    held["popularity"] = held["item_id"].map(popularity)

    scored = (
        held.groupby(["match_id", "lane", "team"])
        .agg(
            advantage=("advantage", "mean"),
            popularity=("popularity", "mean"),
            won=("won", "first"),
        )
        .dropna()
    )

    print(f"\nheld-out lane sides: {len(scored):,}")
    print(f"items scored:        {len(advantages)}")
    print(f"  of which significant: {int(advantages['significant'].sum())}\n")

    print("within-lane separation (winner score minus loser score):")
    for column, label in (
        ("advantage", "lane-advantage score"),
        ("popularity", "popularity baseline"),
    ):
        mean, stderr = paired_separation(scored, column)
        sigma = mean / stderr if stderr else float("nan")
        print(f"  {label:22s} {mean:+12.5f}  +-{stderr:.5f}  ({sigma:+.1f} SE)")

    print(
        "\nA positive figure means winning sides held better-scored items."
        "\nThe popularity baseline is the floor this must beat."
    )

    items = assets.load_items()
    print("\ntop 10 items by within-tier lane advantage:")
    for item_id, row in advantages.head(10).iterrows():
        name = items[int(item_id)].name if int(item_id) in items else str(item_id)
        flag = "" if row["significant"] else "  (weak)"
        print(
            f"  {name:26s} {row['advantage']:+.4f}  n={int(row['n']):6d}"
            f"  {int(row['cost'])} souls{flag}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
