"""Build families: what each item does, as opposed to its shop tab.

Tests that name an item check a claim a Deadlock player made that the asset
data confirmed. If one fails, either the family rules changed or the game did.
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
        """Stats with value "0" are ignored. Every item lists WeaponPower and TechPower as "0"."""
        assert "gun" not in families("Extra Health")
        assert "spirit" not in families("Extra Health")

    def test_reads_the_properties_block_not_just_upgrades(self):
        """Stats are read from `properties` too. Siphon Bullets' weapon damage is only there."""
        assert "gun" in families("Siphon Bullets")

    def test_self_referential_stats_are_ignored(self):
        """AbilityCooldown, the item's own cooldown, doesn't count as spirit."""
        assert "AbilityCooldown" in semantics.SELF_REFERENTIAL
        assert "AbilityDuration" in semantics.SELF_REFERENTIAL

    def test_real_cooldown_reduction_is_spirit(self):
        assert semantics.FAMILY_WEIGHTS["CooldownReduction"][0] == "spirit"

    def test_almost_every_shopable_item_is_scored(self):
        """At most five shop items get no family.

        The five (Tesla Bullets, Mystic Burst, Prism Blast, Frostbite Charm,
        Eternal Gift) are damage procs whose stats, like ChainCount and
        BeamWidth, belong to no family.
        """
        scored = len(semantics.item_families())
        assert scored >= len(assets.shopable_items()) - 5


class TestPlayerCorrections:
    """Corrections a player reported that the data confirmed."""

    def test_siphon_bullets_is_a_gun_item(self):
        """Siphon Bullets is gun, though it's in the vitality tab."""
        assert ITEMS[BY_NAME["Siphon Bullets"]].slot_type == "vitality"
        assert families("Siphon Bullets").get("gun", 0) > 0

    @pytest.mark.parametrize("name", ["Melee Charge", "Crushing Fists"])
    def test_melee_items_are_weapon_slotted(self, name):
        """Melee items are in the weapon tab, so the tab can't tell melee from gun."""
        assert ITEMS[BY_NAME[name]].slot_type == "weapon"
        assert families(name).get("melee", 0) >= 6

    @pytest.mark.parametrize(
        "name", ["Rescue Beam", "Healing Tempo", "Guardian Ward", "Divine Barrier"]
    )
    def test_support_items_are_vitality_slotted(self, name):
        """Support items are in the vitality tab, so the tab would call them tank."""
        assert ITEMS[BY_NAME[name]].slot_type == "vitality"
        assert families(name).get("support", 0) > 0

    def test_divine_ward_does_not_exist(self):
        """There is no "Divine Ward". The player meant Guardian Ward and Divine Barrier."""
        assert "Divine Ward" not in BY_NAME
        assert "Guardian Ward" in BY_NAME
        assert "Divine Barrier" in BY_NAME


class TestTooltipEvidence:
    """Family scores from tooltip text, which says what an item is for."""

    @staticmethod
    def tooltip(name: str) -> str:
        return semantics.tooltip_text(semantics._raw_items()[BY_NAME[name]])

    def test_tooltip_text_strips_markup(self):
        """tooltip_text removes the inline SVG and HTML from tooltips."""
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
        """"Bullets steal Max HP", Siphon Bullets' main effect, is only in the tooltip."""
        assert "steal Max HP" in self.tooltip("Siphon Bullets")
        stats = semantics._stat_names(semantics._raw_items()[BY_NAME["Siphon Bullets"]])
        assert not any("Steal" in s and "Max" in s for s in stats)

    @pytest.mark.parametrize("name", ["Mystic Regeneration", "Radiant Regeneration"])
    def test_regeneration_items_heal_the_buyer_not_allies(self, name):
        """Mystic and Radiant Regeneration are sustain, not support: they heal the buyer."""
        assert "grants you" in self.tooltip(name).lower()
        assert families(name).get("support", 0) == 0
        assert families(name).get("sustain", 0) > 0

    def test_healing_tempo_is_a_gun_item(self):
        """Healing Tempo is gun, because it gives the target bonus fire rate."""
        assert "fire rate" in self.tooltip("Healing Tempo").lower()
        assert families("Healing Tempo").get("gun", 0) > 0

    def test_ally_healing_is_recognised(self):
        assert "allied hero" in self.tooltip("Rescue Beam")
        assert families("Rescue Beam").get("support", 0) > 0

    def test_melee_tooltip_recovers_items_stats_miss(self):
        """Spirit Strike has spirit stats, but its tooltip makes it melee."""
        assert "melee" in self.tooltip("Spirit Strike").lower()
        assert families("Spirit Strike").get("melee", 0) > 0


