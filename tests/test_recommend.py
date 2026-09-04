"""Tests for the paired-design recommender."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from deadlock import recommend as R
from deadlock.model_b import GameState


def _lane_rows(match_id, winner, a_items, b_items, lane=1):
    rows = []
    for slot, team, items in (
        (1, "Team0", a_items), (2, "Team0", a_items),
        (3, "Team1", b_items), (4, "Team1", b_items),
    ):
        for item in items:
            rows.append({
                "match_id": match_id, "player_slot": slot, "assigned_lane": lane,
                "team": team, "won": team == winner, "hero_id": 7,
                "item_id": item, "buy_time_s": 100, "phase": 0,
            })
    return rows


def _dataset(n=400, seed=0):
    """Item 20 genuinely wins lanes; item 30 genuinely loses them."""
    rng = np.random.default_rng(seed)
    rows = []
    for m in range(n):
        a_has_good = m % 2 == 0
        p = 0.75 if a_has_good else 0.25
        winner = "Team0" if rng.random() < p else "Team1"
        rows += _lane_rows(
            m, winner,
            a_items=[10, 20] if a_has_good else [10],
            b_items=[10, 30] if a_has_good else [10],
        )
    return pd.DataFrame(rows)


class TestItemAdvantage:
    def test_detects_a_winning_item(self):
        table = R.item_advantage(_dataset(), min_n=10)
        assert 20 in table.index
        assert table.loc[20, "raw_advantage"] > 0

    def test_shared_items_are_excluded(self):
        # Item 10 is held by both sides in every lane, so it cannot explain
        # any result and must not appear.
        table = R.item_advantage(_dataset(), min_n=10)
        assert 10 not in table.index

    def test_respects_min_n(self):
        assert R.item_advantage(_dataset(), min_n=10**6).empty

    def test_empty_input_is_safe(self):
        empty = _dataset().iloc[:0]
        result = R.item_advantage(empty, min_n=1)
        assert result.empty
        assert "advantage" in result.columns

    def test_reports_standard_error(self):
        table = R.item_advantage(_dataset(), min_n=10)
        assert (table["stderr"] > 0).all()


class TestCostCentring:
    """Raw advantage correlates 0.68 with item cost on real data.

    A side exclusively holding a 6400-soul item is usually just the richer
    side, so advantage must be centred within cost tier or the ranking
    restates wealth instead of comparing real alternatives.
    """

    def test_advantage_is_centred_within_tier(self):
        table = R.item_advantage(_dataset(), min_n=10)
        for _, group in table.groupby("cost"):
            assert group["advantage"].mean() == pytest.approx(0.0, abs=1e-9)

    def test_raw_advantage_is_preserved(self):
        table = R.item_advantage(_dataset(), min_n=10)
        assert "raw_advantage" in table.columns


class TestNextTierCost:
    @pytest.mark.parametrize(
        "souls,expected", [(0, 800), (800, 1600), (1600, 3200), (3200, 6400), (6400, None)]
    )
    def test_finds_next_tier(self, souls, expected):
        assert R.next_tier_cost(souls) == expected


class TestTempoPercentile:
    def test_faster_gap_scores_higher(self):
        gaps = pd.Series([60.0, 90.0, 120.0, 150.0, 180.0])
        assert R.tempo_percentile(gaps, 60) > R.tempo_percentile(gaps, 180)

    def test_ignores_zero_gaps(self):
        # A single-purchase player has no measurable gap.
        gaps = pd.Series([0.0, 0.0, 100.0, 200.0])
        assert 0.0 <= R.tempo_percentile(gaps, 150) <= 1.0

    def test_all_zero_returns_neutral(self):
        assert R.tempo_percentile(pd.Series([0.0, 0.0]), 100) == 0.5


def _advantages():
    from deadlock import assets

    items = assets.load_items()
    cheap = [i for i, v in items.items() if v.cost == 800][:3]
    mid = [i for i, v in items.items() if v.cost == 1600][:3]
    rows = []
    for rank, item_id in enumerate(cheap + mid):
        rows.append({
            "item_id": item_id, "win_rate": 0.5, "n": 1000,
            "raw_advantage": 0.0, "stderr": 0.01,
            "cost": items[item_id].cost,
            "advantage": 0.05 - 0.01 * rank, "significant": True,
        })
    return pd.DataFrame(rows).set_index("item_id")


class TestRecommend:
    def test_only_affordable_items_appear(self):
        advantages = _advantages()
        state = GameState(hero_id=7, phase=0, souls_available=800)
        advice = R.recommend(state, advantages)
        assert all(r.cost <= 800 for r in advice.items)

    def test_owned_items_excluded(self):
        advantages = _advantages()
        first = int(advantages.index[0])
        state = GameState(
            hero_id=7, phase=0, souls_available=10_000,
            owned_item_ids=frozenset({first}),
        )
        assert all(r.item_id != first for r in R.recommend(state, advantages).items)

    def test_ranked_descending(self):
        state = GameState(hero_id=7, phase=0, souls_available=10_000)
        scores = [r.score for r in R.recommend(state, _advantages()).items]
        assert scores == sorted(scores, reverse=True)

    def test_respects_top_k(self):
        state = GameState(hero_id=7, phase=0, souls_available=10_000)
        assert len(R.recommend(state, _advantages(), top_k=2).items) == 2

    def test_weak_items_are_flagged(self):
        advantages = _advantages()
        advantages["significant"] = False
        state = GameState(hero_id=7, phase=0, souls_available=10_000)
        assert all("weak" in r.source for r in R.recommend(state, advantages).items)

    def test_tempo_note_warns_when_slow(self):
        gaps = pd.Series([60.0] * 100)
        state = GameState(hero_id=7, phase=0, souls_available=10_000)
        advice = R.recommend(state, _advantages(), median_gap_s=300, gaps=gaps)
        assert "slower than" in advice.tempo_note

    def test_tempo_note_absent_without_data(self):
        state = GameState(hero_id=7, phase=0, souls_available=10_000)
        assert "not measured" in R.recommend(state, _advantages()).tempo_note


class TestSaveOption:
    def test_offers_next_tier(self):
        advantages = _advantages()
        state = GameState(hero_id=7, phase=0, souls_available=900)
        option = R.save_option(state, advantages)
        assert option is not None
        assert option.cost == 1600
        assert option.source == "save_option"

    def test_none_at_top_tier(self):
        state = GameState(hero_id=7, phase=0, souls_available=6400)
        assert R.save_option(state, _advantages()) is None

    def test_waiting_longer_is_penalized(self):
        advantages = _advantages()
        near = R.save_option(
            GameState(hero_id=7, phase=0, souls_available=1500), advantages
        )
        far = R.save_option(
            GameState(hero_id=7, phase=0, souls_available=900), advantages
        )
        assert near.score > far.score

    def test_none_when_no_scored_item_at_tier(self):
        advantages = _advantages().iloc[:0]
        state = GameState(hero_id=7, phase=0, souls_available=900)
        assert R.save_option(state, advantages) is None
