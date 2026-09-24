"""Build families: what each item does, used to name archetypes.

The shop tab (`Item.slot_type`) often doesn't match what an item does. 84 of
170 shop items sit in a tab that doesn't match their stats. Siphon Bullets is
in the vitality tab and gives +15% weapon damage. Melee Charge is in the
weapon tab and goes in melee builds.

So this module assigns each item to one or more build families, the words
players use (gun, spirit, melee, support, tank), from its stats and its
tooltip text. The tooltip matters because stats alone mislabel items:

- Siphon Bullets' stats are "+15% weapon damage, +10 bullet resist". Its
  tooltip says "your bullets steal Max HP from enemies", which is why people
  buy it, and no stat says that.
- Mystic and Radiant Regeneration look like spirit healing, which reads as
  support. The tooltip says dealing spirit damage heals you, which is why gun
  builds buy them.
- Healing Tempo looks like healing but gives the target bonus fire rate, so
  it shows up in gun builds.

Four traps in the stat data (more in docs/ITEM-SEMANTICS.md):

1. Stats are in two fields. `upgrades[].property_upgrades[]` holds only what
   an upgrade adds, and `properties{}` holds the rest. Siphon Bullets' weapon
   damage is only in `properties`. We read both.
2. `AbilityCooldown` is the item's own cooldown, not cooldown reduction. It
   appears on 90 items, including 48 of the 50 actives. Counting it as spirit
   makes every active look like a spirit item. Real cooldown reduction is
   `CooldownReduction`, on seven items. AbilityDuration, AbilityCastRange,
   AbilityCastDelay, and AbilityChannelTime have the same problem.
3. Healing yourself is not support. Most healing stats heal the buyer, so they
   map to `sustain`, and only tooltip text about allies adds `support`.
   Otherwise Siphon Bullets would count as support alongside Rescue Beam.
4. A stat being listed doesn't mean it's set. Every item lists WeaponPower,
   TechPower, and ChannelMoveSpeed with value "0". Only nonzero values count.

Families can't tell apart two builds of the same family on one hero, like
Venator's two gun builds. That would need to know which ability a build
focuses on, which isn't implemented here.
"""

from __future__ import annotations

import functools
import json
import math
import re
from pathlib import Path
from typing import Any

from . import api, assets

# Build families, in display order.
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

# The word used for each family in an archetype name.
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

# Families that can name an archetype. `sustain`, `control`, and `mobility`
# are still scored, so items in them don't count toward a naming family, but
# nobody names a build after them.
NAMING_FAMILIES = ("gun", "spirit", "melee", "support", "tank")

# The top family's score must be at least this multiple of the second's for
# the archetype to get a family name. Otherwise it keeps the bare hero name.
# When set, 38 of 41 clusters cleared 1.3x easily, and the three that didn't
# were the three a player said were named wrong.
MIN_NAMING_MARGIN = 1.3

# Below this margin the name gets a "Hybrid-" prefix. Venator's two clusters
# are both gun builds, and one also runs spirit and healing. Without the
# prefix they get the same name.
#
# The margins have a natural break at 2.0, but using it marks 9 of 38 clusters
# as hybrids, which is too many to mean anything. 1.7 marks only close calls.
HYBRID_MARGIN = 1.7

# Stat name to (family, weight). Weight 2 is strong evidence, 1 is weak.
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
    # These appear on many actives of every kind, so they are weak evidence.
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
    # --- support (healing or shielding someone else)
    #
    # Few stats here. Most healing stats heal only the buyer, like Mystic
    # Regeneration's TotalHealthRegen, so they map to sustain. Whether an item
    # heals allies is in the tooltip, so `_tooltip_families` provides most of
    # the support evidence.
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
    # --- sustain (healing yourself, which is not support)
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
    # Anti-heal debuffs on enemies. Not support.
    "HealAmpReceivePenaltyPercent": ("control", 2),
    "HealAmpRegenPenaltyPercent": ("control", 2),
    # --- mobility
    "BonusMoveSpeed": ("mobility", 2),
    "BonusSprintSpeed": ("mobility", 2),
    "Stamina": ("mobility", 2),
    "StaminaCooldownReduction": ("mobility", 2),
    "GroundDashReductionPercent": ("mobility", 2),
}

# Stats about the item itself, not the hero. Ignored, because counting them as
# spirit makes every active item look like a spirit item.
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
# Patterns over tooltip text. Each was checked against the items it matches.

# Healing or shielding someone else. "The target" isn't enough, because
# Shrink Ray and Knockdown target enemies.
ALLY_TOOLTIP_RE = re.compile(
    r"(nearby\s+all(?:y|ies)|allied\s+hero|(?:your\s+)?allies\b|"
    r"friendly\s+(?:target|unit)|to\s+an\s+ally|or\s+an\s+ally|"
    r"someone\s+else|non-self)",
    re.IGNORECASE,
)

# Healing yourself, however it's triggered.
SELF_HEAL_TOOLTIP_RE = re.compile(
    r"(grants?\s+you\s+bonus\s+regen|heal\s+yourself|"
    r"steal\s+max\s+hp|lifesteal|siphon)",
    re.IGNORECASE,
)

