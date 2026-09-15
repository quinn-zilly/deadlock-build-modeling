#!/usr/bin/env python
"""Pull Ranked/Normal match metadata into the local cache.

Windowed to the current patch era by default: balance patches shift item
value, so mixing eras muddies item effects.

Usage:  python scripts/pull_data.py [n_matches]

Cost, before you start it (measured on 2026-09-14): 25,000 matches is 125
pages, **about 25 minutes and 11 GB on disk**. `include_objectives` and
`include_mid_boss` roughly doubled page size, from ~43 MB to ~88 MB per 200
matches, so an older 5.3 GB estimate no longer holds. Every page is cached by
its (max_match_id, limit) bound, so an interrupted run resumes and costs only
the page in flight.

`api.get` keys that cache on the whole parameter set, so **changing
`ingest.BASE_PARAMS` invalidates every cached page** and the next run re-pulls
all of them. Pages are fetched newest-first, so a re-pull is a *newer* window,
not the same matches again: any model number measured against the old file is
not comparable to one measured against the new file.

**This window is the wrong one for `hero_build_id`.** Demo analysis lags the
present by weeks, and paging newest-first from the patch start lands squarely
in the gap: 87 of 24,999 matches carry a build id, against 10.2% over a
six-week window. Work that needs the intended build should pass `max_match_id`
to `ingest.pull_matches` and pull its own older window into a separate
`cache_dir`.
"""

from __future__ import annotations

import datetime as dt
import logging
import sys
from pathlib import Path

from deadlock import ingest

# Latest balance patch as of writing (2026-08-22). Data before this is a
# different game for item-value purposes.
PATCH_START = dt.datetime(2026, 8, 22, tzinfo=dt.timezone.utc)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S"
    )
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 25_000

    pages = ingest.pull_matches(
        n,
        min_unix_timestamp=int(PATCH_START.timestamp()),
        cache_dir=Path("data/raw/matches"),
    )
    matches = sum(1 for _ in ingest.iter_matches(pages))
    logging.info("done: %d pages, %d unique matches", len(pages), matches)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
