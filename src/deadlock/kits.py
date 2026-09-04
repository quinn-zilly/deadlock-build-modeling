"""What a hero's abilities do, read from what the game says they do.

Items and abilities hide their descriptions in different fields. Items use
`tooltip_sections`; abilities use `description`, and looking for the item field
on an ability returns nothing. That mistake produced the claim that abilities
carry no descriptive text, and everything downstream of it was scored from stat
keys alone -- which does not work:

- Viscous' The Cube "encases the target in a cube of restorative goo that
  protects from damage and increases health regen". A player calls it the best
  support ability in the game. Its stat block says none of that, so a
  stat-based tagger saw only Puddle Punch's Air Control buff and concluded
  Viscous was not a support hero.
- Vindicta's Stake "tethers enemies to the location where the stake lands", and
  Dynamo's Singularity applies "stun, and pulling in nearby enemies". Both are
  crowd control; neither has a stat key that says so.
- Shiv's Serrated Knives "bleeds an enemy... causing the bleed to increase per
  stack" -- damage over time, invisible to a stat scan.

149 of the 152 signature abilities on playable heroes carry usable text. So the
tags here come from the prose, and the stat block is only a fallback.

The tags are the vocabulary a player uses to describe a kit, which is not the
same vocabulary as item build families: an ability is `burst` or `dot` or `cc`,
where an item is `gun` or `spirit`. A hero's kit says which builds are
plausible on them, not which build a given player is running.
"""

from __future__ import annotations

import functools
import re
from pathlib import Path
from typing import Any

from . import api, assets

# Ability tags, in the vocabulary players use for kits.
TAGS = (
    "burst",
    "dot",
    "cc",
    "support",
    "melee",
    "gun",
    "mobility",
    "sustain",
    "summon",
)

_SVG_RE = re.compile(r"<svg.*?</svg>", re.S)
_TAG_RE = re.compile(r"<[^>]+>")

# An ally word, required before healing counts as support. "Target" alone is
# not one: Vindicta's Crow Familiar and Venator's Ira Domini both target
# something, and neither is a support ability.
_ALLY = r"all(?:y|ies|ied)|teammate|team-?mate"

# Each pattern is a claim about what a phrase means. The examples in the
# comments are the abilities a player named when correcting an earlier,
# stat-based version of this.
TAG_PATTERNS: dict[str, re.Pattern[str]] = {
    # A large hit of spirit damage delivered at once -- Lash's Ground Strike,
    # Dynamo's Kinetic Pulse. "Deals damage" is NOT enough: 33 of 38 heroes
    # match that, which makes the tag meaningless. What distinguishes burst is
    # damage arriving in one moment -- an explosion, an impact, a slam -- so
    # the pattern requires that wording.
    "burst": re.compile(
        r"(explod\w+|detonat\w+|impact\s+damage|on\s+impact|\bslam\w*|"
        r"\bstomp\w*|\bblast\w*|\bpulse\b|\bburst\b|\bshockwave\b|"
        r"\bnova\b|\berupt\w*|damage\s+in\s+(?:a|an|the)\s+(?:area|radius)|"
        r"damag(?:es|ing)\s+(?:all\s+)?enemies\s+(?:in|within)\s+"
        r"(?:a|an|the)\s+(?:area|radius|circle|cone))",
        re.I,
    ),
    # Damage applied over a duration -- Shiv's bleed, Holliday's burn,
    # Infernus' Afterburn.
    "dot": re.compile(
        r"(damage\s+over\s+time|\bbleed\w*|\bburn\w*|\bignit\w*|\bpoison\w*|"
        r"\bdecay\b|per\s+second|damage\s+each\s+second|over\s+its\s+duration)",
        re.I,
    ),
    # Taking control away from the enemy. Slow alone is deliberately excluded:
    # 35 of 152 abilities slow something, which makes it too common to
    # discriminate. Hard control is what players mean by CC.
    "cc": re.compile(
        r"(\bstun\w*|\bknock\s?up\w*|\bknocks?\s+enemies\s+in\s+the\s+air|"
        r"\bimmobiliz\w*|\btether\w*|\broot\w*|\bsilenc\w*|\bsleep\w*|"
        r"\bdisarm\w*|\bpull\w*|\blift\w*|movement\s+is\s+restricted|"
        r"cannot\s+take\s+action|unable\s+to\s+take\s+any\s+new\s+actions)",
        re.I,
    ),
    # Helping someone else -- healing, shielding, or protecting an ally.
    "support": re.compile(
        rf"((?:heal\w*|restor\w*|barrier|shield\w*|protect\w*|regen\w*|"
        rf"cleanse\w*|revive\w*)[^.]{{0,80}}?(?:{_ALLY})|"
        rf"(?:{_ALLY})[^.]{{0,80}}?(?:heal\w*|restor\w*|barrier|shield\w*|"
        rf"protect\w*|regen\w*|cleanse\w*)|"
        r"grant\s+an\s+ally|encase\s+the\s+target[^.]{0,60}restorative|"
        r"protects\s+from\s+damage)",
        re.I,
    ),
    "melee": re.compile(r"(melee\s+damage|heavy\s+melee|melee\s+attack|melee\s+hits)", re.I),
    "gun": re.compile(
        r"(weapon\s+damage|fire\s+rate|bullet\s+(?:damage|resist)|"
        r"reload|your\s+gun|ammo|bullets)",
        re.I,
    ),
    "mobility": re.compile(
        r"(\bdash\w*|\bleap\w*|\bteleport\w*|move\s+speed|sprint|"
        r"\bmantle\b|air\s+control|\bglide\w*|traverse)",
        re.I,
    ),
    # Healing yourself, which is a bruiser pattern and not support.
    "sustain": re.compile(
        r"(heal(?:ing)?\s+(?:for|yourself|you\b)|drain\w*\s+health|"
        r"lifesteal|heal\s+based\s+on\s+the\s+damage|restore\s+health\s+to\s+you)",
        re.I,
    ),
    # Something that fights for you -- Graves, McGinnis, Sinclair.
    "summon": re.compile(
        r"(\bsummon\w*|deploy\w*|\bturret\w*|familiar|\bspirit\s+that\b|"
        r"helpers?\b|minion|\bpet\b|controlled\s+by)",
        re.I,
    ),
}


