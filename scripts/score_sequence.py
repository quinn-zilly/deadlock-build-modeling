"""Score the item model against the baselines on held-out purchases.

The bar is the bigram baseline, scored in the same run on the same decisions
with owned items excluded.

Scores under all three splits. If the model does much better by match than
by account, it is memorizing players. If it does worse by time, the patch has
moved.

With a badge, also scores the weighted and unweighted models on that badge's
decisions only. The weighted model is meant to do worse on all players, so
this is the comparison that shows whether weighting helps.

--ablate adds a kappa sweep and a run without the most specific levels.

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
    """The purchases (first `matches` matches, optionally one hero) and archetype labels."""
    df = pd.read_parquet(PURCHASES, columns=COLUMNS)
    if hero_id is not None:
        df = df[df["hero_id"] == hero_id]
    if matches:
        keep = df["match_id"].drop_duplicates().head(matches)
        df = df[df["match_id"].isin(keep)]
    archetypes = pd.read_parquet(ARCHETYPES)
    return df, archetypes


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--matches",
        type=int,
        default=20000,
        help="use the first N matches, 0 for all (default: %(default)s)",
    )
    parser.add_argument("--hero", type=str, default=None, help="score only this hero")
    parser.add_argument(
        "--limit",
        type=int,
        default=20000,
        help="stop after scoring this many purchases per split (default: %(default)s)",
    )
    parser.add_argument(
        "--ablate",
        action="store_true",
        help="also sweep kappa, and score runs without the most specific backoff levels",
    )
    parser.add_argument(
        "--badge",
        default=f"{sequence.DEFAULT_TARGET_BADGE:g}",
        help=(
            "badge to weight the tables toward, or 'all' for no weighting "
            "(default: %(default)s)"
        ),
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
        # Fit on the training split only, so badge weights never see test rows.
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
            # Judge the weighting here: both models on the same high-badge
            # decisions. Accuracy on all players drops on purpose.
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
            print(f"  correct top-1 picks by backoff level: {share}")

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
