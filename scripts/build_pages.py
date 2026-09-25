#!/usr/bin/env python
"""Write the public site: the home page, a page per hero, a page per build,
the methodology page, and the art they show.

The pages' prose and markup are `deadlock.pages`. This script computes the
facts they state and writes the files:

    index.html                       every hero
    methodology.html                 where the builds come from
    <hero>/index.html                a split hero's chooser, or the build
                                     itself when the hero has one archetype
    <hero>/<archetype>/index.html    one build of a split hero
    assets/{items,heroes,abilities}/<id>.png

Every build must pass the staple check (`evaluate.prevalence_gate`) before
anything is written. One that fails stops the script with a non-zero exit, so
a build missing an item most of its players buy is never published.

Art is copied from data/assets/, and anything missing there is downloaded
from the URL the assets API gives for it and kept for next time.

Pass the same --badge as generate_builds.py, so the pages describe the builds.

    python scripts/build_pages.py [--out DIR] [--badge N|all] [--hero NAME]
"""

from __future__ import annotations

import argparse
import dataclasses
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from deadlock import (  # noqa: E402
    abilityorder,
    api,
    archetype,
    assets,
    build,
    cli,
    counters,
    evaluate,
    features,
    ingest,
    pages,
    sequence,
    tooltips,
)

DEFAULT_OUT = Path("data/site/public")
ART = Path("data/assets")

# The page's phase bands. Three, not the model's four: #19 and #20 merged
# "very late" into late because it held one item on Gun Ivy. The minute
# ranges come from features.PHASE_INTERVAL_S, so they move with it.
PHASE_NAMES = ("Laning", "Mid game", "Late game")


@dataclass
class HeroSite:
    hero: str
    hero_id: int
    slug: str
    builds: list[tuple[str, pages.BuildFacts]] = field(default_factory=list)
    cards: list[pages.Card] = field(default_factory=list)


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


def phase_labels() -> tuple[str, ...]:
    minutes = features.PHASE_INTERVAL_S // 60
    labels = []
    for index, name in enumerate(PHASE_NAMES):
        start = index * minutes
        if index == len(PHASE_NAMES) - 1:
            labels.append(f"{name}, {start}+ min")
        else:
            labels.append(f"{name}, {start}–{start + minutes} min")
    return tuple(labels)


