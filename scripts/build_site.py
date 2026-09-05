"""Render every generated build into a single browsable page.

A read-only view of what `deadlock build` produces, for looking over all 75
hero-and-archetype builds at once rather than one command at a time. The page
is self-contained: the build data is inlined, so it opens from a file path with
no server.

The template lives in `src/deadlock/templates/builds.html` and carries the
markup, styling and render functions. This script supplies the data and checks
the result before writing it.

That check is not ceremony. An earlier version of this page shipped with a
JavaScript syntax error -- a double-quoted string containing double-quoted
attributes -- which killed the whole script, so the page rendered static markup
with a dead search box and an empty build panel. Nothing in the HTML looked
wrong. `node --check` catches it in a second, so it runs here whenever node is
available.

    python scripts/build_site.py [--out PATH] [--hero NAME]
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from deadlock import archetype, assets, build, cli, evaluate  # noqa: E402

TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "deadlock"
    / "templates"
    / "builds.html"
)
DEFAULT_OUT = Path("data/site/builds.html")


def collect(hero_filter: str | None = None) -> list[dict]:
    """Generate every build and reduce it to what the page renders."""
    labels, meta = archetype.load()
    model = cli.load_model()
    purchases = pd.read_parquet(cli.PURCHASES, columns=cli.COLUMNS)
    heroes = assets.playable_heroes()

    wanted = assets.resolve_hero(hero_filter) if hero_filter else None
    rows: list[dict] = []

    for hero_key, entry in meta.get("heroes", {}).items():
        hero_id = int(hero_key)
        if hero_id not in heroes or (wanted is not None and hero_id != wanted):
            continue
        hero_name = heroes[hero_id].name
        hero_rows = purchases[purchases["hero_id"] == hero_id]

        for archetype_entry in entry.get("archetypes", []):
            archetype_id = int(archetype_entry["archetype_id"])
            cell = hero_rows.merge(
                labels[
                    (labels["hero_id"] == hero_id)
                    & (labels["archetype_id"] == archetype_id)
                ][["match_id", "player_slot"]],
                on=["match_id", "player_slot"],
            )
            if cell.empty:
                continue

            prevalence = evaluate.item_prevalence(cell)
            staples = {
                int(i): float(v)
                for i, v in prevalence[
                    prevalence >= evaluate.PREVALENCE_THRESHOLD
                ].items()
            }
            generated = build.generate_build(
                hero_id,
                archetype_id,
                model,
                staples=staples,
                hero_name=hero_name,
                archetype_name=archetype_entry.get("name", ""),
            )
            gate = evaluate.prevalence_gate(
                [item.item_id for item in generated.items],
                cell,
                hero_id=hero_id,
                archetype_id=archetype_id,
            )
            if not gate.passed:
                print(
                    f"  WARNING {generated.label} fails the gate",
                    file=sys.stderr,
                )

            rows.append(
                {
                    "hero": hero_name,
                    "archetype": archetype_entry.get("name") or hero_name,
                    "share": archetype_entry.get("share"),
                    "win_rate": archetype_entry.get("win_rate"),
                    "n": archetype_entry.get("n"),
                    "n_staples": len(gate.staples),
                    "items": [
                        {
                            "name": item.name,
                            "cost": item.cost,
                            "time": item.buy_time_s,
                            "p": round(item.probability, 3),
                            "n": item.n,
                            "level": item.backoff_level,
                            "sold": item.sell_time_s,
                            "staple": item.item_id in staples,
                        }
                        for item in generated.items
                    ],
                }
            )

    return sorted(rows, key=lambda r: (r["hero"], r["archetype"]))


def render(builds: list[dict]) -> str:
    """Inline the data into the template."""
    template = TEMPLATE.read_text(encoding="utf-8")
    payload = "const BUILDS = " + json.dumps(builds, separators=(",", ":")) + ";\n"
    marker = "<script>\nconst clock"
    if marker not in template:
        raise SystemExit(f"{TEMPLATE} no longer has the expected script opening")
    return template.replace(marker, "<script>\n" + payload + "const clock", 1)


def check_script(html: str) -> None:
    """Syntax-check the page's JavaScript, if node is available.

    A syntax error takes down the entire script and leaves a page that looks
    fine but does nothing, so this is worth failing the build over.
    """
    node = shutil.which("node")
    if not node:
        print("  node not found; skipping the JavaScript syntax check", file=sys.stderr)
        return

    start, end = html.find("<script>"), html.find("</script>")
    if start < 0 or end < 0:
        raise SystemExit("the rendered page has no <script> block")

    with tempfile.NamedTemporaryFile(
        "w", suffix=".js", delete=False, encoding="utf-8"
    ) as handle:
        handle.write(html[start + len("<script>") : end])
        path = handle.name
    try:
        result = subprocess.run(
            [node, "--check", path], capture_output=True, text=True
        )
        if result.returncode != 0:
            raise SystemExit(f"the page's JavaScript does not parse:\n{result.stderr}")
        print("  JavaScript parses")
    finally:
        Path(path).unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--hero", type=str, default=None, help="just one hero")
    args = parser.parse_args()

    builds = collect(args.hero)
    if not builds:
        raise SystemExit("no builds generated")

    html = render(builds)
    check_script(html)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(html, encoding="utf-8")
    purchases = sum(len(b["items"]) for b in builds)
    print(
        f"{len(builds)} builds, {purchases} purchases -> {args.out} "
        f"({args.out.stat().st_size:,} bytes)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
