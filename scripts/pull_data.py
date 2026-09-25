#!/usr/bin/env python
"""Download Ranked matches from the current patch into the local cache.

Only matches since `ingest.PATCH_START`, because balance patches change
which items are good.

Usage:  python scripts/pull_data.py [n_matches]

Measured 2026-09-14, 25,000 matches is 125 pages, about 25 minutes, and 11 GB
on disk (about 88 MB per 200-match page). Pages are cached, so an interrupted
run picks up where it stopped.

The cache is keyed on the full parameter set, so changing
`ingest.BASE_PARAMS` makes every cached page miss and the next run downloads
everything again. Pages come newest first, so that re-download is a newer set
of matches. Model scores from before and after aren't comparable.

This window is wrong for `hero_build_id`. Match analysis runs weeks behind,
so the newest matches rarely have it: 87 of 24,999, against 10.2% over a
six-week window. If you need build ids, pass `max_match_id` to
`ingest.pull_matches` to get an older window, and use a separate `cache_dir`.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from deadlock import ingest


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "n_matches",
        nargs="?",
        type=int,
        default=25_000,
        help="how many matches to download (default: %(default)s)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S"
    )

    pages = ingest.pull_matches(
        args.n_matches,
        min_unix_timestamp=int(ingest.PATCH_START.timestamp()),
        cache_dir=Path("data/raw/matches"),
    )
    matches = sum(1 for _ in ingest.iter_matches(pages))
    logging.info("done: %d pages holding %d distinct matches", len(pages), matches)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
