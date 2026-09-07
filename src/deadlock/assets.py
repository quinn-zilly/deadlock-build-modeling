"""Static game assets: items, heroes, and abilities.

The critical export is UPGRADE_IDS. The per-player `items` array returned by
the match metadata endpoint interleaves ability-point spends with actual item
purchases — measured at ~46% ability entries — and the only way to tell them
apart is to join against the asset list on type == "upgrade".

Those ability entries are not noise. They carry the complete ability-leveling
timeline, which is what distinguishes how a hero is being played, so
`load_abilities` and `signature_slots` exist to read them rather than discard
them.

Two asset fields the endpoint returns and the old code never touched:
`item_slot_type` (weapon/vitality/spirit, the archetype signal) and
`component_items` (65 items have prerequisites, referenced by class_name).
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
    # None for all but 11 shopable items. "imbue_active" empowers or copies the
    # ability, "imbue_modifier_value" buffs its numbers, and
    # "imbue_active_non_ult" cannot target the ultimate at all -- so choosing
    # Echo Shard over Mystic Reverb says the build is not about the ult.
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
    """Item ids that represent real purchases, for filtering ability spends."""
    return frozenset(load_items(cache_dir))


@lru_cache(maxsize=1)
def playable_heroes(cache_dir: Path = DEFAULT_CACHE) -> dict[int, Hero]:
    """Heroes actually available in matches (38 of 57 listed as of 2026-09-03)."""
    return {h.id: h for h in load_heroes(cache_dir).values() if not h.disabled}


@lru_cache(maxsize=1)
def load_abilities(cache_dir: Path = DEFAULT_CACHE) -> dict[int, Ability]:
    """Hero abilities, keyed by id (389 as of 2026-09-04).

    These share the /v1/assets/items response with purchasable upgrades and are
    distinguished by type == "ability". They appear in a player's `items` array
    as level-up records, which is how the leveling timeline is recovered.
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
    """Map hero id -> {signature slot 1..4 -> the ability in it}.

    `signature_slots` answers "which slot is this ability", which is all the
    feature path needs. Naming an ability point for a player needs the other
    direction: slot 3 of Holliday is Crackshot, and "put your next point in
    slot 3" is not advice anyone can follow.

    A hero missing a signature simply has no entry for that slot, the same way
    `signature_slots` leaves Silver's reworked abilities unmapped rather than
    guessing at them.
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
    """Map ability id -> signature slot (1..4).

    Each hero's asset entry names its four abilities under `items.signature1`
    through `signature4`, by class_name. Joining those to ability ids gives the
    slot an in-match level-up refers to.

    99.99% of observed ability entries resolve. The exception is hero 80
    (Silver), whose three `ability_werewolf_*` abilities are absent from its
    signature map — a renamed or reworked hero in the asset dump. Callers see
    those as unmapped rather than silently mis-slotted.
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
    """Items that can actually be bought (173 of 251).

    `load_items` deliberately keeps the rest, because filtering ability spends
    needs every upgrade id. Anything ranked as a recommendation should come
    from here instead: the remainder are innate or disabled entries that no
    player can purchase.
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
    """Map item id -> the component items it is built from.

    65 of 251 upgrades have components, referenced by class_name in the raw
    asset and resolved to ids here. Depth reaches 3; two items take two
    components.

    This is a soft ordering prior, NOT a hard constraint. Only ~79% of players
    who buy a composite ever bought its component separately, so forbidding the
    parent before the component would make roughly a fifth of real builds
    unreachable. Use it to prefer an ordering and to check generated builds --
    never to filter training data.
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
    """Match a name the way a person would type it.

    Exact, then case-insensitive, then unique prefix, then unique substring.
    Nobody types 4008176313, and "did you mean" beats a stack trace.
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
    """Hero id from a name a player typed."""
    return _resolve(
        query, {i: h.name for i, h in playable_heroes(cache_dir).items()}, "hero"
    )


def resolve_item(query: str, cache_dir: Path = DEFAULT_CACHE) -> int:
    """Item id from a name a player typed."""
    return _resolve(
        query, {i: it.name for i, it in shopable_items(cache_dir).items()}, "item"
    )
