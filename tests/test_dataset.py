"""Converting match JSON to purchase rows.

Two traps in the objective data give wrong numbers instead of errors, so both
are tested directly: `objectives.team` is the team that lost the objective,
and a `destroyed_time_s` of 0 or 1 means it was never destroyed.

The match dicts are built by hand, so these tests don't need the raw cache.
"""

from __future__ import annotations

import pandas as pd
import pytest

from deadlock import dataset

UPGRADES = frozenset({100, 200, 300})


def _player(slot, team, **extra):
    player = {
        "player_slot": slot,
        "team": team,
        "hero_id": 1,
        "account_id": 1000 + slot,
        "net_worth": 40_000,
        "player_match_outcome": "Win" if team == "Team0" else "Loss",
        "items": [{"item_id": 100, "game_time_s": 300}],
        "stats": [{"time_stamp_s": t, "net_worth": t * 10} for t in (180, 360, 540)],
    }
    player.update(extra)
    return player


def _walker(lane, destroyed_time_s, team):
    """A Walker objective. As in the API, `team` is the team that lost it."""
    return {
        "team_objective": f"Tier2Lane{lane}",
        "destroyed_time_s": destroyed_time_s,
        "team": team,
    }


def _match(objectives=None, mid_boss=None, players=None, **extra):
    match = {
        "match_id": 42,
        "winning_team": "Team0",
        "match_outcome": "TeamWin",
        "average_badge": 61,
        "duration_s": 2400,
        "players": players or [_player(1, "Team0"), _player(7, "Team1")],
    }
    if objectives is not None:
        match["objectives"] = objectives
    if mid_boss is not None:
        match["mid_boss"] = mid_boss
    match.update(extra)
    return match


def _rows_by_team(match):
    rows = dataset.match_to_rows(match, UPGRADES)
    return {row["team"]: row for row in rows}


class TestSlotUnlockTimes:
    def test_first_three_walker_kills_land_on_the_benefiting_team(self):
        # Team1 loses three Walkers, so Team0 unlocks slots 10, 11 and 12.
        match = _match(
            objectives=[
                _walker(2, 1_300, "Team1"),
                _walker(1, 900, "Team1"),
                _walker(3, 1_700, "Team1"),
            ]
        )
        team0 = _rows_by_team(match)["Team0"]
        assert team0["slot10_unlock_s"] == 900
        assert team0["slot11_unlock_s"] == 1_300
        assert team0["slot12_unlock_s"] == 1_700

    def test_the_losing_team_gets_no_slot_from_its_own_walker(self):
        # An objective lost by Team0 unlocks a slot for Team1, not Team0.
        match = _match(objectives=[_walker(1, 900, "Team0")])
        rows = _rows_by_team(match)
        assert rows["Team1"]["slot10_unlock_s"] == 900
        assert rows["Team0"]["slot10_unlock_s"] is None

    def test_every_player_on_the_team_gets_the_same_times(self):
        players = [
            _player(1, "Team0"), _player(2, "Team0"),
            _player(7, "Team1"), _player(8, "Team1"),
        ]
        match = _match(objectives=[_walker(1, 900, "Team1")], players=players)
        rows = dataset.match_to_rows(match, UPGRADES)
        by_slot = {r["player_slot"]: r["slot10_unlock_s"] for r in rows}
        assert by_slot == {1: 900, 2: 900, 7: None, 8: None}

    @pytest.mark.parametrize("sentinel", [0, 1])
    def test_sentinel_destruction_times_are_null_not_zero(self, sentinel):
        # 0 and 1 both mean "never destroyed", not a time.
        match = _match(
            objectives=[_walker(1, sentinel, "Team1"), _walker(2, 1_100, "Team1")]
        )
        team0 = _rows_by_team(match)["Team0"]
        assert team0["slot10_unlock_s"] == 1_100
        assert team0["slot11_unlock_s"] is None

    def test_unreached_slots_are_null_and_the_columns_still_exist(self):
        match = _match(objectives=[_walker(1, 900, "Team1")])
        team0 = _rows_by_team(match)["Team0"]
        assert team0["slot10_unlock_s"] == 900
        assert team0["slot11_unlock_s"] is None
        assert team0["slot12_unlock_s"] is None

    def test_an_unknown_losing_team_credits_nobody(self):
        # `team` can be "Spectator", which must not get the Walkers.
        match = _match(objectives=[_walker(1, 900, "Spectator")])
        rows = _rows_by_team(match)
        assert rows["Team0"]["slot10_unlock_s"] is None
        assert rows["Team1"]["slot10_unlock_s"] is None

    def test_non_walker_objectives_grant_no_slot(self):
        match = _match(
            objectives=[
                {"team_objective": "Tier1Lane1", "destroyed_time_s": 400,
                 "team": "Team1"},
                {"team_objective": "BarrackBossLane2", "destroyed_time_s": 800,
                 "team": "Team1"},
                {"team_objective": "Core", "destroyed_time_s": 2_000,
                 "team": "Team1"},
            ]
        )
        assert _rows_by_team(match)["Team0"]["slot10_unlock_s"] is None


