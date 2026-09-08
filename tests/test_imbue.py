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


class TestTargetsForBuild:
    """What `deadlock build` puts in front of the player.

    A recommendation to buy Mystic Reverb is half an instruction: the item does
    nothing until it is pointed at an ability. `dominant_targets` already knew
    which one; this is the same fact with the names and the evidence attached,
    which is what a player can actually read.
    """

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
        """Most of a build is not imbueable, and saying so for every line is noise."""
        rows = [(0, 3, MYSTIC_REVERB, "active")]
        got = self.targets(rows, [MONSTER_ROUNDS, MYSTIC_REVERB])
        assert [t.item_id for t in got] == [MYSTIC_REVERB]

    def test_an_imbueable_item_the_population_never_imbued_says_so(self):
        """Silence, not a guess.

        Every imbueable purchase carries a target, so a recommended imbueable
        item with no rows means the cell is too thin to speak -- and a build
        that invented an ability there would be worse than one that admits it.
        """
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
        """Item and ability ids both exceed int32; a narrowed id wraps negative."""
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
        """39% is a majority of nothing.

        Ivy's spirit build points Compress Cooldown at Air Drop 39% of the
        time, which is the most common choice and still not what most players
        do. Printing that identically to Wraith's 100% Card Trick would sell a
        coin flip as a rule.
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
        """Dynamo's stomp cluster points Echo Shard somewhere on 4 imbues.

        75% of 4 and 75% of 4,000 print identically otherwise, which is the
        misplaced confidence `THIN_EVIDENCE` exists to prevent everywhere else
        in the tool. Marked rather than hidden: it may still be the right
        ability, and there is nothing else to offer in its place.
        """
        thin = self.targets([(0, 3, MYSTIC_REVERB, "active")] * 4, [MYSTIC_REVERB])[0]
        assert thin.thin and "[thin]" in str(thin)

        solid = self.targets(
            [(0, 3, MYSTIC_REVERB, "active")] * 40, [MYSTIC_REVERB]
        )[0]
        assert not solid.thin and "[thin]" not in str(solid)

    def test_an_absent_target_is_not_called_thin(self):
        """No rows is a different statement from few rows."""
        got = self.targets([], [MYSTIC_REVERB])[0]
        assert not got.thin


class TestOneModeImplementation:
    def test_the_export_and_the_printed_line_agree_on_a_tie(self):
        """Two mode implementations break ties differently.

        The CLI and `generate_builds.py` export the same (hero, archetype)
        build, and a build whose printed imbue target differs from the one in
        its own exported JSON is worse than either answer alone.
        """
        tied = frame(
            [(0, 1, MYSTIC_REVERB, "active"), (1, 3, MYSTIC_REVERB, "active")]
        )
        printed = imbue.targets_for_build(tied, [MYSTIC_REVERB])[0]
        assert imbue.dominant_targets(tied)[MYSTIC_REVERB] == printed.ability_id


class TestConditionalFeatures:
    """Direction only: given the build imbued, which ability did it point at.

    The non-conditional block put `has_imbue` and a depth count in the
    clustering, and heroes split on *whether* a build bought Mystic Reverb
    rather than on what it aimed at. This block carries neither, and it places
    a build that imbued nothing at its hero's mean so it says nothing rather
    than joining every other non-imbuer at the origin.
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
        """Not at zero: zero is a coordinate, and every non-imbuer shares it."""
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
        """No imbuer to average, so there is no mean to place them at."""
        hero_of = self.heroes([0, 1])
        got = imbue.conditional_features(frame([]), hero_of.index, hero_of)
        assert (got == 0.0).all().all()
