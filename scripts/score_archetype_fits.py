#!/usr/bin/env python
"""Held-out next-item accuracy under both candidate archetype fits, one run.

The decision in #10 is whether the imbue block belongs in the clustering, and
part of the evidence is what each fit does to the model that conditions on it.
That comparison is only meaningful within a single run: `separation` falls
whenever k rises, top-1 moves with the match sample and the decision cap, and a
figure recorded under one configuration says nothing about a figure recorded
under another. So both fits are built here, from the same purchases, split the
same way, and scored on the same capped set of held-out decisions.

    python scripts/score_archetype_fits.py [--matches N] [--limit N]
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from deadlock import archetype, assets, evaluate, imbue, sequence, splits  # noqa: E402

PURCHASES = Path("data/processed/purchases.parquet")
IMBUES = Path("data/processed/imbues.parquet")
COLUMNS = [
    "match_id",
    "player_slot",
    "account_id",
    "hero_id",
    "item_id",
    "buy_index",
    "buy_time_s",
    "won",
    "average_badge",
]

IMBUE_WEIGHT = 1.0


def label_frame(
    purchases: pd.DataFrame,
    hero_names: dict[int, str],
    extra: pd.DataFrame | None,
) -> pd.DataFrame:
    """Fit every hero and return the labels alone, skipping the naming pass."""
    frames = []
    for hero_id, group in purchases.groupby("hero_id"):
        fit = archetype.fit_hero(
            group,
            hero_id=int(hero_id),
            hero_name=hero_names.get(int(hero_id), str(hero_id)),
            extra=extra,
        )
        frame = fit.labels.rename("archetype_id").reset_index()
        frame["hero_id"] = int(hero_id)
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matches", type=int, default=20000)
    parser.add_argument("--limit", type=int, default=20000, help="decisions to score")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S"
    )
    df = pd.read_parquet(PURCHASES, columns=COLUMNS)
    if args.matches:
        keep = df["match_id"].drop_duplicates().head(args.matches)
        df = df[df["match_id"].isin(keep)]
    logging.info("%s purchases, %s matches", f"{len(df):,}", f"{df['match_id'].nunique():,}")

    players = archetype.player_index(df)
    heroes = archetype.hero_of(df)
    hero_names = {h: v.name for h, v in assets.load_heroes().items()}

    blocks: dict[str, pd.DataFrame | None] = {"families": None}
    if IMBUES.exists():
        imbue_rows = pd.read_parquet(IMBUES)
        blocks["conditional imbue"] = archetype.scale_block(
            imbue.conditional_features(imbue_rows, players, heroes), IMBUE_WEIGHT
        )
    else:
        logging.warning("no imbue table; scoring the family fit alone")

    train, test = splits.split_by_match(df)
    baselines = evaluate.score_baselines(train, test)
    print(baselines.to_string(index=False))

    for name, extra in blocks.items():
        started = time.time()
        labels = label_frame(df, hero_names, extra)
        k = labels.groupby("hero_id")["archetype_id"].nunique()
        model = sequence.fit(train, labels)
        got = evaluate.next_item_accuracy(model, test, labels, limit=args.limit)
        print(
            f"  {name:18s} top1={got['top1']:.4f}  top3={got['top3']:.4f}  "
            f"n={got['n_decisions']:,}  cells={int(k.sum())}  "
            f"({time.time() - started:.0f}s)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
