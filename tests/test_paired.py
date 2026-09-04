"""Tests for the within-lane paired design.

Deadlock lanes are 2v2, not 1v1: three lanes (1, 4, 6) with two players per
team in each. The original plan assumed duels; validating that assumption
found zero 1v1 lanes in 74,997, so the unit here is a lane SIDE.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from deadlock import paired


def _lane(match_id, lane, slots_teams, items=None):
    """slots_teams: {slot: (team, won)}"""
    items = items or {}
    rows = []
    for slot, (team, won) in slots_teams.items():
        for item in items.get(slot, [10]):
            rows.append({
                "match_id": match_id, "player_slot": slot, "assigned_lane": lane,
                "team": team, "won": won, "hero_id": slot, "item_id": item,
            })
    return rows


def _clean_lane(match_id=1, lane=1, winner="Team0", items=None):
    return _lane(
        match_id, lane,
        {1: ("Team0", winner == "Team0"), 2: ("Team0", winner == "Team0"),
         3: ("Team1", winner == "Team1"), 4: ("Team1", winner == "Team1")},
        items,
    )


class TestLaneSides:
    def test_keeps_clean_2v2(self):
        df = pd.DataFrame(_clean_lane())
        assert len(paired.lane_sides(df)) == 4

    def test_drops_unbalanced_lane(self):
        # Three players in a lane: an abandon or malformed record.
        df = pd.DataFrame(
            _lane(1, 1, {1: ("Team0", True), 2: ("Team0", True), 3: ("Team1", False)})
        )
        assert paired.lane_sides(df).empty

    def test_drops_one_sided_lane(self):
        df = pd.DataFrame(
            _lane(1, 1, {1: ("Team0", True), 2: ("Team0", True),
                         3: ("Team0", True), 4: ("Team0", True)})
        )
        assert paired.lane_sides(df).empty

    def test_rejects_invalid_lane_id(self):
        df = pd.DataFrame(_clean_lane(lane=99))
        assert paired.lane_sides(df).empty

    def test_accepts_all_real_lanes(self):
        for lane in paired.VALID_LANES:
            assert not paired.lane_sides(pd.DataFrame(_clean_lane(lane=lane))).empty


class TestSideFeatures:
    def test_sums_across_the_two_players(self):
        df = pd.DataFrame(_clean_lane())
        features = pd.DataFrame(
            {"x": [1.0, 2.0, 10.0, 20.0]},
            index=pd.MultiIndex.from_tuples(
                [(1, 1), (1, 2), (1, 3), (1, 4)], names=["match_id", "player_slot"]
            ),
        )
        sides = paired.side_features(df, ["x"], features)
        assert len(sides) == 2
        assert sorted(sides["x"]) == [3.0, 30.0]

    def test_carries_the_outcome(self):
        df = pd.DataFrame(_clean_lane(winner="Team1"))
        features = pd.DataFrame(
            {"x": [0.0] * 4},
            index=pd.MultiIndex.from_tuples(
                [(1, 1), (1, 2), (1, 3), (1, 4)], names=["match_id", "player_slot"]
            ),
        )
        sides = paired.side_features(df, ["x"], features)
        assert sides.set_index("team").loc["Team1", "won"]
        assert not sides.set_index("team").loc["Team0", "won"]


def _sides_frame(n=200, seed=0):
    """Lanes where Team0's win is independent of match_id parity.

    An earlier version tied the winner to a per-match random draw taken in
    match order, which happened to march in lockstep with the A-side
    randomizer's own draws and produced an all-False label. Drawing the winner
    from a separate generator keeps the two independent.
    """
    rng = np.random.default_rng(seed)
    winner_rng = np.random.default_rng(seed + 991)
    rows = []
    for m in range(n):
        strong = rng.random()
        team0_won = bool(winner_rng.random() < 0.5)
        rows.append({"match_id": m, "lane": 1, "team": "Team0",
                     "x": strong, "won": team0_won})
        rows.append({"match_id": m, "lane": 1, "team": "Team1",
                     "x": 1 - strong, "won": not team0_won})
    return pd.DataFrame(rows)


class TestDifferenceLanes:
    def test_one_row_per_lane(self):
        sides = _sides_frame(50)
        assert len(paired.difference_lanes(sides, ["x"])) == 50

    def test_label_is_balanced(self):
        # Randomized A-side assignment; always taking Team0 would bake in
        # whatever side advantage the game has.
        out = paired.difference_lanes(_sides_frame(4000), ["x"])
        assert 0.45 < out["a_won"].mean() < 0.55

    def test_records_which_team_is_a(self):
        out = paired.difference_lanes(_sides_frame(20), ["x"])
        assert "a_team" in out.columns
        assert set(out["a_team"]) <= {"Team0", "Team1"}

    def test_difference_is_antisymmetric(self):
        # A lane's difference must equal minus the difference of its mirror.
        sides = _sides_frame(200)
        out = paired.difference_lanes(sides, ["x"], seed=1)
        for _, row in out.head(20).iterrows():
            lane = sides[sides.match_id == row.match_id]
            a = lane[lane.team == row.a_team]["x"].iloc[0]
            b = lane[lane.team != row.a_team]["x"].iloc[0]
            assert row.d_x == pytest.approx(a - b)

    def test_label_matches_a_side(self):
        sides = _sides_frame(200)
        out = paired.difference_lanes(sides, ["x"], seed=2)
        for _, row in out.head(20).iterrows():
            lane = sides[sides.match_id == row.match_id]
            assert row.a_won == bool(lane[lane.team == row.a_team]["won"].iloc[0])

    def test_seed_is_deterministic(self):
        sides = _sides_frame(100)
        a = paired.difference_lanes(sides, ["x"], seed=5)
        b = paired.difference_lanes(sides, ["x"], seed=5)
        pd.testing.assert_frame_equal(a, b)


class TestItemDifferenceMatrix:
    def test_shared_items_cancel(self):
        # Both sides buy item 10 equally -> zero, so it cannot explain the
        # result. This cancellation is the whole point of the design.
        df = pd.DataFrame(_clean_lane(items={1: [10], 2: [10], 3: [10], 4: [10]}))
        features = pd.DataFrame(
            {"x": [0.0] * 4},
            index=pd.MultiIndex.from_tuples(
                [(1, 1), (1, 2), (1, 3), (1, 4)], names=["match_id", "player_slot"]
            ),
        )
        sides = paired.side_features(df, ["x"], features)
        pairs = paired.difference_lanes(sides, ["x"])
        matrix, _ = paired.item_difference_matrix(df, pairs, [10, 20])
        assert matrix[0, 0] == 0.0

    def test_exclusive_item_shows_up_signed(self):
        df = pd.DataFrame(_clean_lane(items={1: [20], 2: [10], 3: [10], 4: [10]}))
        features = pd.DataFrame(
            {"x": [0.0] * 4},
            index=pd.MultiIndex.from_tuples(
                [(1, 1), (1, 2), (1, 3), (1, 4)], names=["match_id", "player_slot"]
            ),
        )
        sides = paired.side_features(df, ["x"], features)
        pairs = paired.difference_lanes(sides, ["x"])
        matrix, names = paired.item_difference_matrix(df, pairs, [10, 20])
        col = names.index("d_item_20")
        # Team0 holds item 20; sign depends on which side drew "A".
        expected = 1.0 if pairs.iloc[0]["a_team"] == "Team0" else -1.0
        assert matrix[0, col] == expected

    def test_shape_matches_pairs(self):
        df = pd.DataFrame(_clean_lane() + _clean_lane(match_id=2))
        idx = pd.MultiIndex.from_tuples(
            [(m, s) for m in (1, 2) for s in (1, 2, 3, 4)],
            names=["match_id", "player_slot"],
        )
        features = pd.DataFrame({"x": [0.0] * 8}, index=idx)
        sides = paired.side_features(df, ["x"], features)
        pairs = paired.difference_lanes(sides, ["x"])
        matrix, names = paired.item_difference_matrix(df, pairs, [10, 20, 30])
        assert matrix.shape == (len(pairs), 3)
        assert len(names) == 3
