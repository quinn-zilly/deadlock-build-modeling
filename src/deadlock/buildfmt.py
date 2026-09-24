"""The Build type, and export to the in-game build browser's JSON format.

A build is a purchase sequence, not an inventory. The median player makes 17
purchases and ends holding 11 or 12 items, because about a third of purchases
are later sold or absorbed. The final inventory alone would lose advice like
"buy Extra Regen early, sell it around 20 minutes".

`Build.items` is the full sequence with sell times. `held_items()` is what is
left at the end, which is all the build browser can import because its format
has no way to say "sell".
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# Cost of each shop tier. Every buyable item's cost is set by its tier. The
# asset file also lists 17 tier 5 items at 9999, but none of 5,095,598
# purchases was tier 5, so they aren't in the shop.
TIER_COSTS = (800, 1600, 3200, 6400)

# Inventory limit, measured on items held at match end (max 12, mean 10.78).
# There is no limit per slot type: 83.5% of players hold more than four items
# of one type.
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
        """The items still held at match end, which is what the game can import."""
        return [item for item in self.items if not item.sold]

    def __str__(self) -> str:
        held = len(self.held_items())
        lines = [
            f"{self.label}: {len(self.items)} purchases, "
            f"{held} held, {self.total_cost:,} souls"
        ]
        lines.extend(f"  {item}" for item in self.items)
        return "\n".join(lines)


def ability_order_json(order: list) -> dict:
    """The ability order in the format `/v1/builds` uses.

    `currency_changes` is a list of 16 entries in spend order, one per point,
    each naming the ability and the point's cost. We checked this against the
    live endpoint: printing one real build's levels in entry order gives
    `1111234223432434`.

    Unlocking an ability costs 1 of currency type 2. Levels 2, 3, and 4 cost
    1, 2, and 5 of type 1. These costs are the game's, copied from the
    endpoint.
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
    """Convert a build to the JSON the in-game build browser imports.

    Uses the same structure as /v1/builds: `mod_categories` holds named groups
    of `mods`, where each mod's `ability_id` is an item id, and
    `ability_order` holds the ability points.

    Only held items are exported, in purchase order, because the format can't
    express selling. The text view shows sell times. The ability order exports
    in full, since points are never refunded.
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
                        # The ability players most often imbue with this item.
                        # None for the items that can't be imbued.
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
                "Timings are medians. Buy each item when you can afford it, "
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
    """Group items into one section per cost, cheapest first, keeping buy order.

    The sections are only for display in the build browser. Build generation
    doesn't limit how many items go in each.
    """
    groups: dict[str, list[BuildItem]] = {}
    for item in items:
        groups.setdefault(f"{item.cost} souls", []).append(item)
    return dict(sorted(groups.items(), key=lambda kv: kv[1][0].cost))


def export_build(build: Build, path: Path, **kwargs) -> Path:
    """Write a build as JSON the game can import. Returns the path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_deadlock_json(build, **kwargs), indent=2))
    return path
