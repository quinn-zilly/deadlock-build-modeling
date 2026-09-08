"""Ability order: the sequence half of a build.

The load-bearing rules here are the two that differ from the item path. A slot
takes four points, so the ownership mask that protects items would be wrong.
And a slot at level 4 is illegal, which is the only hard constraint an ability
order has.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from deadlock import abilities, abilityorder, sequence
from deadlock.state import GameState

ABILITIES = Path("data/processed/abilities.parquet")


def points(rows: list[tuple[int, int, int, int]], hero_id: int = 7) -> pd.DataFrame:
    """Rows of (player, signature_slot, level, game_time_s)."""
    return pd.DataFrame(
        [
            {
                "match_id": 1,
                "player_slot": player,
                "hero_id": hero_id,
                "ability_id": 100 + slot,
                "signature_slot": slot,
                "level": level,
                "game_time_s": time,
            }
            for player, slot, level, time in rows
        ]
    )


def repeated(order: list[int], n_players: int = 40, hero_id: int = 7) -> pd.DataFrame:
    """A population that always levels in the same order."""
    rows = []
    for player in range(n_players):
        levels = {slot: 0 for slot in range(1, 5)}
        for position, slot in enumerate(order):
            levels[slot] += 1
            rows.append((player, slot, levels[slot], position * 60))
    frame = points(rows, hero_id=hero_id)
    frame["match_id"] = frame["player_slot"] + 1
    frame["player_slot"] = 0
    return frame


class TestPointFrame:
    def test_shapes_abilities_like_purchases(self):
        frame = abilityorder.point_frame(points([(0, 1, 1, 10), (0, 2, 1, 20)]))
        assert set(frame.columns) == {
            "match_id", "player_slot", "hero_id", "item_id", "buy_index", "buy_time_s"
        }

    def test_outcome_is_the_signature_slot(self):
        frame = abilityorder.point_frame(points([(0, 3, 1, 10)]))
        assert frame["item_id"].iloc[0] == 3

    def test_positions_are_chronological(self):
        frame = abilityorder.point_frame(points([(0, 2, 1, 90), (0, 1, 1, 10)]))
        assert frame.sort_values("buy_index")["item_id"].tolist() == [1, 2]

    def test_unmapped_abilities_are_dropped_and_positions_stay_contiguous(self):
        """A slot the assets cannot name is not advice, so it is not modelled."""
        frame = abilityorder.point_frame(
            points([(0, abilities.UNMAPPED_SLOT, 1, 5), (0, 1, 1, 10), (0, 2, 1, 20)])
        )
        assert frame["buy_index"].tolist() == [0, 1]
        assert abilities.UNMAPPED_SLOT not in frame["item_id"].tolist()


class TestGenerateOrder:
    def test_recovers_the_order_a_population_always_takes(self):
        order = [1, 1, 2, 3, 1, 2, 4, 1, 2, 2, 3, 3, 3, 4, 4, 4]
        population = repeated(order)
        model = abilityorder.fit(population)
        got = abilityorder.generate_order(
            model, abilityorder.point_frame(population), 7, 0
        )
        assert [point.slot for point in got] == order

    def test_a_slot_stops_at_level_four(self):
        """The only hard constraint. A fifth point in one slot is not a build."""
        population = repeated([1] * 4 + [2, 3, 4] * 4)
        model = abilityorder.fit(population)
        got = abilityorder.generate_order(
            model, abilityorder.point_frame(population), 7, 0
        )
        counts = pd.Series([point.slot for point in got]).value_counts()
        assert counts.max() <= abilityorder.MAX_LEVEL

    def test_levels_climb_by_one(self):
        population = repeated([1, 2, 1, 2, 1, 2, 1, 2])
        model = abilityorder.fit(population)
        got = abilityorder.generate_order(
            model, abilityorder.point_frame(population), 7, 0
        )
        seen: dict[int, int] = {}
        for point in got:
            seen[point.slot] = seen.get(point.slot, 0) + 1
            assert point.level == seen[point.slot]

    def test_never_exceeds_sixteen_points(self):
        population = repeated([1, 2, 3, 4] * 4)
        model = abilityorder.fit(population)
        frame = abilityorder.point_frame(population)
        assert len(abilityorder.generate_order(model, frame, 7, 0, n_points=99)) <= 16

    def test_carries_evidence_for_every_point(self):
        population = repeated([1, 2, 3, 4] * 4)
        model = abilityorder.fit(population)
        for point in abilityorder.generate_order(
            model, abilityorder.point_frame(population), 7, 0
        ):
            assert point.n > 0
            assert point.backoff_level.startswith("L")

    def test_timings_come_from_the_population(self):
        population = repeated([1, 2, 3, 4] * 4)
        model = abilityorder.fit(population)
        got = abilityorder.generate_order(
            model, abilityorder.point_frame(population), 7, 0,
            timings={0: 30.0, 1: 120.0},
        )
        assert got[0].game_time_s == 30.0
        assert got[1].game_time_s == 120.0


    def test_a_cell_with_no_timings_raises(self):
        """Silence would be a confident wrong answer, so it fails loudly.

        Three of the six levels key on `time_bucket`. A roll-forward with a
        frozen clock asks every one of them for the first five minutes of the
        match: measured, that diverged at the seventh point and reported
        p=0.892 for the wrong slot. A miss is recoverable, a confident wrong
        answer is not.
        """
        population = repeated([1, 2, 3, 4] * 4)
        model = abilityorder.fit(population)
        frame = abilityorder.point_frame(population)
        with pytest.raises(ValueError, match="timings"):
            abilityorder.generate_order(model, frame, hero_id=999, archetype_id=0)


class TestRecommend:
    def test_a_maxed_slot_is_not_offered(self):
        model = abilityorder.fit(repeated([1, 2, 3, 4] * 4))
        state = GameState(hero_id=7, game_time_s=0.0, souls_available=0,
                          archetype_posterior={0: 1.0})
        ranked = abilityorder.recommend(model, state, levels={1: 4})
        assert all(point.slot != 1 for point in ranked)

    def test_a_repeated_slot_is_still_offered(self):
        """Unlike items, a slot is taken four times -- masking it would be wrong.

        This is the bug the item path's `mask_owned` would introduce here: the
        first point into slot 1 would make every later point into slot 1
        invisible, and no hero could ever max an ability.
        """
        model = abilityorder.fit(repeated([1, 1, 1, 1, 2, 3, 4] + [2, 3, 4] * 3))
        state = GameState(hero_id=7, game_time_s=60.0, souls_available=0,
                          purchased=(1,), owned_item_ids=frozenset({1}),
                          archetype_posterior={0: 1.0})
        assert any(point.slot == 1 for point in abilityorder.recommend(model, state))


class TestFormatOrder:
    def test_reports_the_max_order_first(self):
        population = repeated([1] * 4 + [2] * 4 + [3] * 4 + [4] * 4)
        model = abilityorder.fit(population)
        text = abilityorder.format_order(
            abilityorder.generate_order(
                model, abilityorder.point_frame(population), 7, 0
            )
        )
        assert text.splitlines()[0].startswith("max order:")

    def test_empty_order_says_so(self):
        assert "no ability order" in abilityorder.format_order([])


class TestAgainstRealData:
    """The claim the ability reversal rests on, pinned on real players."""

    def test_holliday_gun_rushes_crackshot_and_spirit_does_not(self):
        """Measured: the gun archetype maxes Crackshot 38% against 1%.

        If a refit ever makes these two orders agree, the ability features have
        stopped separating the archetypes they were added to separate.
        """
        if not ABILITIES.exists():
            pytest.skip("requires the processed ability table")
        import json

        from deadlock import assets

        meta = json.loads(Path("data/processed/archetype_meta.json").read_text())
        hero_id = next(
            int(h) for h, v in meta["heroes"].items() if v["hero_name"] == "Holliday"
        )
        crackshot = next(
            slot
            for slot, ability in assets.hero_signatures()[hero_id].items()
            if ability.name == "Crackshot"
        )
        df = pd.read_parquet(ABILITIES)
        labels = pd.read_parquet("data/processed/archetypes.parquet")
        model = abilityorder.fit(df[df.hero_id == hero_id], labels)

        # Keyed on the family half of the name, not the shipped name: two of
        # Holliday's clusters are spirit builds and are told apart by what they
        # imbue, so "the spirit one" is not a single archetype any more.
        families = {
            entry["archetype_id"]: entry["family_name"]
            for entry in meta["heroes"][str(hero_id)]["archetypes"]
        }
        gun = next(a for a, n in families.items() if n.startswith("Gun"))
        spirits = [a for a, n in families.items() if n.startswith("Spirit")]
        assert spirits

        frame = abilityorder.point_frame(df[df.hero_id == hero_id]).merge(
            labels[["match_id", "player_slot", "archetype_id"]],
            on=["match_id", "player_slot"],
            how="left",
        )

        def position_of_second_point(archetype: int) -> int:
            order = abilityorder.generate_order(model, frame, hero_id, archetype)
            return next(
                point.position
                for point in order
                if point.slot == crackshot and point.level == 2
            )

        assert all(
            position_of_second_point(gun) < position_of_second_point(spirit)
            for spirit in spirits
        )

    def test_the_model_is_a_sequence_model_not_a_new_one(self):
        """Reuse is the design: no second model to keep in step with the first."""
        model = abilityorder.fit(repeated([1, 2, 3, 4] * 4))
        assert isinstance(model, sequence.SequenceModel)
