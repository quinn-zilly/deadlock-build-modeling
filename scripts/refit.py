#!/usr/bin/env python
"""Rebuild every derived artifact from the cached pages, in order.

One command, because a refit is five commands that must run in a fixed order
and each one silently reads what the last one wrote. Done by hand it is a
sequence a person gets wrong once and then debugs as if the model were broken.

The order is the dependency order:

    1. purchases.parquet   scripts/build_features.py
    2. abilities.parquet   scripts/build_abilities.py
    3. imbues.parquet      scripts/build_imbues.py
    4. the archetype fit   scripts/review_archetypes.py  (labels + review sheet)
    5. builds + the gate   scripts/generate_builds.py
    6. the browsable page  scripts/build_site.py

Steps 1-3 read the cached match pages and take the longest; `--from` skips
ahead when only the fit downstream of them changed, which is the common case.
Step 5 exits non-zero if any hero-and-archetype build misses a staple, and that
exit code is this script's own: a refit that produces builds which fail the
gate has not succeeded, whatever it wrote to disk.

Before its first step it deletes the models the CLI caches beside the tables, because
the CLI reuses a cache for as long as it exists and would otherwise answer from
the models fitted before this refit.

    python scripts/refit.py [--from STEP] [--badge N|all] [--hero NAME]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (name, script, whether --hero and --badge apply)
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

# What the CLI caches beside the tables, and the step that makes each stale.
# It reuses a cached file for as long as it exists, so a refit that rebuilt the
# tables and left these behind had the CLI answering from the old models. Every
# badge bracket gets its own file, hence a prefix rather than a name.
CACHES: tuple[tuple[str, str], ...] = (
    ("sequence_model*", "archetypes"),   # purchases + archetype labels
    ("ability_model*", "archetypes"),    # abilities + archetype labels
    ("counter_lifts.parquet", "purchases"),
)


def clear_caches(processed: Path, start: str) -> list[Path]:
    """Delete every CLI cache that a refit starting at `start` makes stale.

    Deleted rather than rebuilt: the CLI refits each one on first use, and only
    it knows which brackets a person asks for.
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
            "badge to weight the builds and the page toward, or 'all'; both "
            "steps get the same one, so the page cannot disagree with the "
            "builds it is showing"
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
