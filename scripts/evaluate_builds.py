#!/usr/bin/env python
"""Report the prevalence staples per hero and the next-item baselines.

The Stage 1 artifact. Run before any model exists, so the bar and the gate are
both fixed in advance rather than chosen after seeing what a model produces.

Usage:
    python scripts/evaluate_builds.py [--hero NAME] [--matches N]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from deadlock import assets, evaluate, splits

PURCHASES = Path("data/processed/purchases.parquet")
COLUMNS = ["match_id", "player_slot", "account_id", "hero_id", "item_id", "buy_index"]

# What the old planner chose for Wraith, per docs/DIAGNOSIS.md. Kept here as a
# calibration point: the gate must fail this build, or it cannot catch the
# failure that motivated the pivot.
OLD_PLANNER_WRAITH = [
    "Golden Goose Egg",
    "Split Shot",
    "Infuser",
    "Escalating Exposure",
]


def report_staples(df: pd.DataFrame, names: dict[int, str], hero_names: dict[int, str]) -> None:
    print("\n=== Prevalence staples per hero (>=70% of players) ===\n")
    print(f"{'hero':16s} {'n':>7s}  staples")
    for hero_id, group in df.groupby("hero_id"):
        result = evaluate.prevalence_gate([], group, hero_id=int(hero_id))
        if result.inconclusive:
            print(f"{hero_names.get(hero_id, hero_id):16s} {result.n:7,}  (inconclusive)")
            continue
        staples = sorted(result.staples.items(), key=lambda kv: -kv[1])
        listed = ", ".join(f"{names[i]} {p:.0%}" for i, p in staples[:4])
        more = f" +{len(staples) - 4}" if len(staples) > 4 else ""
        print(f"{hero_names.get(hero_id, hero_id):16s} {result.n:7,}  {listed}{more}")


def report_old_planner(df: pd.DataFrame, names: dict[int, str], hero_names: dict[int, str]) -> bool:
    """The gate proving itself against the known-bad build."""
    by_name = {v: k for k, v in names.items()}
    wraith_id = next((h for h, n in hero_names.items() if n == "Wraith"), None)
    if wraith_id is None:
        print("\n(Wraith not found; skipping calibration)")
        return True

    build = [by_name[n] for n in OLD_PLANNER_WRAITH if n in by_name]
    result = evaluate.prevalence_gate(build, df[df.hero_id == wraith_id], hero_id=wraith_id)

    print("\n=== Calibration: the old planner's Wraith build ===\n")
    print(f"It chose: {', '.join(OLD_PLANNER_WRAITH)}")
    print(result.describe(names))
    if result.passed:
        print("\n!! The gate PASSED a build a human rejected. The gate is wrong.")
        return False
    print("\nThe gate reproduces the human judgement. Proceed.")
    return True


def report_baselines(df: pd.DataFrame) -> None:
    print("\n=== Next-item baselines (owned items excluded) ===\n")
    for label, split in [
        ("by match", splits.split_by_match),
        ("by account", splits.split_by_account),
        ("by time", splits.split_by_time),
    ]:
        train, test = split(df)
        scored = evaluate.score_baselines(train, test)
        print(f"--- split {label} ---")
        print(scored.to_string(index=False))
        print()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hero", help="restrict the baseline run to one hero")
    parser.add_argument(
        "--matches", type=int, default=6000, help="matches to sample for baselines"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if not PURCHASES.exists():
        logging.error("no %s; run scripts/build_features.py first", PURCHASES)
        return 1

    items = assets.load_items()
    names = {k: v.name for k, v in items.items()}
    hero_names = {k: v.name for k, v in assets.load_heroes().items()}

    df = pd.read_parquet(PURCHASES, columns=COLUMNS)
    logging.info("%s rows, %s player-matches", f"{len(df):,}",
                 f"{len(df[['match_id', 'player_slot']].drop_duplicates()):,}")

    report_staples(df, names, hero_names)
    calibrated = report_old_planner(df, names, hero_names)

    if args.hero:
        hero_id = next((h for h, n in hero_names.items() if n == args.hero), None)
        if hero_id is None:
            logging.error("unknown hero %r", args.hero)
            return 1
        subset = df[df.hero_id == hero_id]
    else:
        sample = pd.Series(df.match_id.unique()).sample(
            min(args.matches, df.match_id.nunique()), random_state=0
        )
        subset = df[df.match_id.isin(set(sample))]

    report_baselines(subset)
    return 0 if calibrated else 1


if __name__ == "__main__":
    sys.exit(main())
