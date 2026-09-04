"""Ability leveling recovery, and the defects it has to survive.

The load-bearing one: level comes from `upgrade_info`, never from a running
count. 7.9% of players have a missing level row, so counting would mis-level
every one of them silently.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from deadlock import abilities, assets

ABILITIES = Path("data/processed/abilities.parquet")

# Two ability ids and one upgrade id, standing in for the asset join.
FIRE = 100
ICE = 200
DASH = 300
ITEM = 900
UPGRADES = frozenset({ITEM})
SLOTS = {FIRE: 1, ICE: 2, DASH: 3}


def entry(item_id: int, t: int, level: int = 1) -> dict:
    """One `items` array entry, with the level encoded as the game does."""
    bits = {1: 1, 2: 3, 3: 7, 4: 15}[level]
    return {"item_id": item_id, "game_time_s": t, "upgrade_info": (bits << 16) | 1}


def player(entries: list[dict]) -> dict:
    return {"items": entries}


def table(rows: list[tuple[int, int, int, int]]) -> pd.DataFrame:
    """Rows of (player_slot, signature_slot, level, game_time_s)."""
    return pd.DataFrame(
        [
            {
                "match_id": 1,
                "player_slot": p,
                "signature_slot": s,
                "level": lvl,
                "game_time_s": t,
            }
            for p, s, lvl, t in rows
        ]
    )


class TestAbilityLevel:
    @pytest.mark.parametrize("bits,expected", [(1, 1), (3, 2), (7, 3), (15, 4)])
    def test_decodes_the_four_levels(self, bits, expected):
        assert abilities.ability_level((bits << 16) | 1) == expected

    def test_ignores_the_low_word(self):
        """The low word is always 1 and carries nothing."""
        assert abilities.ability_level((7 << 16) | 9999) == 3

    def test_unknown_encoding_is_zero_not_a_guess(self):
        """A patch changing the format must show as zeros, not plausible levels."""
        assert abilities.ability_level((5 << 16) | 1) == 0

    def test_zero_is_zero(self):
        assert abilities.ability_level(0) == 0


class TestCleanAbilityPoints:
    def test_keeps_abilities_drops_purchases(self):
        p = player([entry(FIRE, 10), entry(ITEM, 20), entry(ICE, 30)])
        got = abilities.clean_ability_points(p, UPGRADES)
        assert [e["item_id"] for e in got] == [FIRE, ICE]

    def test_sorts_by_time(self):
        """Source arrays are not reliably ordered."""
        p = player([entry(ICE, 300), entry(FIRE, 10), entry(DASH, 100)])
        got = abilities.clean_ability_points(p, UPGRADES)
        assert [e["game_time_s"] for e in got] == [10, 100, 300]

    def test_is_the_complement_of_clean_purchases(self):
        """Together the two paths must partition the array, leaving nothing."""
        from deadlock import features

        entries = [entry(FIRE, 10), entry(ITEM, 20), entry(ICE, 30), entry(ITEM, 40)]
        p = player(entries)
        n_abilities = len(abilities.clean_ability_points(p, UPGRADES))
        n_purchases = len(features.clean_purchases(p, UPGRADES))
        assert n_abilities + n_purchases == len(entries)

    def test_missing_items_key_is_safe(self):
        assert abilities.clean_ability_points({}, UPGRADES) == []

    def test_none_items_is_safe(self):
        assert abilities.clean_ability_points({"items": None}, UPGRADES) == []


class TestAbilityRows:
    def test_maps_signature_slots(self):
        p = player([entry(FIRE, 10), entry(ICE, 20)])
        rows = abilities.ability_rows(p, UPGRADES, SLOTS)
        assert [r["signature_slot"] for r in rows] == [1, 2]

    def test_unmapped_ability_is_flagged_not_dropped(self):
        """Hero 80's abilities have no signature entry; counts must reconcile."""
        p = player([entry(FIRE, 10), entry(777, 20)])
        rows = abilities.ability_rows(p, UPGRADES, SLOTS)
        assert len(rows) == 2
        assert rows[1]["signature_slot"] == abilities.UNMAPPED_SLOT

    def test_reads_level_from_upgrade_info(self):
        p = player([entry(FIRE, 10, level=3)])
        assert abilities.ability_rows(p, UPGRADES, SLOTS)[0]["level"] == 3

    def test_does_not_count_rows_for_level(self):
        """The defect this guards: a player missing level 2 must not read as 1,2,3.

        Three rows at levels 1, 3 and 4 must decode as 1, 3, 4 -- a running
        count would report 1, 2, 3 and be wrong for 7.9% of players.
        """
        p = player([entry(FIRE, 10, 1), entry(FIRE, 20, 3), entry(FIRE, 30, 4)])
        rows = abilities.ability_rows(p, UPGRADES, SLOTS)
        assert [r["level"] for r in rows] == [1, 3, 4]


