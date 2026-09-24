"""The ability-order model.

Two rules differ from items. A slot takes up to four points, so it must not
be masked after the first like an owned item. And a slot at level 4 can't take
another point.
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
    """Players who all level in the same order."""
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
        """Unmapped abilities are dropped, and positions are renumbered without gaps."""
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
        """A slot at level 4 is never recommended again."""
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
        """generate_order raises when it has no timings for the cell.

        Three backoff levels key on the time bucket. With the clock stuck at
        zero, a measured order went wrong at the seventh point with p=0.892,
        so an error is better than a guess.
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
        """A slot that already has points is still recommended.

        With `mask_owned`, the first point in slot 1 would hide slot 1 for the
        rest of the order, and no ability could reach level 4.
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
    """On real players, archetypes of one hero level abilities in different orders."""

    def test_holliday_gun_rushes_crackshot_and_spirit_does_not(self):
        """Holliday's gun archetype maxes Crackshot first and the spirit one doesn't.

        Measured at 38% against 1%. If a refit makes the two orders agree, the
        ability order no longer tells these archetypes apart.
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

        # Match on family_name, not name. Holliday has two spirit archetypes,
        # named apart by what they imbue.
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
        """abilityorder.fit returns the same SequenceModel type as the item model."""
        model = abilityorder.fit(repeated([1, 2, 3, 4] * 4))
        assert isinstance(model, sequence.SequenceModel)


class TestBadgeWeighting:
    """Ability points can be badge-weighted like purchases.

    The abilities table has no badge column, so `attach_badges` copies it from
    the purchase table first.
    """

    def two_brackets(self) -> pd.DataFrame:
        """High-badge players max slot 1 first; low-badge players max slot 2."""
        frames = []
        for badge, first in ((100, 1), (40, 2)):
            order = [first] * 4 + [3, 3, 3, 3]
            frame = repeated(order, n_players=40)
            frame["match_id"] = frame["match_id"] * 10 + (1 if badge == 100 else 2)
            frame["average_badge"] = badge
            frames.append(frame)
        return pd.concat(frames, ignore_index=True)

    def test_point_frame_carries_the_badge_when_it_is_there(self):
        frame = abilityorder.point_frame(self.two_brackets())
        assert "average_badge" in frame
        assert set(frame["average_badge"].unique()) == {100, 40}

    def test_point_frame_omits_the_badge_when_it_is_not(self):
        frame = abilityorder.point_frame(points([(0, 1, 1, 10)]))
        assert "average_badge" not in frame

    def test_target_badge_shifts_the_first_point(self):
        df = self.two_brackets()
        state = GameState(hero_id=7, game_time_s=0.0, souls_available=10**9)

        def first(model):
            ids, probability = model.distribution(state)
            return int(ids[probability.argmax()])

        assert first(abilityorder.fit(df, target_badge=100.0, badge_halfwidth=20.0)) == 1
        assert first(abilityorder.fit(df, target_badge=40.0, badge_halfwidth=20.0)) == 2

    def test_attach_badges_carries_the_match_badge_across(self):
        abilities_df = points([(0, 1, 1, 10)])
        purchases = pd.DataFrame(
            [{"match_id": 1, "player_slot": 0, "average_badge": 91}]
        )
        joined = abilityorder.attach_badges(abilities_df, purchases)
        assert joined["average_badge"].tolist() == [91]

    def test_attach_badges_leaves_unmatched_rows_unweighted(self):
        """Rows with no matching purchase get a null badge, not 0.

        `row_weights` gives a null badge weight 1. A badge of 0 would get
        almost no weight.
        """
        abilities_df = points([(0, 1, 1, 10)])
        purchases = pd.DataFrame(
            [{"match_id": 999, "player_slot": 0, "average_badge": 91}]
        )
        joined = abilityorder.attach_badges(abilities_df, purchases)
        assert joined["average_badge"].isna().all()


class TestTimingsFollowTheBracket:
    """With a badge, ability timings come from that badge's players too.

    Three backoff levels key on the time bucket, so timings from all players
    would give a strong player's build the average player's pace.
    """

    @staticmethod
    def frame_with_two_paces() -> pd.DataFrame:
        """High-badge players spend a point a minute; low-badge players, one every five."""
        rows = []
        for badge, step in ((100, 60), (40, 300)):
            for player in range(40):
                for position in range(4):
                    rows.append(
                        {
                            "match_id": player * 10 + (1 if badge == 100 else 2),
                            "player_slot": 0,
                            "hero_id": 7,
                            "item_id": 1,
                            "buy_index": position,
                            "buy_time_s": step * (position + 1),
                            "average_badge": badge,
                        }
                    )
        return pd.DataFrame(rows)

    def test_the_population_median_is_the_default(self):
        timings = abilityorder.median_timings(self.frame_with_two_paces(), 7, 0)
        assert timings[0] == pytest.approx(180.0)

    def test_a_bracket_gets_its_own_pace(self):
        fast = abilityorder.median_timings(
            self.frame_with_two_paces(), 7, 0, target_badge=100.0, badge_halfwidth=20.0
        )
        slow = abilityorder.median_timings(
            self.frame_with_two_paces(), 7, 0, target_badge=40.0, badge_halfwidth=20.0
        )
        assert fast[0] == pytest.approx(60.0)
        assert slow[0] == pytest.approx(300.0)

    def test_a_frame_without_a_badge_column_still_answers(self):
        """Without a badge column, median_timings returns plain medians instead of raising."""
        frame = self.frame_with_two_paces().drop(columns=["average_badge"])
        timings = abilityorder.median_timings(frame, 7, 0, target_badge=100.0)
        assert timings[0] == pytest.approx(180.0)

    def test_generate_order_dates_its_points_by_the_bracket(self):
        """generate_order uses the timings of the badge it was given."""
        order = [1, 1, 2, 3, 1, 2, 4, 1, 2, 2, 3, 3, 3, 4, 4, 4]
        frames = []
        for badge, step in ((100, 30), (40, 240)):
            frame = repeated(order, n_players=40)
            frame["match_id"] = frame["match_id"] * 10 + (1 if badge == 100 else 2)
            frame["game_time_s"] = frame.groupby(
                ["match_id", "player_slot"]
            ).cumcount() * step
            frame["average_badge"] = badge
            frames.append(frame)
        df = pd.concat(frames, ignore_index=True)
        points = abilityorder.point_frame(df)
        model = abilityorder.fit(df)

        fast = abilityorder.generate_order(model, points, 7, 0, target_badge=100.0,
                                           badge_halfwidth=20.0)
        slow = abilityorder.generate_order(model, points, 7, 0, target_badge=40.0,
                                           badge_halfwidth=20.0)
        assert fast[-1].game_time_s < slow[-1].game_time_s