class TestSupportVersusSustain:
    def test_self_healing_is_not_support(self):
        """Siphon Bullets heals only the buyer, so it is sustain, not support."""
        assert families("Siphon Bullets").get("support", 0) == 0
        assert families("Siphon Bullets").get("sustain", 0) > 0

    def test_siphon_bullets_is_both_gun_and_sustain(self):
        """Siphon Bullets is gun and sustain: it raises gun damage and steals max HP."""
        scores = families("Siphon Bullets")
        assert scores.get("gun", 0) > 0 and scores.get("sustain", 0) > 0

    def test_heal_shaped_stats_default_to_sustain(self):
        """Healing stats map to sustain. Only tooltip text about allies adds support."""
        assert semantics.FAMILY_WEIGHTS["TotalHealthRegen"][0] == "sustain"
        assert semantics.FAMILY_WEIGHTS["Regeneration"][0] == "sustain"

    def test_anti_heal_is_control_not_support(self):
        """Crippling Headshot cuts enemy healing, which is not support."""
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
        """Every naming family has IDF above 0, so none is on every item."""
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
        """Crushing Fists counts in melee, gun, and tank."""
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
        """When two families nearly tie, the cluster keeps the bare hero name."""
        name, _, margin = semantics.name_cluster({}, "Ivy")
        assert name == "Ivy"
        assert margin == 0.0

    def test_returns_scores_for_review(self):
        _, scores, _ = semantics.name_cluster(self.lifts_for(["Melee Charge"]), "Abrams")
        assert scores["melee"] > 0

    def test_a_close_second_family_reads_as_hybrid(self):
        """A close second family gives a "Hybrid-" name, like Venator's gun build that also runs spirit."""
        # Gun evidence leading, spirit close behind.
        name, _, margin = semantics.name_cluster(
            {BY_NAME["Siphon Bullets"]: 0.5, BY_NAME["Boundless Spirit"]: 0.3},
            "Venator",
        )
        assert semantics.MIN_NAMING_MARGIN <= margin < semantics.HYBRID_MARGIN
        assert name.startswith("Hybrid-")

    def test_a_clear_winner_is_not_hybrid(self):
        name, _, margin = semantics.name_cluster(
            self.lifts_for(["Melee Charge", "Crushing Fists"]), "Abrams"
        )
        assert margin >= semantics.HYBRID_MARGIN
        assert not name.startswith("Hybrid-")

    def test_margin_is_reported(self):
        _, _, margin = semantics.name_cluster(
            self.lifts_for(["Melee Charge", "Crushing Fists"]), "Abrams"
        )
        assert margin >= semantics.MIN_NAMING_MARGIN


class TestHeroAbilities:
    def test_calico_kit_points_at_melee(self):
        """Calico's kit points at melee.

        Leaping Slash's only stat is HealAmount, but its description says
        "dealing melee damage".
        """
        scores = semantics.hero_ability_families(
            next(h for h, v in assets.load_heroes().items() if v.name == "Calico")
        )
        assert scores.get("melee", 0) > 0

    def test_viscous_kit_points_at_support(self):
        """Viscous' kit points at support, because of The Cube's description."""
        scores = semantics.hero_ability_families(
            next(h for h, v in assets.load_heroes().items() if v.name == "Viscous")
        )
        assert scores.get("support", 0) > 0

    def test_kelvin_kit_points_at_support(self):
        """Kelvin's kit points at support: Frost Grenade heals teammates."""
        scores = semantics.hero_ability_families(
            next(h for h, v in assets.load_heroes().items() if v.name == "Kelvin")
        )
        assert scores.get("support", 0) > 0 or scores.get("control", 0) > 0

    def test_unknown_hero_scores_nothing(self):
        assert semantics.hero_ability_families(999_999) == {}
