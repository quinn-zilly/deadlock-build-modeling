"""Bulk match download from /v1/matches/metadata.

This endpoint returns items, the 180s net-worth series, and badge for 200
matches per request. The /v1/sql endpoint is limited to 2 requests a minute
and 20 an hour, which is too slow for a training set.

Two parameter rules, found by testing:

- game_mode is lowercase ("normal") and match_mode is capitalized ("Ranked").
  Mixing the two styles returns HTTP 400.
- The default order is oldest first, which returns 2024 matches with no
  average_badge. We page newest first and also pass a recent
  min_unix_timestamp.

Only Ranked matches have average_badge (1.14M of 1.14M Ranked, 0 of 2.13M
Unranked), so we download Ranked matches in the Normal game mode.

Download size limits a pull more than the request count does. Measured
2026-09-15: a 25,000-match pull is about 11.6 GB, which took about 14 minutes
at 13.5 MB/s. The endpoint's 9 requests a minute also takes about 14 minutes.
So a bigger MATCHES_PER_PAGE or an API key saves almost nothing. Requesting
fewer fields (see BASE_PARAMS) would. The 13.5 MB/s came from one machine on
one day, so measure again before relying on it.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path
from typing import Any, Iterator

from . import api

log = logging.getLogger(__name__)

# The start of the data window: the latest balance patch when this was
# written. scripts/pull_data.py pulls matches since this date, and the public
# site states it, so both read this one value. It is the intended window. The
# pulled matches carry no timestamp, so nothing checks it against the data.
PATCH_START = dt.datetime(2026, 8, 22, tzinfo=dt.timezone.utc)

# The endpoint allows up to 10000 matches per page. We ask for 200 because
# iter_matches loads a whole page into memory. Measured 2026-09-15, a match is
# about 430 KB, so a 200-match page is about 92 MB on disk and 150 MB in
# memory. A 10000-match page would be about 7.5 GB in memory, and its download
# would exceed api.get's 180s timeout.
MATCHES_PER_PAGE = 200
PLAYERS_PER_MATCH = 12

# What each include flag adds:
#
#   include_player_items  purchases and their timestamps
#   include_player_stats  the net-worth series, sampled every 180s
#   include_player_info   per-player metadata, including hero_build_id and
#                         pregame_hero_id
#   include_objectives    the objectives list, 18 to 26 entries per match.
#                         An objective that was never destroyed is sometimes
#                         listed with destroyed_time_s 0 or 1 and sometimes
#                         left out, so treat a missing objective as never
#                         destroyed. This is the only source of Walker kills,
#                         which unlock item slots.
#   include_mid_boss      Mid-Boss kills
#
# Not requested: include_player_death_details, include_player_final_stats.
#
# api.get caches on the full parameter set, so adding a flag here makes every
# cached page miss and forces a full download.
BASE_PARAMS: dict[str, Any] = {
    "match_mode": "Ranked",      # capitalized
    "game_mode": "normal",       # lowercase
    "include_player_items": "true",
    "include_player_stats": "true",
    "include_player_info": "true",
    "include_objectives": "true",
    "include_mid_boss": "true",
    "order_by": "match_id",
    "order_direction": "desc",   # newest first; oldest matches have no badge
}


def pull_matches(
    n_matches: int,
    *,
    min_unix_timestamp: int,
    cache_dir: Path = Path("data/raw/matches"),
    max_match_id: int | None = None,
) -> list[Path]:
    """Download pages, newest first, until n_matches are cached. Returns the page files.

    Pages are cached by their parameters, so rerunning an interrupted pull
    reads the finished pages from disk.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    pages: list[Path] = []
    seen = 0
    cursor = max_match_id

    while seen < n_matches:
        limit = min(MATCHES_PER_PAGE, n_matches - seen)
        params = dict(BASE_PARAMS, limit=limit, min_unix_timestamp=min_unix_timestamp)
        if cursor is not None:
            params["max_match_id"] = cursor

        batch: list[dict[str, Any]] = api.get(
            "/v1/matches/metadata", params, cache_dir=cache_dir
        )
        if not batch:
            log.info("no more matches in range; stopping early")
            break

        page_file = api._cache_path(cache_dir, "/v1/matches/metadata", params)
        pages.append(page_file)
        seen += len(batch)

        lowest = min(m["match_id"] for m in batch)
        # max_match_id is inclusive, so start below the lowest id we have.
        cursor = lowest - 1
        log.info("have %d of %d matches; next page starts at match id %d", seen, n_matches, cursor)

        if len(batch) < limit:
            log.info(
                "page held %d of %d matches, so there are no older ones; stopping",
                len(batch), limit,
            )
            break

    return pages


def iter_matches(pages: list[Path]) -> Iterator[dict[str, Any]]:
    """Stream match dicts from cached page files, de-duplicated by match_id."""
    seen: set[int] = set()
    for page in pages:
        with Path(page).open(encoding="utf-8") as fh:
            for match in json.load(fh):
                mid = match["match_id"]
                if mid in seen:
                    continue
                seen.add(mid)
                yield match


def cached_pages(cache_dir: Path = Path("data/raw/matches")) -> list[Path]:
    """Every cached metadata page, so tables can be rebuilt without downloading."""
    return sorted(Path(cache_dir).glob("v1_matches_metadata__*.json"))