# Effects that work through your bullets. Some of these items look like spirit
# items by their stats but are bought for gun builds.
BULLET_TOOLTIP_RE = re.compile(
    r"(your\s+bullets|bullet\s+damage|weapon\s+damage|fire\s+rate|"
    r"bullets?\s+(?:apply|deal|steal|build))",
    re.IGNORECASE,
)

MELEE_TOOLTIP_RE = re.compile(r"(heavy\s+melee|light\s+melee|melee\s+attack)", re.IGNORECASE)

_SVG_RE = re.compile(r"<svg.*?</svg>", re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def tooltip_text(entry: dict[str, Any]) -> str:
    """An item's tooltip as plain text, or "" if it has none.

    Tooltips are nested JSON with inline SVG and HTML. 155 of 173 shop items
    have one.
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

# Hand-set family scores for items the stats and tooltip patterns get wrong,
# each with its reason. Kept here, not folded into the stat table, so every
# manual call is easy to find.
TOOLTIP_OVERRIDES: dict[str, dict[str, int]] = {
    # "When you perform a Light or Heavy Melee attack against a hero, deal
    # extra spirit damage." Spirit stats, bought for melee.
    "upgrade_acolytes_glove": {"melee": 3},
    # Its stat is gun, but community guides put it in melee builds, and 93%
    # of Abrams' melee cluster buys it.
    "upgrade_close_range": {"melee": 2},
    # A barrier cast on an ally. Its stats look the same as Plated Armor's.
    "upgrade_guardian_ward": {"support": 4},
    "upgrade_divine_barrier": {"support": 4},
}


@functools.lru_cache(maxsize=1)
def _raw_items(cache_dir: Path = assets.DEFAULT_CACHE) -> dict[int, dict[str, Any]]:
    """Raw upgrade asset entries by id. `Item` doesn't keep stats or tooltips."""
    raw: list[dict[str, Any]] = api.get("/v1/assets/items", cache_dir=cache_dir)
    return {e["id"]: e for e in raw if e.get("type") == "upgrade"}


def _stat_names(entry: dict[str, Any]) -> set[str]:
    """Names of the item's nonzero stats, from both stat fields, minus SELF_REFERENTIAL.

    Zero values are skipped. Every item lists WeaponPower, TechPower, and
    ChannelMoveSpeed as "0", and counting those would put all 173 items in
    both gun and spirit.
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
    """Whether a stat value is set and not zero."""
    if value is None:
        return False
    try:
        return float(value) != 0.0
    except (TypeError, ValueError):
        return bool(value)


@functools.lru_cache(maxsize=1)
def item_families(cache_dir: Path = assets.DEFAULT_CACHE) -> dict[int, dict[str, int]]:
    """Map each shop item to a score per family.

    An item can be in several families. Crushing Fists is melee, gun, and tank.
    One label per item would hide that gun and melee builds share Close
    Quarters.
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
    """Family scores from the item's tooltip text.

    See the module docstring for items where the tooltip corrects the stats.
    Healing allies scores 3, more than any single stat, because it is the
    clearest sign of a support item.
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
    """Inverse document frequency of each family across shop items.

    Without this, tank (99 items) and gun (71) outweigh melee (9) and
    support (12), and Abrams, Sinclair, and Kelvin get the wrong names.
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
    """Score each family for a cluster from its items' lifts.

    `lifts` maps item id to (prevalence in this cluster - prevalence in the
    hero's other clusters). Using lift rather than prevalence names a cluster
    for what sets it apart, not for the staples every cluster of the hero
    buys. Negative lifts are ignored.
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
    """Name a cluster after its top build family.

    Returns (name, family scores, margin of the top family over the second).

    If the margin is below `min_margin`, returns the bare hero name. IDF gives
    rare families a lot of weight, so two healing items can outweigh four gun
    items. Ivy's middle cluster leads on Quicksilver Reload, Tesla Bullets,
    and Titanic Magazine, yet scored "Support" by 1.2x.
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
        # The second family is close behind. See HYBRID_MARGIN.
        label = f"Hybrid-{label}"
    return f"{label} {hero_name}", scores, margin


# Ability kit tags that have a matching build family, as (family, weight).
# `burst`, `dot`, and `cc` have no item equivalent and are left out.
KIT_TAG_FAMILIES = {
    "support": ("support", 3),
    "melee": ("melee", 3),
    "gun": ("gun", 2),
    "sustain": ("sustain", 2),
    "mobility": ("mobility", 1),
}


def hero_ability_families(
    hero_id: int, cache_dir: Path = assets.DEFAULT_CACHE
) -> dict[str, int]:
    """Family scores from a hero's ability descriptions, via `kits.hero_kits`.

    Uses the description text, not stats. Calico's Leaping Slash has only a
    HealAmount stat, but its description says "dealing melee damage".

    A kit says which builds make sense on a hero, not which one a player is
    running. Against the fitted archetypes, the kit predicts the build family
    only for melee.
    """
    from . import kits

    scores: dict[str, int] = {}
    for tag, count in kits.hero_kits(cache_dir).get(hero_id, {}).items():
        mapping = KIT_TAG_FAMILIES.get(tag)
        if mapping is None:
            continue
        family, weight = mapping
        scores[family] = scores.get(family, 0) + weight * count
    return scores
