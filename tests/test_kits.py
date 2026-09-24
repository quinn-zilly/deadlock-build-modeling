"""Ability tags read from the ability descriptions.

Most tests check a claim a Deadlock player made about an ability. An earlier
version read only stat keys and wrongly rejected two of the player's six
groupings of heroes by kit.
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
        """Ability text is in `description`. `tooltip_sections` is an item field."""
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
    """Abilities a player named when correcting the stat-based tagger."""

    def test_the_cube_is_support(self):
        """The Cube is support. Its stats don't say so; its description does."""
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
        """Tethers, knockups, stuns, and immobilizes are cc. None has a stat key."""
        assert "cc" in tags(hero, name)

    def test_serrated_knives_is_damage_over_time(self):
        """Serrated Knives is dot (it bleeds), not burst."""
        assert "dot" in tags("Shiv", "Serrated Knives")

    def test_powder_keg_is_burst_and_dot(self):
        """Powder Keg is both burst and dot, since it explodes and then burns."""
        assert {"burst", "dot"} <= tags("Holliday", "Powder Keg")

    def test_leaping_slash_is_melee(self):
        """Leaping Slash is melee. Its only stat is HealAmount."""
        assert "melee" in tags("Calico", "Leaping Slash")

    @pytest.mark.parametrize("hero,name", [("Lash", "Ground Strike"), ("Viscous", "Goo Ball")])
    def test_spirit_burst_examples(self, hero, name):
        assert "burst" in tags(hero, name)


class TestClaimedGroupings:
    """The six groupings of heroes by kit that a player named all hold."""

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
    """No tag applies to nearly every hero."""

    @pytest.mark.parametrize("tag", ["support", "melee", "dot", "summon"])
    def test_rare_tags_are_rare(self, tag):
        assert len(kits.heroes_by_tag(tag)) <= 15

    def test_burst_is_not_universal(self):
        """Burst needs words like explosion or impact. "Deals damage" matched 33 of 38 heroes."""
        assert len(kits.heroes_by_tag("burst")) <= 26

    def test_idf_ranks_rare_tags_higher(self):
        idf = kits.tag_idf()
        assert idf["support"] > idf["burst"]
        assert idf["melee"] > idf["cc"]


class TestHeroKits:
    def test_covers_every_playable_hero(self):
        assert len(kits.hero_kits()) == 38

    def test_only_signature_abilities_count(self):
        """Only playable heroes' abilities count. 69 of the 221 belong to disabled heroes."""
        assert all(hero in PLAYABLE for hero in kits.hero_kits())

    def test_every_hero_has_at_least_one_tag(self):
        assert all(tags for tags in kits.hero_kits().values())

    def test_summon_exists_as_a_kit_tag(self):
        """`summon` is a kit tag, though no build family matches it."""
        assert kits.heroes_by_tag("summon")
