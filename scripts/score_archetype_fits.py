#!/usr/bin/env python
"""Held-out next-item accuracy under the candidate archetype fits, one run.

The decision in #10 is whether the imbue block belongs in the clustering, and
part of the evidence is what each fit does to the model that conditions on it.
That comparison is only meaningful within a single run: `separation` falls
whenever k rises, top-1 moves with the match sample and the decision cap, and a
figure recorded under one configuration says nothing about a figure recorded
under another. So every fit is built here, from the same purchases, split the
same way, and scored on the same capped set of held-out decisions.

#39 puts ability point **order** through the same test, so the candidate list
is a flag rather than a fixed pair. `families` is always scored, because it is
the control every other fit is read against and a control from another run is
not a control.

    python scripts/score_archetype_fits.py [--matches N] [--limit N]
        [--blocks families,order_mean,...]

Block names: `families`, `conditional imbue`, `order` (raw point order),
`order_mean` (point order minus the hero's own mean) and `order_rank` (point
order as a within-hero percentile).
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from deadlock import (  # noqa: E402
    abilities,
    archetype,
    assets,
    evaluate,
    imbue,
    sequence,
    splits,
)

PURCHASES = Path("data/processed/purchases.parquet")
IMBUES = Path("data/processed/imbues.parquet")
ABILITIES = Path("data/processed/abilities.parquet")
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
ORDER_WEIGHT = 1.0

DEFAULT_BLOCKS = ("families", "conditional imbue")


def candidate_blocks(
    names: tuple[str, ...],
    players: pd.MultiIndex,
    heroes: pd.Series,
) -> dict[str, pd.DataFrame | None]:
    """Build the requested feature blocks, already scaled.

    `families` is the control and carries no block at all, so it is always
    present whatever the caller asked for. A block whose source table is
    missing is skipped with a warning rather than faked: an empty block scores
    as the control and would quietly report a tie.
    """
    out: dict[str, pd.DataFrame | None] = {"families": None}
    wants_order = any(name.startswith("order") for name in names)
    ability_rows = (
        pd.read_parquet(ABILITIES) if wants_order and ABILITIES.exists() else None
    )
    if wants_order and ability_rows is None:
        logging.warning("no abilities table; skipping every order block")

    for name in names:
        if name == "families":
            continue
        if name == "conditional imbue":
            if not IMBUES.exists():
                logging.warning("no imbue table; skipping %s", name)
                continue
            block = imbue.conditional_features(
                pd.read_parquet(IMBUES), players, heroes
            )
            out[name] = archetype.scale_block(block, IMBUE_WEIGHT)
        elif name.startswith("order"):
            if ability_rows is None:
                continue
            if name == "order":
                block = abilities.point_order_features(ability_rows)
            elif name == "order_mean":
                block = abilities.residual_point_order_features(
                    ability_rows, form="mean"
                )
            elif name == "order_rank":
                block = abilities.residual_point_order_features(
                    ability_rows, form="rank"
                )
            else:
                raise ValueError(f"unknown block {name!r}")
            out[name] = archetype.scale_block(block, ORDER_WEIGHT)
        else:
            raise ValueError(f"unknown block {name!r}")
    return out


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
    parser.add_argument(
        "--blocks",
        default=",".join(DEFAULT_BLOCKS),
        help="comma-separated block names to score against the families control",
    )
    args = parser.parse_args()
    wanted = tuple(name.strip() for name in args.blocks.split(",") if name.strip())

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

    blocks = candidate_blocks(wanted, players, heroes)

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
