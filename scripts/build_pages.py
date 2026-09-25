#!/usr/bin/env python
"""Write the public site's pages. For now, the methodology page.

The page's prose is `deadlock.pages`. This script computes the facts it
states: the rank tier at the badge the builds are weighted toward (from the
assets API), that tier's share of player-matches (from purchases.parquet),
and the start of the data window (`ingest.PATCH_START`).

Pass the same --badge as generate_builds.py, so the page describes the builds
it sits beside.

    python scripts/build_pages.py [--out DIR] [--badge N|all]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from deadlock import cli, ingest, pages, sequence  # noqa: E402

DEFAULT_OUT = Path("data/site/public")


def measure_bracket(badge: float | None) -> pages.Bracket | None:
    """The tier name and measured share for a badge, or None for no weighting."""
    if badge is None:
        return None
    frame = pd.read_parquet(
        cli.PURCHASES, columns=["match_id", "player_slot", "average_badge"]
    )
    return pages.Bracket(
        tier_name=sequence.badge_tier_name(badge),
        share=sequence.bracket_share(frame, badge),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="directory to write the pages into (default: %(default)s)",
    )
    parser.add_argument(
        "--badge",
        default=f"{sequence.DEFAULT_TARGET_BADGE:g}",
        help=(
            "badge the builds are weighted toward, or 'all' for every player "
            "(default: %(default)s)"
        ),
    )
    args = parser.parse_args()

    badge = sequence.parse_target_badge(args.badge)
    facts = measure_bracket(badge)
    html = pages.methodology(
        bracket=facts, window_start=ingest.PATCH_START.date()
    )

    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / "methodology.html"
    path.write_text(html, encoding="utf-8")
    stated = (
        "no bracket"
        if facts is None
        else f"{facts.tier_name} and above, {facts.share:.1%} of player-matches"
    )
    print(f"wrote {path} ({stated}; window from {ingest.PATCH_START:%Y-%m-%d})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
