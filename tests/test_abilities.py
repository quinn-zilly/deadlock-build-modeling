"""Reading ability points from the `items` list, and the features built on them.

The most important check: the level comes from `upgrade_info`, not from
counting rows. 7.9% of players are missing a level row, and counting would
give them wrong levels.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from deadlock import abilities, assets

ABILITIES = Path("data/processed/abilities.parquet")

# Two ability ids and one upgrade id, in place of the real asset data.
FIRE = 100
ICE = 200
DASH = 300
ITEM = 900
UPGRADES = frozenset({ITEM})
SLOTS = {FIRE: 1, ICE: 2, DASH: 3}


def entry(item_id: int, t: int, level: int = 1) -> dict:
    """One `items` entry, with the level encoded the way the game does it."""
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
        """The low 16 bits (always 1 in real data) don't affect the level."""
        assert abilities.ability_level((7 << 16) | 9999) == 3

    def test_unknown_encoding_is_zero_not_a_guess(self):
        """An unknown encoding decodes to 0, so a format change is easy to spot."""
        assert abilities.ability_level((5 << 16) | 1) == 0

    def test_zero_is_zero(self):
        assert abilities.ability_level(0) == 0


class TestCleanAbilityPoints:
    def test_keeps_abilities_drops_purchases(self):
        p = player([entry(FIRE, 10), entry(ITEM, 20), entry(ICE, 30)])
        got = abilities.clean_ability_points(p, UPGRADES)
        assert [e["item_id"] for e in got] == [FIRE, ICE]

    def test_sorts_by_time(self):
        """Ability points come back in time order, whatever order the source has."""
        p = player([entry(ICE, 300), entry(FIRE, 10), entry(DASH, 100)])
        got = abilities.clean_ability_points(p, UPGRADES)
        assert [e["game_time_s"] for e in got] == [10, 100, 300]

    def test_is_the_complement_of_clean_purchases(self):
        """Every `items` entry is either a purchase or an ability point, never both or neither."""
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
        """An ability with no signature slot is kept with UNMAPPED_SLOT, not dropped."""
        p = player([entry(FIRE, 10), entry(777, 20)])
        rows = abilities.ability_rows(p, UPGRADES, SLOTS)
        assert len(rows) == 2
        assert rows[1]["signature_slot"] == abilities.UNMAPPED_SLOT

    def test_reads_level_from_upgrade_info(self):
        p = player([entry(FIRE, 10, level=3)])
        assert abilities.ability_rows(p, UPGRADES, SLOTS)[0]["level"] == 3

    def test_does_not_count_rows_for_level(self):
        """Rows at levels 1, 3, and 4 decode as 1, 3, 4, not 1, 2, 3."""
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
        """A slot's level is the highest reached, so out-of-order rows can't lower it."""
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
        """Levels are read mid-match, because at the end Ivy averages 3.6-3.8 on all four."""
        assert abilities.ARCHETYPE_READ_TIME_S == 480.0

    def test_records_first_slot(self):
        rows = table([(0, 3, 1, 10), (0, 1, 1, 50)])
        assert abilities.ability_features(rows)["first_slot"].iloc[0] == 3

    def test_names_all_four_level_columns(self):
        rows = table([(0, 1, 1, 10)])
        got = abilities.ability_features(rows)
        assert all(f"lvl_{i}" in got.columns for i in range(1, 5))

    def test_unmapped_player_survives_as_zeros(self):
        """A player with only unmapped abilities still gets a row of zeros."""
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
        """order_index uses only level 1, when each slot was unlocked."""
        rows = table([(0, 1, 1, 10), (0, 1, 2, 20), (0, 2, 1, 30)])
        got = abilities.order_index(rows)
        assert got["order_1"].iloc[0] == 1
        assert got["order_2"].iloc[0] == 2


