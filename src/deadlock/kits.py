"""Tags for what each hero's abilities do, read from the ability descriptions.

Abilities keep their text in `description`. Items keep theirs in
`tooltip_sections`, and reading that field on an ability returns nothing.

The tags come from the description text because the stat block misses what
players care about. Viscous' The Cube "encases the target in a cube of
restorative goo that protects from damage", but nothing in its stats says
support. Vindicta's Stake "tethers enemies" and Shiv's Serrated Knives
"bleeds an enemy", and neither has a stat key for crowd control or damage over
time. 149 of the 152 signature abilities on playable heroes have usable text.

Ability tags (`burst`, `dot`, `cc`, ...) are a different vocabulary from item
build families (`gun`, `spirit`). A hero's kit says which builds make sense on
them, not which build a given player is running.
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

# Healing only counts as support near one of these words. "Target" isn't
# enough: Vindicta's Crow Familiar and Venator's Ira Domini both have a target
# and neither is support.
_ALLY = r"all(?:y|ies|ied)|teammate|team-?mate"

# The abilities named in these comments are the examples a player gave when
# correcting an earlier, stat-based version.
TAG_PATTERNS: dict[str, re.Pattern[str]] = {
    # Damage that lands all at once, like Lash's Ground Strike or Dynamo's
    # Kinetic Pulse. "Deals damage" alone matches 33 of 38 heroes, so the
    # pattern needs an explosion, impact, slam, or similar word.
    "burst": re.compile(
        r"(explod\w+|detonat\w+|impact\s+damage|on\s+impact|\bslam\w*|"
        r"\bstomp\w*|\bblast\w*|\bpulse\b|\bburst\b|\bshockwave\b|"
        r"\bnova\b|\berupt\w*|damage\s+in\s+(?:a|an|the)\s+(?:area|radius)|"
        r"damag(?:es|ing)\s+(?:all\s+)?enemies\s+(?:in|within)\s+"
        r"(?:a|an|the)\s+(?:area|radius|circle|cone))",
        re.I,
    ),
    # Damage over time, like Shiv's bleed or Infernus' Afterburn.
    "dot": re.compile(
        r"(damage\s+over\s+time|\bbleed\w*|\bburn\w*|\bignit\w*|\bpoison\w*|"
        r"\bdecay\b|per\s+second|damage\s+each\s+second|over\s+its\s+duration)",
        re.I,
    ),
    # Hard crowd control: stuns, roots, silences, pulls. Slows don't count,
    # because 35 of 152 abilities slow something.
    "cc": re.compile(
        r"(\bstun\w*|\bknock\s?up\w*|\bknocks?\s+enemies\s+in\s+the\s+air|"
        r"\bimmobiliz\w*|\btether\w*|\broot\w*|\bsilenc\w*|\bsleep\w*|"
        r"\bdisarm\w*|\bpull\w*|\blift\w*|movement\s+is\s+restricted|"
        r"cannot\s+take\s+action|unable\s+to\s+take\s+any\s+new\s+actions)",
        re.I,
    ),
    # Healing, shielding, or protecting an ally.
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
    # Healing yourself. This is not support.
    "sustain": re.compile(
        r"(heal(?:ing)?\s+(?:for|yourself|you\b)|drain\w*\s+health|"
        r"lifesteal|heal\s+based\s+on\s+the\s+damage|restore\s+health\s+to\s+you)",
        re.I,
    ),
    # Something that fights for you, like Graves' or McGinnis' summons.
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
    """An ability's description as plain text, or "" if it has none.

    Reads `description.desc`, falling back to `active` and then `passive`.
    """
    description = entry.get("description") or {}
    for key in ("desc", "active", "passive"):
        value = description.get(key)
        if isinstance(value, str) and value.strip():
            text = _TAG_RE.sub("", _SVG_RE.sub(" ", value))
            return re.sub(r"\s+", " ", text).strip()
    return ""


def ability_tags(entry: dict[str, Any]) -> set[str]:
    """The tags that match one ability's description.

    An ability tagged both `dot` and `burst` loses `burst` unless its text
    mentions an explosion or impact. That makes Shiv's Serrated Knives a dot
    and not both.
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
    """For each playable hero, how many of their abilities carry each tag.

    Counts only the four signature abilities a player levels. The assets list
    221 signature abilities, but only 152 belong to the 38 playable heroes.
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
    """Inverse document frequency of each tag across heroes.

    A tag most heroes have gets a weight near 0.
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
    """(hero name, ability count) for every hero with this tag, highest count first."""
    names = {h: v.name for h, v in assets.load_heroes(cache_dir).items()}
    scored = [
        (names.get(hero, str(hero)), tags[tag])
        for hero, tags in hero_kits(cache_dir).items()
        if tags.get(tag)
    ]
    return sorted(scored, key=lambda pair: (-pair[1], pair[0]))
