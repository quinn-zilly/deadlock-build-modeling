#!/usr/bin/env python
"""Convert cached match pages into the purchase-level Parquet table.

Usage:  python scripts/build_features.py [out_path]
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from deadlock import dataset, ingest


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S"
    )
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/processed/purchases.parquet")

    pages = ingest.cached_pages()
    if not pages:
        logging.error("no cached pages found; run scripts/pull_data.py first")
        return 1

    logging.info("converting %d cached pages", len(pages))
    dataset.convert_pages(pages, out)

    size_mb = out.stat().st_size / 1e6
    logging.info("wrote %s (%.1f MB)", out, size_mb)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
