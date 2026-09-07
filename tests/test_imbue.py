"""Imbue: which ability an imbueable item is pointed at.

The claim the feature design rests on is that a target is **never missing** --
the game makes the player choose at the counter. So a player with no imbue
features is a player who bought no imbueable item, which the item features
already record. Imputing anything there would invent a statement.
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
    """(item_id, imbued_ability_id) pairs as an `items` array."""
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
        """9 in practice: 11 shopable, of which 2 are tier 5 and never bought."""
        items = assets.shopable_items()
        imbueable = imbue.imbueable_items()
        assert len(imbueable) == 11
        assert sum(1 for i in imbueable if items[i].tier < 5) == 9

    def test_every_type_maps_to_a_group(self):
        for kind in imbue.imbueable_items().values():
            assert kind in imbue.TYPE_GROUP

    def test_echo_shard_is_an_active_imbue_that_cannot_target_the_ult(self):
        """The restriction is itself a signal about what the build wants."""
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
        """If targets ever stop being universal, it must show as absence.

        A zero target on an imbueable item would mean the game recorded a
        choice that was never made. Emitting slot 0 would bury that in the
        features; emitting nothing makes the coverage check catch it.
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
        """Direction and commitment are different facts.

        Dynamo's ult cluster imbues Singularity 1.78 times per player against
        0.77 for its stomp cluster. Shares alone read those as identical.
        """
        one = imbue.imbue_features(frame([(0, 1, MYSTIC_REVERB, "active")]))
        many = imbue.imbue_features(
            frame([(0, 1, MYSTIC_REVERB, "active")] * 4)
        )
        assert many["imb_depth"].iloc[0] > one["imb_depth"].iloc[0]
        assert one["imb_active_1"].iloc[0] == many["imb_active_1"].iloc[0]

    def test_a_player_who_imbued_nothing_is_zeros_and_flagged(self):
        """Not a hero mean: they made no statement, and the flag says so."""
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
        """The claim the whole encoding rests on, checked on real data.

        If this fails, `has_imbue` has stopped meaning "bought no imbueable
        item" and the all-zeros encoding is wrong.
        """
        if not IMBUES.exists():
            pytest.skip("requires the imbue table")
        df = pd.read_parquet(IMBUES, columns=["imbued_ability_id", "signature_slot"])
        assert (df["imbued_ability_id"] > 0).all()
        assert (df["signature_slot"] >= 1).mean() > 0.99

    def test_ids_survive_the_round_trip(self):
        """73 of 173 item ids exceed int32 and wrap silently if stored narrower."""
        if not IMBUES.exists():
            pytest.skip("requires the imbue table")
        df = pd.read_parquet(IMBUES, columns=["item_id", "imbued_ability_id"])
        assert (df["item_id"] > 0).all()
        assert (df["imbued_ability_id"] > 0).all()
        assert set(df["item_id"].unique()) <= set(imbue.imbueable_items())
