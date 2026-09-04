"""Tests for the player-level design matrix."""

from __future__ import annotations

import numpy as np
import pandas as pd

from deadlock import design

ITEMS = [10, 20, 30]
HEROES = [1, 2]


def _purchases():
    """Two players in one match: slot 1 (Team0, hero 1), slot 2 (Team1, hero 2)."""
    base = dict(
        match_id=1, average_badge=80, duration_s=2000, assigned_lane=1,
        nw_vs_match_median=1.0, nw_vs_team_avg=1.0, nw_rank_in_match=0.5,
        sold=False, sold_time_s=0, buy_time_s=100, buy_index=0,
        account_id=1, nw_at_buy=1000.0,
    )
    rows = [
        {**base, "player_slot": 1, "team": "Team0", "hero_id": 1, "won": True,
         "final_net_worth": 40000, "item_id": 10, "phase": 0, "nw_vs_enemy_avg": 1.2},
        {**base, "player_slot": 1, "team": "Team0", "hero_id": 1, "won": True,
         "final_net_worth": 40000, "item_id": 20, "phase": 2, "nw_vs_enemy_avg": 1.2},
        {**base, "player_slot": 2, "team": "Team1", "hero_id": 2, "won": False,
         "final_net_worth": 30000, "item_id": 30, "phase": 1, "nw_vs_enemy_avg": 0.8},
    ]
    return pd.DataFrame(rows)


class TestPlayerLevel:
    def test_one_row_per_player(self):
        players = design.player_level(_purchases())
        assert len(players) == 2
        assert set(players.player_slot) == {1, 2}

    def test_counts_purchases(self):
        players = design.player_level(_purchases()).set_index("player_slot")
        assert players.loc[1, "n_purchases"] == 2
        assert players.loc[2, "n_purchases"] == 1

    def test_early_wealth_falls_back_when_no_phase0_buys(self):
        # Slot 2 buys only in phase 1, so the early figure must fall back to
        # the match-wide mean rather than becoming NaN.
        players = design.player_level(_purchases()).set_index("player_slot")
        assert players.loc[2, "nw_vs_enemy_avg_early"] == 0.8
        assert not players.nw_vs_enemy_avg_early.isna().any()


class TestItemPhaseMatrix:
    def test_encodes_item_and_phase(self):
        df = _purchases()
        players = design.player_level(df)
        m, names = design.item_phase_matrix(df, players, ITEMS)
        assert m.shape == (2, len(ITEMS) * 4)
        dense = m.toarray()
        slot1 = players.index[players.player_slot == 1][0]
        assert dense[slot1, names.index("item_10_p0")] == 1
        assert dense[slot1, names.index("item_20_p2")] == 1
        assert dense[slot1, names.index("item_20_p0")] == 0

    def test_is_binary(self):
        df = pd.concat([_purchases(), _purchases()])  # duplicate buys
        players = design.player_level(df)
        m, _ = design.item_phase_matrix(df, players, ITEMS)
        assert set(np.unique(m.toarray())) <= {0.0, 1.0}


class TestComposition:
    def test_marks_own_ally_and_enemy(self):
        df = _purchases()
        players = design.player_level(df)
        m, names = design.composition_matrix(players, HEROES)
        dense = m.toarray()
        r = players.index[players.player_slot == 1][0]
        assert dense[r, names.index("hero_1")] == 1
        assert dense[r, names.index("ally_1")] == 1     # own team includes self
        assert dense[r, names.index("enemy_2")] == 1
        assert dense[r, names.index("enemy_1")] == 0


class TestBuildDesign:
    def test_shapes_line_up(self):
        df = _purchases()
        x, y, names, players = design.build_design(df, ITEMS, HEROES)
        assert x.shape[0] == len(y) == len(players)
        assert x.shape[1] == len(names)

    def test_controls_only_excludes_items(self):
        df = _purchases()
        x_full, _, names_full, _ = design.build_design(df, ITEMS, HEROES)
        x_ctl, _, names_ctl, _ = design.build_design(df, ITEMS, HEROES, include_items=False)
        assert not any(n.startswith("item_") for n in names_ctl)
        assert any(n.startswith("item_") for n in names_full)
        # Same rows, so the AUC comparison is like-for-like.
        assert x_full.shape[0] == x_ctl.shape[0]

    def test_labels_match_players(self):
        df = _purchases()
        _, y, _, players = design.build_design(df, ITEMS, HEROES)
        assert list(y) == [int(w) for w in players.won]


class TestMediatorControls:
    """Controls must not absorb the effect being measured.

    Net worth aggregated over the same window as the purchases is a mediator
    of item effects, not merely a confounder: items help a player farm, which
    raises net worth, which predicts winning. Measured on 25k matches,
    including those aggregates drops item lift from +0.0052 to +0.0008.
    """

    def test_default_controls_exclude_window_aggregates(self):
        assert not set(design.CONTROL_COLUMNS) & set(design.MEDIATOR_COLUMNS)

    def test_mediators_are_named(self):
        assert "nw_vs_enemy_avg_mean" in design.MEDIATOR_COLUMNS

    def test_controls_are_pre_decision(self):
        # Every default control must be knowable before the modeled purchases.
        assert set(design.CONTROL_COLUMNS) <= {
            "nw_vs_enemy_avg_early", "average_badge", "assigned_lane",
        }

    def test_player_level_still_exposes_mediators(self):
        # They remain available for description, just not as controls.
        players = design.player_level(_purchases())
        for col in design.MEDIATOR_COLUMNS:
            assert col in players.columns