class TestPointOrderFeatures:
    """When each slot reached each level, as a fraction of the player's points."""

    def test_position_is_a_fraction_of_the_player_s_points(self):
        rows = table(
            [(0, 1, 1, 10), (0, 1, 2, 20), (0, 2, 1, 30), (0, 2, 2, 40)]
        )
        got = abilities.point_order_features(rows)
        # Four points. Slot 1 reaches level 2 on the second point (index 1), so 1/4.
        assert got["pt_1_l2"].iloc[0] == pytest.approx(0.25)
        assert got["pt_2_l2"].iloc[0] == pytest.approx(0.75)

    def test_a_level_never_reached_reads_one(self):
        """A level never reached gets 1.0, later than any level that was reached."""
        rows = table([(0, 1, 1, 10), (0, 1, 2, 20)])
        got = abilities.point_order_features(rows)
        assert got["pt_1_l4"].iloc[0] == 1.0
        assert got["pt_3_l2"].iloc[0] == 1.0

    def test_a_missing_level_row_does_not_hide_the_level(self):
        """A player recorded at level 1 and then 3 counts as having reached level 2.

        7.9% of players are missing a level row.
        """
        rows = table([(0, 1, 1, 10), (0, 1, 3, 20)])
        got = abilities.point_order_features(rows)
        assert got["pt_1_l2"].iloc[0] < 1.0
        assert got["pt_1_l2"].iloc[0] == got["pt_1_l3"].iloc[0]

    def test_ordered_by_point_not_by_clock(self):
        """Two players with the same order at different speeds get the same features."""
        fast = table([(0, 1, 1, 10), (0, 1, 2, 20), (0, 2, 1, 30)])
        slow = table([(0, 1, 1, 100), (0, 1, 2, 400), (0, 2, 1, 900)])
        assert abilities.point_order_features(fast).values.tolist() == (
            abilities.point_order_features(slow).values.tolist()
        )

    def test_every_player_gets_a_row(self):
        rows = table([(0, 1, 1, 10), (1, 2, 1, 10)])
        assert len(abilities.point_order_features(rows)) == 2

    def test_twelve_columns(self):
        rows = table([(0, 1, 1, 10)])
        got = abilities.point_order_features(rows)
        assert list(got.columns) == [
            f"pt_{slot}_l{level}" for level in (2, 3, 4) for slot in (1, 2, 3, 4)
        ]

    def test_unmapped_slots_are_ignored_but_still_count_as_points(self):
        """An unmapped ability has no column but still counts toward the total points."""
        rows = table([(0, abilities.UNMAPPED_SLOT, 1, 5), (0, 1, 2, 10)])
        got = abilities.point_order_features(rows)
        assert got["pt_1_l2"].iloc[0] == pytest.approx(0.5)

    def test_separates_a_real_hero_the_state_features_could_not(self):
        """On real data, Holliday's gun archetype levels its third slot much earlier.

        This is the evidence that order differs between archetypes where levels
        at 480s didn't. If it stops holding, these features aren't useful.
        """
        if not ABILITIES.exists():
            pytest.skip("requires the processed ability table")
        import json

        meta = json.loads(Path("data/processed/archetype_meta.json").read_text())
        hero_id = next(
            int(h) for h, v in meta["heroes"].items() if v["hero_name"] == "Holliday"
        )
        df = pd.read_parquet(ABILITIES)
        labels = pd.read_parquet("data/processed/archetypes.parquet").set_index(
            ["match_id", "player_slot"]
        )
        features = abilities.point_order_features(df[df.hero_id == hero_id])
        joined = features.join(labels["archetype_id"], how="inner")
        means = joined.groupby("archetype_id")["pt_3_l2"].mean()
        assert means.max() - means.min() > 0.4