def slug(name: str) -> str:
    """A URL segment for a hero or archetype name: "Mo & Krill" -> "mo-krill"."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower().replace("'", "")).strip("-")


def collect(
    badge: float | None, hero_filter: str | None = None
) -> tuple[list[HeroSite], list[str]]:
    """Every hero's builds and chooser cards, and the builds that fail the gate."""
    labels, meta = archetype.load()
    model = cli.load_model(badge=badge)
    ability_model, ability_frame = cli.load_ability_model(badge=badge)
    lifts = cli.load_counters()
    purchases = pd.read_parquet(cli.PURCHASES, columns=cli.COLUMNS)
    playable = assets.playable_heroes()
    hero_names = {i: h.name for i, h in assets.load_heroes().items()}
    item_names = {i: it.name for i, it in assets.load_items().items()}
    phases = phase_labels()
    item_tips = {
        entry["id"]: tooltips.item_tooltip(entry)
        for entry in api.get("/v1/assets/items", cache_dir=assets.DEFAULT_CACHE)
        if entry.get("type") == "upgrade"
    }
    wanted = assets.resolve_hero(hero_filter) if hero_filter else None

    heroes: list[HeroSite] = []
    failures: list[str] = []
    for hero_key, entry in meta.get("heroes", {}).items():
        hero_id = int(hero_key)
        if hero_id not in playable or (wanted is not None and hero_id != wanted):
            continue
        hero_name = playable[hero_id].name
        site = HeroSite(hero=hero_name, hero_id=hero_id, slug=slug(hero_name))
        hero_rows = purchases[purchases["hero_id"] == hero_id]

        for arch in entry.get("archetypes", []):
            archetype_id = int(arch["archetype_id"])
            name = arch.get("name") or hero_name
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
                archetype_name=name,
            )
            item_ids = [i.item_id for i in generated.items]
            gate = evaluate.prevalence_gate(
                item_ids, cell, hero_id=hero_id, archetype_id=archetype_id
            )
            # Same rule as generate_builds.py: a cell too thin to judge is
            # inconclusive, not a failure.
            if gate.missing:
                failures.append(f"{name}: {gate.describe(item_names)}")

            points = []
            if ability_model is not None:
                try:
                    points = abilityorder.generate_order(
                        ability_model,
                        ability_frame,
                        hero_id,
                        archetype_id,
                        target_badge=badge,
                    )
                except ValueError as exc:
                    print(f"  no ability order for {name}: {exc}", file=sys.stderr)

            targets = [
                t for t in cli.load_imbue_targets(cell, item_ids)
                if t.ability_id is not None
            ]
            imbue_by_item = {
                t.item_id: pages.Imbue(
                    item=t.item_name,
                    ability=t.ability_name,
                    share=t.share,
                    n=t.n,
                    ability_id=t.ability_id,
                    split=t.split,
                )
                for t in targets
            }
            imbues = tuple(imbue_by_item.values())
            into = build.absorbed_into(generated)
            uptake = evaluate.item_uptake(cell)
            arch_slug = slug(name)
            facts = pages.BuildFacts(
                hero=hero_name,
                hero_id=hero_id,
                archetype=name,
                share=float(arch["share"]),
                n=int(arch["n"]),
                items=tuple(
                    pages.Item(
                        item_id=i.item_id,
                        name=i.name,
                        cost=i.cost,
                        phase=min(
                            int(features.phase_of(i.buy_time_s)), len(PHASE_NAMES) - 1
                        ),
                        buyers=int(uptake.loc[i.item_id, "buyers"]),
                        players=int(uptake.loc[i.item_id, "players"]),
                        position=int(uptake.loc[i.item_id, "position"]),
                        builds_into=into[i.position].name if i.position in into else None,
                        imbue=imbue_by_item.get(i.item_id),
                        tooltip=item_tips.get(i.item_id),
                    )
                    for i in generated.items
                ),
                phases=phases,
                abilities=tuple(
                    pages.AbilityPoint(
                        ability_id=p.ability_id,
                        name=p.ability_name,
                        cost=_point_cost(p.level),
                    )
                    for p in points
                ),
                counter_picks=tuple(
                    pages.CounterPick(
                        enemy=hero_names.get(c.enemy_hero_id, "?"),
                        item=item_names.get(c.item_id, str(c.item_id)),
                        facing=c.facing_rate,
                        baseline=c.baseline_rate,
                        n=c.n_facing,
                    )
                    for c in counters.for_build(lifts, item_ids)
                ),
                chooser_href=None,
            )
            site.builds.append((arch_slug, facts))

            columns = evaluate.item_columns(cell, arch.get("top_items", []))
            site.cards.append(
                pages.Card(
                    archetype=name,
                    href=f"{arch_slug}/index.html",
                    share=float(arch["share"]),
                    win_rate=float(arch["win_rate"]),
                    n=int(arch["n"]),
                    most_common=_entries(columns.most_common, item_names),
                    defining=_entries(columns.defining, item_names),
                    imbues=imbues,
                )
            )
        # Decided after the loop: an archetype with no players is skipped, so
        # a split hero can end up with one build, and then it has no chooser.
        if len(site.builds) > 1:
            site.builds = [
                (s_, dataclasses.replace(f, chooser_href="../index.html"))
                for s_, f in site.builds
            ]
        slugs = [s_ for s_, _ in site.builds]
        if len(set(slugs)) != len(slugs):
            raise SystemExit(f"{hero_name} has two archetypes with one URL: {slugs}")
        if site.builds:
            heroes.append(site)
    return sorted(heroes, key=lambda h: h.hero), failures


def _point_cost(level: int) -> int | None:
    """What a point at this level costs in ability points; None for an unlock.

    From abilityorder.LEVEL_COST: an unlock spends its own currency (type 2),
    and upgrades spend ability points (type 1).
    """
    currency, change = abilityorder.LEVEL_COST[level]
    return -change if currency == 1 else None


