"""Game data from the assets API: items, heroes, abilities, and ranks.

A player's `items` list mixes item purchases with ability-point spends (about
46% are ability points). `upgrade_ids` tells them apart: an entry is a
purchase if its id is an asset of type "upgrade".

The ability-point entries give the full ability-leveling timeline, which
`load_abilities` and `signature_slots` read.
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
    # None except on the few items that imbue an ability. "imbue_active"
    # empowers or copies the ability, "imbue_modifier_value" raises its
    # numbers, and "imbue_active_non_ult" can't target the ultimate.
    imbue: str | None = None

    @property
    def imbueable(self) -> bool:
        return self.imbue is not None


@dataclass(frozen=True)
class Hero:
    id: int
    name: str
    disabled: bool
    in_development: bool


@dataclass(frozen=True)
class Ability:
    id: int
    class_name: str
    name: str
    hero_id: int | None


@dataclass(frozen=True)
class Rank:
    tier: int   # the badge's tens digit
    name: str


def parse_ranks(raw: list[dict[str, Any]]) -> dict[int, Rank]:
    """Rank tiers keyed by tier number, from a /v1/assets/ranks payload."""
    return {
        int(entry["tier"]): Rank(tier=int(entry["tier"]), name=entry["name"])
        for entry in raw
    }


@lru_cache(maxsize=1)
def load_ranks(cache_dir: Path = DEFAULT_CACHE) -> dict[int, Rank]:
    """The twelve rank tiers, Obscurus (0) to Eternus (11), on 2026-09-25.

    Cached like every other asset, so a Valve rename needs the cache cleared.
    """
    return parse_ranks(api.get("/v1/assets/ranks", cache_dir=cache_dir))


@lru_cache(maxsize=1)
def load_items(cache_dir: Path = DEFAULT_CACHE) -> dict[int, Item]:
    """Every upgrade asset, keyed by item id (251 on 2026-09-03).

    Includes upgrades that aren't in the shop. Use `shopable_items` for
    anything a player can buy.
    """
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
            imbue=entry.get("imbue"),
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
    """Every upgrade id. Used to separate purchases from ability-point spends."""
    return frozenset(load_items(cache_dir))


@lru_cache(maxsize=1)
def playable_heroes(cache_dir: Path = DEFAULT_CACHE) -> dict[int, Hero]:
    """Heroes that aren't disabled (38 of 57 on 2026-09-03)."""
    return {h.id: h for h in load_heroes(cache_dir).values() if not h.disabled}


@lru_cache(maxsize=1)
def load_abilities(cache_dir: Path = DEFAULT_CACHE) -> dict[int, Ability]:
    """Hero abilities, keyed by id (389 on 2026-09-04).

    /v1/assets/items returns abilities alongside upgrades, with type
    "ability". Each ability point a player spends appears in their `items`
    list under the ability's id.
    """
    raw: list[dict[str, Any]] = api.get("/v1/assets/items", cache_dir=cache_dir)
    return {
        entry["id"]: Ability(
            id=entry["id"],
            class_name=entry.get("class_name", ""),
            name=entry.get("name", ""),
            hero_id=entry.get("hero"),
        )
        for entry in raw
        if entry.get("type") == "ability"
    }


@lru_cache(maxsize=1)
def hero_signatures(cache_dir: Path = DEFAULT_CACHE) -> dict[int, dict[int, Ability]]:
    """Map hero id to {signature slot 1-4: ability}.

    The reverse of `signature_slots`. Output uses it to name abilities
    ("Crackshot", not "slot 3"). A slot with no matching ability is left out.
    """
    heroes: list[dict[str, Any]] = api.get("/v1/assets/heroes", cache_dir=cache_dir)
    abilities = load_abilities(cache_dir)
    by_class = {a.class_name: a for a in abilities.values()}

    out: dict[int, dict[int, Ability]] = {}
    for hero in heroes:
        signatures = hero.get("items") or {}
        slots: dict[int, Ability] = {}
        for slot in range(1, 5):
            ability = by_class.get(signatures.get(f"signature{slot}"))
            if ability is not None:
                slots[slot] = ability
        if slots:
            out[int(hero["id"])] = slots
    return out


