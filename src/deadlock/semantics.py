"""What an item does, as opposed to which shop tab it sits in.

`Item.slot_type` is a shop category. Measured against the items' own stat
blocks, **84 of 170 shopable items sit in a tab that does not match what they
do** -- so naming a build from its slot shares is close to a coin flip. Siphon
Bullets is vitality-slotted and grants +15% weapon damage; Melee Charge is
weapon-slotted and belongs to melee builds; Rescue Beam is vitality-slotted and
belongs to support builds.

This module assigns each item to one or more **build families** -- the
vocabulary players actually use -- by reading its stats.

Three things make that harder than it looks, each learned the hard way (see
docs/ITEM-SEMANTICS.md):

1. **Stats live in two places.** `upgrades[].property_upgrades[]` holds only
   what the tier-upgrade adds; `properties{}` holds the full block. Siphon
   Bullets' weapon damage is in `properties` ONLY, so reading the first field
   alone gives the flagged item no weapon signal at all. Both are unioned here.

2. **`AbilityCooldown` is not cooldown reduction.** It appears on 90 items --
   48 of the 50 actives -- and refers to the item's OWN cooldown. Counting it
   as spirit makes every active look like a spirit item, which is what dragged
   Rescue Beam into "spirit" in a first pass. The real global stat is
   `CooldownReduction`, on seven items. Same trap for AbilityDuration,
   AbilityCastRange, AbilityCastDelay, AbilityChannelTime.

3. **Self-healing is not support.** Without splitting `sustain` from `support`,
   Siphon Bullets' HP-steal lands in the same bucket as Healing Tempo and
   Kelvin's support build stops being distinguishable. Healing an ALLY is
   support; healing yourself is sustain.

Barrier-on-ally items (Guardian Ward, Divine Barrier) carry no typed stat that
separates them from Plated Armor. The only evidence is the tooltip clause about
casting on someone else, so the regex is not optional.
"""

from __future__ import annotations

import functools
import json
import math
import re
from pathlib import Path
from typing import Any

from . import api, assets

# Families, in the vocabulary players use. Order is the display order.
FAMILIES = (
    "gun",
    "spirit",
    "melee",
    "support",
    "tank",
    "sustain",
    "control",
    "mobility",
)

# How a family is spoken about when naming a build.
DISPLAY = {
    "gun": "Gun",
    "spirit": "Spirit",
    "melee": "Melee",
    "support": "Support",
    "tank": "Tank",
    "sustain": "Bruiser",
    "control": "Control",
    "mobility": "Mobility",
}

# Families that name a build. `sustain`, `control` and `mobility` are real
# properties of items but nobody calls a build by them -- they are scored so
# they can absorb evidence away from the naming families, not to win.
NAMING_FAMILIES = ("gun", "spirit", "melee", "support", "tank")

# How far ahead the winning family must be before the label is asserted.
# Chosen from the observed margin distribution: 38 of 41 clusters clear 1.3x
# comfortably, and the three that do not are the three that read wrong to a
# player. Below this the cluster keeps the bare hero name.
MIN_NAMING_MARGIN = 1.3

