"""Imbues: which ability each imbueable item is aimed at.

The game makes players pick a target when they buy, so a target is never
missing. A player with no imbue rows simply bought no imbueable item.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from deadlock import assets, imbue

IMBUES = Path("data/processed/imbues.parquet")

MYSTIC_REVERB = 3577481646      # imbue_active
DURATION_EXTENDER = 2951612397  # imbue_modifier_value
ECHO_SHARD = 630839635          # imbue_active_non_ult
MONSTER_ROUNDS = 1414319208     # not imbueable

SLOTS = {901: 1, 902: 2, 903: 3, 904: 4}
IMBUEABLE = {
    MYSTIC_REVERB: "imbue_active",
    DURATION_EXTENDER: "imbue_modifier_value",
    ECHO_SHARD: "imbue_active_non_ult",
}


def player(entries: list[tuple[int, int]]) -> dict:
    """A player whose `items` list holds the given (item_id, imbued_ability_id) pairs."""
    return {
        "items": [
            {"item_id": item, "imbued_ability_id": target, "game_time_s": 100 * i}
            for i, (item, target) in enumerate(entries)
        ]
    }


def frame(rows: list[tuple[int, int, int, str]]) -> pd.DataFrame:
    """(player_slot, signature_slot, item_id, imbue_group) rows."""
    return pd.DataFrame(
        [
            {
                "match_id": 1,
                "player_slot": slot,
                "hero_id": 11,
                "item_id": item,
                "imbued_ability_id": 900 + signature,
                "signature_slot": signature,
                "imbue_group": group,
                "game_time_s": 100,
            }
            for slot, signature, item, group in rows
        ]
    )


class TestImbueableItems:
    def test_only_a_handful_of_items_can_be_imbued(self):
        """11 shop items are imbueable, and 2 of those are tier 5, which nobody buys."""
        items = assets.shopable_items()
        imbueable = imbue.imbueable_items()
        assert len(imbueable) == 11
        assert sum(1 for i in imbueable if items[i].tier < 5) == 9

    def test_every_type_maps_to_a_group(self):
        for kind in imbue.imbueable_items().values():
            assert kind in imbue.TYPE_GROUP

    def test_echo_shard_is_an_active_imbue_that_cannot_target_the_ult(self):
        """Echo Shard is imbue_active_non_ult and groups as active."""
        assert imbue.imbueable_items()[ECHO_SHARD] == "imbue_active_non_ult"
        assert imbue.TYPE_GROUP["imbue_active_non_ult"] == imbue.ACTIVE


class TestImbueRows:
    def test_reads_the_target_and_its_slot(self):
        rows = imbue.imbue_rows(player([(MYSTIC_REVERB, 903)]), IMBUEABLE, SLOTS)
        assert rows[0]["imbued_ability_id"] == 903
        assert rows[0]["signature_slot"] == 3

    def test_ignores_items_that_cannot_be_imbued(self):
        rows = imbue.imbue_rows(player([(MONSTER_ROUNDS, 901)]), IMBUEABLE, SLOTS)
        assert rows == []

    def test_a_missing_target_produces_no_row_rather_than_slot_zero(self):
        """An imbueable purchase with target 0 gives no row, not a row with slot 0.

        That way build_imbues.py's coverage check notices if targets ever go
        missing.
        """
        rows = imbue.imbue_rows(player([(MYSTIC_REVERB, 0)]), IMBUEABLE, SLOTS)
        assert rows == []

    def test_groups_active_and_modifier_separately(self):
        rows = imbue.imbue_rows(
            player([(MYSTIC_REVERB, 901), (DURATION_EXTENDER, 901)]), IMBUEABLE, SLOTS
        )
        assert {r["imbue_group"] for r in rows} == {imbue.ACTIVE, imbue.MODIFIER}


class TestImbueFeatures:
    def test_shares_sum_to_one_within_a_group(self):
        got = imbue.imbue_features(
            frame([(0, 1, MYSTIC_REVERB, "active"), (0, 3, MYSTIC_REVERB, "active")])
        )
        actives = [got[f"imb_active_{slot}"].iloc[0] for slot in range(1, 5)]
        assert sum(actives) == pytest.approx(1.0)
        assert actives[0] == pytest.approx(0.5)
        assert actives[2] == pytest.approx(0.5)

    def test_active_and_modifier_do_not_mix(self):
        got = imbue.imbue_features(
            frame([(0, 1, MYSTIC_REVERB, "active"), (0, 2, DURATION_EXTENDER, "modifier")])
        )
        assert got["imb_active_1"].iloc[0] == pytest.approx(1.0)
        assert got["imb_mod_2"].iloc[0] == pytest.approx(1.0)
        assert got["imb_active_2"].iloc[0] == 0.0

    def test_depth_separates_one_imbue_from_four(self):
        """imb_depth tells one imbue from four, which the shares can't.

        Dynamo's ult cluster imbues Singularity 1.78 times per player, against
        0.77 for its stomp cluster.
        """
        one = imbue.imbue_features(frame([(0, 1, MYSTIC_REVERB, "active")]))
        many = imbue.imbue_features(
            frame([(0, 1, MYSTIC_REVERB, "active")] * 4)
        )
        assert many["imb_depth"].iloc[0] > one["imb_depth"].iloc[0]
        assert one["imb_active_1"].iloc[0] == many["imb_active_1"].iloc[0]

    def test_a_player_who_imbued_nothing_is_zeros_and_flagged(self):
        """A player with no imbues gets all zeros and has_imbue 0."""
        index = pd.MultiIndex.from_tuples([(1, 0)], names=["match_id", "player_slot"])
        got = imbue.imbue_features(frame([]), players=index)
        assert got["has_imbue"].iloc[0] == 0.0
        assert got["imb_depth"].iloc[0] == 0.0
        assert (got.drop(columns=["has_imbue", "imb_depth"]).iloc[0] == 0.0).all()

    def test_non_imbuers_still_get_a_row(self):
        index = pd.MultiIndex.from_tuples(
            [(1, 0), (1, 1)], names=["match_id", "player_slot"]
        )
        got = imbue.imbue_features(frame([(0, 1, MYSTIC_REVERB, "active")]), players=index)
        assert len(got) == 2
        assert got["has_imbue"].tolist() == [1.0, 0.0]

    def test_ten_columns(self):
        got = imbue.imbue_features(frame([(0, 1, MYSTIC_REVERB, "active")]))
        assert len(got.columns) == 10


class TestDominantTargets:
    def test_reports_the_ability_a_population_picks_most(self):
        rows = frame(
            [(0, 1, MYSTIC_REVERB, "active")] * 3 + [(1, 4, MYSTIC_REVERB, "active")]
        )
        assert imbue.dominant_targets(rows)[MYSTIC_REVERB] == 901

    def test_empty_population_has_no_targets(self):
        assert imbue.dominant_targets(frame([])) == {}


class TestAgainstRealData:
    def test_every_imbueable_purchase_carries_a_target(self):
        """On real data, every imbueable purchase has a target.

        If this fails, a player with no imbues might still have bought an
        imbueable item, and the imbue code's assumption is wrong.
        """
        if not IMBUES.exists():
            pytest.skip("requires the imbue table")
        df = pd.read_parquet(IMBUES, columns=["imbued_ability_id", "signature_slot"])
        assert (df["imbued_ability_id"] > 0).all()
        assert (df["signature_slot"] >= 1).mean() > 0.99

    def test_ids_survive_the_round_trip(self):
        """Ids stay int64. 73 of 173 item ids would wrap negative as int32."""
        if not IMBUES.exists():
            pytest.skip("requires the imbue table")
        df = pd.read_parquet(IMBUES, columns=["item_id", "imbued_ability_id"])
        assert (df["item_id"] > 0).all()
        assert (df["imbued_ability_id"] > 0).all()
        assert set(df["item_id"].unique()) <= set(imbue.imbueable_items())


class TestTargetsForBuild:
    """`targets_for_build`: the imbue lines `deadlock build` prints, with names and counts."""

    ITEM_NAMES = {MYSTIC_REVERB: "Mystic Reverb", DURATION_EXTENDER: "Duration Extender",
                  MONSTER_ROUNDS: "Monster Rounds"}
    ABILITY_NAMES = {901: "Kinetic Pulse", 903: "Singularity"}

    def targets(self, rows, item_ids):
        return imbue.targets_for_build(
            frame(rows),
            item_ids,
            item_names=self.ITEM_NAMES,
            ability_names=self.ABILITY_NAMES,
            imbueable=IMBUEABLE,
        )

    def test_names_the_ability_with_the_evidence_behind_it(self):
        rows = [(0, 3, MYSTIC_REVERB, "active")] * 3 + [(1, 1, MYSTIC_REVERB, "active")]
        got = self.targets(rows, [MYSTIC_REVERB])
        assert len(got) == 1
        assert got[0].ability_id == 903
        assert got[0].ability_name == "Singularity"
        assert got[0].n == 4
        assert got[0].share == pytest.approx(0.75)
        assert "Singularity" in str(got[0])

    def test_items_that_cannot_be_imbued_are_absent(self):
        """Items that can't be imbued get no line."""
        rows = [(0, 3, MYSTIC_REVERB, "active")]
        got = self.targets(rows, [MONSTER_ROUNDS, MYSTIC_REVERB])
        assert [t.item_id for t in got] == [MYSTIC_REVERB]

    def test_an_imbueable_item_the_population_never_imbued_says_so(self):
        """An imbueable item nobody in the cell bought gets ability None, not a guess."""
        got = self.targets([(0, 3, MYSTIC_REVERB, "active")], [DURATION_EXTENDER])
        assert [t.item_id for t in got] == [DURATION_EXTENDER]
        assert got[0].ability_id is None
        assert got[0].n == 0
        assert "no imbue" in str(got[0])

    def test_order_follows_the_build(self):
        rows = [(0, 3, MYSTIC_REVERB, "active"), (0, 1, DURATION_EXTENDER, "modifier")]
        got = self.targets(rows, [DURATION_EXTENDER, MYSTIC_REVERB])
        assert [t.item_id for t in got] == [DURATION_EXTENDER, MYSTIC_REVERB]

    def test_a_repeated_item_is_reported_once(self):
        rows = [(0, 3, MYSTIC_REVERB, "active")]
        got = self.targets(rows, [MYSTIC_REVERB, MYSTIC_REVERB])
        assert len(got) == 1

    def test_an_empty_population_leaves_every_target_unknown(self):
        got = self.targets([], [MYSTIC_REVERB])
        assert got[0].ability_id is None

    def test_ability_ids_stay_wide(self):
        """Ability ids come back unchanged. Some don't fit in int32."""
        wide = 3577481646
        rows = pd.DataFrame(
            [{"match_id": 1, "player_slot": 0, "item_id": MYSTIC_REVERB,
              "imbued_ability_id": wide, "signature_slot": 2,
              "imbue_group": "active", "game_time_s": 100}]
        )
        got = imbue.targets_for_build(
            rows, [MYSTIC_REVERB], item_names=self.ITEM_NAMES,
            ability_names={}, imbueable=IMBUEABLE
        )
        assert got[0].ability_id == wide

    def test_a_split_population_is_marked_rather_than_stated_flatly(self):
        """A most-common target under 50% is marked [split].

        Ivy's spirit build aims Compress Cooldown at Air Drop 39% of the time.
        That shouldn't print the same as Wraith's 100% Card Trick.
        """
        rows = (
            [(0, 3, MYSTIC_REVERB, "active")] * 2
            + [(1, 1, MYSTIC_REVERB, "active")] * 2
            + [(2, 4, MYSTIC_REVERB, "active")]
        )
        split = self.targets(rows, [MYSTIC_REVERB])[0]
        assert split.split and "[split]" in str(split)

        agreed = self.targets([(0, 3, MYSTIC_REVERB, "active")] * 5, [MYSTIC_REVERB])[0]
        assert not agreed.split and "[split]" not in str(agreed)

    def test_a_target_from_four_imbues_is_marked_thin(self):
        """A target from only 4 imbues is marked [thin], but still shown.

        Dynamo's stomp cluster has only 4 Echo Shard imbues. Otherwise 75% of 4
        would print the same as 75% of 4,000.
        """
        thin = self.targets([(0, 3, MYSTIC_REVERB, "active")] * 4, [MYSTIC_REVERB])[0]
        assert thin.thin and "[thin]" in str(thin)

        solid = self.targets(
            [(0, 3, MYSTIC_REVERB, "active")] * 40, [MYSTIC_REVERB]
        )[0]
        assert not solid.thin and "[thin]" not in str(solid)

    def test_an_absent_target_is_not_called_thin(self):
        """A target with no data is not marked thin. No rows and few rows are different."""
        got = self.targets([], [MYSTIC_REVERB])[0]
        assert not got.thin


