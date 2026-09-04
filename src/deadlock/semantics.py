"""What an item does, as opposed to which shop tab it sits in.

`Item.slot_type` is a shop category. Measured against the items' own stat
blocks, **84 of 170 shopable items sit in a tab that does not match what they
do** -- so naming a build from its slot shares is close to a coin flip. Siphon
Bullets is vitality-slotted and grants +15% weapon damage; Melee Charge is
weapon-slotted and belongs to melee builds; Rescue Beam is vitality-slotted and
belongs to support builds.

This module assigns each item to one or more **build families** -- the
vocabulary players actually use -- by reading its stats AND its tooltip.

The tooltip is not decoration. Stats say which numbers an item moves; the
tooltip says what it is FOR, and they disagree often enough that a stats-only
reading mislabels real builds:

- Siphon Bullets' typed block is "+15% weapon damage, +10 bullet resist". Its
  tooltip says "your bullets steal Max HP from enemies" -- the actual reason
  anyone buys it, present in no stat key.
- Mystic and Radiant Regeneration type as spirit healing, so a stats-only pass
  called them support. The tooltip says dealing spirit damage grants YOU
  regeneration: self-sustain, which is why a gun carry stacks them.
- Healing Tempo types as healing but grants the target bonus FIRE RATE, which
  is why it appears in gun builds. Read as a heal, it made Venator's hybrid
  gun/spirit build look like a support build.

Four more things make this harder than it looks (see docs/ITEM-SEMANTICS.md):

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

3. **Self-healing is not support.** Almost every heal-shaped STAT is self-regen
   whatever triggers it, so the stat table maps them to `sustain` and lets the
   tooltip establish the exception. Healing an ALLY is support; healing
   yourself is a bruiser pattern. Without the split, Siphon Bullets' HP-steal
   lands beside Rescue Beam and Kelvin's support build stops being visible.

4. **Key presence is not evidence.** Every item lists WeaponPower, TechPower
   and ChannelMoveSpeed as `value: "0"` placeholders. Counting keys makes all
   173 items look like gun AND spirit items, collapsing every IDF to zero.

A family label is only as good as the vocabulary allows: two builds of the same
family on one hero (Venator has two gun builds, Celeste two spirit) cannot be
told apart this way. Distinguishing those needs ability focus -- "ult" versus
"stomp" -- which is not implemented here.
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

# Below this the winning family leads, but a second carries enough weight to be
# part of the build's identity. A player calls that a hybrid -- Venator's two
# clusters are both gun builds, and what separates them is that one runs spirit
# and healing alongside the gun; without this they collapse to one label.
#
# Set low on purpose. The margins have a natural break at 2.0, but marking
# everything below it labels nine of 38 clusters "Hybrid-", which drains the
# word of meaning. At 1.7 it flags only genuinely close calls.
HYBRID_MARGIN = 1.7

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
    #
    # Deliberately thin. Most heal-shaped stats are self-regen whatever
    # triggers them -- Mystic Regeneration's TotalHealthRegen fires on dealing
    # spirit damage and heals only the buyer, which is a bruiser pattern, not
    # a support one. Whether healing reaches an ALLY lives in the tooltip, so
    # `_tooltip_families` supplies most of this family's evidence.
    "HealAmpCastPercent": ("support", 1),
    "HealAmpRegenPercent": ("sustain", 1),
    "HealPercentAmount": ("support", 2),
    "TotalHealthRegen": ("sustain", 2),
    "HealingPerCast": ("sustain", 2),
    "Regeneration": ("sustain", 2),
    "HealFromHero": ("sustain", 2),
    "HealFromNPC": ("sustain", 1),
    "HealPerStack": ("sustain", 1),
    "MinStaminaRestore": ("support", 1),
    "MinHeal": ("sustain", 1),
    "AllyPercentage": ("support", 2),
    "HealOnActivate": ("sustain", 1),
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

# --- Tooltip evidence -----------------------------------------------------
#
# Stats do not say what an item is FOR. Siphon Bullets' typed block reads
# "+15% weapon damage, +10 bullet resist", but its tooltip says "your bullets
# steal Max HP from enemies" -- which is the reason anyone buys it. Mystic
# Regeneration types as spirit and heals; only the tooltip reveals that it
# heals YOU for dealing spirit damage, so a build stacking it is sustaining
# itself rather than supporting a team.
#
# Each pattern is a claim about what a phrase means, checked against the items
# it matches.

# Healing or shielding SOMEONE ELSE. "The target" alone is not enough --
# Shrink Ray and Knockdown target enemies.
ALLY_TOOLTIP_RE = re.compile(
    r"(nearby\s+all(?:y|ies)|allied\s+hero|(?:your\s+)?allies\b|"
    r"friendly\s+(?:target|unit)|to\s+an\s+ally|or\s+an\s+ally|"
    r"someone\s+else|non-self)",
    re.IGNORECASE,
)

# Healing YOURSELF, however it is triggered. The line that separates a support
# build from a bruiser one.
SELF_HEAL_TOOLTIP_RE = re.compile(
    r"(grants?\s+you\s+bonus\s+regen|heal\s+yourself|"
    r"steal\s+max\s+hp|lifesteal|siphon)",
    re.IGNORECASE,
)

# The item's damage rides on your gun. These read as spirit items by stats but
# are bought to make bullets hit harder -- the hybrid gun/spirit pattern.
BULLET_TOOLTIP_RE = re.compile(
    r"(your\s+bullets|bullet\s+damage|weapon\s+damage|fire\s+rate|"
    r"bullets?\s+(?:apply|deal|steal|build))",
    re.IGNORECASE,
)

MELEE_TOOLTIP_RE = re.compile(r"(heavy\s+melee|light\s+melee|melee\s+attack)", re.IGNORECASE)

_SVG_RE = re.compile(r"<svg.*?</svg>", re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def tooltip_text(entry: dict[str, Any]) -> str:
    """The item's human-readable description, stripped of markup.

    Tooltips are nested JSON carrying inline SVG icons and HTML spans; 155 of
    173 shopable items have one. This is the only place the asset data says
    what an item is FOR rather than which numbers it moves.
    """
    sections = entry.get("tooltip_sections")
    if not sections:
        return ""

    parts: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("loc_string", "name", "title") and isinstance(value, str):
                    parts.append(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(sections)
    text = _TAG_RE.sub("", _SVG_RE.sub(" ", " ".join(parts)))
    return re.sub(r"\s+", " ", text).strip()

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

        for family, weight in _tooltip_families(entry).items():
            scores[family] = scores.get(family, 0) + weight

        override = TOOLTIP_OVERRIDES.get(entry.get("class_name", ""))
        for family, weight in (override or {}).items():
            scores[family] = scores.get(family, 0) + weight

        if scores:
            out[item_id] = scores
    return out


def _tooltip_families(entry: dict[str, Any]) -> dict[str, int]:
    """What the item's description says it is for.

    Stats and text disagree often enough that this is not a tie-breaker, it is
    primary evidence:

    - Mystic and Radiant Regeneration type as spirit healing, so a stats-only
      reading called them support. The text says "dealing spirit damage grants
      YOU bonus regeneration" -- self-sustain, and the reason a gun carry buys
      them alongside Healing Booster.
    - Healing Tempo types as healing, but grants the target BONUS FIRE RATE,
      which is why it appears in gun builds.
    - Siphon Bullets' whole point ("your bullets steal Max HP") appears in no
      stat key at all.

    Ally-healing is scored at 3, above any stat, because it is the single
    clearest signal that a build is supporting a team rather than itself.
    """
    text = tooltip_text(entry)
    if not text:
        return {}

    scores: dict[str, int] = {}
    heals_ally = bool(ALLY_TOOLTIP_RE.search(text))
    heals_self = bool(SELF_HEAL_TOOLTIP_RE.search(text))

    if heals_ally:
        scores["support"] = 3
    if heals_self and not heals_ally:
        scores["sustain"] = scores.get("sustain", 0) + 2
    if BULLET_TOOLTIP_RE.search(text):
        scores["gun"] = scores.get("gun", 0) + 2
    if MELEE_TOOLTIP_RE.search(text):
        scores["melee"] = scores.get("melee", 0) + 3
    return scores


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

    label = DISPLAY[best[1]]
    if margin < HYBRID_MARGIN:
        # A second family with real weight behind the winner. Venator's two
        # clusters are both gun builds; what separates them is that one leans
        # on spirit and healing alongside the gun, which a player calls a
        # "hybrid gun" build. Naming it that way distinguishes a pair the bare
        # family label collapses.
        label = f"Hybrid-{label}"
    return f"{label} {hero_name}", scores, margin


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