# Stat -> (family, weight). Weight 2 defines a family, 1 supports it.
FAMILY_WEIGHTS: dict[str, tuple[str, int]] = {
    # --- gun
    "BonusFireRate": ("gun", 2),
    "ActiveBonusFireRate": ("gun", 2),
    "BaseAttackDamagePercent": ("gun", 2),
    "BonusClipSizePercent": ("gun", 2),
    "BulletArmorReduction": ("gun", 2),
    "BulletResistReduction": ("gun", 2),
    "BonusBulletSpeedPercent": ("gun", 1),
    "BulletLifestealPercent": ("gun", 1),
    "WeaponPowerPerStack": ("gun", 2),
    "RicochetDamagePercent": ("gun", 2),
    "LongRangeBonusWeaponPower": ("gun", 2),
    "CloseRangeBonusWeaponPower": ("gun", 2),
    "HeadShotBonusDamage": ("gun", 2),
    "CritDamagePercent": ("gun", 2),
    "BonusAttackRangePercent": ("gun", 1),
    "NonPlayerBonusWeaponPower": ("gun", 1),
    "BulletSplitShot": ("gun", 2),
    "HealPercentPerHeadshot": ("gun", 1),
    "BonusWeaponPower": ("gun", 2),
    "WeaponPower": ("gun", 2),
    # --- spirit
    "TechPower": ("spirit", 2),
    "SpiritPower": ("spirit", 2),
    "BonusSpirit": ("spirit", 2),
    "BonusSpiritForChargedAbilities": ("spirit", 2),
    "CooldownReduction": ("spirit", 2),
    "BonusAbilityDurationPercent": ("spirit", 2),
    "BonusAbilityCharges": ("spirit", 2),
    "TechArmorDamageReduction": ("spirit", 2),
    "TechPowerReduction": ("spirit", 2),
    "AbilityLifestealPercentHero": ("spirit", 1),
    # Ride along on many actives regardless of direction -- weak evidence.
    "TechRangeMultiplier": ("spirit", 1),
    "TechRadiusMultiplier": ("spirit", 1),
    # --- melee
    "MeleeDistanceScale": ("melee", 2),
    "BonusMeleeDamagePercent": ("melee", 2),
    "BonusHeavyMeleeDamage": ("melee", 2),
    "HeavyMeleeMultiplier": ("melee", 2),
    "AmbushBonusMeleeDamage": ("melee", 2),
    "ParryCooldownReduction": ("melee", 2),
    "ParrySuccessHealPercentage": ("melee", 1),
    "LifestrikeHeal": ("melee", 1),
    "LightMeleeAmmo": ("melee", 1),
    # --- support (healing or shielding SOMEONE ELSE)
    "HealAmpCastPercent": ("support", 2),
    "HealAmpRegenPercent": ("support", 2),
    "HealPercentAmount": ("support", 2),
    "TotalHealthRegen": ("support", 2),
    "HealingPerCast": ("support", 2),
    "Regeneration": ("support", 2),
    "HealFromHero": ("support", 2),
    "HealFromNPC": ("support", 1),
    "HealPerStack": ("support", 1),
    "MinStaminaRestore": ("support", 1),
    "MinHeal": ("support", 1),
    "AllyPercentage": ("support", 2),
    "HealOnActivate": ("support", 1),
    "GuardianWardCombatBarrier": ("support", 2),
    # --- tank
    "BonusHealth": ("tank", 2),
    "BulletResist": ("tank", 2),
    "TechResist": ("tank", 2),
    "MeleeResistPercent": ("tank", 1),
    "StatusResistancePercent": ("tank", 2),
    "CombatBarrier": ("tank", 2),
    "BonusBarrierHealth": ("tank", 2),
    "DamageAbsorb": ("tank", 2),
    "SlowResistancePercent": ("tank", 1),
    "DeathImmunityDuration": ("tank", 1),
    # --- sustain (healing YOURSELF -- deliberately not support)
    "OutOfCombatHealthRegen": ("sustain", 2),
    "BonusHealthRegen": ("sustain", 2),
    "HealthStealPctHero": ("sustain", 2),
    "HealOnKill": ("sustain", 2),
    "HealOnVeil": ("sustain", 2),
    "HealOnSuccess": ("sustain", 2),
    "HealLifePercentOutOfCombat": ("sustain", 2),
    "HealthRegen": ("sustain", 1),
    # --- control
    "SlowPercent": ("control", 2),
    "FireRateSlow": ("control", 2),
    "StunDuration": ("control", 2),
    "SilenceDuration": ("control", 2),
    "OutgoingDamagePenaltyPercent": ("control", 2),
    "MovementSlowPercent": ("control", 2),
    # Anti-heal debuffs. Emphatically not support.
    "HealAmpReceivePenaltyPercent": ("control", 2),
    "HealAmpRegenPenaltyPercent": ("control", 2),
    # --- mobility
    "BonusMoveSpeed": ("mobility", 2),
    "BonusSprintSpeed": ("mobility", 2),
    "Stamina": ("mobility", 2),
    "StaminaCooldownReduction": ("mobility", 2),
    "GroundDashReductionPercent": ("mobility", 2),
}

# Stats describing the item's OWN behaviour, never the character's. Counting
# these as spirit makes every active item look like a spirit item.
SELF_REFERENTIAL = frozenset(
    {
        "AbilityCooldown",
        "AbilityDuration",
        "AbilityCastRange",
        "AbilityCastDelay",
        "AbilityChannelTime",
        "AbilityResourceCost",
        "AbilityCharges",
        "StealDuration",
        "ProcChance",
        "Duration",
        "Radius",
        "Range",
        "Cooldown",
    }
)

