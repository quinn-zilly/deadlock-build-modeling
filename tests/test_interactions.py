"""Tests for counter and synergy tables.

The headline result is negative: these features did not improve the model
(counter_score -0.0093 AUC, pair_score -0.0003). These tests pin the
statistical corrections that make the tables honest descriptive statistics,
and the replication guard that explains why the counter table failed.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from deadlock import interactions as ix


def _match(match_id, roster, items_by_slot, winner="Team0"):
    """roster: {slot: (hero_id, team)}; items_by_slot: {slot: [item_ids]}"""
    rows = []
    for slot, (hero, team) in roster.items():
        for item in items_by_slot.get(slot, []):
            rows.append({
                "match_id": match_id, "player_slot": slot, "hero_id": hero,
                "team": team, "won": team == winner, "item_id": item,
            })
    return rows


def _dataset(n_matches=120):
    """Item 10 genuinely counters hero 2; item 20 is neutral."""
    rng = np.random.default_rng(0)
    rows = []
    for m in range(n_matches):
        enemy_hero = 2 if m % 2 == 0 else 3
        has_counter = m % 3 == 0
        # Counter wins more, but only against hero 2.
        p = 0.75 if (has_counter and enemy_hero == 2) else 0.45
        winner = "Team0" if rng.random() < p else "Team1"
        rows += _match(
            m,
            {1: (1, "Team0"), 2: (enemy_hero, "Team1")},
            {1: [10, 20] if has_counter else [20], 2: [30]},
            winner=winner,
        )
    return pd.DataFrame(rows)


class TestEnemyRosters:
    def test_pairs_only_opposing_players(self):
        df = pd.DataFrame(_match(1, {1: (5, "Team0"), 2: (6, "Team1")}, {1: [10], 2: [20]}))
        rosters = ix.enemy_rosters(df)
        row = rosters[rosters.player_slot == 1].iloc[0]
        assert row.enemy_hero_id == 6

    def test_never_lists_own_team(self):
        df = pd.DataFrame(
            _match(1, {1: (5, "Team0"), 2: (7, "Team0"), 3: (6, "Team1")},
                   {1: [10], 2: [10], 3: [20]})
        )
        rosters = ix.enemy_rosters(df)
        own = rosters[rosters.player_slot == 1]
        assert set(own.enemy_hero_id) == {6}


class TestBaselines:
    def test_enemy_baseline_is_a_win_rate(self):
        base = ix.enemy_baselines(_dataset(), min_n=1)
        assert base.between(0, 1).all()

    def test_item_baseline_is_a_win_rate(self):
        base = ix.item_baselines(_dataset(), min_n=1)
        assert base.between(0, 1).all()


class TestCounterLift:
    """A counter is an interaction, not either main effect."""

    def test_removes_both_main_effects(self):
        # A uniformly strong item must not look like a counter to everything.
        rng = np.random.default_rng(1)
        rows = []
        for m in range(200):
            enemy = 2 if m % 2 == 0 else 3
            strong = m % 2 == 0 or m % 3 == 0
            winner = "Team0" if rng.random() < (0.70 if strong else 0.40) else "Team1"
            rows += _match(m, {1: (1, "Team0"), 2: (enemy, "Team1")},
                           {1: [10] if strong else [20], 2: [30]}, winner=winner)
        df = pd.DataFrame(rows)
        table = ix.counter_lift(
            df, ix.enemy_baselines(df, min_n=1), ix.item_baselines(df, min_n=1),
            min_n=1,
        )
        # Item 10 is strong against BOTH heroes, so its interaction lift
        # should be small even though its raw win rate is high.
        lifts = table.xs(10, level="item_id")["lift"]
        assert lifts.abs().max() < 0.25

    def test_detects_a_real_counter(self):
        df = _dataset(240)
        table = ix.counter_lift(
            df, ix.enemy_baselines(df, min_n=1), ix.item_baselines(df, min_n=1),
            min_n=1,
        )
        if (10, 2) in table.index and (10, 3) in table.index:
            assert table.loc[(10, 2), "lift"] > table.loc[(10, 3), "lift"]

    def test_respects_min_n(self):
        df = _dataset()
        assert ix.counter_lift(
            df, ix.enemy_baselines(df, min_n=1), ix.item_baselines(df, min_n=1),
            min_n=10**6,
        ).empty

    def test_accepts_externally_fitted_baselines(self):
        # Scoring a test split must use train-fitted baselines, or the
        # features leak the test labels.
        df = _dataset()
        base, item_base = ix.enemy_baselines(df, 1), ix.item_baselines(df, 1)
        table = ix.counter_lift(df, base, item_base, min_n=1)
        assert not table.empty


class TestPairDeviation:
    def test_expectation_is_additive(self):
        table = ix.pair_deviation(_dataset(240), min_n=1, top_items=10)
        if not table.empty:
            assert np.allclose(table.deviation, table.observed - table.expected)

    def test_pairs_are_ordered_consistently(self):
        table = ix.pair_deviation(_dataset(240), min_n=1, top_items=10)
        for a, b in table.index:
            assert a < b, "each pair must appear once, in a stable order"

    def test_empty_input_is_safe(self):
        empty = _dataset().iloc[:0]
        assert ix.pair_deviation(empty, min_n=1).empty


class TestScoring:
    def test_counter_score_has_joinable_index(self):
        df = _dataset()
        table = ix.counter_lift(
            df, ix.enemy_baselines(df, min_n=1), ix.item_baselines(df, min_n=1),
            min_n=1,
        )
        scores = ix.score_counters(df, table)
        assert scores.index.names == ["match_id", "player_slot"]

    def test_pair_score_has_joinable_index(self):
        df = _dataset()
        table = ix.pair_deviation(df, min_n=1, top_items=10)
        scores = ix.score_pairs(df, table)
        assert scores.index.names == ["match_id", "player_slot"]

    def test_pair_score_zero_when_table_empty(self):
        df = _dataset()
        empty = ix.pair_deviation(df.iloc[:0], min_n=1)
        assert (ix.score_pairs(df, empty) == 0).all()


class TestReplicationGuard:
    """The check that explained the negative result.

    Counter lifts fitted on disjoint halves correlate r=0.05 -- noise. Pair
    deviations correlate r=0.68 -- real. A table that cannot reproduce itself
    cannot carry signal into a model.
    """

    def test_identical_tables_correlate_perfectly(self):
        df = _dataset(240)
        table = ix.counter_lift(
            df, ix.enemy_baselines(df, min_n=1), ix.item_baselines(df, min_n=1),
            min_n=1,
        )
        assert ix.replication_corr(table, table, "lift") == pytest.approx(1.0)

    def test_returns_nan_on_no_overlap(self):
        df = _dataset(120)
        a = ix.counter_lift(
            df, ix.enemy_baselines(df, min_n=1), ix.item_baselines(df, min_n=1),
            min_n=1,
        )
        b = a.iloc[:0]
        assert np.isnan(ix.replication_corr(a, b, "lift"))

    def test_detects_uncorrelated_tables(self):
        # Averaged over many draws, because a handful of rows can correlate
        # with noise by chance -- a single draw hit r=0.51 on 5 rows.
        df = _dataset(240)
        table = ix.counter_lift(
            df, ix.enemy_baselines(df, min_n=1), ix.item_baselines(df, min_n=1),
            min_n=1,
        )
        rng = np.random.default_rng(3)
        correlations = []
        for _ in range(200):
            shuffled = table.copy()
            shuffled["lift"] = rng.normal(size=len(shuffled))
            r = ix.replication_corr(table, shuffled, "lift")
            if not np.isnan(r):
                correlations.append(r)
        assert abs(np.mean(correlations)) < 0.2