class TestOneModeImplementation:
    def test_the_export_and_the_printed_line_agree_on_a_tie(self):
        """On a tie, the exported target and the printed target are the same ability.

        The CLI and `generate_builds.py` must not export different targets for
        the same build.
        """
        tied = frame(
            [(0, 1, MYSTIC_REVERB, "active"), (1, 3, MYSTIC_REVERB, "active")]
        )
        printed = imbue.targets_for_build(tied, [MYSTIC_REVERB])[0]
        assert imbue.dominant_targets(tied)[MYSTIC_REVERB] == printed.ability_id


class TestConditionalFeatures:
    """`conditional_features`: target shares only, with non-imbuers at their hero's mean.

    Leaves out `has_imbue` and `imb_depth`, which made heroes split on whether
    a player bought an imbueable item.
    """

    def heroes(self, slots: list[int], hero_id: int = 11) -> pd.Series:
        index = pd.MultiIndex.from_tuples(
            [(1, s) for s in slots], names=["match_id", "player_slot"]
        )
        return pd.Series(hero_id, index=index)

    def test_carries_direction_and_nothing_about_ownership(self):
        hero_of = self.heroes([0])
        got = imbue.conditional_features(
            frame([(0, 1, MYSTIC_REVERB, "active")]), hero_of.index, hero_of
        )
        assert "has_imbue" not in got.columns
        assert not [c for c in got.columns if c.startswith("imb_depth")]
        assert len(got.columns) == 8
        assert got["imb_active_1"].iloc[0] == pytest.approx(1.0)

    def test_a_build_that_imbued_nothing_sits_at_its_heros_mean(self):
        """A player who imbued nothing gets the hero's mean shares, not zeros."""
        hero_of = self.heroes([0, 1, 2])
        got = imbue.conditional_features(
            frame(
                [
                    (0, 1, MYSTIC_REVERB, "active"),
                    (1, 3, MYSTIC_REVERB, "active"),
                ]
            ),
            hero_of.index,
            hero_of,
        )
        silent = got.loc[(1, 2)]
        assert silent["imb_active_1"] == pytest.approx(0.5)
        assert silent["imb_active_3"] == pytest.approx(0.5)

    def test_the_mean_is_the_heros_own_not_the_populations(self):
        first = self.heroes([0, 1], hero_id=11)
        second = self.heroes([2, 3], hero_id=12)
        hero_of = pd.concat([first, second])
        got = imbue.conditional_features(
            frame(
                [
                    (0, 1, MYSTIC_REVERB, "active"),
                    (2, 4, MYSTIC_REVERB, "active"),
                ]
            ),
            hero_of.index,
            hero_of,
        )
        assert got.loc[(1, 1), "imb_active_1"] == pytest.approx(1.0)
        assert got.loc[(1, 3), "imb_active_4"] == pytest.approx(1.0)
        assert got.loc[(1, 3), "imb_active_1"] == pytest.approx(0.0)

    def test_a_hero_nobody_imbued_stays_at_zero(self):
        """If no player of a hero imbued, there's no mean, so they stay at zero."""
        hero_of = self.heroes([0, 1])
        got = imbue.conditional_features(frame([]), hero_of.index, hero_of)
        assert (got == 0.0).all().all()


