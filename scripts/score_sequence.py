"""Score the backoff model against the baselines it has to beat.

The bar is measured, not assumed: on the same held-out decisions, with owned
items excluded, the bigram reaches 0.277 top-1. A model that cannot clear that
is not worth its extra machinery.

Reports every metric under all three splits. The match-vs-account gap is the
memorisation signal -- an imitation model can score well by learning that one
account always buys Leech -- and the time gap is patch drift. Both are
reported rather than quietly averaged away.

Under `--badge` the weighted and unweighted models are both scored on the
held-out decisions of that bracket. That pairing is the point: a badge-weighted
model is worse on the general population on purpose, so only the same-bracket
comparison says whether the weighting bought anything.

    python scripts/score_sequence.py [--matches N] [--hero NAME] [--ablate]
                                     [--badge N|all]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from deadlock import assets, evaluate, sequence, splits  # noqa: E402

PURCHASES = Path("data/processed/purchases.parquet")
ARCHETYPES = Path("data/processed/archetypes.parquet")
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


def load(matches: int | None, hero_id: int | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = pd.read_parquet(PURCHASES, columns=COLUMNS)
    if hero_id is not None:
        df = df[df["hero_id"] == hero_id]
    if matches:
        keep = df["match_id"].drop_duplicates().head(matches)
        df = df[df["match_id"].isin(keep)]
    archetypes = pd.read_parquet(ARCHETYPES)
    return df, archetypes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matches", type=int, default=20000)
    parser.add_argument("--hero", type=str, default=None)
    parser.add_argument("--limit", type=int, default=20000, help="decisions to score")
    parser.add_argument("--ablate", action="store_true", help="kappa and level sweep")
    parser.add_argument(
        "--badge",
        default=str(sequence.DEFAULT_TARGET_BADGE),
        help="badge to weight the tables toward, or 'all' for none",
    )
    args = parser.parse_args()

    hero_id = None
    if args.hero:
        heroes = {h.name.lower(): i for i, h in assets.playable_heroes().items()}
        hero_id = heroes[args.hero.lower()]

    df, archetypes = load(args.matches, hero_id)
    print(f"{len(df):,} purchases, {df['match_id'].nunique():,} matches")

    target_badge = sequence.parse_target_badge(args.badge)
    print(f"weighting toward {sequence.describe_badge(target_badge)}")

    for name, split in (
        ("match", splits.split_by_match),
        ("account", splits.split_by_account),
        ("time", splits.split_by_time),
    ):
        train, test = split(df)
        started = time.time()
        # Fitted on the training split alone, so the badge kernel never sees a
        # held-out row -- a weight derived from the test set leaks the answer
        # into the tables, and the leak is invisible in the score it produces.
        model = sequence.fit(train, archetypes, target_badge=target_badge)
        result = evaluate.next_item_accuracy(model, test, archetypes, limit=args.limit)
        baselines = evaluate.score_baselines(train, test)

        print(f"\n--- split by {name} ---")
        print(baselines.to_string(index=False))
        print(
            f"  backoff       top1={result['top1']:.3f}  top3={result['top3']:.3f}  "
            f"n={result['n_decisions']:,}  ({time.time()-started:.0f}s)"
        )
        if target_badge is not None:
            # The figure the weighting is judged on. General-population
            # accuracy gets worse by design here, and win rate is an outcome
            # downstream of every decision the build makes, so neither is the
            # bar. The unweighted model is scored on the same decisions, which
            # is the only comparison that means anything.
            plain = sequence.fit(train, archetypes)
            for label, scored in (("weighted", model), ("unweighted", plain)):
                high = evaluate.next_item_accuracy(
                    scored, test, archetypes, limit=args.limit, min_badge=target_badge
                )
                print(
                    f"  {label:12s} on badge>={target_badge:g}  "
                    f"top1={high['top1']:.3f}  top3={high['top3']:.3f}  "
                    f"n={high['n_decisions']:,}"
                )

        if name == "match" and result["levels"]:
            total = sum(result["levels"].values())
            share = {
                k: f"{v/total:.1%}"
                for k, v in sorted(result["levels"].items())
            }
            print(f"  level carrying correct top-1: {share}")

    if args.ablate:
        train, test = splits.split_by_match(df)
        print("\n--- kappa sweep (match split) ---")
        for kappa in (5.0, 10.0, 20.0, 40.0, 80.0):
            model = sequence.fit(train, archetypes, kappa=kappa)
            got = evaluate.next_item_accuracy(
                model, test, archetypes, limit=args.limit
            )
            print(f"  kappa={kappa:5.0f}  top1={got['top1']:.4f}  top3={got['top3']:.4f}")

        print("\n--- level ablation (match split) ---")
        for label, levels in (
            ("all six", None),
            ("no L0", (1, 2, 3, 4, 5)),
            ("no L0,L1", (2, 3, 4, 5)),
        ):
            model = sequence.fit(train, archetypes, levels=levels)
            got = evaluate.next_item_accuracy(
                model, test, archetypes, limit=args.limit
            )
            rows = sum(len(level.item_ids) for level in model.levels)
            print(f"  {label:10s} top1={got['top1']:.4f}  rows={rows:,}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
