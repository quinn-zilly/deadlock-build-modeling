#!/usr/bin/env python
"""Rebuild everything from the cached match pages, in order.

Each step reads what the previous one wrote:

    1. purchases.parquet   scripts/build_features.py
    2. abilities.parquet   scripts/build_abilities.py
    3. imbues.parquet      scripts/build_imbues.py
    4. archetypes          scripts/review_archetypes.py  (labels + review sheet)
    5. builds + the gate   scripts/generate_builds.py
    6. the website         scripts/build_site.py

Steps 1-3 read the match pages and are the slowest. Use --from to start
later, for example when only the archetype fit changed.

If step 5 finds a build missing a staple it exits non-zero, and so does this
script.

First, it deletes the models the CLI has cached, since the CLI would keep
using them otherwise. The CLI refits them on first use.

    python scripts/refit.py [--from STEP] [--badge N|all] [--hero NAME]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (name, script, takes --hero, takes --badge)
STEPS: tuple[tuple[str, str, bool, bool], ...] = (
    ("purchases", "build_features.py", False, False),
    ("abilities", "build_abilities.py", False, False),
    ("imbues", "build_imbues.py", False, False),
    ("archetypes", "review_archetypes.py", False, False),
    ("builds", "generate_builds.py", True, True),
    ("site", "build_site.py", True, True),
)
NAMES = [name for name, _, _, _ in STEPS]

PROCESSED = ROOT / "data" / "processed"

# Files the CLI caches, as (glob pattern, last step that makes it stale).
# Each badge has its own model file, so the models are matched by pattern.
CACHES: tuple[tuple[str, str], ...] = (
    ("sequence_model*", "archetypes"),   # purchases + archetype labels
    ("ability_model*", "archetypes"),    # abilities + archetype labels
    ("counter_lifts.parquet", "purchases"),
)


def clear_caches(processed: Path, start: str) -> list[Path]:
    """Delete the CLI caches that a refit starting at `start` makes stale.

    Returns the deleted paths. They aren't rebuilt here because the CLI
    refits them on first use, for whichever badges are asked for.
    """
    removed = []
    for pattern, stale_after in CACHES:
        if NAMES.index(start) > NAMES.index(stale_after):
            continue
        for path in sorted(Path(processed).glob(pattern)):
            path.unlink()
            removed.append(path)
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--from",
        dest="start",
        default=NAMES[0],
        choices=NAMES,
        help="start at this step, keeping what earlier steps already wrote",
    )
    parser.add_argument(
        "--badge",
        default=None,
        help=(
            "badge to weight the builds and the website toward, or 'all'. "
            "Both steps get the same value."
        ),
    )
    parser.add_argument("--hero", default=None, help="one hero, for a quick check")
    args = parser.parse_args()

    for path in clear_caches(PROCESSED, args.start):
        print(f"== cleared stale CLI cache {path.name}", flush=True)

    start = NAMES.index(args.start)
    for name, script, takes_hero, takes_badge in STEPS[start:]:
        command = [sys.executable, str(ROOT / "scripts" / script)]
        if takes_hero and args.hero:
            command += ["--hero", args.hero]
        if takes_badge and args.badge:
            command += ["--badge", args.badge]

        print(f"== {name}: {' '.join(command[1:])}", flush=True)
        started = time.time()
        result = subprocess.run(command, cwd=ROOT)
        elapsed = time.time() - started
        if result.returncode != 0:
            print(
                f"== {name} failed after {elapsed:.0f}s (exit {result.returncode})",
                file=sys.stderr,
            )
            return result.returncode
        print(f"== {name} done in {elapsed:.0f}s", flush=True)

    print("refit complete; every build passed the prevalence gate")
    print("the CLI refits its cached models on first use (about a minute each)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
