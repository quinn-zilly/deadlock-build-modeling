"""Tests for economic features.

These replace positional item encoding, which measurably hurt the model
(-0.0055 AUC) because buy position is largely a price proxy
(corr(buy_index, cost) = 0.435).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from deadlock import economy
from deadlock.assets import Item

ITEMS = {
    10: Item(10, "cheap", "Cheap", "weapon", 1, 800),
    20: Item(20, "mid", "Mid", "spirit", 2, 1600),
    30: Item(30, "big", "Big", "vitality", 3, 3200),
    40: Item(40, "huge", "Huge", "weapon", 4, 6400),
}


def _frame(rows):
    """rows: (match_id, player_slot, item_id, buy_time_s)"""
    return pd.DataFrame(rows, columns=["match_id", "player_slot", "item_id", "buy_time_s"])


class TestAnnotateCosts:
    def test_attaches_cost_and_tier(self):
        df = _frame([(1, 1, 10, 60), (1, 1, 40, 600)])
        out = economy.annotate_costs(df, ITEMS)
        assert list(out["cost"]) == [800, 6400]
        assert list(out["tier"]) == [1, 4]

    def test_unknown_item_is_nan_not_crash(self):
        df = _frame([(1, 1, 999, 60)])
        out = economy.annotate_costs(df, ITEMS)
        assert pd.isna(out["cost"].iloc[0])


class TestPlayerEconomics:
    def test_basic_totals(self):
        df = economy.annotate_costs(
            _frame([(1, 1, 10, 60), (1, 1, 20, 200), (1, 1, 30, 500)]), ITEMS
        )
        got = economy.player_economics(df)
        assert got["total_spend"] == 800 + 1600 + 3200
        assert got["max_item_cost"] == 3200
        assert got["tier_max"] == 3

    def test_counts_tier_jumps(self):
        df = economy.annotate_costs(
            _frame([(1, 1, 10, 60), (1, 1, 20, 200), (1, 1, 40, 900)]), ITEMS
        )
        assert economy.player_economics(df)["n_tier_jumps"] == 2

    def test_handles_unsorted_input(self):
        # Purchase arrays are not reliably time-ordered in the source data.
        ordered = economy.annotate_costs(
            _frame([(1, 1, 10, 60), (1, 1, 40, 600)]), ITEMS
        )
        shuffled = economy.annotate_costs(
            _frame([(1, 1, 40, 600), (1, 1, 10, 60)]), ITEMS
        )
        assert economy.player_economics(ordered) == economy.player_economics(shuffled)

    def test_single_purchase_is_safe(self):
        df = economy.annotate_costs(_frame([(1, 1, 10, 60)]), ITEMS)
        got = economy.player_economics(df)
        assert got["total_spend"] == 800
        assert got["median_gap_s"] == 0.0
        assert got["cost_slope"] == 0.0

    def test_detects_saving(self):
        # Three quick buys then a long pause before an expensive item.
        df = economy.annotate_costs(
            _frame([
                (1, 1, 10, 60), (1, 1, 10, 120), (1, 1, 10, 180), (1, 1, 40, 900),
            ]),
            ITEMS,
        )
        assert economy.player_economics(df)["n_saved_up"] >= 1

    def test_cost_slope_positive_when_ramping(self):
        df = economy.annotate_costs(
            _frame([(1, 1, 10, 60), (1, 1, 20, 200), (1, 1, 30, 400), (1, 1, 40, 800)]),
            ITEMS,
        )
        assert economy.player_economics(df)["cost_slope"] > 0

    def test_cost_slope_negative_when_descending(self):
        df = economy.annotate_costs(
            _frame([(1, 1, 40, 60), (1, 1, 30, 200), (1, 1, 20, 400), (1, 1, 10, 800)]),
            ITEMS,
        )
        assert economy.player_economics(df)["cost_slope"] < 0


class TestEconomicFeatures:
    def test_one_row_per_player(self):
        df = _frame([(1, 1, 10, 60), (1, 1, 20, 200), (1, 2, 30, 100), (2, 1, 40, 50)])
        out = economy.economic_features(df, ITEMS)
        assert len(out) == 3
        assert set(out.columns) == set(economy.ECONOMIC_COLUMNS)

    def test_matches_per_group_implementation(self):
        # The vectorized path and player_economics() must not drift apart.
        rng = np.random.default_rng(0)
        rows = []
        for player in range(12):
            for k in range(rng.integers(2, 9)):
                rows.append(
                    (1, player, int(rng.choice(list(ITEMS))), int(60 + k * rng.integers(40, 300)))
                )
        df = _frame(rows)
        vectorized = economy.economic_features(df, ITEMS)
        annotated = economy.annotate_costs(df, ITEMS)
        for (match_id, slot), group in annotated.groupby(["match_id", "player_slot"]):
            reference = economy.player_economics(group)
            for key in ["total_spend", "mean_item_cost", "max_item_cost",
                        "tier_mean", "n_tier_jumps", "median_gap_s", "n_saved_up"]:
                assert vectorized.loc[(match_id, slot), key] == pytest.approx(
                    reference[key], rel=1e-6, abs=1e-6
                )

    def test_no_nans(self):
        df = _frame([(1, 1, 10, 60), (1, 2, 999, 100)])  # includes unknown item
        assert not economy.economic_features(df, ITEMS).isna().any().any()


class TestWealthProxySeparation:
    """total_spend correlates 0.78 with net worth on real data.

    A player who spent more souls had more souls, so it carries the same
    problem as nw_final: it is largely an outcome, not a choice. It must not
    enter a model whose lift is measured against the wealth baseline.
    """

    def test_total_spend_is_flagged(self):
        assert "total_spend" in economy.WEALTH_PROXY_COLUMNS

    def test_behavioural_excludes_proxies(self):
        assert not set(economy.BEHAVIOURAL_COLUMNS) & economy.WEALTH_PROXY_COLUMNS

    def test_behavioural_keeps_the_saving_signal(self):
        # The save-vs-buy behaviour is the point of this module.
        for col in ("median_gap_s", "n_saved_up", "saved_up_fraction", "cost_slope"):
            assert col in economy.BEHAVIOURAL_COLUMNS

    def test_behavioural_is_a_strict_subset(self):
        assert set(economy.BEHAVIOURAL_COLUMNS) < set(economy.ECONOMIC_COLUMNS)