class TestMidBoss:
    def test_first_kill_attaches_to_the_claiming_team(self):
        match = _match(
            mid_boss=[
                {"team_killed": "Team0", "team_claimed": "Team0",
                 "destroyed_time_s": 1_500},
                {"team_killed": "Team0", "team_claimed": "Team0",
                 "destroyed_time_s": 1_100},
            ]
        )
        rows = _rows_by_team(match)
        assert rows["Team0"]["midboss_kill_s"] == 1_100
        assert rows["Team1"]["midboss_kill_s"] is None

    def test_a_stolen_mid_boss_credits_the_claimant(self):
        # team_killed and team_claimed differ in about 13% of kills. The souls
        # go to team_claimed.
        match = _match(
            mid_boss=[{"team_killed": "Team0", "team_claimed": "Team1",
                       "destroyed_time_s": 1_200}]
        )
        rows = _rows_by_team(match)
        assert rows["Team1"]["midboss_kill_s"] == 1_200
        assert rows["Team0"]["midboss_kill_s"] is None

    def test_sentinel_kill_time_is_null(self):
        match = _match(
            mid_boss=[{"team_killed": "Team0", "team_claimed": "Team0",
                       "destroyed_time_s": 0}]
        )
        assert _rows_by_team(match)["Team0"]["midboss_kill_s"] is None


class TestPreChangePages:
    def test_a_match_with_no_objectives_key_converts_to_nulls(self):
        # Pages cached before objectives were requested have neither key.
        rows = dataset.match_to_rows(_match(), UPGRADES)
        assert rows
        for row in rows:
            assert row["slot10_unlock_s"] is None
            assert row["slot11_unlock_s"] is None
            assert row["slot12_unlock_s"] is None
            assert row["midboss_kill_s"] is None

    def test_has_objectives_separates_not_requested_from_never_happened(self):
        # Both cases put null in slot10_unlock_s, but they mean different
        # things. has_objectives tells them apart.
        stale = dataset.match_to_rows(_match(), UPGRADES)[0]
        fresh = dataset.match_to_rows(
            _match(objectives=[_walker(1, 0, "Team1")]), UPGRADES
        )[0]
        assert stale["slot10_unlock_s"] is None
        assert fresh["slot10_unlock_s"] is None
        assert stale[dataset.OBJECTIVES_PRESENT_COLUMN] is False
        assert fresh[dataset.OBJECTIVES_PRESENT_COLUMN] is True

    def test_an_empty_objectives_array_still_counts_as_requested(self):
        rows = dataset.match_to_rows(_match(objectives=[]), UPGRADES)
        assert rows[0][dataset.OBJECTIVES_PRESENT_COLUMN] is True

    def test_existing_columns_are_unchanged(self):
        match = _match(objectives=[_walker(1, 900, "Team1")])
        row = _rows_by_team(match)["Team0"]
        assert row["match_id"] == 42
        assert row["item_id"] == 100
        assert row["buy_time_s"] == 300
        assert row["won"] is True
        assert row["average_badge"] == 61
        assert row["duration_s"] == 2400

    def test_row_count_is_one_per_purchase(self):
        match = _match(objectives=[_walker(1, 900, "Team1")])
        assert len(dataset.match_to_rows(match, UPGRADES)) == 2


class TestIntendedBuild:
    def test_build_and_pregame_hero_pass_through_per_player(self):
        players = [
            _player(1, "Team0", hero_build_id=256_053, pregame_hero_id=6),
            _player(7, "Team1", hero_build_id=126_856, pregame_hero_id=17),
        ]
        rows = _rows_by_team(_match(players=players))
        assert rows["Team0"]["hero_build_id"] == 256_053
        assert rows["Team0"]["pregame_hero_id"] == 6
        assert rows["Team1"]["hero_build_id"] == 126_856

    def test_missing_build_id_is_null_not_zero(self):
        # Most matches are never analyzed. The API sends null or 0 for
        # "unknown", and both become null.
        players = [_player(1, "Team0"), _player(7, "Team1", hero_build_id=0)]
        rows = _rows_by_team(_match(players=players))
        assert rows["Team0"]["hero_build_id"] is None
        assert rows["Team1"]["hero_build_id"] is None

    def test_build_id_beyond_int32_survives(self):
        big = 3_000_000_000
        players = [_player(1, "Team0", hero_build_id=big), _player(7, "Team1")]
        df = dataset.build_purchase_table([_match(players=players)], UPGRADES)
        got = df.loc[df["team"] == "Team0", "hero_build_id"]
        assert got.iloc[0] == big


class TestPurchaseTableDtypes:
    def test_new_columns_are_nullable_integers(self):
        match = _match(
            objectives=[_walker(1, 900, "Team1")],
            players=[_player(1, "Team0", hero_build_id=7, pregame_hero_id=3),
                     _player(7, "Team1")],
        )
        df = dataset.build_purchase_table([match], UPGRADES)
        for column in dataset.OBJECTIVE_COLUMNS + dataset.BUILD_COLUMNS:
            assert df[column].dtype == "Int64", column
        assert df.loc[df["team"] == "Team1", "slot10_unlock_s"].isna().all()

    def test_empty_input_still_carries_the_new_columns(self):
        df = dataset.build_purchase_table([], UPGRADES)
        assert set(dataset.OBJECTIVE_COLUMNS) <= set(df.columns)
        assert set(dataset.BUILD_COLUMNS) <= set(df.columns)


class TestIngestParameters:
    def test_objective_flags_are_requested(self):
        from deadlock import ingest

        assert ingest.BASE_PARAMS["include_objectives"] == "true"
        assert ingest.BASE_PARAMS["include_mid_boss"] == "true"
        assert ingest.BASE_PARAMS["include_player_info"] == "true"
