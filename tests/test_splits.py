"""Splits must not leak, and each must leak differently from the others.

The account split is the one that matters for an imitation model: a player's
build habits repeat across their own matches, so a match-level split lets a
model score by recalling a person rather than learning a strategy.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from deadlock import splits


def frame(n_matches: int = 40, players: int = 4, accounts: int = 10) -> pd.DataFrame:
    rows = []
    for m in range(n_matches):
        for p in range(players):
            rows.append(
                {
                    "match_id": 1000 + m,
                    "player_slot": p,
                    # Accounts recur across matches, as they do in real data.
                    "account_id": (m * players + p) % accounts,
                    "item_id": p,
                }
            )
    return pd.DataFrame(rows)


class TestSplitByMatch:
    def test_no_match_on_both_sides(self):
        train, test = splits.split_by_match(frame())
        assert not set(train["match_id"]) & set(test["match_id"])

    def test_covers_every_row(self):
        df = frame()
        train, test = splits.split_by_match(df)
        assert len(train) + len(test) == len(df)

    def test_respects_test_fraction(self):
        df = frame(n_matches=100)
        _, test = splits.split_by_match(df, test_frac=0.25)
        assert 0.2 <= len(test) / len(df) <= 0.3

    def test_is_deterministic(self):
        a, _ = splits.split_by_match(frame(), seed=7)
        b, _ = splits.split_by_match(frame(), seed=7)
        pd.testing.assert_frame_equal(a, b)

    def test_seed_changes_split(self):
        a, _ = splits.split_by_match(frame(n_matches=200), seed=0)
        b, _ = splits.split_by_match(frame(n_matches=200), seed=1)
        assert set(a["match_id"]) != set(b["match_id"])

    def test_leaves_accounts_on_both_sides(self):
        """The reason split_by_account exists.

        A match-level split does not separate players, so this overlap is
        expected -- and is exactly the leak an imitation model can exploit.
        """
        train, test = splits.split_by_match(frame())
        assert set(train["account_id"]) & set(test["account_id"])


class TestSplitByAccount:
    def test_no_account_on_both_sides(self):
        train, test = splits.split_by_account(frame())
        assert not set(train["account_id"]) & set(test["account_id"])

    def test_covers_every_row(self):
        df = frame()
        train, test = splits.split_by_account(df)
        assert len(train) + len(test) == len(df)

    def test_is_deterministic(self):
        a, _ = splits.split_by_account(frame(), seed=3)
        b, _ = splits.split_by_account(frame(), seed=3)
        pd.testing.assert_frame_equal(a, b)


class TestSplitByTime:
    def test_train_precedes_test(self):
        train, test = splits.split_by_time(frame())
        assert max(train["match_id"]) < min(test["match_id"])

    def test_covers_every_row(self):
        df = frame()
        train, test = splits.split_by_time(df)
        assert len(train) + len(test) == len(df)

    def test_ignores_row_order(self):
        df = frame().sample(frac=1.0, random_state=0)
        train, test = splits.split_by_time(df)
        assert max(train["match_id"]) < min(test["match_id"])


class TestLeakageGuard:
    def test_duration_is_leaky(self):
        """Match length is unknown at buy time and encodes the outcome."""
        assert "duration_s" in splits.LEAKY_FEATURES

    def test_purchase_count_is_leaky(self):
        """n_purchases counts the very process being modeled."""
        assert "n_purchases" in splits.LEAKY_FEATURES

    def test_final_networth_is_leaky(self):
        assert "nw_final" in splits.LEAKY_FEATURES


class TestReplicationCorr:
    def test_identical_tables_correlate_one(self):
        table = pd.DataFrame({"lift": [0.1, 0.4, -0.2, 0.3]}, index=[1, 2, 3, 4])
        assert splits.replication_corr(table, table, "lift") == pytest.approx(1.0)

    def test_noise_does_not_replicate(self):
        rng = np.random.default_rng(0)
        idx = range(200)
        a = pd.DataFrame({"lift": rng.normal(size=200)}, index=idx)
        b = pd.DataFrame({"lift": rng.normal(size=200)}, index=idx)
        assert abs(splits.replication_corr(a, b, "lift")) < 0.2

    def test_too_few_rows_is_nan(self):
        a = pd.DataFrame({"lift": [0.1, 0.2]}, index=[1, 2])
        assert np.isnan(splits.replication_corr(a, a, "lift"))

    def test_joins_on_index_not_position(self):
        a = pd.DataFrame({"lift": [0.1, 0.5, 0.9]}, index=[1, 2, 3])
        b = pd.DataFrame({"lift": [0.9, 0.5, 0.1]}, index=[3, 2, 1])
        assert splits.replication_corr(a, b, "lift") == pytest.approx(1.0)
