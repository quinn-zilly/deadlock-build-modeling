"""What items do, versus which shop tab they sit in.

Every test naming a specific item encodes a claim a Deadlock player made and
the asset data confirmed. If one fails, either the taxonomy drifted or the
game changed -- both worth knowing.
"""

from __future__ import annotations

import pytest

from deadlock import assets, semantics

ITEMS = assets.load_items()
BY_NAME = {item.name: i for i, item in ITEMS.items()}


def families(name: str) -> dict[str, int]:
    return semantics.item_families().get(BY_NAME[name], {})


class TestStatExtraction:
    def test_zero_valued_stats_are_not_evidence(self):
        """Every item lists WeaponPower and TechPower as `value: "0"` schema
        placeholders. Counting key presence makes all 173 items look like both
        gun and spirit items, collapsing every IDF to zero."""
        assert "gun" not in families("Extra Health")
        assert "spirit" not in families("Extra Health")

    def test_reads_the_properties_block_not_just_upgrades(self):
        """Siphon Bullets' +15% weapon damage is in `properties` ONLY.

        Reading `property_upgrades` alone gives the flagged item no weapon
        signal at all.
        """
        assert "gun" in families("Siphon Bullets")

    def test_self_referential_stats_are_ignored(self):
        """AbilityCooldown is an active item's OWN cooldown, on 48 of 50
        actives. Counting it as spirit makes every active a spirit item."""
        assert "AbilityCooldown" in semantics.SELF_REFERENTIAL
        assert "AbilityDuration" in semantics.SELF_REFERENTIAL

    def test_real_cooldown_reduction_is_spirit(self):
        assert semantics.FAMILY_WEIGHTS["CooldownReduction"][0] == "spirit"

    def test_almost_every_shopable_item_is_scored(self):
        """Five items score nothing, and correctly so: Tesla Bullets, Mystic
        Burst, Prism Blast, Frostbite Charm and Eternal Gift are pure-damage
        procs whose stats are one-off mechanics (ChainCount, BeamWidth). They
        belong to no build family."""
        scored = len(semantics.item_families())
        assert scored >= len(assets.shopable_items()) - 5


class TestPlayerCorrections:
    """Each of these was reported by a player and confirmed in the data."""

    def test_siphon_bullets_is_a_gun_item(self):
        """Vitality-slotted, but it is why Lash's gun build read as "Tank"."""
        assert ITEMS[BY_NAME["Siphon Bullets"]].slot_type == "vitality"
        assert families("Siphon Bullets").get("gun", 0) > 0

    @pytest.mark.parametrize("name", ["Melee Charge", "Crushing Fists"])
    def test_melee_items_are_weapon_slotted(self, name):
        """Slot type can never separate melee from gun."""
        assert ITEMS[BY_NAME[name]].slot_type == "weapon"
        assert families(name).get("melee", 0) >= 6

    @pytest.mark.parametrize(
        "name", ["Rescue Beam", "Healing Tempo", "Guardian Ward", "Divine Barrier"]
    )
    def test_support_items_are_vitality_slotted(self, name):
        """All would be named "Tank" by slot type."""
        assert ITEMS[BY_NAME[name]].slot_type == "vitality"
        assert families(name).get("support", 0) > 0

    def test_divine_ward_does_not_exist(self):
        """The player named it; the asset table has Guardian Ward and Divine
        Barrier instead, and both do what they described."""
        assert "Divine Ward" not in BY_NAME
        assert "Guardian Ward" in BY_NAME
        assert "Divine Barrier" in BY_NAME


class TestTooltipEvidence:
    """Stats say which numbers move; the tooltip says what the item is for."""

    @staticmethod
    def tooltip(name: str) -> str:
        return semantics.tooltip_text(semantics._raw_items()[BY_NAME[name]])

    def test_tooltip_text_strips_markup(self):
        """Tooltips are nested JSON carrying inline SVG icons and HTML spans."""
        text = self.tooltip("Siphon Bullets")
        assert "<" not in text
        assert "steal Max HP" in text

    def test_most_items_have_a_tooltip(self):
        with_text = sum(
            1
            for i in assets.shopable_items()
            if semantics.tooltip_text(semantics._raw_items()[i])
        )
        assert with_text >= 150

    def test_siphon_bullets_primary_effect_is_only_in_the_tooltip(self):
        """Its whole point -- bullets steal Max HP -- appears in no stat key.

        A player raised this directly: the +15% weapon damage the stats show is
        real but secondary.
        """
        assert "steal Max HP" in self.tooltip("Siphon Bullets")
        stats = semantics._stat_names(semantics._raw_items()[BY_NAME["Siphon Bullets"]])
        assert not any("Steal" in s and "Max" in s for s in stats)

    @pytest.mark.parametrize("name", ["Mystic Regeneration", "Radiant Regeneration"])
    def test_regeneration_items_heal_the_buyer_not_allies(self, name):
        """They type as spirit healing, which read as "support" and mislabelled
        Venator's hybrid gun build. The text says dealing spirit damage grants
        YOU regeneration."""
        assert "grants you" in self.tooltip(name).lower()
        assert families(name).get("support", 0) == 0
        assert families(name).get("sustain", 0) > 0

    def test_healing_tempo_is_a_gun_item(self):
        """It grants the target bonus FIRE RATE -- why a gun carry buys it."""
        assert "fire rate" in self.tooltip("Healing Tempo").lower()
        assert families("Healing Tempo").get("gun", 0) > 0

    def test_ally_healing_is_recognised(self):
        assert "allied hero" in self.tooltip("Rescue Beam")
        assert families("Rescue Beam").get("support", 0) > 0

    def test_melee_tooltip_recovers_items_stats_miss(self):
        """Spirit Strike types as spirit; its text is about melee attacks."""
        assert "melee" in self.tooltip("Spirit Strike").lower()
        assert families("Spirit Strike").get("melee", 0) > 0