def _entries(column: list[evaluate.ColumnItem], names: dict[int, str]) -> tuple:
    return tuple(
        pages.ColumnEntry(
            item_id=c.item_id,
            name=names.get(c.item_id, str(c.item_id)),
            rate=c.rate,
            elsewhere=c.elsewhere,
        )
        for c in column
    )


def render(
    heroes: list[HeroSite], bracket: pages.Bracket | None
) -> dict[Path, str]:
    """Every page, keyed by its path under the site root."""
    window = ingest.PATCH_START.date()
    out: dict[Path, str] = {
        Path("index.html"): pages.home(
            heroes=[
                pages.HeroLink(
                    hero=h.hero,
                    hero_id=h.hero_id,
                    href=f"{h.slug}/index.html",
                    builds=len(h.builds),
                )
                for h in heroes
            ],
            bracket=bracket,
            window_start=window,
        ),
        Path("methodology.html"): pages.methodology(
            bracket=bracket, window_start=window
        ),
    }
    for h in heroes:
        if len(h.builds) == 1:
            out[Path(h.slug, "index.html")] = pages.build_page(
                h.builds[0][1], bracket=bracket, window_start=window, root="../"
            )
            continue
        out[Path(h.slug, "index.html")] = pages.chooser(
            hero=h.hero,
            hero_id=h.hero_id,
            cards=h.cards,
            bracket=bracket,
            window_start=window,
            root="../",
        )
        for arch_slug, facts in h.builds:
            out[Path(h.slug, arch_slug, "index.html")] = pages.build_page(
                facts, bracket=bracket, window_start=window, root="../../"
            )
    return out


def art_needed(heroes: list[HeroSite]) -> dict[Path, str | None]:
    """Each image the pages show, mapped to where to download it if it's missing."""
    raw_items = {e["id"]: e for e in api.get("/v1/assets/items", cache_dir=assets.DEFAULT_CACHE)}
    raw_heroes = {e["id"]: e for e in api.get("/v1/assets/heroes", cache_dir=assets.DEFAULT_CACHE)}
    needed: dict[Path, str | None] = {}
    for h in heroes:
        needed[Path("heroes", f"{h.hero_id}.png")] = (
            (raw_heroes.get(h.hero_id) or {}).get("images") or {}
        ).get("icon_hero_card")
        item_ids = {i.item_id for _, b in h.builds for i in b.items}
        item_ids |= {e.item_id for c in h.cards for e in (*c.most_common, *c.defining)}
        for item_id in item_ids:
            entry = raw_items.get(item_id) or {}
            needed[Path("items", f"{item_id}.png")] = entry.get("shop_image") or entry.get("image")
        ability_ids = {p.ability_id for _, b in h.builds for p in b.abilities}
        ability_ids |= {
            i.imbue.ability_id
            for _, b in h.builds
            for i in b.items
            if i.imbue is not None and i.imbue.ability_id is not None
        }
        for ability_id in ability_ids:
            needed[Path("abilities", f"{ability_id}.png")] = (
                raw_items.get(ability_id) or {}
            ).get("image")
    return needed


def copy_art(needed: dict[Path, str | None], out: Path) -> list[str]:
    """Copy each image into the site, downloading any not cached. Returns the misses."""
    missing = []
    for rel, url in sorted(needed.items()):
        cached = ART / rel
        if not cached.exists() and url:
            try:
                response = requests.get(
                    url, headers={"User-Agent": api.USER_AGENT}, timeout=30
                )
            except requests.RequestException:
                response = None
            if response is not None and response.ok and response.content:
                cached.parent.mkdir(parents=True, exist_ok=True)
                cached.write_bytes(response.content)
        if not cached.exists():
            missing.append(str(rel))
            continue
        dest = out / "assets" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(cached, dest)
    return missing