class TestResidualPointOrderFeatures:
    """Point order relative to the player's hero, not to all players.

    Rejected as a clustering input (ADR 0003), but kept because the scripts
    behind that decision use it.
    """

    @staticmethod
    def heroed(rows: pd.DataFrame, heroes: dict[int, int]) -> pd.DataFrame:
        """`table` rows with a hero per player slot."""
        return rows.assign(hero_id=rows["player_slot"].map(heroes))

    def test_mean_form_centres_each_hero_on_zero(self):
        rows = self.heroed(
            table([(0, 1, 2, 10), (0, 2, 1, 20), (1, 2, 2, 10), (1, 1, 1, 20)]),
            {0: 7, 1: 7},
        )
        got = abilities.residual_point_order_features(rows, form="mean")
        assert got["pt_1_l2"].mean() == pytest.approx(0.0)

    def test_two_heroes_are_centred_separately(self):
        """Each hero is centered on its own mean, not the mean of all heroes."""
        rows = self.heroed(
            table([(0, 1, 2, 10), (0, 2, 1, 20), (1, 1, 1, 10), (1, 1, 2, 20)]),
            {0: 7, 1: 8},
        )
        got = abilities.residual_point_order_features(rows, form="mean")
        # One player per hero, so each sits exactly on its own hero's mean.
        assert got["pt_1_l2"].abs().max() == pytest.approx(0.0)

    def test_rank_form_is_a_within_hero_percentile_centred_on_zero(self):
        rows = self.heroed(
            table(
                [
                    (0, 1, 2, 10),
                    (0, 2, 1, 20),
                    (1, 1, 1, 10),
                    (1, 2, 1, 20),
                    (1, 1, 2, 30),
                ]
            ),
            {0: 7, 1: 7},
        )
        raw = abilities.point_order_features(rows)
        got = abilities.residual_point_order_features(rows, form="rank")
        # A percentile, so the latest player is at the top and the raw order
        # is kept.
        assert got["pt_1_l2"].max() == pytest.approx(0.5)
        assert got["pt_1_l2"].rank().tolist() == raw["pt_1_l2"].rank().tolist()

    def test_keeps_the_raw_index_and_columns(self):
        rows = self.heroed(table([(0, 1, 2, 10), (1, 2, 1, 10)]), {0: 7, 1: 8})
        raw = abilities.point_order_features(rows)
        got = abilities.residual_point_order_features(rows)
        assert got.index.equals(raw.index)
        assert list(got.columns) == list(raw.columns)

    def test_an_unknown_form_is_refused(self):
        rows = self.heroed(table([(0, 1, 2, 10)]), {0: 7})
        with pytest.raises(ValueError, match="unknown residual form"):
            abilities.residual_point_order_features(rows, form="zscore")


class TestFirstMaxedSlot:
    def test_reports_the_slot_taken_to_four_first(self):
        rows = table(
            [(0, 1, 4, 300), (0, 2, 4, 100), (0, 3, 1, 10)]
        )
        assert abilities.first_maxed_slot(rows).iloc[0] == 2

    def test_a_player_who_maxes_nothing_is_zero(self):
        rows = table([(0, 1, 3, 10)])
        assert abilities.first_maxed_slot(rows).iloc[0] == 0


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
        """No real row decodes to level 0, which would mean an unknown encoding."""
        assert (self.load()["level"] == 0).sum() == 0

    def test_levels_are_in_range(self):
        levels = self.load()["level"]
        assert levels.min() >= 1
        assert levels.max() <= abilities.MAX_ABILITY_LEVEL

    def test_unmapped_slots_are_negligible(self):
        """Only hero 80 (Silver) has unmapped abilities, about 0.015% of rows."""
        df = self.load()
        unmapped = (df["signature_slot"] == abilities.UNMAPPED_SLOT).mean()
        assert unmapped < 0.001

    def test_unmapped_rows_are_one_hero(self):
        df = self.load()
        bad = df[df["signature_slot"] == abilities.UNMAPPED_SLOT]
        assert bad["hero_id"].nunique() == 1

    def test_every_player_levels_abilities(self):
        """The ability table covers over 290,000 players, so almost no one is missing."""
        df = self.load()
        assert df.groupby(["match_id", "player_slot"]).ngroups > 290_000


class TestSamePlayersAsPurchases:
    """Every player in the ability table is in the purchase table (#41)."""

    PURCHASES = Path("data/processed/purchases.parquet")
    KEY = ["match_id", "player_slot"]

    def test_every_leveling_player_is_in_the_purchase_table(self):
        if not ABILITIES.exists() or not self.PURCHASES.exists():
            pytest.skip("requires the ability and purchase tables")
        bought = pd.read_parquet(self.PURCHASES, columns=self.KEY).drop_duplicates()
        leveled = pd.read_parquet(ABILITIES, columns=self.KEY).drop_duplicates()
        missing = leveled.merge(bought, on=self.KEY, how="left", indicator=True)
        assert (missing["_merge"] == "both").all()
