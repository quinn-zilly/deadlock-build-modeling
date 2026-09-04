"""What a hero's abilities do, read from the game's own descriptions.

Nearly every test here encodes a claim a Deadlock player made and the
description text confirmed. An earlier version scored abilities from stat keys
alone and told the player that two of their six kit groupings were "not
supported by the data" -- that was the tagger failing, not the groupings.
"""

from __future__ import annotations

import pytest

from deadlock import assets, kits

HEROES = {hero.name: hero_id for hero_id, hero in assets.load_heroes().items()}
PLAYABLE = set(assets.playable_heroes())


def ability(hero: str, name: str) -> dict:
    """One signature ability, by hero and ability name."""
    slots = assets.signature_slots()
    for ability_id, entry in kits._raw_abilities().items():
        if (
            ability_id in slots
            and entry.get("hero") == HEROES[hero]
            and entry.get("name") == name
        ):
            return entry
    raise AssertionError(f"no signature ability {name!r} on {hero}")


def tags(hero: str, name: str) -> set[str]:
    return kits.ability_tags(ability(hero, name))


def rank(tag: str, hero: str) -> int | None:
    ordered = [name for name, _ in kits.heroes_by_tag(tag)]
    return ordered.index(hero) + 1 if hero in ordered else None


class TestAbilityText:
    def test_descriptions_live_in_description_not_tooltip_sections(self):
        """The mistake that started this: `tooltip_sections` is an ITEM field.

        Looking for it on an ability returns nothing, which produced the false
        claim that abilities carry no descriptive text.
        """
        entry = ability("Viscous", "The Cube")
        assert not entry.get("tooltip_sections")
        assert kits.ability_text(entry)

    def test_text_is_stripped_of_markup(self):
        text = kits.ability_text(ability("Dynamo", "Kinetic Pulse"))
        assert "<" not in text
        assert "spirit damage" in text

    def test_nearly_every_signature_ability_has_text(self):
        slots = assets.signature_slots()
        signature = [
            entry
            for ability_id, entry in kits._raw_abilities().items()
            if ability_id in slots and entry.get("hero") in PLAYABLE
        ]
        with_text = sum(1 for entry in signature if kits.ability_text(entry))
        assert len(signature) == 152
        assert with_text >= 149


class TestPlayerExamples:
    """Each case is an ability a player named to correct the stat-based tagger."""

    def test_the_cube_is_support(self):
        """"Probably the single best support ability in the game." Its stat
        block says nothing about that; its description says it encases the
        target in restorative goo."""
        assert "support" in tags("Viscous", "The Cube")

    def test_viscous_is_a_support_hero(self):
        assert rank("support", "Viscous") is not None

    @pytest.mark.parametrize(
        "hero,name",
        [
            ("Vindicta", "Stake"),
            ("Dynamo", "Kinetic Pulse"),
            ("Dynamo", "Singularity"),
            ("Paige", "Captivating Read"),
        ],
    )
    def test_crowd_control_examples(self, hero, name):
        """Tethers, knockups, stuns and immobilizes -- none of which appear as
        stat keys."""
        assert "cc" in tags(hero, name)

    def test_serrated_knives_is_damage_over_time(self):
        """"Literally just a spirit damage over time ability." It bleeds."""
        assert "dot" in tags("Shiv", "Serrated Knives")

    def test_powder_keg_is_burst_and_dot(self):
        """"A burst of damage then spirit damage over time." Both, correctly."""
        assert {"burst", "dot"} <= tags("Holliday", "Powder Keg")

    def test_leaping_slash_is_melee(self):
        """The gap in the stat-based version: it carries only HealAmount, so a
        stat scan could not see that it deals melee damage."""
        assert "melee" in tags("Calico", "Leaping Slash")

    @pytest.mark.parametrize("hero,name", [("Lash", "Ground Strike"), ("Viscous", "Goo Ball")])
    def test_spirit_burst_examples(self, hero, name):
        assert "burst" in tags(hero, name)


class TestClaimedGroupings:
    """The six kit groupings a player named. All six must hold."""

    @pytest.mark.parametrize(
        "tag,heroes",
        [
            ("support", ["Kelvin", "Dynamo", "Paige", "Viscous", "Rem"]),
            ("gun", ["Venator", "Wraith", "Haze", "Vindicta"]),
            ("melee", ["Calico", "Viscous", "Billy"]),
            ("burst", ["Lash", "Viscous", "Dynamo", "Apollo"]),
            ("cc", ["Paige", "Vindicta", "Dynamo", "Ivy", "Graves"]),
            ("dot", ["Infernus", "Shiv", "Holliday"]),
        ],
    )
    def test_every_named_hero_carries_the_tag(self, tag, heroes):
        missing = [hero for hero in heroes if rank(tag, hero) is None]
        assert not missing, f"{tag}: {missing} do not carry it"

    def test_infernus_leads_damage_over_time(self):
        assert kits.heroes_by_tag("dot")[0][0] == "Infernus"

    def test_kelvin_leads_support(self):
        assert kits.heroes_by_tag("support")[0][0] == "Kelvin"

    def test_venator_leads_gun(self):
        assert kits.heroes_by_tag("gun")[0][0] == "Venator"


class TestTagDiscrimination:
    """A tag on every hero says nothing about any hero."""

    @pytest.mark.parametrize("tag", ["support", "melee", "dot", "summon"])
    def test_rare_tags_are_rare(self, tag):
        assert len(kits.heroes_by_tag(tag)) <= 15

    def test_burst_is_not_universal(self):
        """"Deals damage" matched 33 of 38 heroes, which is meaningless.

        Burst means damage delivered in one moment -- an explosion, an impact,
        a slam -- so the pattern requires that wording.
        """
        assert len(kits.heroes_by_tag("burst")) <= 26

    def test_idf_ranks_rare_tags_higher(self):
        idf = kits.tag_idf()
        assert idf["support"] > idf["burst"]
        assert idf["melee"] > idf["cc"]


class TestHeroKits:
    def test_covers_every_playable_hero(self):
        assert len(kits.hero_kits()) == 38

    def test_only_signature_abilities_count(self):
        """69 of the 221 mapped abilities belong to disabled heroes."""
        assert all(hero in PLAYABLE for hero in kits.hero_kits())

    def test_every_hero_has_at_least_one_tag(self):
        assert all(tags for tags in kits.hero_kits().values())

    def test_summon_exists_as_a_kit_tag(self):
        """A family the item vocabulary has no word for."""
        assert kits.heroes_by_tag("summon")
