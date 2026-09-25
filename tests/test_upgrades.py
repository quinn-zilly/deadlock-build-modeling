"""Ability upgrade effects and gun-routed abilities (#42).

The traps these guard: a weapon property listed at "0" and never upgraded is
not a weapon effect, enemy debuffs carry weapon modifier types, and every
upgrade-effect feature is a function of the point timeline.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from deadlock import abilities, upgrades


def ability(props: dict, tiers: list[list[tuple[str, str]]] | None = None) -> dict:
    return {
        "properties": props,
        "upgrades": [
            {"property_upgrades": [{"name": n, "bonus": b} for n, b in tier]}
            for tier in (tiers or [])
        ],
    }


FIRE_RATE = {"value": "20", "provided_property_type": "MODIFIER_VALUE_FIRE_RATE"}


class TestWeaponProperty:
    def test_own_fire_rate_counts(self):
        assert upgrades.is_weapon_property("BonusFireRate", FIRE_RATE)

    def test_on_hit_proc_counts_by_name(self):
        assert upgrades.is_weapon_property("MagicDamagePerBullet", {"value": "2"})
        assert upgrades.is_weapon_property("CritBuildup", {"value": "15"})

    @pytest.mark.parametrize(
        "name",
        ["FireRateSlow", "WeaponPowerDebuff", "DebuffAccuracy", "SummonFireRate"],
    )
    def test_enemy_and_summon_guns_do_not_count(self, name):
        prop = {"value": "-25", "provided_property_type": "MODIFIER_VALUE_FIRE_RATE"}
        assert not upgrades.is_weapon_property(name, prop)

    def test_defensive_bullet_properties_do_not_count(self):
        assert not upgrades.is_weapon_property(
            "BulletResist", {"provided_property_type": "MODIFIER_VALUE_BULLET_ARMOR_DAMAGE_RESIST"}
        )
        assert not upgrades.is_weapon_property("TargetBulletEvasionChance", {"value": "0"})

    def test_placeholders_do_not_count(self):
        assert not upgrades.is_weapon_property("WeaponPower", {"value": "0"})


class TestWeaponTier:
    def test_set_at_base(self):
        assert upgrades.weapon_tier(ability({"BonusFireRate": FIRE_RATE})) == 0

    def test_listed_at_zero_and_never_upgraded_is_not_a_weapon_effect(self):
        """Kinetic Pulse lists BonusFireRate at "0" and no tier sets it."""
        entry = ability(
            {"BonusFireRate": {**FIRE_RATE, "value": "0"}},
            [[("AbilityCharges", "1")], [("BulletResistReduction", "-15")], [("Damage", "135")]],
        )
        assert upgrades.weapon_tier(entry) is None

    def test_granted_by_the_five_point_tier(self):
        entry = ability(
            {"UnlimitedAmmo": {"value": "0"}},
            [[("AbilityCooldown", "-20")], [("AbilityDuration", "3")], [("UnlimitedAmmo", "1")]],
        )
        assert upgrades.weapon_tier(entry) == 3

    def test_values_with_units(self):
        assert not upgrades.is_set({"value": "0m"})
        assert upgrades.is_set({"value": "4m"})
        assert upgrades.is_set({"value": 2.0})


class TestSpiritScaling:
    def test_reads_scale_function_not_scale(self):
        entry = ability({"Damage": {"value": "50", "scale": {}, "scale_function": {
            "class_name": "scale_function_single_stat",
            "specific_stat_scale_type": "ETechPower", "stat_scale": 0.8}}})
        assert upgrades.is_spirit_scaling(entry)

    def test_tech_damage_class_without_a_stat_type(self):
        """Full Auto's MagicDamagePerBullet has the class and no stat type."""
        entry = ability({"MagicDamagePerBullet": {"value": "2", "scale_function": {
            "class_name": "scale_function_tech_damage", "stat_scale": 0.03}}})
        assert upgrades.is_spirit_scaling(entry)

    def test_weapon_power_is_not_spirit(self):
        entry = ability({"MaxBonusBulletDamage": {"value": "10", "scale_function": {
            "class_name": "scale_function_kinetic_carbine_damage",
            "specific_stat_scale_type": "EWeaponPower", "stat_scale": 125.0}}})
        assert not upgrades.is_spirit_scaling(entry)


