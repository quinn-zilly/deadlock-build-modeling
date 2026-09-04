"""Static game assets: items and heroes.

The critical export is UPGRADE_IDS. The per-player `items` array returned by
the match metadata endpoint interleaves ability-point spends with actual item
purchases — measured at ~46% ability entries — and the only way to tell them
apart is to join against the asset list on type == "upgrade".
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from . import api

DEFAULT_CACHE = Path("data/raw/assets")


@dataclass(frozen=True)
class Item:
    id: int
    class_name: str
    name: str
    slot_type: str | None   # weapon | vitality | spirit
    tier: int | None        # 1..5
    cost: int


@dataclass(frozen=True)
class Hero:
    id: int
    name: str
    disabled: bool
    in_development: bool


@lru_cache(maxsize=1)
def load_items(cache_dir: Path = DEFAULT_CACHE) -> dict[int, Item]:
    """All purchasable upgrades, keyed by item id (251 as of 2026-09-03)."""
    raw: list[dict[str, Any]] = api.get("/v1/assets/items", cache_dir=cache_dir)
    items: dict[int, Item] = {}
    for entry in raw:
        if entry.get("type") != "upgrade":
            continue
        items[entry["id"]] = Item(
            id=entry["id"],
            class_name=entry.get("class_name", ""),
            name=entry.get("name", ""),
            slot_type=entry.get("item_slot_type"),
            tier=entry.get("item_tier"),
            cost=entry.get("cost") or 0,
        )
    return items


@lru_cache(maxsize=1)
def load_heroes(cache_dir: Path = DEFAULT_CACHE) -> dict[int, Hero]:
    raw: list[dict[str, Any]] = api.get("/v1/assets/heroes", cache_dir=cache_dir)
    return {
        entry["id"]: Hero(
            id=entry["id"],
            name=entry.get("name", ""),
            disabled=bool(entry.get("disabled")),
            in_development=bool(entry.get("in_development")),
        )
        for entry in raw
    }


@lru_cache(maxsize=1)
def upgrade_ids(cache_dir: Path = DEFAULT_CACHE) -> frozenset[int]:
    """Item ids that represent real purchases, for filtering ability spends."""
    return frozenset(load_items(cache_dir))


@lru_cache(maxsize=1)
def playable_heroes(cache_dir: Path = DEFAULT_CACHE) -> dict[int, Hero]:
    """Heroes actually available in matches (38 of 57 listed as of 2026-09-03)."""
    return {h.id: h for h in load_heroes(cache_dir).values() if not h.disabled}
