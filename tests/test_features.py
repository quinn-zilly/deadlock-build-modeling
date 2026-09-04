"""Regression tests for the three source-data defects.

Each test encodes a defect measured on live API data (2026-09-03). If any of
these fail, the wealth controls downstream are silently wrong.
"""

from __future__ import annotations

import numpy as np
import pytest

from deadlock import features

UPGRADES = frozenset({100, 200, 300})


def _player(items, stats, net_worth=50_000, slot=1, team="Team0"):
    return {
        "player_slot": slot,
        "team": team,
        "net_worth": net_worth,
        "items": items,
        "stats": [{"time_stamp_s": t, "net_worth": nw} for t, nw in stats],
    }


class TestAbilityFiltering:
    """Defect 1: ~46% of `items` entries are ability points, not purchases."""

    def test_drops_non_upgrade_ids(self):
        player = _player(
            items=[
                {"item_id": 100, "game_time_s": 60},
                {"item_id": 999, "game_time_s": 70},   # ability point
                {"item_id": 200, "game_time_s": 80},
                {"item_id": 12345, "game_time_s": 90},  # ability point
            ],
            stats=[(180, 2000)],
        )
        got = features.clean_purchases(player, UPGRADES)
        assert [i["item_id"] for i in got] == [100, 200]

    def test_empty_items_is_safe(self):
        assert features.clean_purchases(_player([], [(180, 100)]), UPGRADES) == []

    def test_missing_items_key_is_safe(self):
        assert features.clean_purchases({"stats": []}, UPGRADES) == []


class TestPurchaseOrdering:
    """Defect 2: 11.5% of players have items not sorted by game_time_s."""

    def test_sorts_unordered_array(self):
        player = _player(
            items=[
                {"item_id": 300, "game_time_s": 900},
                {"item_id": 100, "game_time_s": 60},
                {"item_id": 200, "game_time_s": 400},
            ],
            stats=[(180, 2000)],
        )
        got = features.clean_purchases(player, UPGRADES)
        times = [i["game_time_s"] for i in got]
        assert times == sorted(times)
        assert [i["item_id"] for i in got] == [100, 200, 300]


class TestNetWorthReconstruction:
    """Defect 3: net_worth_at_buy is corrupt; reconstruct from the series."""

    def test_never_reads_corrupt_field(self):
        # net_worth_at_buy carries the final net worth on an early buy, the
        # exact corruption seen in 9% of live records. It must be ignored.
        player = _player(
            items=[{"item_id": 100, "game_time_s": 23, "net_worth_at_buy": 19_982}],
            stats=[(180, 1732), (360, 3623)],
            net_worth=19_982,
        )
        got = features.networth_at(player, np.array([23.0]))
        assert got[0] < 1000, "must not echo the corrupt final net worth"

    def test_origin_anchor_prevents_flat_extrapolation(self):
        # 8.8% of purchases precede the first 180s snapshot. Without a (0,0)
        # anchor np.interp would return 1732 for a 13-second purchase.
        player = _player(items=[], stats=[(180, 1732), (360, 3623)])
        got = features.networth_at(player, np.array([13.0]))
        assert got[0] == pytest.approx(1732 * 13 / 180, rel=0.01)
        assert got[0] < 200

    def test_anchor_present_in_series(self):
        times, worths = features.networth_series(_player([], [(180, 1732)]))
        assert times[0] == 0.0 and worths[0] == 0.0

    def test_sorts_unordered_snapshots(self):
        times, _ = features.networth_series(_player([], [(360, 3623), (180, 1732)]))
        assert list(times) == sorted(times)

    def test_interpolates_between_snapshots(self):
        player = _player([], [(180, 1000), (360, 2000)])
        assert features.networth_at(player, np.array([270.0]))[0] == pytest.approx(1500)

    def test_empty_query_returns_empty(self):
        got = features.networth_at(_player([], [(180, 1000)]), np.array([]))
        assert got.size == 0

    def test_monotone_nondecreasing_output(self):
        player = _player([], [(180, 1000), (360, 2000), (540, 2500)])
        got = features.networth_at(player, np.array([0.0, 90.0, 270.0, 450.0, 600.0]))
        assert np.all(np.diff(got) >= 0)


class TestPhase:
    def test_phase_boundaries(self):
        assert list(features.phase_of(np.array([0, 599, 600, 1799, 2400, 9999]))) == [
            0, 0, 1, 2, 3, 3
        ]


class TestWithinMatchPosition:
    """The more reliable wealth measure: same-snapshot, so bias cancels."""

    def test_ratios_and_rank(self):
        match = {
            "players": [
                _player([], [(180, 1000)], slot=1, team="Team0"),
                _player([], [(180, 3000)], slot=2, team="Team0"),
                _player([], [(180, 2000)], slot=3, team="Team1"),
                _player([], [(180, 2000)], slot=4, team="Team1"),
            ]
        }
        pos = features.within_match_position(match, 180.0)
        assert set(pos) == {1, 2, 3, 4}
        # slot 2 is richest -> above median, ahead of its own team average
        assert pos[2]["nw_vs_match_median"] > 1.0
        assert pos[2]["nw_vs_team_avg"] > 1.0
        assert pos[1]["nw_vs_match_median"] < 1.0
        assert pos[2]["nw_rank_in_match"] > pos[1]["nw_rank_in_match"]

    def test_empty_match_is_safe(self):
        assert features.within_match_position({"players": []}, 180.0) == {}


class TestPlayerWon:
    """The metadata endpoint has no per-player `won` field.

    Only the SQL table carries one. Reading `player.get("won")` returns None
    for every metadata row, which silently becomes a 0% win rate and destroys
    the label. Resolve from player_match_outcome, falling back to the team.
    """

    def test_reads_player_match_outcome(self):
        match = {"winning_team": "Team0", "match_outcome": "TeamWin"}
        assert features.player_won({"player_match_outcome": "Win"}, match) is True
        assert features.player_won({"player_match_outcome": "Loss"}, match) is False

    def test_falls_back_to_team_comparison(self):
        match = {"winning_team": "Team1", "match_outcome": "TeamWin"}
        assert features.player_won({"team": "Team1"}, match) is True
        assert features.player_won({"team": "Team0"}, match) is False

    def test_outcome_takes_precedence_over_team(self):
        match = {"winning_team": "Team0", "match_outcome": "TeamWin"}
        player = {"player_match_outcome": "Loss", "team": "Team0"}
        assert features.player_won(player, match) is False

    @pytest.mark.parametrize("outcome", ["Invalid", "NotScored"])
    def test_unusable_outcomes_return_none(self, outcome):
        match = {"winning_team": "Team0", "match_outcome": "TeamWin"}
        assert features.player_won({"player_match_outcome": outcome}, match) is None

    def test_draw_is_not_a_label(self):
        match = {"winning_team": "Team0", "match_outcome": "Draw"}
        assert features.player_won({"team": "Team0"}, match) is None

    def test_missing_everything_returns_none(self):
        assert features.player_won({}, {}) is None

    def test_never_silently_false(self):
        # The original bug: absent data must not read as a loss.
        assert features.player_won({}, {"winning_team": "Team0"}) is not False
