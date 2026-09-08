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
wrong. So whenever node is available the script is both parsed and *run*: every
build is rendered against a DOM stub and the result is checked for the sections
it should contain. A page that parses can still throw on its first render, and
on the page the two failures look identical.

The page must be generated at the same bracket as the builds it is showing --
a page rendered from the default cache while the builds came from another
bracket would disagree with them silently, which is the one thing this project
never ships.

    python scripts/build_site.py [--out PATH] [--hero NAME] [--badge N|all]
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

from deadlock import (  # noqa: E402
    abilityorder,
    archetype,
    assets,
    build,
    cli,
    counters,
    evaluate,
    sequence,
)

TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "deadlock"
    / "templates"
    / "builds.html"
)
DEFAULT_OUT = Path("data/site/builds.html")


def collect(
    hero_filter: str | None = None,
    badge: float | None = sequence.DEFAULT_TARGET_BADGE,
) -> list[dict]:
    """Generate every build and reduce it to what the page renders.

    The page shows what `deadlock build` shows: the purchase order, the ability
    order, what to imbue, and the matchups the build's items answer. A web view
    that showed only the items would be a different, smaller product than the
    CLI, and the player would have no way to know what was missing.
    """
    labels, meta = archetype.load()
    model = cli.load_model(badge=badge)
    ability_model, ability_frame = cli.load_ability_model(badge=badge)
    lifts = cli.load_counters() if cli.COUNTERS_PATH.exists() else pd.DataFrame()
    purchases = pd.read_parquet(cli.PURCHASES, columns=cli.COLUMNS)
    heroes = assets.playable_heroes()
    hero_names = {i: h.name for i, h in assets.load_heroes().items()}
    item_names = {i: it.name for i, it in assets.load_items().items()}

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

            order = []
            if ability_model is not None:
                try:
                    order = abilityorder.generate_order(
                        ability_model,
                        ability_frame,
                        hero_id,
                        archetype_id,
                        target_badge=badge,
                    )
                except ValueError as exc:
                    print(f"  no ability order for {hero_name}: {exc}", file=sys.stderr)

            item_ids = [item.item_id for item in generated.items]
            targets = cli.load_imbue_targets(cell, item_ids)
            matchups = counters.for_build(lifts, item_ids)

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
                    "abilities": [
                        {
                            "position": point.position + 1,
                            "name": point.ability_name,
                            "level": point.level,
                            "time": point.game_time_s,
                            "p": round(point.probability, 3),
                            "n": point.n,
                            "backoff": point.backoff_level,
                            "thin": point.thin,
                        }
                        for point in order
                    ],
                    "imbue": [
                        {
                            "item": t.item_name,
                            "ability": t.ability_name,
                            "share": round(t.share, 3),
                            "n": t.n,
                            "thin": t.thin,
                            "split": t.split,
                        }
                        for t in targets
                        if t.ability_id is not None
                    ],
                    "counters": [
                        {
                            "item": item_names.get(c.item_id, str(c.item_id)),
                            "enemy": hero_names.get(c.enemy_hero_id, "?"),
                            "lift": round(c.lift, 4),
                            "facing": round(c.facing_rate, 4),
                            "baseline": round(c.baseline_rate, 4),
                            "n": c.n_facing,
                        }
                        for c in matchups
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


# A DOM small enough to run the page's render functions and large enough that
# they cannot tell the difference: the three elements the script looks up by
# id, plus createElement.
DOM_SHIM = """
function el() {
  const node = {
    children: [], className: "", type: "", style: {},
    _text: "", innerHTML: "", onclick: null,
    setAttribute() {}, addEventListener() {},
    appendChild(c) { this.children.push(c); },
    append(...c) { this.children.push(...c); },
    replaceChildren() { this.children = []; },
  };
  Object.defineProperty(node, "textContent", {
    get() { return this._text; },
    set(v) { this._text = String(v); },
  });
  return node;
}
const NODES = { list: el(), panel: el(), q: el() };
const document = {
  getElementById: id => NODES[id] || el(),
  createElement: () => el(),
};
"""

# Each build field, and the heading the page must show when that field has
# data. A section that quietly renders to nothing is the failure this catches.
SECTIONS = (
    ("abilities", "Ability order"),
    ("imbue", "What to imbue"),
    ("counters", "Counter-picks"),
)


def exercise_source() -> str:
    """The harness that renders every build and checks what came out."""
    checks = "\n".join(
        '  if (BUILDS[i].{field}.length && !html.includes("{heading}"))'
        '\n    missing.push(BUILDS[i].archetype + ": {heading}");'.format(
            field=field, heading=heading
        )
        for field, heading in SECTIONS
    )
    return (
        "const missing = [];\n"
        "for (let i = 0; i < BUILDS.length; i++) {\n"
        "  current = i;\n"
        "  renderBuild();\n"
        "  const html = NODES.panel.innerHTML;\n"
        '  if (!html || html.length < 200)\n'
        '    throw new Error("build " + i + " rendered nothing");\n'
        + checks
        + "\n}\n"
        'renderList("");\n'
        "if (missing.length)\n"
        '  throw new Error("sections missing: " + missing.slice(0, 5).join("; "));\n'
        'console.log("  rendered " + BUILDS.length + " builds, every section present");\n'
    )


def check_script(html: str) -> None:
    """Parse the page's JavaScript, then run it, if node is available.

    Parsing alone is not enough, and this page is why the rule exists: an
    earlier version shipped with a syntax error that killed the whole script,
    leaving markup that looked fine and did nothing. A version that parses can
    still throw on its first render -- a renderer reading a field the collector
    stopped emitting -- and the symptom on the page is identical.

    So the script is also run against a DOM stub, over every build rather than
    the first, and the rendered panel is checked for the sections it should
    contain. A build with no counter-picks and a cell with no imbues are
    exactly the cases a renderer gets wrong.
    """
    node = shutil.which("node")
    if not node:
        print("  node not found; skipping the JavaScript checks", file=sys.stderr)
        return

    start, end = html.find("<script>"), html.find("</script>")
    if start < 0 or end < 0:
        raise SystemExit("the rendered page has no <script> block")
    script = html[start + len("<script>") : end]

    run_node(node, script, "--check")
    print("  JavaScript parses")
    print(run_node(node, DOM_SHIM + script + exercise_source()).strip())


def run_node(node: str, script: str, *flags: str) -> str:
    """Run one script under node, failing the build on anything it reports."""
    with tempfile.NamedTemporaryFile(
        "w", suffix=".js", delete=False, encoding="utf-8"
    ) as handle:
        handle.write(script)
        path = handle.name
    try:
        result = subprocess.run([node, *flags, path], capture_output=True, text=True)
        if result.returncode != 0:
            raise SystemExit(f"the page's JavaScript failed:\n{result.stderr}")
        return result.stdout
    finally:
        Path(path).unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--hero", type=str, default=None, help="just one hero")
    parser.add_argument(
        "--badge",
        default=str(sequence.DEFAULT_TARGET_BADGE),
        help="badge to weight the builds toward, or 'all' for the whole population",
    )
    args = parser.parse_args()

    badge = sequence.parse_target_badge(args.badge)
    print(f"rendering builds weighted toward {sequence.describe_badge(badge)}")
    builds = collect(args.hero, badge=badge)
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
