#!/usr/bin/env python
"""Generate a build for every hero and export it as Deadlock-importable JSON.

The point is inspection. Aggregate metrics say the ranking carries signal;
only reading whole builds shows whether they make sense to someone who plays
the game. Bad builds here are worth more than a good AUC.

Usage:
    python scripts/make_builds.py                  # all heroes
    python scripts/make_builds.py Wraith Infernus  # named heroes
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd

from deadlock import assets, confound, planner, recommend

OUT_DIR = Path("data/builds")


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    path = Path("data/processed/purchases.parquet")
    if not path.exists():
        print(f"missing {path}; run scripts/build_features.py first")
        return 1

    df = pd.read_parquet(path)
    early = df[df.phase <= 1]

    # Fitted on the training split only, so the exported builds are not tuned
    # to data any later evaluation would use.
    train, _ = confound.split_by_match(early)
    global_table = recommend.item_advantage(train)

    heroes = assets.playable_heroes()
    wanted = sys.argv[1:]
    if wanted:
        lowered = {name.lower() for name in wanted}
        heroes = {i: h for i, h in heroes.items() if h.name.lower() in lowered}
        if not heroes:
            print(f"no heroes matched {wanted}")
            return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for hero_id in sorted(heroes):
        advantages = planner.blended_advantage(
            train, hero_id, global_table=global_table
        )
        build = planner.plan_build(advantages, hero_id)
        if not build.items:
            print(f"{heroes[hero_id].name}: no build (insufficient data)")
            continue

        slug = heroes[hero_id].name.lower().replace(" ", "_").replace("&", "and")
        planner.export_build(build, OUT_DIR / f"{slug}.json")
        print(build)
        print()

    print(f"exported to {OUT_DIR}/")
    print(
        "\nScores are lane-level win-rate advantages, centred within cost tier "
        "and shrunk\nby sample size. Purchase tempo outweighs item choice in "
        "every model measured\nhere, so spending souls promptly matters more "
        "than following this exactly."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
