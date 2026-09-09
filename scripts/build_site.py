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

Beyond what the command line prints, the page does the two things only a page
can: it puts two archetypes of one hero side by side with the purchases unique
to each marked, which is the question a three-archetype hero raises, and it
hands over the importable JSON. That export drops every absorbed component --
the game's schema cannot express a sale -- so the page states the loss with
this build's own count rather than an average.

Every figure on the page is generated, including the masthead and the footer.
The accuracy figures are read from the README's held-out table rather than
copied here, so the page cannot end up quoting a number from a different run.

The page must be generated at the same bracket as the builds it is showing --
a page rendered from the default cache while the builds came from another
bracket would disagree with them silently, which is the one thing this project
never ships. The page names the bracket it was built at, for the same reason.

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
    buildfmt,
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

            # The same JSON `deadlock build --export` writes, carried inline so
            # the page can hand over a file without a server. Only held items
            # survive the schema, which is why the page states the loss.
            export = buildfmt.to_deadlock_json(
                generated,
                ability_order=order,
                imbue_targets={
                    t.item_id: t.ability_id
                    for t in targets
                    if t.ability_id is not None
                },
                description=(
                    "Purchase order. Only held items are exported: the build "
                    "schema cannot express a sale, and about a third of these "
                    "purchases are components absorbed into later items."
                ),
            )

            rows.append(
                {
                    "hero": hero_name,
                    "archetype": archetype_entry.get("name") or hero_name,
                    "share": archetype_entry.get("share"),
                    "win_rate": archetype_entry.get("win_rate"),
                    "n": archetype_entry.get("n"),
                    "n_staples": len(gate.staples),
                    "export": export,
                    "items": [
                        {
                            "id": int(item.item_id),
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


README = Path(__file__).resolve().parents[1] / "README.md"

# The two accuracy figures the masthead shows, as they are written in the
# README's held-out table. They are read from there rather than typed here so
# the page cannot drift from the measurement: two numbers from two different
# runs is the comparison this project does not make, and a page that had its
# own copy of them would be exactly that, silently.
METRIC_ROWS = {"bigram": "bigram (the bar)", "top1": "backoff chain"}


def read_metrics() -> dict[str, float]:
    """Pull the held-out accuracies out of the README's table."""
    figures: dict[str, float] = {}
    for line in README.read_text(encoding="utf-8").splitlines():
        cells = [cell.strip().strip("*") for cell in line.split("|")]
        if len(cells) < 4:
            continue
        for key, label in METRIC_ROWS.items():
            if cells[1] == label:
                figures[key] = float(cells[2])
    missing = [METRIC_ROWS[key] for key in METRIC_ROWS if key not in figures]
    if missing:
        raise SystemExit(
            f"{README} no longer has the held-out rows: {', '.join(missing)}"
        )
    return figures


def page_meta(badge: float | None) -> dict:
    """What the masthead and footer state, measured rather than typed."""
    purchases = pd.read_parquet(cli.PURCHASES, columns=["match_id", "player_slot"])
    players = len(purchases.drop_duplicates(["match_id", "player_slot"]))
    return {
        **read_metrics(),
        "purchases": f"{len(purchases):,}",
        "players": f"{players / 1000:.0f}k" if players >= 1000 else str(players),
        "bracket": sequence.describe_badge(badge),
    }


def render(builds: list[dict], meta: dict) -> str:
    """Inline the data into the template."""
    template = TEMPLATE.read_text(encoding="utf-8")
    payload = (
        "const BUILDS = " + json.dumps(builds, separators=(",", ":")) + ";\n"
        "const META = " + json.dumps(meta, separators=(",", ":")) + ";\n"
    )
    marker = "<script>\nconst clock"
    if marker not in template:
        raise SystemExit(f"{TEMPLATE} no longer has the expected script opening")
    return template.replace(marker, "<script>\n" + payload + "const clock", 1)


# A DOM small enough to run the page's render functions and large enough that
# they cannot tell the difference: the elements the script looks up by id,
# plus createElement and the handful of browser globals the export path uses.
#
# The export path is stubbed rather than skipped for a reason. Downloading is
# the one thing this page does that leaves it, so a typo there is invisible on
# every build that renders -- the panel looks perfect and the button does
# nothing. Stubbing Blob and URL lets the harness press it.
DOM_SHIM = """
function el() {
  const node = {
    children: [], className: "", type: "", style: {},
    _text: "", innerHTML: "", onclick: null, href: "", download: "",
    hidden: false, value: "",
    setAttribute() {}, addEventListener() {}, removeAttribute() {},
    appendChild(c) { this.children.push(c); return c; },
    append(...c) { this.children.push(...c); },
    replaceChildren(...c) { this.children = c; },
    remove() {}, click() { this.clicked = true; },
    closest() { return null; },
  };
  Object.defineProperty(node, "textContent", {
    get() { return this._text; },
    set(v) { this._text = String(v); },
  });
  return node;
}
const NODES = {
  list: el(), panel: el(), q: el(), facts: el(), footer: el(),
};
const document = {
  getElementById: id => NODES[id] || el(),
  createElement: () => el(),
  body: el(),
};
class Blob {
  constructor(parts) { this.parts = parts; this.size = String(parts).length; }
}
const URL = { createObjectURL: () => "blob:stub", revokeObjectURL() {} };
"""

# Each build field, and the heading the page must show when that field has
# data. A section that quietly renders to nothing is the failure this catches.
SECTIONS = (
    ("abilities", "Ability order"),
    ("imbue", "What to imbue"),
    ("counters", "Counter-picks"),
    ("export", "Take it into the game"),
)


def exercise_source() -> str:
    """The harness that renders every build and checks what came out."""
    # `export` is an object and the rest are arrays, so emptiness is asked as
    # "is there anything in it" rather than `.length`, which an object lacks.
    checks = "\n".join(
        '  if (present(BUILDS[i].{field}) && !html.includes("{heading}"))'
        '\n    missing.push(BUILDS[i].archetype + ": {heading}");'.format(
            field=field, heading=heading
        )
        for field, heading in SECTIONS
    )
    return (
        "const present = v =>\n"
        "  Array.isArray(v) ? v.length : (v && Object.keys(v).length);\n"
        # The masthead and footer are written from META, so a field the
        # collector stopped sending would show as "undefined" on a page that
        # otherwise renders perfectly.
        "renderMeta();\n"
        "[NODES.facts.innerHTML, NODES.footer.innerHTML].forEach(text => {\n"
        "  if (!text || text.includes(\"undefined\") || text.includes(\"NaN\"))\n"
        '    throw new Error("the masthead or footer is missing a figure");\n'
        "});\n"
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
        # Downloading and comparing are the two things whose failure the panel
        # cannot show: the markup renders either way and the control is dead.
        # So both are actually operated here, on every build that offers them.
        "for (let i = 0; i < BUILDS.length; i++) {\n"
        "  current = i;\n"
        "  const file = exportFile(BUILDS[i]);\n"
        "  if (!file.name.endsWith(\".json\"))\n"
        '    throw new Error("export of build " + i + " has no filename");\n'
        "  const parsed = JSON.parse(file.text);\n"
        "  if (!parsed.hero_build || !parsed.hero_build.details.mod_categories.length)\n"
        '    throw new Error("export of build " + i + " carries no items");\n'
        "  downloadBuild(BUILDS[i]);\n"
        "}\n"
        "let compared = 0;\n"
        "Object.keys(byHero).forEach(hero => {\n"
        "  if (byHero[hero].length < 2) return;\n"
        "  current = byHero[hero][0].i;\n"
        "  other = byHero[hero][1].i;\n"
        "  renderBuild();\n"
        "  const html = NODES.panel.innerHTML;\n"
        '  if (!html.includes("Side by side"))\n'
        '    throw new Error(hero + ": comparison did not render");\n'
        "  if (!html.includes(esc(BUILDS[other].archetype)))\n"
        '    throw new Error(hero + ": comparison omits the other build");\n'
        "  compared++;\n"
        "});\n"
        "other = null;\n"
        # A one-hero page can legitimately have nothing to compare, so this
        # only fires when the data offered a pair and the panel did not show
        # it -- silence from a renderer that had the input is the bug.
        "const pairs = Object.keys(byHero).filter(h => byHero[h].length > 1).length;\n"
        "if (pairs && !compared)\n"
        '  throw new Error(pairs + " heroes have two builds and none compared");\n'
        'console.log("  rendered " + BUILDS.length + " builds, every section '
        'present;\\n  exported " + BUILDS.length + " files, compared " + compared '
        '+ " heroes");\n'
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

    html = render(builds, page_meta(badge))
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