class TestCategories:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("BulletResistReduction", "shred"),
            ("SlowPercent", "control"),
            ("FireRateSlow", "control"),
            ("HealAmount", "sustain"),
            ("AbilityCooldown", "cooldown"),
            ("AbilityDuration", "duration"),
            ("Radius", "area"),
            ("Damage", "damage"),
            ("UnlimitedAmmo", "weapon"),
        ],
    )
    def test_first_match(self, name, expected):
        assert upgrades.effect_categories(name, {"value": "1"}) == expected


def points(rows: list[tuple[int, int, int, int]]) -> pd.DataFrame:
    """Ability rows of (player_slot, signature_slot, level, game_time_s) for hero 7."""
    return pd.DataFrame(
        [
            {"match_id": 1, "player_slot": p, "hero_id": 7, "signature_slot": s,
             "level": lvl, "game_time_s": t}
            for p, s, lvl, t in rows
        ]
    )


def hero_table(cats: dict[tuple[int, int], set[str]]) -> pd.DataFrame:
    rows = []
    for slot in range(1, 5):
        row = {"hero_id": 7, "signature_slot": slot}
        for level in upgrades.TIER_LEVELS:
            row[f"cats_l{level}"] = frozenset(cats.get((slot, level), set()))
        rows.append(row)
    return pd.DataFrame(rows)


class TestEffectFeatures:
    ROWS = points(
        [(0, 1, 1, 0), (0, 1, 2, 10), (0, 2, 1, 20), (0, 1, 3, 30), (0, 1, 4, 40),
         (1, 2, 1, 0), (1, 2, 2, 10), (1, 1, 1, 20), (1, 1, 2, 30), (1, 2, 3, 40)]
    )

    def test_is_a_linear_map_of_point_order(self):
        """The effect block holds nothing the order columns don't."""
        table = hero_table({(1, 2): {"shred"}, (2, 2): {"shred"}, (1, 4): {"weapon"}})
        got = upgrades.effect_features(self.ROWS, table=table)
        order = abilities.point_order_features(self.ROWS)
        expected_shred = ((1 - order["pt_1_l2"]) + (1 - order["pt_2_l2"])) / 2
        np.testing.assert_allclose(got["eff_shred"].to_numpy(), expected_shred.to_numpy())
        np.testing.assert_allclose(got["eff_weapon"].to_numpy(), (1 - order["pt_1_l4"]).to_numpy())

    def test_five_point_tier_only(self):
        table = hero_table({(1, 2): {"shred"}, (1, 4): {"weapon"}})
        got = upgrades.effect_features(self.ROWS, levels=(4,), table=table)
        assert (got["eff_shred"] == 0).all()
        assert got.loc[(1, 0), "eff_weapon"] > 0
        assert got.loc[(1, 1), "eff_weapon"] == 0


class TestReroute:
    FAMILIES = pd.DataFrame(
        {"gun": [0.2, 0.5], "spirit": [0.6, 0.3], "tank": [0.2, 0.2]},
        index=pd.MultiIndex.from_tuples([(1, 0), (1, 1)], names=["match_id", "player_slot"]),
    )

    def test_moves_spirit_to_gun_and_keeps_the_sum(self):
        w = pd.Series([0.5, 0.0], index=self.FAMILIES.index)
        out = upgrades.reroute(self.FAMILIES, w)
        assert out.loc[(1, 0), "gun"] == pytest.approx(0.5)
        assert out.loc[(1, 0), "spirit"] == pytest.approx(0.3)
        np.testing.assert_allclose(out.sum(axis=1), 1.0)

    def test_zero_exposure_changes_nothing(self):
        w = pd.Series(0.0, index=self.FAMILIES.index)
        pd.testing.assert_frame_equal(upgrades.reroute(self.FAMILIES, w), self.FAMILIES)