class TestDirectionGate:
    """`item_direction` and `gated_heroes`: which heroes' players disagree on where an item goes.

    Direction is measured per item. Two items that each go to a fixed but
    different slot are two constants, not a contested choice.
    """

    def heroes(self, n: int, hero_id: int = 11) -> pd.Series:
        index = pd.MultiIndex.from_tuples(
            [(1, s) for s in range(n)], names=["match_id", "player_slot"]
        )
        return pd.Series(hero_id, index=index)

    def test_a_fifty_fifty_item_carries_one_bit(self):
        got = imbue.item_direction(
            frame([(0, 1, MYSTIC_REVERB, "active"), (1, 2, MYSTIC_REVERB, "active")]),
            self.heroes(2),
        )
        row = got.iloc[0]
        assert row["entropy"] == pytest.approx(1.0)
        assert row["top_share"] == pytest.approx(0.5)
        assert row["buy_rate"] == pytest.approx(1.0)

    def test_two_fixed_items_are_not_contested(self):
        """Pooled over items this would be one bit. Per item it is zero."""
        got = imbue.item_direction(
            frame([(0, 1, MYSTIC_REVERB, "active"), (1, 2, DURATION_EXTENDER, "modifier")]),
            self.heroes(2),
        )
        assert (got["entropy"] == 0.0).all()

    def test_buy_rate_counts_players_not_purchases(self):
        got = imbue.item_direction(
            frame([(0, 1, MYSTIC_REVERB, "active"), (0, 1, MYSTIC_REVERB, "active")]),
            self.heroes(4),
        )
        assert got.iloc[0]["buyers"] == 1
        assert got.iloc[0]["buy_rate"] == pytest.approx(0.25)

    def test_a_contested_item_gates_its_hero_in(self):
        rows = [(s, 1 + s % 2, MYSTIC_REVERB, "active") for s in range(10)]
        got = imbue.gated_heroes(frame(rows), self.heroes(10), min_purchases=5)
        assert got == {11}

    def test_a_constant_item_leaves_its_hero_out(self):
        rows = [(s, 1, MYSTIC_REVERB, "active") for s in range(10)]
        assert imbue.gated_heroes(frame(rows), self.heroes(10), min_purchases=5) == set()

    def test_a_hero_most_players_do_not_imbue_is_left_out(self):
        """Below MIN_GATE_IMBUE_RATE the mean-imputed rows are the majority."""
        rows = [(s, 1 + s % 2, MYSTIC_REVERB, "active") for s in range(10)]
        got = imbue.gated_heroes(frame(rows), self.heroes(30), min_purchases=5, min_buy_rate=0.0)
        assert got == set()


