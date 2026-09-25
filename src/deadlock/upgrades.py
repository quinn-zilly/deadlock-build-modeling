"""What each ability upgrade gives, and which abilities work through the gun.

Two signals read from the ability records in `/v1/assets/items` (issue #42).
Nothing else in this project reads either.

**Upgrade effects.** Each ability has an `upgrades` list of three tiers,
costing 1, 2 and 5 ability points (levels 2, 3 and 4). Each tier's
`property_upgrades` is a list of `{name, bonus}`. `effect_categories` sorts
the property names into a few categories (weapon, shred, control, ...), so a
player's upgrades can be described by what they unlocked rather than by slot.

Which effects a player has unlocked is fixed by which tiers they reached and
when, and the tier-to-effect table is the same for every player on a hero. So
every upgrade-effect feature here is a function of the ability point
timeline. `effect_features` is exactly a per-hero linear projection of
`abilities.point_order_features`: it pools the twelve (slot, level) columns by
the categories each tier unlocks. It can cluster differently from raw order,
because KMeans depends on the geometry, but it cannot carry information that
order doesn't.

**Weapon-attached abilities.** An ability can scale with spirit power and
still work through the weapon (Wraith's Full Auto, Infernus's Afterburn).
`ability_table` flags these from property names and the game's own
`provided_property_type` tags. `behaviours` has no such flag, and `TechPower`
and `WeaponPower` are placeholders on every ability.

Scaling lives under `properties[<name>].scale_function`. The `scale` key is
always empty and reads as a clean, wrong zero.
"""

from __future__ import annotations

import contextlib
import functools
import re
from pathlib import Path
from typing import Any, Iterator

import numpy as np
import pandas as pd

from . import abilities, api, archetype, assets

# Placeholders present on every ability with value "0" (docs/game-mechanics.md).
PLACEHOLDERS = frozenset({"TechPower", "WeaponPower"})

# The regex docs/game-mechanics.md used for "has a weapon property". It also
# matches defensive and enemy-debuff properties (BulletResist, FireRateSlow,
# TargetBulletEvasionChance), so it is kept only to reproduce the old count.
BROAD_WEAPON_RE = re.compile(
    r"bullet|firerate|ammo|magazine|reload|weapondamage|crit|recoil|perbullet|buffbaseweapon",
    re.IGNORECASE,
)

# A property improves the caster's own gun when the game tags it with one of
# these modifier types...
WEAPON_MODIFIER_TYPES = frozenset(
    {
        "MODIFIER_VALUE_FIRE_RATE",
        "MODIFIER_VALUE_WEAPON_DAMAGE_INCREASE",
        "MODIFIER_VALUE_FLAT_BULLET_DAMAGE_POST_SCALE",
        "MODIFIER_VALUE_BONUS_CRIT_DAMAGE_PERCENT",
        "MODIFIER_VALUE_AMMO_CLIP_SIZE",
        "MODIFIER_VALUE_AMMO_CLIP_SIZE_PERCENT",
        "MODIFIER_VALUE_BONUS_BULLET_SPEED_PERCENT",
        "MODIFIER_VALUE_WEAPON_RECOIL_REDUCTION_PERCENT",
        "MODIFIER_VALUE_BULLET_LIFESTEAL",
        "MODIFIER_VALUE_FIREARM_ACCURACY_PERCENTAGE",
        "MODIFIER_VALUE_WEAPON_DAMAGE_TO_NPC_INCREASE",
        "MODIFIER_VALUE_BONUS_ATTACK_RANGE_PERCENT",
    }
)
# ...or its name says the ability is fed by the caster's shots (on-hit procs,
# per-bullet damage, build-up per shot) or changes the caster's weapon directly.
WEAPON_NAME_RE = re.compile(
    r"PerBullet|BulletPercentPerHit|CritBuildup|BulletCrit|BulletHit|OnBullet"
    r"|PerShot|PerHeadshot|HeadshotBonus|RefillDurationCrit|BuffBaseWeapon"
    r"|WeaponDamageBurst|^BonusBullets$|UnlimitedAmmo|BulletsReloaded"
    r"|WeaponDamageBonus|BonusFireRate|FireRateBonus|FireRatePer",
)
# These hit the enemy's gun or a summon's, not the caster's: fire-rate slows
# (two carry MODIFIER_VALUE_FIRE_RATE), Warden's WeaponPowerDebuff and
# Doorman's DebuffAccuracy (weapon modifier types with negative values), and
# Graves' SummonFireRate.
NOT_WEAPON_RE = re.compile(r"Slow|Debuff|Summon", re.IGNORECASE)