class TestSupportVersusSustain:
    def test_self_healing_is_not_support(self):
        """Without this split, Siphon Bullets' HP-steal lands beside Rescue
        Beam and Kelvin's support build stops being distinguishable."""
        assert families("Siphon Bullets").get("support", 0) == 0
        assert families("Siphon Bullets").get("sustain", 0) > 0

    def test_siphon_bullets_is_both_gun_and_sustain(self):
        """A player's description: it steals max HP AND raises gun damage."""
        scores = families("Siphon Bullets")
        assert scores.get("gun", 0) > 0 and scores.get("sustain", 0) > 0

    def test_heal_shaped_stats_default_to_sustain(self):
        """Almost every heal STAT is self-regen whatever triggers it; only the
        tooltip establishes that healing reaches an ally."""
        assert semantics.FAMILY_WEIGHTS["TotalHealthRegen"][0] == "sustain"
        assert semantics.FAMILY_WEIGHTS["Regeneration"][0] == "sustain"

    def test_anti_heal_is_control_not_support(self):
        """Crippling Headshot debuffs enemy healing. It is a gun item."""
        assert families("Crippling Headshot").get("support", 0) == 0

    def test_healing_an_ally_is_support(self):
        assert families("Rescue Beam").get("support", 0) > 0


class TestIDF:
    def test_rare_families_score_higher(self):
        idf = semantics.family_idf()
        assert idf["melee"] > idf["tank"]
        assert idf["support"] > idf["gun"]

    def test_melee_is_the_rarest_family(self):
        idf = semantics.family_idf()
        assert idf["melee"] == max(idf.values())

    def test_naming_families_all_have_positive_idf(self):
        """A family on every item carries no information and can never win."""
        idf = semantics.family_idf()
        assert all(idf.get(f, 0) > 0 for f in semantics.NAMING_FAMILIES)


class TestScoring:
    def test_negative_lift_contributes_nothing(self):
        gun = BY_NAME["Siphon Bullets"]
        assert semantics.score_families({gun: -0.5})["gun"] == 0.0

    def test_lift_scales_the_score(self):
        gun = BY_NAME["Siphon Bullets"]
        small = semantics.score_families({gun: 0.1})["gun"]
        large = semantics.score_families({gun: 0.5})["gun"]
        assert large > small

    def test_multi_family_items_count_everywhere(self):
        """Crushing Fists is melee and gun and tank; forcing one label per
        item throws away that gun and melee builds share items."""
        scores = families("Crushing Fists")
        assert len([f for f, v in scores.items() if v > 0]) > 1


class TestNaming:
    @staticmethod
    def lifts_for(names: list[str], lift: float = 0.5) -> dict[int, float]:
        return {BY_NAME[n]: lift for n in names}

    def test_melee_items_name_a_melee_build(self):
        name, _, _ = semantics.name_cluster(
            self.lifts_for(["Melee Charge", "Crushing Fists"]), "Abrams"
        )
        assert name == "Melee Abrams"

    def test_support_items_name_a_support_build(self):
        name, _, _ = semantics.name_cluster(
            self.lifts_for(["Rescue Beam", "Healing Tempo", "Guardian Ward"]), "Kelvin"
        )
        assert name == "Support Kelvin"

    def test_thin_margin_declines_to_label(self):
        """A near-tie is a coin flip a player would read as wrong."""
        name, _, margin = semantics.name_cluster({}, "Ivy")
        assert name == "Ivy"
        assert margin == 0.0

    def test_returns_scores_for_review(self):
        _, scores, _ = semantics.name_cluster(self.lifts_for(["Melee Charge"]), "Abrams")
        assert scores["melee"] > 0

    def test_margin_is_reported(self):
        _, _, margin = semantics.name_cluster(
            self.lifts_for(["Melee Charge", "Crushing Fists"]), "Abrams"
        )
        assert margin >= semantics.MIN_NAMING_MARGIN


class TestHeroAbilities:
    def test_ability_stats_do_not_encode_melee(self):
        """A limit worth pinning, not a bug.

        A player noted Calico's Leaping Slash deals melee damage and heals off
        spirit, which is why melee Calico is a real build. But the ability
        carries no typed melee stat -- only HealAmount -- so the kit signal
        cannot recover it. Hero-level ability evidence is a weak prior here,
        and item evidence is what actually names the build.
        """
        scores = semantics.hero_ability_families(
            next(h for h, v in assets.load_heroes().items() if v.name == "Calico")
        )
        assert scores.get("melee", 0) == 0

    def test_kelvin_kit_points_at_support(self):
        """Frost Grenade heals teammates and slows enemies."""
        scores = semantics.hero_ability_families(
            next(h for h, v in assets.load_heroes().items() if v.name == "Kelvin")
        )
        assert scores.get("support", 0) > 0 or scores.get("control", 0) > 0

    def test_unknown_hero_scores_nothing(self):
        assert semantics.hero_ability_families(999_999) == {}
