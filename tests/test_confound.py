"""Tests for the wealth-baseline gate and stratified adjustment."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from deadlock import confound


def _frame(n=600, seed=0):
    """Synthetic purchases where wealth drives winning, as in the real data."""
    rng = np.random.default_rng(seed)
    n_matches = n // 12
    match_id = np.repeat(np.arange(1000, 1000 + n_matches), 12)[:n]
    nw = rng.uniform(1000, 40000, n)
    # Win probability rises with wealth -- the confound we must detect.
    won = rng.random(n) < (0.2 + 0.6 * (nw / 40000))
    return pd.DataFrame(
        {
            "match_id": match_id,
            "won": won,
            "item_id": rng.choice([10, 20, 30], n),
            "nw_at_buy": nw,
            "nw_vs_match_median": nw / np.median(nw),
            "nw_vs_team_avg": rng.normal(1, 0.1, n),
            "nw_vs_enemy_avg": nw / np.median(nw),
            "nw_rank_in_match": rng.random(n),
            "average_badge": rng.integers(40, 100, n),
            "duration_s": rng.integers(1200, 3000, n),
            "buy_time_s": rng.integers(30, 3000, n),
            "phase": rng.integers(0, 4, n),
            "nw_quintile": rng.integers(0, 5, n),
        }
    )


class TestSplits:
    def test_match_split_shares_no_matches(self):
        df = _frame()
        train, test = confound.split_by_match(df, test_frac=0.25)
        assert not set(train.match_id) & set(test.match_id)
        assert len(train) + len(test) == len(df)

    def test_match_split_keeps_players_together(self):
        # Every row of a match must land on the same side, or the shared
        # outcome leaks across the split.
        df = _frame()
        train, test = confound.split_by_match(df)
        for part in (train, test):
            for mid, grp in part.groupby("match_id"):
                assert len(grp) == (df.match_id == mid).sum()

    def test_time_split_is_ordered(self):
        df = _frame()
        train, test = confound.split_by_time(df, test_frac=0.25)
        assert train.match_id.max() < test.match_id.min()

    def test_splits_are_deterministic(self):
        df = _frame()
        a, _ = confound.split_by_match(df, seed=7)
        b, _ = confound.split_by_match(df, seed=7)
        assert a.index.equals(b.index)


class TestWealthBaseline:
    def test_detects_wealth_signal(self):
        df = _frame(n=2400)
        train, test = confound.split_by_match(df)
        result = confound.wealth_baseline(train, test)
        # Wealth genuinely predicts the synthetic outcome, so this must be
        # well above chance -- that is the point of the baseline.
        assert result.auc > 0.65
        assert result.n_train > 0 and result.n_test > 0

    def test_uses_no_item_features(self):
        assert not any("item" in f for f in confound.BASELINE_FEATURES)

    def test_missing_feature_raises(self):
        df = _frame().drop(columns=["nw_at_buy"])
        train, test = confound.split_by_match(df)
        with pytest.raises(KeyError, match="nw_at_buy"):
            confound.wealth_baseline(train, test)

    def test_coefficients_returned_for_all_features(self):
        df = _frame(n=2400)
        train, test = confound.split_by_match(df)
        result = confound.wealth_baseline(train, test)
        assert set(result.coefficients.index) == set(confound.BASELINE_FEATURES)


class TestStratifiedWinRate:
    def test_adjustment_moves_toward_population(self):
        df = _frame(n=6000)
        rates = confound.stratified_item_winrate(df, min_matches=10)
        assert not rates.empty
        assert {"adjusted_win_rate", "raw_win_rate", "wealth_inflation"} <= set(rates.columns)
        assert rates.adjusted_win_rate.between(0, 1).all()

    def test_respects_min_matches(self):
        df = _frame(n=6000)
        rates = confound.stratified_item_winrate(df, min_matches=100_000)
        assert rates.empty

    def test_wealth_inflation_is_raw_minus_adjusted(self):
        df = _frame(n=6000)
        r = confound.stratified_item_winrate(df, min_matches=10)
        assert np.allclose(r.wealth_inflation, r.raw_win_rate - r.adjusted_win_rate)


class TestGate:
    """The gate threshold scales with sample size.

    A +0.003 AUC lift is noise on 20k test rows and a solid result on 800k.
    A fixed tolerance either waves through junk on small samples or rejects
    real effects on large ones.
    """

    def test_flags_failure_when_no_lift(self):
        base = confound.BaselineResult(0.700, 100_000, 50_000, pd.Series(dtype=float))
        assert "FAILED GATE" in confound.report_gate(0.7001, base)

    def test_passes_with_real_lift(self):
        base = confound.BaselineResult(0.700, 100_000, 50_000, pd.Series(dtype=float))
        assert "passed gate" in confound.report_gate(0.760, base)

    def test_small_lift_fails_on_small_sample(self):
        base = confound.BaselineResult(0.700, 2_000, 1_000, pd.Series(dtype=float))
        assert "FAILED GATE" in confound.report_gate(0.7030, base)

    def test_same_small_lift_passes_on_large_sample(self):
        # Identical lift, 800x the data: now many SE from zero.
        base = confound.BaselineResult(0.700, 2_000_000, 800_000, pd.Series(dtype=float))
        assert "passed gate" in confound.report_gate(0.7030, base)

    def test_explicit_tolerance_overrides(self):
        base = confound.BaselineResult(0.700, 2_000_000, 800_000, pd.Series(dtype=float))
        assert "FAILED GATE" in confound.report_gate(0.7030, base, tolerance=0.05)

    def test_standard_error_shrinks_with_n(self):
        assert confound.auc_standard_error(0.7, 1_000) > confound.auc_standard_error(0.7, 1_000_000)

    def test_reports_lift_in_standard_errors(self):
        base = confound.BaselineResult(0.700, 2_000_000, 800_000, pd.Series(dtype=float))
        assert "SE" in confound.report_gate(0.760, base)


class TestLeakageGuard:
    """Outcome-encoding features must never enter the baseline.

    duration_s and nw_final describe how the match ENDED, not what a player
    knew while buying. With them included the controls-only model reaches
    ~0.92 AUC on real data and no item model can clear it, which reads as
    "items are worthless" when the real cause is a circular comparison.
    """

    def test_leaky_features_are_excluded_from_baseline(self):
        assert not confound.LEAKY_FEATURES & set(confound.BASELINE_FEATURES)

    def test_duration_and_final_networth_are_flagged(self):
        assert "duration_s" in confound.LEAKY_FEATURES
        assert "nw_final" in confound.LEAKY_FEATURES

    def test_passing_a_leaky_feature_raises(self):
        df = _frame()
        df["duration_s"] = 2000
        train, test = confound.split_by_match(df)
        with pytest.raises(ValueError, match="leaking"):
            confound.wealth_baseline(
                train, test, features=[*confound.BASELINE_FEATURES, "duration_s"]
            )

    def test_design_controls_carry_no_leaks(self):
        from deadlock import design

        assert not confound.LEAKY_FEATURES & set(design.CONTROL_COLUMNS)