# Effect categories for upgrade tiers, first match wins. Written before any
# fit was run (#42).
CATEGORY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("shred", re.compile(
        r"ResistReduction|ArmorReduction|Vulnerab|Vulnerbility|DamageAmp|DamageTakenIncrease"
        r"|AmpPercent|AmpDamage|ResReduced|ResistShred|BulletAmp|MaxAmp|ResistDebuff",
        re.IGNORECASE)),
    ("control", re.compile(
        r"Slow|Stun|Silence|Immobiliz|Sleep|Petrify|Disarm|Entangle|Hex|Toss|Tether"
        r"|Knock|Fear|StaminaDrain|StaminaReduction|DisableHealing|PauseStaminaRegen",
        re.IGNORECASE)),
    ("sustain", re.compile(
        r"Heal|Lifesteal|LifeSteal|LifeDrain|LifeLeech|Regen|Barrier|Shield|Resist$"
        r"|ResistOnActive|DamageReduction|Evasion|Immunity|Unstoppable|MaxHealth|BonusHealth"
        r"|StatusResistance|IncomingDamagePercent|ArmorGain|DamageResist",
        re.IGNORECASE)),
    ("mobility", re.compile(
        r"MoveSpeed|MovementSpeed|Dash|Jump|Sprint|Stamina|AirControl|SpeedOnLand"
        r"|SpeedBoost|SpeedChange|TravelRange|FlightControl|Slide",
        re.IGNORECASE)),
    ("cooldown", re.compile(
        r"Cooldown|Charges|ChargeReplenish|Recast|Refund|Refresh|Reset",
        re.IGNORECASE)),
    ("duration", re.compile(r"Duration|Lifetime|Linger", re.IGNORECASE)),
    ("area", re.compile(
        r"Radius|Range|Width|Height|Length|Distance|Angle|Targets|TargetLimit|Count"
        r"|Bounces|Split|Stacks",
        re.IGNORECASE)),
    ("damage", re.compile(r"Damage|DPS|Dps|Burst|Explode|Proc", re.IGNORECASE)),
)
CATEGORIES = ("weapon",) + tuple(name for name, _ in CATEGORY_PATTERNS) + ("other",)

# Ability points each upgrade costs, by the level it reaches.
TIER_LEVELS = (2, 3, 4)
LEVEL_COST = {2: 1, 3: 2, 4: 5}


@functools.lru_cache(maxsize=1)
def _raw_abilities(cache_dir: Path = assets.DEFAULT_CACHE) -> dict[int, dict[str, Any]]:
    raw: list[dict[str, Any]] = api.get("/v1/assets/items", cache_dir=cache_dir)
    return {e["id"]: e for e in raw if e.get("type") == "ability" and e.get("hero")}


def is_weapon_property(name: str, prop: dict[str, Any] | None) -> bool:
    """Whether a property makes the ability work through the caster's gun."""
    if name in PLACEHOLDERS or NOT_WEAPON_RE.search(name):
        return False
    modifier = (prop or {}).get("provided_property_type")
    return modifier in WEAPON_MODIFIER_TYPES or bool(WEAPON_NAME_RE.search(name))


def _number(value: Any) -> float | None:
    """The leading number of a property value ("0m" is 0), or None if there isn't one."""
    if isinstance(value, (int, float)):
        return float(value)
    match = re.match(r"\s*(-?\d+(?:\.\d+)?)", str(value or ""))
    return float(match.group(1)) if match else None


def is_set(prop: Any) -> bool:
    """Whether a base property is set: a nonzero value, or a value that isn't a number.

    Many properties are listed at "0" and only get a value from an upgrade
    tier (Full Auto's UnlimitedAmmo). Listed isn't set, the same trap
    `semantics.py` records for items.
    """
    if not isinstance(prop, dict):
        return False
    number = _number(prop.get("value"))
    return number is None or number != 0.0


def weapon_tier(entry: dict[str, Any]) -> int | None:
    """When the ability starts working through the gun.

    0 if a weapon property is set at base, 1-3 for the first upgrade tier
    (1, 2 or 5 points) that grants one, None if neither.
    """
    props = entry.get("properties") or {}
    for name, prop in props.items():
        if is_weapon_property(name, prop if isinstance(prop, dict) else None) and is_set(prop):
            return 0
    for index, tier in enumerate(entry.get("upgrades") or [], start=1):
        for bonus in tier.get("property_upgrades") or []:
            prop = props.get(bonus["name"])
            if is_weapon_property(bonus["name"], prop if isinstance(prop, dict) else None):
                if (_number(bonus.get("bonus")) or 0.0) != 0.0:
                    return index
    return None


