"""Build representation and export to Deadlock's build-browser schema.

A *build* here is a purchase sequence, not an inventory. The distinction is
load-bearing: the median player makes 17 purchases but holds only 11-12 items,
because 37.3% of purchases are later sold. Emitting just the final inventory
would silently drop a third of the decisions the model is meant to advise on,
and "buy Extra Regen early, sell it around 20 minutes" is real advice that only
the sequence view can express.

So `Build.items` is the full ordered sequence with sell annotations, and
`held_items()` is the subset that survives to the end -- which is what the
in-game build browser imports, since it has no way to represent a sale.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# Deadlock's shop tiers. Tier 5 exists in the asset file (17 items at cost
# 9999) but is never purchased -- zero rows in 5,095,598 -- so it is not in the
# shop this patch. Cost is a perfect function of tier for everything buyable.
TIER_COSTS = (800, 1600, 3200, 6400)

# The real inventory limit, measured on items held at match end: max 12,
# mean 10.78. There is no per-slot-type cap; 83.5% of players hold more than
# four items of some one type, which the old 4/4/4/3 section prior forbade.
MAX_HELD_ITEMS = 12


@dataclass
class BuildItem:
    """One purchase in a build, in sequence order."""

    item_id: int
    name: str
    cost: int
    position: int
    buy_time_s: float
    probability: float
    n: int
    backoff_level: str
    sell_time_s: float | None = None

    @property
    def sold(self) -> bool:
        return self.sell_time_s is not None

    def __str__(self) -> str:
        clock = f"{int(self.buy_time_s) // 60:2d}:{int(self.buy_time_s) % 60:02d}"
        line = (
            f"{self.position + 1:2d}. {clock}  {self.name:26s} "
            f"{self.cost:5d} souls  p={self.probability:.3f} "
            f"(n={self.n:,}, {self.backoff_level})"
        )
        if self.sold:
            sell = f"{int(self.sell_time_s) // 60}:{int(self.sell_time_s) % 60:02d}"
            line += f"  [usually sold ~{sell}]"
        return line


@dataclass
class Build:
    """An ordered purchase sequence for one hero and archetype."""

    hero_id: int
    hero_name: str
    archetype_id: int = 0
    archetype_name: str = ""
    items: list[BuildItem] = field(default_factory=list)

    @property
    def total_cost(self) -> int:
        return sum(item.cost for item in self.items)

    @property
    def label(self) -> str:
        return self.archetype_name or self.hero_name

    def held_items(self) -> list[BuildItem]:
        """The items still owned at match end -- what the shop can import."""
        return [item for item in self.items if not item.sold]

    def __str__(self) -> str:
        held = len(self.held_items())
        lines = [
            f"{self.label} -- {len(self.items)} purchases, "
            f"{held} held, {self.total_cost:,} souls"
        ]
        lines.extend(f"  {item}" for item in self.items)
        return "\n".join(lines)


def ability_order_json(order: list) -> dict:
    """The ability order, in the shape `/v1/builds` returns it.

    `details.ability_order.currency_changes` is a flat ordered list of 16
    entries, one per point, each naming the ability and what the point cost.
    Verified against the live endpoint: entry order *is* spend order, and each
    ability's own levels appear in ascending order within it -- one real build
    reads `1111234223432434` when levels are printed in entry order.

    Unlocking spends one point of currency type 2; levels 2, 3 and 4 spend 1, 2
    and 5 of type 1. Those costs come from the endpoint rather than from us.
    """
    from . import abilityorder

    return {
        "currency_changes": [
            {
                "ability_id": point.ability_id,
                "currency_type": abilityorder.LEVEL_COST[point.level][0],
                "delta": abilityorder.LEVEL_COST[point.level][1],
                "annotation": (
                    f"~{int(point.game_time_s) // 60}min "
                    f"(p={point.probability:.2f}, n={point.n})"
                ),
            }
            for point in order
        ]
    }


def to_deadlock_json(
    build: Build,
    *,
    name: str | None = None,
    description: str = "",
    ability_order: list | None = None,
    imbue_targets: dict[int, int] | None = None,
) -> dict:
    """Serialize to the hero-build schema Deadlock's build browser accepts.

    Mirrors the structure returned by /v1/builds: `mod_categories` holding
    named groups of `mods`, each keyed by `ability_id` (the item id), and
    `ability_order` holding the point sequence.

    Only held items are exported. The schema has no way to say "buy this, then
    sell it", so an exported build is the surviving inventory in purchase
    order; the sell advice lives in the human-readable view. The ability order
    has no such loss: a point once spent is never refunded, so the sequence
    exports whole.
    """
    held = build.held_items()
    categories = []
    for label, group in _group_by_tier(held).items():
        categories.append(
            {
                "name": label,
                "width": 1030.0,
                "height": 0.0,
                "description": None,
                "mods": [
                    {
                        "ability_id": item.item_id,
                        "annotation": (
                            f"buy ~{int(item.buy_time_s) // 60}min "
                            f"(p={item.probability:.2f}, n={item.n})"
                        ),
                        "required_flex_slots": None,
                        "sell_priority": None,
                        # Deadlock's own schema has always had this field and
                        # this exporter always sent null, so every build it
                        # produced left the imbue choice to the reader. Only
                        # 9 shopable items can be imbued, and for those the
                        # target is what the population actually picks.
                        "imbue_target_ability_id": (imbue_targets or {}).get(
                            item.item_id
                        ),
                    }
                    for item in group
                ],
                "optional": None,
            }
        )

    return {
        "hero_build": {
            "hero_id": build.hero_id,
            "name": name or f"{build.label} - build order",
            "description": description
            or (
                f"Generated from {build.hero_name} purchase sequences over 25k "
                "matches. Items are ordered by when players actually buy them. "
                "Timings are population medians -- buy when you can afford it, "
                "not by the clock."
            ),
            "language": 0,
            "version": 1,
            "tags": [],
            "details": (
                {"mod_categories": categories}
                if not ability_order
                else {
                    "mod_categories": categories,
                    "ability_order": ability_order_json(ability_order),
                }
            ),
        }
    }


def _group_by_tier(items: list[BuildItem]) -> dict[str, list[BuildItem]]:
    """Group a sequence into shop-tier sections, preserving buy order.

    Sections are a presentation device for the build browser, not a constraint
    on generation -- the old code had this backwards and forced builds into a
    4/4/4/3 shape that only 16.5% of real players match.
    """
    groups: dict[str, list[BuildItem]] = {}
    for item in items:
        groups.setdefault(f"{item.cost} souls", []).append(item)
    return dict(sorted(groups.items(), key=lambda kv: kv[1][0].cost))


def export_build(build: Build, path: Path, **kwargs) -> Path:
    """Write a build as Deadlock-importable JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_deadlock_json(build, **kwargs), indent=2))
    return path
