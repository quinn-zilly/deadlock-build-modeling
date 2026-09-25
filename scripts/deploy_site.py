#!/usr/bin/env python
"""Publish the public site to GitHub Pages. One command, run by hand.

The pages are built from data/, which git ignores, so CI can't build them.
This script builds them here and commits the output to the `site` branch,
which holds only the published files. It then pushes that branch and starts
the Pages workflow (.github/workflows/pages.yml), which publishes it. It uses a
temporary index, so it never touches the checkout or the current branch.

The site redeploys when this runs, never on a timer: a build describes one
data window, and the methodology page says so.

Pass the same --badge as generate_builds.py, so the pages describe the builds.

    python scripts/deploy_site.py [--badge N|all] [--no-push]

--no-push builds and commits the `site` branch locally and stops. Inspect it
with `git show site --stat`.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from deadlock import sequence  # noqa: E402

BRANCH = "site"
WORKFLOW = "pages.yml"
URL = "https://quinn-zilly.github.io/deadlock-build-modeling/"

# Every page the site must have. A deploy missing one stops before pushing.
REQUIRED = ("methodology.html",)


def git(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    ).stdout.strip()


def ref_exists(repo: Path, ref: str) -> bool:
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", "-q", ref],
        capture_output=True,
    ).returncode == 0


def commit_site(repo: Path, directory: Path, branch: str, message: str) -> str:
    """Commit exactly the files under `directory` to `branch`, and return it.

    The commit's tree is the directory and nothing else, so a page the build
    stopped writing disappears. It builds on what was last deployed, the
    remote branch if there is one, so every deploy is a fast-forward.
    """
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(tmp) / "index")}
        work = f"--work-tree={Path(directory).resolve()}"
        git(repo, work, "add", "-A", "-f", ".", env=env)
        tree = git(repo, work, "write-tree", env=env)

    parents: list[str] = []
    for ref in (f"refs/remotes/origin/{branch}", f"refs/heads/{branch}"):
        if ref_exists(repo, ref):
            parents = ["-p", git(repo, "rev-parse", ref)]
            break
    commit = git(repo, "commit-tree", tree, *parents, "-m", message)
    git(repo, "update-ref", f"refs/heads/{branch}", commit)
    return commit


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--badge",
        default=f"{sequence.DEFAULT_TARGET_BADGE:g}",
        help="badge the builds are weighted toward, or 'all' (default: %(default)s)",
    )
    parser.add_argument(
        "--no-push",
        action="store_true",
        help="commit the site branch locally and stop",
    )
    args = parser.parse_args()

    # Base the commit on the deployed branch, if the remote has one.
    subprocess.run(
        ["git", "-C", str(ROOT), "fetch", "-q", "origin", BRANCH],
        capture_output=True,
    )

    with tempfile.TemporaryDirectory() as out:
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "build_pages.py"),
                "--out",
                out,
                "--badge",
                args.badge,
            ],
            cwd=ROOT,
            check=True,
        )
        missing = [name for name in REQUIRED if not (Path(out) / name).exists()]
        if missing:
            raise SystemExit(f"the build wrote no {', '.join(missing)}; not deploying")

        source = git(ROOT, "rev-parse", "--short", "HEAD")
        commit = commit_site(
            ROOT, Path(out), BRANCH, f"Deploy from {source} at badge {args.badge}"
        )
    print(f"committed {commit[:7]} to {BRANCH}")

    if args.no_push:
        print(f"not pushed; inspect with: git show {BRANCH} --stat")
        return 0

    subprocess.run(
        ["git", "-C", str(ROOT), "push", "origin", f"{BRANCH}:{BRANCH}"], check=True
    )
    subprocess.run(["gh", "workflow", "run", WORKFLOW, "--ref", "main"], check=True)
    print(f"started the Pages workflow; the site updates at {URL} in a minute or two")
    print("watch it with: gh run watch")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
