#!/usr/bin/env python
"""Convert cached match pages into the purchase-level Parquet table.

Usage:  python scripts/build_features.py [out_path]
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from deadlock import dataset, ingest


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "out",
        nargs="?",
        type=Path,
        default=Path("data/processed/purchases.parquet"),
        help="where to write the table (default: %(default)s)",
    )
    args = parser.parse_args()
    out = args.out

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S"
    )

    pages = ingest.cached_pages()
    if not pages:
        logging.error("no cached match pages; run scripts/pull_data.py first")
        return 1

    logging.info("converting %d cached pages", len(pages))
    dataset.convert_pages(pages, out)

    size_mb = out.stat().st_size / 1e6
    logging.info("wrote %s (%.1f MB)", out, size_mb)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