def is_spirit_scaling(entry: dict[str, Any]) -> bool:
    """Whether any property scales with spirit power.

    True when a property's `scale_function` names `ETechPower`, or is the
    `scale_function_tech_damage` class, which is spirit damage scaling and
    often carries no stat type (Full Auto's `MagicDamagePerBullet`).
    """
    for prop in (entry.get("properties") or {}).values():
        if not isinstance(prop, dict):
            continue
        function = prop.get("scale_function") or {}
        if function.get("specific_stat_scale_type") == "ETechPower":
            return True
        if function.get("class_name") == "scale_function_tech_damage":
            return True
    return False


def effect_categories(name: str, prop: dict[str, Any] | None = None) -> str:
    """The effect category of one upgrade property name."""
    if is_weapon_property(name, prop):
        return "weapon"
    for category, pattern in CATEGORY_PATTERNS:
        if pattern.search(name):
            return category
    return "other"


def _names(entry: dict[str, Any], *, upgrades: bool = True) -> set[str]:
    names = set((entry.get("properties") or {}).keys())
    if upgrades:
        for tier in entry.get("upgrades") or []:
            names |= {p["name"] for p in tier.get("property_upgrades") or []}
    return names - PLACEHOLDERS


@functools.lru_cache(maxsize=1)
def ability_table(cache_dir: Path = assets.DEFAULT_CACHE) -> pd.DataFrame:
    """One row per hero ability record, with the two signals' flags.

    Columns: ability_id, hero_id, name, signature_slot (0 if not a signature
    of a playable hero), has_upgrades, n_tiers, weapon_broad (the old regex),
    weapon_listed (the strict rule on property names, set or not),
    weapon_attached (the strict rule, set at base or by an upgrade),
    weapon_tier (0 at base, 1-3 the upgrade that grants it, -1 never),
    spirit_scaling, and for each tier level L in 2-4 `cats_lL`, the set of
    effect categories that tier unlocks.
    """
    raw = _raw_abilities(cache_dir)
    playable = assets.playable_heroes(cache_dir)
    slot_of = {
        a.id: slot
        for hero_id, slots in assets.hero_signatures(cache_dir).items()
        if hero_id in playable
        for slot, a in slots.items()
    }
    rows = []
    for ability_id, entry in raw.items():
        props = entry.get("properties") or {}
        upgrades = entry.get("upgrades") or []
        tier = weapon_tier(entry)
        listed = any(
            is_weapon_property(n, p if isinstance(p, dict) else None)
            for n, p in props.items()
        )
        row = {
            "ability_id": int(ability_id),
            "hero_id": int(entry["hero"]),
            "name": entry.get("name", ""),
            "signature_slot": int(slot_of.get(ability_id, 0)),
            "has_upgrades": bool(upgrades),
            "n_tiers": len(upgrades),
            "weapon_broad": any(BROAD_WEAPON_RE.search(n) for n in _names(entry)),
            "weapon_listed": listed,
            "weapon_attached": tier is not None,
            "weapon_tier": -1 if tier is None else int(tier),
            "spirit_scaling": is_spirit_scaling(entry),
        }
        for index, level in enumerate(TIER_LEVELS):
            tier = upgrades[index] if index < len(upgrades) else {}
            row[f"cats_l{level}"] = frozenset(
                effect_categories(
                    u["name"],
                    props.get(u["name"]) if isinstance(props.get(u["name"]), dict) else None,
                )
                for u in tier.get("property_upgrades") or []
            )
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["hero_id", "signature_slot", "ability_id"])


def signature_table(cache_dir: Path = assets.DEFAULT_CACHE) -> pd.DataFrame:
    """`ability_table` restricted to the four signature abilities of playable heroes."""
    table = ability_table(cache_dir)
    return table[table["signature_slot"] > 0].reset_index(drop=True)


def gun_routed_slots(
    table: pd.DataFrame | None = None, *, broad: bool = False
) -> dict[int, set[int]]:
    """Hero id to the signature slots that scale with spirit and work through the gun."""
    table = signature_table() if table is None else table
    flag = table["weapon_broad"] if broad else table["weapon_attached"]
    hit = table[flag & table["spirit_scaling"]]
    out: dict[int, set[int]] = {}
    for row in hit.itertuples():
        out.setdefault(int(row.hero_id), set()).add(int(row.signature_slot))
    return out


