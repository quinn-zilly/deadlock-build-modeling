"""Build planner: generate a full item build for a hero, exportable to Deadlock.

This is the first place the modeling meets a human judgement. An AUC lift of
+0.0169 says the ranking carries signal; it does not say the builds look sane
to someone who plays the game. Generating whole builds makes that checkable.

Two decisions shape what comes out:

**Hero-specific scores are blended with global ones.** A per-hero advantage
table scores ~120 items but only ~30 significantly, because each hero appears
in a fraction of lanes. The global table scores 141 with 70 significant. Hero
and global rankings correlate 0.77 -- related but not redundant -- so the
planner shrinks each hero estimate toward the global one in proportion to how
much evidence backs it. An item with 2,000 hero-specific observations is
trusted on its own; one with 50 is mostly told what the global table says.

**Builds respect the shop, not just the scores.** Ranking items by advantage
alone produces a list nobody could buy in order: all 6400-soul items, no
progression. The planner walks the tiers the way a match does, filling early
slots from cheap items and later ones from expensive, so the output is a
sequence a player can actually follow.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import assets, recommend

log = logging.getLogger(__name__)

# Items with fewer observations than this are shrunk heavily toward the global
# estimate. Chosen to match the point where a per-item standard error (~0.5 /
# sqrt(n)) falls near the size of the effects being measured, ~0.03.
SHRINKAGE_PRIOR_N = 400

# An item needs this many lane observations before it can enter a build.
# Guards against recommending something on no evidence at all.
MIN_BUILD_OBSERVATIONS = 150

# A build's shape, following how a match actually unfolds: cheap items early,
# expensive ones late. Counts are per section.
BUILD_SECTIONS: tuple[tuple[str, int, tuple[int, ...]], ...] = (
    ("lane", 4, (800,)),
    ("early", 4, (800, 1600)),
    ("core", 4, (1600, 3200)),
    ("late", 3, (6400,)),
)


@dataclass
class BuildItem:
    item_id: int
    name: str
    cost: int
    score: float
    n: int
    section: str

    def __str__(self) -> str:
        return f"{self.name:26s} {self.score:+.4f}  {self.cost:5d} souls  (n={self.n:,})"


@dataclass
class Build:
    hero_id: int
    hero_name: str
    items: list[BuildItem] = field(default_factory=list)

    @property
    def total_cost(self) -> int:
        return sum(item.cost for item in self.items)

    def by_section(self) -> dict[str, list[BuildItem]]:
        sections: dict[str, list[BuildItem]] = {}
        for item in self.items:
            sections.setdefault(item.section, []).append(item)
        return sections

    def __str__(self) -> str:
        lines = [f"{self.hero_name} -- {len(self.items)} items, {self.total_cost:,} souls"]
        for section, items in self.by_section().items():
            lines.append(f"\n  [{section}]")
            lines.extend(f"    {item}" for item in items)
        return "\n".join(lines)


def blended_advantage(
    df: pd.DataFrame,
    hero_id: int,
    *,
    global_table: pd.DataFrame | None = None,
    prior_n: int = SHRINKAGE_PRIOR_N,
    min_n: int = 50,
) -> pd.DataFrame:
    """Hero-specific advantage shrunk toward the global estimate.

    weight = n / (n + prior_n), so an item with plenty of hero-specific
    evidence keeps its own score while a rarely-bought one defers to the
    global table. This avoids both extremes: a pure hero table is too noisy to
    rank on, and a pure global table gives every hero the same build.
    """
    if global_table is None:
        global_table = recommend.item_advantage(df)
    hero_table = recommend.item_advantage(df, hero_id=hero_id, min_n=min_n)

    if hero_table.empty:
        return global_table.assign(hero_n=0, blend_weight=0.0)

    joined = global_table.join(
        hero_table[["advantage", "n"]].rename(
            columns={"advantage": "hero_advantage", "n": "hero_n"}
        ),
        how="left",
    )
    joined["hero_n"] = joined["hero_n"].fillna(0)
    joined["blend_weight"] = joined["hero_n"] / (joined["hero_n"] + prior_n)
    joined["hero_advantage"] = joined["hero_advantage"].fillna(joined["advantage"])

    joined["blended"] = (
        joined["blend_weight"] * joined["hero_advantage"]
        + (1 - joined["blend_weight"]) * joined["advantage"]
    )
    return joined.sort_values("blended", ascending=False)


def plan_build(
    advantages: pd.DataFrame,
    hero_id: int,
    *,
    score_column: str = "blended",
    sections: tuple[tuple[str, int, tuple[int, ...]], ...] = BUILD_SECTIONS,
    min_observations: int = MIN_BUILD_OBSERVATIONS,
) -> Build:
    """Assemble a full build, walking the shop tiers in match order.

    Ranking on score alone would return whichever items score highest
    regardless of price -- a build of all 6400-soul items that no player could
    follow. Filling per-section from the allowed price bands keeps the result
    buyable in sequence.
    """
    items = assets.load_items()
    heroes = assets.playable_heroes()
    hero_name = heroes[hero_id].name if hero_id in heroes else str(hero_id)

    if score_column not in advantages.columns:
        score_column = "advantage"

    ranked = advantages.sort_values(score_column, ascending=False)
    chosen: list[BuildItem] = []
    used: set[int] = set()

    for section, count, allowed_costs in sections:
        picked = 0
        for item_id, row in ranked.iterrows():
            if picked >= count:
                break
            item_id = int(item_id)
            if item_id in used or item_id not in items:
                continue
            if items[item_id].cost not in allowed_costs:
                continue
            # Never recommend an item on no evidence. The gate must read the
            # SAME count that is reported: checking the global `n` while
            # displaying `hero_n` let items through with zero hero-specific
            # observations, which is what produced n=0 picks.
            evidence = int(row.get("hero_n", row.get("n", 0)))
            if evidence < min_observations:
                continue
            chosen.append(
                BuildItem(
                    item_id=item_id,
                    name=items[item_id].name,
                    cost=items[item_id].cost,
                    score=float(row[score_column]),
                    n=evidence,
                    section=section,
                )
            )
            used.add(item_id)
            picked += 1

        if picked < count:
            log.warning(
                "section %r for hero %s: only %d of %d items available",
                section, hero_name, picked, count,
            )

    return Build(hero_id=hero_id, hero_name=hero_name, items=chosen)


def to_deadlock_json(build: Build, *, name: str | None = None, description: str = "") -> dict:
    """Serialize to the hero-build schema Deadlock's build browser accepts.

    Mirrors the structure returned by /v1/builds: `mod_categories` holding
    named groups of `mods`, each keyed by `ability_id` (the item id).
    """
    categories = []
    for section, items in build.by_section().items():
        categories.append(
            {
                "name": section,
                "width": 1030.0,
                "height": 0.0,
                "description": None,
                "mods": [
                    {
                        "ability_id": item.item_id,
                        "annotation": f"lane advantage {item.score:+.3f} (n={item.n})",
                        "required_flex_slots": None,
                        "sell_priority": None,
                        "imbue_target_ability_id": None,
                    }
                    for item in items
                ],
                "optional": None,
            }
        )

    return {
        "hero_build": {
            "hero_id": build.hero_id,
            "name": name or f"{build.hero_name} - lane advantage",
            "description": description
            or (
                "Generated from within-lane item advantage over 25k ranked "
                "matches. Scores are lane-level and centred within cost tier. "
                "Purchase tempo matters more than item choice -- spend souls "
                "promptly."
            ),
            "language": 0,
            "version": 1,
            "tags": [],
            "details": {"mod_categories": categories},
        }
    }


def export_build(build: Build, path: Path, **kwargs) -> Path:
    """Write a build as Deadlock-importable JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_deadlock_json(build, **kwargs), indent=2))
    return path