def signature_slots(cache_dir: Path = DEFAULT_CACHE) -> dict[int, int]:
    """Map ability id to signature slot (1-4).

    Each hero's asset entry names its four abilities by class_name under
    `items.signature1` to `signature4`. This joins those names to ability ids.

    99.99% of ability points in match data map to a slot. The rest are Silver's
    (hero 80) three `ability_werewolf_*` abilities, which the hero's signature
    list doesn't include. They are left unmapped.
    """
    heroes: list[dict[str, Any]] = api.get("/v1/assets/heroes", cache_dir=cache_dir)
    by_class = {a.class_name: a.id for a in load_abilities(cache_dir).values()}

    slots: dict[int, int] = {}
    for hero in heroes:
        signatures = (hero.get("items") or {})
        for slot in range(1, 5):
            class_name = signatures.get(f"signature{slot}")
            ability_id = by_class.get(class_name) if class_name else None
            if ability_id is not None:
                slots[ability_id] = slot
    return slots


@lru_cache(maxsize=1)
def shopable_items(cache_dir: Path = DEFAULT_CACHE) -> dict[int, Item]:
    """Items a player can buy (173 of 251 upgrades).

    Recommendations must come from here. The other upgrades are innate or
    disabled. `load_items` keeps them because separating purchases from
    ability points needs every upgrade id.
    """
    raw: list[dict[str, Any]] = api.get("/v1/assets/items", cache_dir=cache_dir)
    shopable = {
        entry["id"]
        for entry in raw
        if entry.get("type") == "upgrade"
        and entry.get("shopable")
        and not entry.get("disabled")
    }
    return {i: item for i, item in load_items(cache_dir).items() if i in shopable}


@lru_cache(maxsize=1)
def component_map(cache_dir: Path = DEFAULT_CACHE) -> dict[int, tuple[int, ...]]:
    """Map item id to the component items it is built from.

    65 of 251 upgrades have components. Chains go up to 3 deep, and two items
    have two components.

    Don't use this to forbid buying a composite before its component. Only
    about 79% of players who buy a composite bought its component first, so
    that rule would block about a fifth of real builds. Use it to prefer an
    order and to check generated builds, never to filter training data.
    """
    raw: list[dict[str, Any]] = api.get("/v1/assets/items", cache_dir=cache_dir)
    by_class = {
        entry.get("class_name"): entry["id"]
        for entry in raw
        if entry.get("type") == "upgrade"
    }
    out: dict[int, tuple[int, ...]] = {}
    for entry in raw:
        if entry.get("type") != "upgrade":
            continue
        components = tuple(
            by_class[c] for c in (entry.get("component_items") or []) if c in by_class
        )
        if components:
            out[entry["id"]] = components
    return out


def _resolve(query: str, options: dict[int, str], kind: str) -> int:
    """Find the id for a typed name.

    Tries an exact match, then case-insensitive, then a unique prefix, then a
    unique substring. Raises KeyError listing the ambiguous matches or some
    close names.
    """
    query = query.strip()
    lowered = query.lower()
    for key, name in options.items():
        if name == query:
            return key
    matches = [k for k, name in options.items() if name.lower() == lowered]
    if len(matches) == 1:
        return matches[0]
    for predicate in (
        lambda name: name.lower().startswith(lowered),
        lambda name: lowered in name.lower(),
    ):
        matches = [k for k, name in options.items() if predicate(name)]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            names = sorted(options[k] for k in matches)
            raise KeyError(
                f"{query!r} matches several {kind}s: {', '.join(names[:6])}"
            )
    close = sorted(
        (name for name in options.values() if lowered[:3] in name.lower()),
    )[:5]
    hint = f" Did you mean: {', '.join(close)}?" if close else ""
    raise KeyError(f"no {kind} matching {query!r}.{hint}")


def resolve_hero(query: str, cache_dir: Path = DEFAULT_CACHE) -> int:
    """Hero id for a typed hero name."""
    return _resolve(
        query, {i: h.name for i, h in playable_heroes(cache_dir).items()}, "hero"
    )


def resolve_item(query: str, cache_dir: Path = DEFAULT_CACHE) -> int:
    """Item id for a typed item name."""
    return _resolve(
        query, {i: it.name for i, it in shopable_items(cache_dir).items()}, "item"
    )