# The only evidence that a barrier item targets an ally rather than oneself.
ALLY_TOOLTIP_RE = re.compile(
    r"(on\s+(?:an?\s+)?all(?:y|ied)|someone\s+else|nearby\s+all(?:y|ies)|"
    r"target\s+all(?:y|ied)|non-self|allied\s+hero)",
    re.IGNORECASE,
)

# Items whose family the typed stats cannot express, with the source of the
# claim. Kept short and explicit rather than widening the stat table, so an
# override is visible as a judgement call.
TOOLTIP_OVERRIDES: dict[str, dict[str, int]] = {
    # "When you perform a Light or Heavy Melee attack against a hero, deal
    # extra spirit damage" -- typed as spirit, played as melee.
    "upgrade_acolytes_glove": {"melee": 3},
    # CloseRangeBonusWeaponPower types as gun; community guides list it in
    # melee builds, and Abrams' melee cluster buys it at 93%.
    "upgrade_close_range": {"melee": 2},
    # Barrier cast on an ally; indistinguishable from Plated Armor by stats.
    "upgrade_guardian_ward": {"support": 4},
    "upgrade_divine_barrier": {"support": 4},
}


@functools.lru_cache(maxsize=1)
def _raw_items(cache_dir: Path = assets.DEFAULT_CACHE) -> dict[int, dict[str, Any]]:
    """Raw asset entries, since `Item` keeps only six fields."""
    raw: list[dict[str, Any]] = api.get("/v1/assets/items", cache_dir=cache_dir)
    return {e["id"]: e for e in raw if e.get("type") == "upgrade"}


def _stat_names(entry: dict[str, Any]) -> set[str]:
    """Every stat an item actually carries, from both fields that hold them.

    A key's presence is not evidence. Every item's `properties` block lists
    WeaponPower, TechPower and ChannelMoveSpeed as schema placeholders with
    `value: "0"` -- read naively, all 173 shopable items look like gun items
    AND spirit items, every family's IDF collapses to zero, and the rule can
    never name anything. Only non-zero values count.
    """
    names: set[str] = set()
    for upgrade in entry.get("upgrades") or []:
        for prop in upgrade.get("property_upgrades") or []:
            if prop.get("name") and _nonzero(prop.get("bonus")):
                names.add(prop["name"])

    properties = entry.get("properties") or {}
    if isinstance(properties, dict):
        for name, spec in properties.items():
            value = spec.get("value") if isinstance(spec, dict) else spec
            if _nonzero(value):
                names.add(name)
    return names - SELF_REFERENTIAL


def _nonzero(value: Any) -> bool:
    """Is this stat actually set, rather than a zero placeholder?"""
    if value is None:
        return False
    try:
        return float(value) != 0.0
    except (TypeError, ValueError):
        return bool(value)


@functools.lru_cache(maxsize=1)
def item_families(cache_dir: Path = assets.DEFAULT_CACHE) -> dict[int, dict[str, int]]:
    """Map each shopable item to the families it feeds, and how strongly.

    An item counts in EVERY family it feeds. Crushing Fists is melee, gun and
    tank at once; forcing one label per item would throw away the fact that gun
    and melee builds share Close Quarters.
    """
    entries = _raw_items(cache_dir)
    shopable = assets.shopable_items(cache_dir)

    out: dict[int, dict[str, int]] = {}
    for item_id in shopable:
        entry = entries.get(item_id, {})
        scores: dict[str, int] = {}
        for stat in _stat_names(entry):
            weighting = FAMILY_WEIGHTS.get(stat)
            if weighting is None:
                continue
            family, weight = weighting
            scores[family] = scores.get(family, 0) + weight

        override = TOOLTIP_OVERRIDES.get(entry.get("class_name", ""))
        if override:
            for family, weight in override.items():
                scores[family] = scores.get(family, 0) + weight
        elif _mentions_ally(entry):
            scores["support"] = scores.get("support", 0) + 2

        if scores:
            out[item_id] = scores
    return out


def _mentions_ally(entry: dict[str, Any]) -> bool:
    """Does the tooltip say this is cast on someone else?"""
    sections = entry.get("tooltip_sections")
    if not sections:
        return False
    return bool(ALLY_TOOLTIP_RE.search(json.dumps(sections)))