def _exposure(ability_rows: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """(1 - pt_s_lL) for every (slot, level), and each player's hero.

    1 - pt is how much of the player's point sequence the tier was held for.
    A tier never reached is 0.
    """
    order = abilities.point_order_features(ability_rows, levels=TIER_LEVELS)
    keys = ["match_id", "player_slot"]
    heroes = (
        ability_rows[keys + ["hero_id"]]
        .drop_duplicates(subset=keys)
        .set_index(keys)["hero_id"]
        .reindex(order.index)
    )
    return 1.0 - order, heroes


def effect_features(
    ability_rows: pd.DataFrame,
    *,
    levels: tuple[int, ...] = TIER_LEVELS,
    table: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Each player's exposure to each effect category, in [0, 1].

    For category c on the player's hero, the mean over the hero's upgrade
    tiers (restricted to `levels`) that unlock c of how much of the player's
    point sequence that tier was held for. A player who reaches every
    weapon tier on their first points scores near 1 on `eff_weapon`.

    A per-hero linear map of `point_order_features` (see the module
    docstring). Columns with no tier on a hero are 0 for its players.
    """
    table = signature_table() if table is None else table
    exposure, heroes = _exposure(ability_rows)
    out = pd.DataFrame(0.0, index=exposure.index, columns=[f"eff_{c}" for c in CATEGORIES])
    for hero_id, hero_table in table.groupby("hero_id"):
        members = heroes.index[heroes.to_numpy() == hero_id]
        if not len(members):
            continue
        weights = np.zeros((len(CATEGORIES), 4 * len(TIER_LEVELS)))
        columns = []
        for slot in range(1, 5):
            for level in TIER_LEVELS:
                columns.append(f"pt_{slot}_l{level}")
        for row in hero_table.itertuples():
            for level in levels:
                for category in getattr(row, f"cats_l{level}"):
                    j = columns.index(f"pt_{int(row.signature_slot)}_l{level}")
                    weights[CATEGORIES.index(category), j] = 1.0
        totals = weights.sum(axis=1, keepdims=True)
        weights = np.divide(weights, totals, out=np.zeros_like(weights), where=totals > 0)
        values = exposure.loc[members, columns].to_numpy() @ weights.T
        out.loc[members, :] = values
    return out


def gun_exposure(
    ability_rows: pd.DataFrame, routed: dict[int, set[int]] | None = None
) -> pd.Series:
    """Each player's share of ability-point exposure held in gun-routed abilities.

    Exposure is cost-weighted (1, 2, 5 points for levels 2, 3, 4) and counts
    how much of the point sequence each tier was held for. 0 for every player
    on a hero with no gun-routed ability.
    """
    routed = gun_routed_slots() if routed is None else routed
    exposure, heroes = _exposure(ability_rows)
    total = pd.Series(0.0, index=exposure.index)
    routed_part = pd.Series(0.0, index=exposure.index)
    hero_values = heroes.to_numpy()
    for slot in range(1, 5):
        on_hero = np.array(
            [slot in routed.get(int(h), ()) if pd.notna(h) else False for h in hero_values]
        )
        for level in TIER_LEVELS:
            column = exposure[f"pt_{slot}_l{level}"] * LEVEL_COST[level]
            total += column
            routed_part += column.where(on_hero, 0.0)
    share = routed_part.div(total.replace(0.0, np.nan)).fillna(0.0)
    return share.rename("gun_exposure")


def gun_block(families: pd.DataFrame, exposure: pd.Series) -> pd.DataFrame:
    """One column: the player's spirit share times their gun-routed exposure."""
    w = exposure.reindex(families.index).fillna(0.0)
    return (families["spirit"] * w).rename("spirit_via_gun").to_frame()


def reroute(families: pd.DataFrame, exposure: pd.Series) -> pd.DataFrame:
    """Family shares with gun-routed spirit counted as gun.

    gun + spirit * w and spirit * (1 - w), everything else unchanged, so rows
    still sum to 1. With w = 0 the shares are unchanged.
    """
    w = exposure.reindex(families.index).fillna(0.0)
    out = families.copy()
    moved = out["spirit"] * w
    out["gun"] = out["gun"] + moved
    out["spirit"] = out["spirit"] - moved
    return out


@contextlib.contextmanager
def rerouted_families(exposure: pd.Series) -> Iterator[None]:
    """Make `archetype.family_shares` return rerouted shares inside the block.

    `archetype.fit_hero` builds its features through `family_shares`, so this
    is how a fit clusters on the rerouted shares without changing the module.
    """
    original = archetype.family_shares

    def patched(purchases: pd.DataFrame, items=None) -> pd.DataFrame:
        return reroute(original(purchases, items), exposure)

    archetype.family_shares = patched
    try:
        yield
    finally:
        archetype.family_shares = original
