#!/usr/bin/env python
"""Convert cached match pages into the imbue Parquet table.

A third pass over the same pages, alongside `build_features.py` (purchases) and
`build_abilities.py` (ability points), and a separate one for the same reason:
`purchases.parquet` is a known-good artifact the regression tests are
calibrated against, and regenerating it to add a column would risk that for no
gain.

Only imbueable items produce rows -- 9 of 173 shopable items in practice -- so
this table is small even though it reads every page.

**Item and ability ids are int64.** 73 of 173 item ids exceed int32 and wrap
silently to negative numbers if stored narrower; the wrapped id still sorts,
still groups and still wins an argmax, so nothing raises and the model just
gets quietly worse.

Usage:  python scripts/build_imbues.py [out_path] [--limit N]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from deadlock import assets, imbue, ingest

COLUMNS = [
    "match_id",
    "player_slot",
    "hero_id",
    "item_id",
    "imbued_ability_id",
    "signature_slot",
    "imbue_group",
    "game_time_s",
]


def build(pages: list[Path], limit: int | None = None) -> tuple[pd.DataFrame, dict]:
    imbueable = imbue.imbueable_items()
    slots = assets.signature_slots()

    rows: list[dict] = []
    tally = {"matches": 0, "players": 0, "imbueable_bought": 0}

    for match in ingest.iter_matches(pages):
        if limit is not None and tally["matches"] >= limit:
            break
        tally["matches"] += 1
        match_id = match.get("match_id")
        for player in match.get("players") or []:
            tally["players"] += 1
            tally["imbueable_bought"] += sum(
                1 for e in (player.get("items") or []) if e.get("item_id") in imbueable
            )
            for row in imbue.imbue_rows(player, imbueable, slots):
                row["match_id"] = match_id
                row["player_slot"] = player.get("player_slot")
                row["hero_id"] = player.get("hero_id")
                rows.append(row)

    df = pd.DataFrame(rows, columns=COLUMNS)
    for column, dtype in [
        ("match_id", "int64"),
        ("player_slot", "int64"),
        ("hero_id", "int64"),
        ("item_id", "int64"),
        ("imbued_ability_id", "int64"),
        ("signature_slot", "int8"),
        ("game_time_s", "int32"),
    ]:
        df[column] = df[column].astype(dtype)
    return df, tally


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("out", nargs="?", default="data/processed/imbues.parquet")
    parser.add_argument("--limit", type=int, help="stop after N matches")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S"
    )

    pages = ingest.cached_pages()
    if not pages:
        logging.error("no cached pages found; run scripts/pull_data.py first")
        return 1

    logging.info("parsing %s pages for imbues...", len(pages))
    df, tally = build(pages, limit=args.limit)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)

    # Every imbueable purchase must carry a target. If this ever drops below
    # 100% the game has changed, and the "never missing" claim that the whole
    # feature design rests on has stopped holding.
    covered = 100 * len(df) / max(tally["imbueable_bought"], 1)
    unmapped = int((df["signature_slot"] < 1).sum())
    logging.info(
        "%s imbues over %s matches / %s players -> %s",
        f"{len(df):,}", f"{tally['matches']:,}", f"{tally['players']:,}", out,
    )
    logging.info(
        "imbueable purchases carrying a target: %.2f%% | unmapped targets: %s",
        covered, f"{unmapped:,}",
    )
    if covered < 99.0:
        logging.warning(
            "targets are no longer near-universal; the imbue features assume "
            "a target is never missing"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