PURCHASES = Path("data/processed/purchases.parquet")
PLAYER_KEY = ["match_id", "player_slot"]


@pytest.fixture(scope="module")
def players():
    """(purchase players, imbuing players), one row per (match, slot)."""
    if not IMBUES.exists() or not PURCHASES.exists():
        pytest.skip("requires the imbue and purchase tables")
    bought = pd.read_parquet(PURCHASES, columns=[*PLAYER_KEY, "hero_id"])
    imbued = pd.read_parquet(IMBUES, columns=[*PLAYER_KEY, "hero_id"])
    return bought.drop_duplicates(PLAYER_KEY), imbued.drop_duplicates(PLAYER_KEY)


class TestSamePlayersAsPurchases:
    """Every player in the imbue table is in the purchase table.

    The imbue table once kept abandon and draw players that the purchase table
    dropped, which put Wraith, Warden, and Mina's imbue rates above 1.0 (#41).
    """

    def test_every_imbuing_player_is_in_the_purchase_table(self, players):
        bought, imbued = players
        missing = imbued.merge(bought[PLAYER_KEY], on=PLAYER_KEY, how="left", indicator=True)
        assert (missing["_merge"] == "both").all()

    def test_no_hero_imbues_more_players_than_it_has(self, players):
        bought, imbued = players
        rate = imbued.groupby("hero_id").size() / bought.groupby("hero_id").size()
        assert (rate.dropna() <= 1.0).all()
