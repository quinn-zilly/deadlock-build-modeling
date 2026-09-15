"""Bulk match ingestion via /v1/matches/metadata.

Why this endpoint and not /v1/sql: the SQL passthrough is limited to 2 req/min
and 20 req/hr per IP, which cannot move a training set. The metadata endpoint
returns items, the 180s net-worth series, and badge in a single call at 200
matches per request.

Two parameter details are load-bearing and were established by testing:

- game_mode must be lowercase ("normal") while match_mode stays capitalized
  ("Ranked"). Mixing the conventions returns HTTP 400.
- The default ordering is oldest-first, which silently yields 2024 matches
  where average_badge is never populated. We page newest-first and also pass a
  recent min_unix_timestamp.

average_badge is populated only for Ranked matches (verified: 1.14M/1.14M
Ranked vs 0/2.13M Unranked), and rank is an essential control, so the modeling
population is Ranked + Normal.

What actually bounds a pull, measured 2026-09-15: bytes, not requests. A
25,000-match pull moves ~11.6 GB, which at the ~13.5 MB/s this machine saw
takes ~14 minutes on its own. Pacing at the endpoint's 9 req/min costs about
the same 14 minutes, so the two floors now coincide and neither dominates.

That has one consequence worth knowing before optimising: raising
MATCHES_PER_PAGE or adding an API key buys close to nothing here, because
both attack the request count while the bytes stay put. Fewer *fields* would
be the lever — see BASE_PARAMS — and 13.5 MB/s is a property of one machine
on one day, so re-measure before trusting the number.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Iterator

from . import api

log = logging.getLogger(__name__)

# The endpoint allows 10000 per page and defaults to 1000. We ask for 200
# because a page is held whole in memory: iter_matches json.loads the entire
# cached file. Measured 2026-09-15 at ~430 KB/match, linear from limit=10 to
# limit=200, so a page costs ~92 MB on disk and ~150 MB parsed. At the
# endpoint's own maximum that would be ~4.7 GB parsing to ~7.5 GB, and the
# download alone would exceed api.get's 180s timeout.
#
# An earlier note here said ~35 MB/200. That was true before e7be5da added
# include_objectives and include_mid_boss; each match grew, the note did not.
MATCHES_PER_PAGE = 200
PLAYERS_PER_MATCH = 12

# What each include flag buys, so a session can see what the endpoint offers
# before concluding a fact is unreachable:
#
#   include_player_items  purchases and their timestamps — the modelled grain
#   include_player_stats  the 180s net-worth series behind every wealth control
#   include_player_info   per-player metadata, including hero_build_id and
#                         pregame_hero_id (no extra flag needed for those)
#   include_objectives    the objective array (18-26 entries, median 20 over
#                         100 sampled matches). It is sparse: an objective that
#                         was never destroyed is sometimes present with the 0/1
#                         sentinel and sometimes absent outright, so absence is
#                         not impossible and must read as "never destroyed".
#                         Walker kills are the item slot clock, and this is the
#                         only source for them
#   include_mid_boss      Mid-Boss kills, the soul injection before a buy
#
# Still unrequested and unconsumed: include_player_death_details,
# include_player_final_stats.
#
# api.get keys its cache on the parameter set, so adding a flag here
# invalidates every cached page and forces a full re-pull.
BASE_PARAMS: dict[str, Any] = {
    "match_mode": "Ranked",      # capitalized
    "game_mode": "normal",       # lowercase — mixing conventions gives HTTP 400
    "include_player_items": "true",
    "include_player_stats": "true",
    "include_player_info": "true",
    "include_objectives": "true",
    "include_mid_boss": "true",
    "order_by": "match_id",
    "order_direction": "desc",   # newest first; default is oldest (no badge)
}


def pull_matches(
    n_matches: int,
    *,
    min_unix_timestamp: int,
    cache_dir: Path = Path("data/raw/matches"),
    max_match_id: int | None = None,
) -> list[Path]:
    """Page newest-first until n_matches are cached. Returns the page files.

    Each page is cached by its (max_match_id, limit) bound, so resuming an
    interrupted pull re-reads from disk and issues no new requests.
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
            log.info("no more matches at cursor %s; stopping early", cursor)
            break

        page_file = api._cache_path(cache_dir, "/v1/matches/metadata", params)
        pages.append(page_file)
        seen += len(batch)

        lowest = min(m["match_id"] for m in batch)
        # Bounds are inclusive, so step past the lowest id or the next page
        # repeats it.
        cursor = lowest - 1
        log.info("pulled %d/%d matches (next cursor %d)", seen, n_matches, cursor)

        if len(batch) < limit:
            log.info("short page (%d < %d); reached end of range", len(batch), limit)
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
    """Every cached metadata page, for re-running feature builds offline."""
    return sorted(Path(cache_dir).glob("v1_matches_metadata__*.json"))