@functools.lru_cache(maxsize=1)
def _raw_abilities(cache_dir: Path = assets.DEFAULT_CACHE) -> dict[int, dict[str, Any]]:
    raw: list[dict[str, Any]] = api.get("/v1/assets/items", cache_dir=cache_dir)
    return {e["id"]: e for e in raw if e.get("type") == "ability"}


def ability_text(entry: dict[str, Any]) -> str:
    """An ability's description, stripped of markup.

    Abilities keep this in `description`, NOT the `tooltip_sections` items use.
    Falls back through the sub-keys because coverage varies: `desc` covers most,
    with `active`/`passive` filling in the rest.
    """
    description = entry.get("description") or {}
    for key in ("desc", "active", "passive"):
        value = description.get(key)
        if isinstance(value, str) and value.strip():
            text = _TAG_RE.sub("", _SVG_RE.sub(" ", value))
            return re.sub(r"\s+", " ", text).strip()
    return ""


def ability_tags(entry: dict[str, Any]) -> set[str]:
    """What one ability does, from its description.

    `burst` is suppressed when the same ability reads as damage over time, so
    Shiv's Serrated Knives is a dot rather than both -- the two describe how
    damage arrives, and an ability delivers it one way or the other.
    """
    text = ability_text(entry)
    if not text:
        return set()
    tags = {tag for tag, pattern in TAG_PATTERNS.items() if pattern.search(text)}
    if "dot" in tags and "burst" in tags and not re.search(
        r"(explod\w+|detonat\w+|impact\s+damage|on\s+impact)", text, re.I
    ):
        tags.discard("burst")
    return tags


@functools.lru_cache(maxsize=1)
def hero_kits(cache_dir: Path = assets.DEFAULT_CACHE) -> dict[int, dict[str, int]]:
    """Map each playable hero to its kit tags and how many abilities carry each.

    Only signature abilities count -- the four a player levels. Scoped to
    playable heroes: 152 of the 221 mapped signature abilities belong to the 38
    heroes actually in matches, the rest to disabled or in-development ones.
    """
    abilities = _raw_abilities(cache_dir)
    slots = assets.signature_slots(cache_dir)
    playable = set(assets.playable_heroes(cache_dir))

    kits: dict[int, dict[str, int]] = {hero: {} for hero in playable}
    for ability_id, entry in abilities.items():
        hero = entry.get("hero")
        if ability_id not in slots or hero not in playable:
            continue
        for tag in ability_tags(entry):
            kits[hero][tag] = kits[hero].get(tag, 0) + 1
    return kits


@functools.lru_cache(maxsize=1)
def tag_idf(cache_dir: Path = assets.DEFAULT_CACHE) -> dict[str, float]:
    """How rare each tag is across heroes, so common ones weigh less.

    Every hero deals damage and nearly every hero has some slow, so those tags
    carry little information about what makes a kit distinctive.
    """
    import math

    kits = hero_kits(cache_dir)
    total = len(kits)
    counts: dict[str, int] = {}
    for tags in kits.values():
        for tag in tags:
            counts[tag] = counts.get(tag, 0) + 1
    return {
        tag: math.log(total / count) if count else 0.0 for tag, count in counts.items()
    }


def heroes_by_tag(tag: str, cache_dir: Path = assets.DEFAULT_CACHE) -> list[tuple[str, int]]:
    """Heroes carrying a tag, most abilities first. The reviewable readout."""
    names = {h: v.name for h, v in assets.load_heroes(cache_dir).items()}
    scored = [
        (names.get(hero, str(hero)), tags[tag])
        for hero, tags in hero_kits(cache_dir).items()
        if tags.get(tag)
    ]
    return sorted(scored, key=lambda pair: (-pair[1], pair[0]))
