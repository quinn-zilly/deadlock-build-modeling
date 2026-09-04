#!/usr/bin/env python
"""Convert cached match pages into the ability-leveling Parquet table.

A separate pass from `build_features.py` rather than a dual-output rewrite of
it. The purchase table is a known-good 189MB artifact that the regression tests
are calibrated against, and regenerating it to add a second output would put
that at risk for no gain. This pass only touches `player["items"]`, skipping
the net-worth interpolation that makes the purchase build slow.

Usage:  python scripts/build_abilities.py [out_path] [--reconcile N]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from deadlock import abilities, assets, ingest

COLUMNS = [
    "match_id",
    "player_slot",
    "hero_id",
    "ability_id",
    "signature_slot",
    "level",
    "game_time_s",
]


def build(pages: list[Path], limit: int | None = None) -> tuple[pd.DataFrame, dict]:
    """Parse ability level-ups from cached pages.

    Returns the table plus counts for the reconciliation check.
    """
    upgrade_ids = assets.upgrade_ids()
    slots = assets.signature_slots()

    rows: list[dict] = []
    tally = {"matches": 0, "players": 0, "raw_entries": 0, "purchases": 0}

    for match in ingest.iter_matches(pages):
        if limit is not None and tally["matches"] >= limit:
            break
        tally["matches"] += 1
        match_id = match.get("match_id")
        for player in match.get("players") or []:
            tally["players"] += 1
            raw = player.get("items") or []
            tally["raw_entries"] += len(raw)
            tally["purchases"] += sum(1 for e in raw if e.get("item_id") in upgrade_ids)

            for row in abilities.ability_rows(player, upgrade_ids, slots):
                row["match_id"] = match_id
                row["player_slot"] = player.get("player_slot")
                row["hero_id"] = player.get("hero_id")
                rows.append(row)

    df = pd.DataFrame(rows, columns=COLUMNS)
    for column, dtype in [
        ("match_id", "int64"),
        ("player_slot", "int64"),
        ("hero_id", "int64"),
        ("ability_id", "int64"),
        ("signature_slot", "int8"),
        ("level", "int8"),
        ("game_time_s", "int32"),
    ]:
        df[column] = df[column].astype(dtype)
    return df, tally


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("out", nargs="?", default="data/processed/abilities.parquet")
    parser.add_argument(
        "--reconcile",
        type=int,
        default=2000,
        metavar="N",
        help="matches to check purchases+abilities == raw entries (0 to skip)",
    )
    parser.add_argument("--limit", type=int, help="stop after N matches")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S"
    )

    pages = ingest.cached_pages()
    if not pages:
        logging.error("no cached pages found; run scripts/pull_data.py first")
        return 1

    if args.reconcile:
        logging.info("reconciling over %s matches...", f"{args.reconcile:,}")
        _, tally = build(pages, limit=args.reconcile)
        n_abilities = tally["raw_entries"] - tally["purchases"]
        ok, message = abilities.reconcile(
            tally["purchases"], n_abilities, tally["raw_entries"]
        )
        logging.info("reconciliation: %s", message)
        if not ok:
            logging.error("the two paths do not partition the items array; stopping")
            return 1

    logging.info("parsing %s pages...", len(pages))
    df, tally = build(pages, limit=args.limit)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)

    unmapped = int((df["signature_slot"] == abilities.UNMAPPED_SLOT).sum())
    bad_level = int((df["level"] == 0).sum())
    logging.info(
        "%s rows over %s matches / %s players -> %s",
        f"{len(df):,}", f"{tally['matches']:,}", f"{tally['players']:,}", out,
    )
    logging.info(
        "unmapped slots: %s (%.3f%%) | unrecognized levels: %s (%.3f%%)",
        f"{unmapped:,}", 100 * unmapped / max(len(df), 1),
        f"{bad_level:,}", 100 * bad_level / max(len(df), 1),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