# A stub DOM for the build page's script: one item row and the tooltip. The
# check hovers the row, focuses it, presses Escape and opens it, and fails if
# the tooltip or aria-expanded don't follow.
SCRIPT_CHECK_SETUP = """
function node(extra) {
  var n = { listeners: {}, attrs: {}, hidden: true, innerHTML: "", style: {},
    offsetWidth: 300, offsetHeight: 200,
    addEventListener: function (k, f) { (this.listeners[k] = this.listeners[k] || []).push(f); },
    fire: function (k, e) { (this.listeners[k] || []).forEach(function (f) { f(e || {}); }); },
    setAttribute: function (k, v) { this.attrs[k] = String(v); },
    getBoundingClientRect: function () { return { left: 100, right: 400, top: 50 }; } };
  for (var k in extra) n[k] = extra[k];
  return n;
}
var summary = node({});
var head = node({ innerHTML: "<h4>Item</h4>" });
var facts = node({ innerHTML: "<p>does things</p>" });
var row = node({ open: false, querySelector: function (sel) {
  return sel === "summary" ? summary : sel === ".tiphead" ? head : sel === ".facts" ? facts : null; } });
var tip = node({});
var doc = node({ querySelectorAll: function () { return [row]; },
  getElementById: function (id) { return id === "tip" ? tip : null; } });
var document = doc;
var window = node({ innerWidth: 1280, innerHeight: 900,
  matchMedia: function () { return { matches: true }; } });
function setTimeout(f) { f(); return 1; }
function clearTimeout() {}
"""

SCRIPT_CHECK_RUN = """
function expect(cond, what) { if (!cond) throw new Error(what); }
summary.fire("mouseenter");
expect(!tip.hidden && tip.innerHTML.indexOf("does things") >= 0, "hover shows the tooltip");
doc.fire("keydown", { key: "Escape" });
expect(tip.hidden, "Escape hides the tooltip");
summary.fire("focus");
expect(!tip.hidden, "keyboard focus shows the tooltip");
row.open = true;
row.fire("toggle");
expect(tip.hidden, "opening the row hides the tooltip");
expect(summary.attrs["aria-expanded"] === "true", "aria-expanded follows the row");
console.log("  the build page's script runs: tooltip and aria-expanded behave");
"""


def check_script() -> None:
    """Run the build page's script under node against a stub DOM, if installed."""
    node = shutil.which("node")
    if not node:
        print("  node not found; skipping the script check", file=sys.stderr)
        return
    source = SCRIPT_CHECK_SETUP + pages.PAGE_SCRIPT + SCRIPT_CHECK_RUN
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(source)
        path = f.name
    try:
        result = subprocess.run([node, path], capture_output=True, text=True)
    finally:
        Path(path).unlink(missing_ok=True)
    if result.returncode != 0:
        raise SystemExit(f"the build page's script failed:\n{result.stderr}")
    print(result.stdout.rstrip())


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="directory to write the site into (default: %(default)s)",
    )
    parser.add_argument(
        "--badge",
        default=f"{sequence.DEFAULT_TARGET_BADGE:g}",
        help=(
            "badge the builds are weighted toward, or 'all' for every player "
            "(default: %(default)s)"
        ),
    )
    parser.add_argument("--hero", default=None, help="build only this hero")
    args = parser.parse_args()

    badge = sequence.parse_target_badge(args.badge)
    bracket = measure_bracket(badge)
    heroes, failures = collect(badge, args.hero)
    if failures:
        print("not writing the site; these builds fail the staple check:", file=sys.stderr)
        for line in failures:
            print(f"  {line}", file=sys.stderr)
        return 1

    check_script()
    written = render(heroes, bracket)
    for rel, html in written.items():
        path = args.out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")

    missing = copy_art(art_needed(heroes), args.out)
    if missing:
        print(f"  {len(missing)} images unavailable, e.g. {missing[:3]}", file=sys.stderr)

    n_builds = sum(len(h.builds) for h in heroes)
    stated = (
        "no bracket"
        if bracket is None
        else f"{bracket.tier_name} and above, {bracket.share:.1%} of player-matches"
    )
    print(
        f"wrote {len(written)} pages for {len(heroes)} heroes and {n_builds} builds "
        f"to {args.out} ({stated}; window from {ingest.PATCH_START:%Y-%m-%d})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