@functools.lru_cache(maxsize=1)
def family_idf(cache_dir: Path = assets.DEFAULT_CACHE) -> dict[str, float]:
    """Inverse document frequency per family: how rare its evidence is.

    The load-bearing part of the naming rule. Without it, tank (99 items) and
    gun (71) drown melee (9) and support (12), and the rule mislabels Abrams,
    Sinclair and Kelvin. A tank stat is cheap evidence; a melee stat is
    expensive evidence.
    """
    families = item_families(cache_dir)
    total = len(assets.shopable_items(cache_dir))
    counts: dict[str, int] = {}
    for scores in families.values():
        for family in scores:
            counts[family] = counts.get(family, 0) + 1
    return {
        family: math.log(total / count) if count else 0.0
        for family, count in counts.items()
    }


def score_families(
    lifts: dict[int, float], cache_dir: Path = assets.DEFAULT_CACHE
) -> dict[str, float]:
    """Score each family for a cluster, from its items' lift over the others.

    `lifts` maps item id to (prevalence here - prevalence elsewhere). Lift, not
    prevalence: raw prevalence would name every cluster after the hero's
    staples, where lift names it after what makes this cluster different, which
    is what a label is for. Negative lift contributes nothing.
    """
    families = item_families(cache_dir)
    idf = family_idf(cache_dir)

    scores: dict[str, float] = {f: 0.0 for f in FAMILIES}
    for item_id, lift in lifts.items():
        if lift <= 0:
            continue
        for family, weight in families.get(item_id, {}).items():
            scores[family] = scores.get(family, 0.0) + lift * weight * idf.get(family, 0.0)
    return scores


def name_cluster(
    lifts: dict[int, float],
    hero_name: str,
    *,
    min_margin: float = MIN_NAMING_MARGIN,
    cache_dir: Path = assets.DEFAULT_CACHE,
) -> tuple[str, dict[str, float], float]:
    """Name a cluster for its dominant build family.

    Returns the label, the full score vector, and the winner's margin over the
    runner-up -- so a review sheet can show what the naming rested on.

    A win by less than `min_margin` is not asserted. IDF makes rare evidence
    expensive, which is what recovers melee and support at all, but it can also
    let two healing items outweigh four gun items: Ivy's middle cluster leads
    on Quicksilver Reload, Tesla Bullets and Titanic Magazine by lift, yet
    scored "Support" at a 1.2x margin. Where the rule is nearly undecided it
    says so, rather than asserting a coin flip a player would read as wrong.
    """
    scores = score_families(lifts, cache_dir)
    ranked = sorted(
        ((scores.get(f, 0.0), f) for f in NAMING_FAMILIES), reverse=True
    )
    best, runner_up = ranked[0], ranked[1]
    if best[0] <= 0:
        return hero_name, scores, 0.0

    margin = best[0] / runner_up[0] if runner_up[0] > 0 else float("inf")
    if margin < min_margin:
        return hero_name, scores, margin
    return f"{DISPLAY[best[1]]} {hero_name}", scores, margin


@functools.lru_cache(maxsize=1)
def _raw_abilities(cache_dir: Path = assets.DEFAULT_CACHE) -> dict[int, dict[str, Any]]:
    raw: list[dict[str, Any]] = api.get("/v1/assets/items", cache_dir=cache_dir)
    return {e["id"]: e for e in raw if e.get("type") == "ability"}


def hero_ability_families(
    hero_id: int, cache_dir: Path = assets.DEFAULT_CACHE
) -> dict[str, int]:
    """Which families a hero's own abilities point toward.

    A hero's kit says what builds are plausible on them, independent of any
    cluster: Calico's Leaping Slash deals melee damage and heals off spirit,
    and Kelvin's Frost Grenade heals allies while slowing enemies. That is why
    melee Calico and support Kelvin are real builds.

    This is weaker evidence than items -- it describes the hero, not which of
    their clusters is which -- so it is a tie-breaker, never the primary
    signal.
    """
    abilities = _raw_abilities(cache_dir)
    slots = assets.signature_slots(cache_dir)
    scores: dict[str, int] = {}
    for ability_id, entry in abilities.items():
        if entry.get("hero") != hero_id or ability_id not in slots:
            continue
        for stat in _stat_names(entry):
            weighting = FAMILY_WEIGHTS.get(stat)
            if weighting is None:
                continue
            family, weight = weighting
            scores[family] = scores.get(family, 0) + weight
    return scores