class TestAbilityStateAt:
    def test_reads_state_at_an_instant(self):
        rows = table([(0, 1, 1, 10), (0, 1, 2, 100), (0, 2, 1, 200)])
        assert abilities.ability_state_at(rows, 150) == {1: 2, 2: 0, 3: 0, 4: 0}

    def test_includes_the_boundary(self):
        rows = table([(0, 1, 1, 480)])
        assert abilities.ability_state_at(rows, 480)[1] == 1

    def test_before_any_spend_is_all_zero(self):
        rows = table([(0, 1, 1, 600)])
        assert abilities.ability_state_at(rows, 60) == {1: 0, 2: 0, 3: 0, 4: 0}

    def test_takes_max_not_last(self):
        """Out-of-order rows must not make state go backwards."""
        rows = table([(0, 1, 3, 100), (0, 1, 1, 90)])
        assert abilities.ability_state_at(rows, 200)[1] == 3

    def test_always_names_all_four_slots(self):
        assert set(abilities.ability_state_at(table([]), 100)) == {1, 2, 3, 4}


class TestAbilityFeatures:
    def test_one_row_per_player(self):
        rows = table([(0, 1, 1, 10), (0, 2, 1, 20), (1, 1, 1, 30)])
        assert len(abilities.ability_features(rows)) == 2

    def test_reads_at_the_given_time(self):
        rows = table([(0, 1, 1, 100), (0, 1, 4, 900)])
        early = abilities.ability_features(rows, at_time=480.0)
        assert early["lvl_1"].iloc[0] == 1

    def test_default_read_time_is_mid_match(self):
        """Final levels saturate -- Ivy averages 3.6-3.8 on all four."""
        assert abilities.ARCHETYPE_READ_TIME_S == 480.0

    def test_records_first_slot(self):
        rows = table([(0, 3, 1, 10), (0, 1, 1, 50)])
        assert abilities.ability_features(rows)["first_slot"].iloc[0] == 3

    def test_names_all_four_level_columns(self):
        rows = table([(0, 1, 1, 10)])
        got = abilities.ability_features(rows)
        assert all(f"lvl_{i}" in got.columns for i in range(1, 5))

    def test_unmapped_player_survives_as_zeros(self):
        """Dropping them would silently shrink the join."""
        rows = table([(0, abilities.UNMAPPED_SLOT, 1, 10)])
        got = abilities.ability_features(rows)
        assert len(got) == 1
        assert got["lvl_1"].iloc[0] == 0


class TestOrderIndex:
    def test_ranks_by_first_investment(self):
        rows = table([(0, 2, 1, 10), (0, 1, 1, 50), (0, 3, 1, 90)])
        got = abilities.order_index(rows)
        assert got["order_2"].iloc[0] == 1
        assert got["order_1"].iloc[0] == 2

    def test_unleveled_slot_is_zero(self):
        rows = table([(0, 1, 1, 10)])
        assert abilities.order_index(rows)["order_4"].iloc[0] == 0

    def test_ignores_higher_levels(self):
        """Order is about when a slot was first touched."""
        rows = table([(0, 1, 1, 10), (0, 1, 2, 20), (0, 2, 1, 30)])
        got = abilities.order_index(rows)
        assert got["order_1"].iloc[0] == 1
        assert got["order_2"].iloc[0] == 2


class TestReconcile:
    def test_exact_partition_passes(self):
        ok, message = abilities.reconcile(100, 90, 190)
        assert ok
        assert "exact" in message

    def test_mismatch_fails_and_reports_the_gap(self):
        ok, message = abilities.reconcile(100, 90, 195)
        assert not ok
        assert "-5" in message


class TestAssetLoaders:
    def test_abilities_load(self):
        assert len(assets.load_abilities()) == 389

    def test_signature_slots_cover_four_per_hero(self):
        counts = {}
        for slot in assets.signature_slots().values():
            counts[slot] = counts.get(slot, 0) + 1
        assert set(counts) == {1, 2, 3, 4}

    def test_shopable_is_a_subset_of_items(self):
        assert set(assets.shopable_items()) <= set(assets.load_items())

    def test_shopable_count(self):
        assert len(assets.shopable_items()) == 173

    def test_component_map_resolves_to_ids(self):
        components = assets.component_map()
        items = assets.load_items()
        assert all(c in items for parts in components.values() for c in parts)

    def test_component_map_size(self):
        assert len(assets.component_map()) == 65


@pytest.mark.data
@pytest.mark.skipif(not ABILITIES.exists(), reason="needs abilities.parquet")
class TestAgainstRealData:
    @staticmethod
    def load() -> pd.DataFrame:
        return pd.read_parquet(ABILITIES)

    def test_every_level_decoded(self):
        """A level of 0 means an encoding this code does not understand."""
        assert (self.load()["level"] == 0).sum() == 0

    def test_levels_are_in_range(self):
        levels = self.load()["level"]
        assert levels.min() >= 1
        assert levels.max() <= abilities.MAX_ABILITY_LEVEL

    def test_unmapped_slots_are_negligible(self):
        """Only hero 80 (Silver) should be unmapped, at ~0.015%."""
        df = self.load()
        unmapped = (df["signature_slot"] == abilities.UNMAPPED_SLOT).mean()
        assert unmapped < 0.001

    def test_unmapped_rows_are_one_hero(self):
        df = self.load()
        bad = df[df["signature_slot"] == abilities.UNMAPPED_SLOT]
        assert bad["hero_id"].nunique() == 1

    def test_every_player_levels_abilities(self):
        """Zero players had no ability spends when this was measured."""
        df = self.load()
        assert df.groupby(["match_id", "player_slot"]).ngroups > 290_000
