"""Tests for the recommender's candidate filtering and ranking."""

from __future__ import annotations

import pandas as pd
import pytest

from deadlock import assets, model_b


@pytest.fixture(scope="module")
def real_items():
    """Uses the cached asset list; no network call after the first run."""
    return assets.load_items()


class TestCandidateFiltering:
    def test_excludes_unaffordable(self, real_items):
        cheap = model_b.GameState(hero_id=7, phase=0, souls_available=800)
        rich = model_b.GameState(hero_id=7, phase=0, souls_available=100_000)
        assert len(model_b.candidate_items(cheap)) < len(model_b.candidate_items(rich))
        assert all(real_items[i].cost <= 800 for i in model_b.candidate_items(cheap))

    def test_excludes_owned(self, real_items):
        state = model_b.GameState(hero_id=7, phase=0, souls_available=100_000)
        first = model_b.candidate_items(state)[0]
        with_owned = model_b.GameState(
            hero_id=7, phase=0, souls_available=100_000,
            owned_item_ids=frozenset({first}),
        )
        assert first not in model_b.candidate_items(with_owned)

    def test_broke_player_gets_nothing(self):
        state = model_b.GameState(hero_id=7, phase=0, souls_available=0)
        assert model_b.candidate_items(state) == []


def _purchase_frame():
    rows = []
    for i in range(400):
        rows.append(
            {
                "match_id": 1000 + i // 4,
                "hero_id": 7,
                "phase": 0,
                "item_id": 1548066885 if i % 2 else 1009965641,
                "won": i % 3 != 0,
                "nw_quintile": i % 5,
            }
        )
    return pd.DataFrame(rows)


class TestLocalScorer:
    def test_fits_and_ranks(self):
        df = _purchase_frame()
        tables = model_b.fit_local_scores(df, min_matches=40)
        assert (7, 0) in tables
        state = model_b.GameState(hero_id=7, phase=0, souls_available=100_000)
        recs = model_b.recommend_local(state, tables)
        assert recs
        assert all(isinstance(r, model_b.Recommendation) for r in recs)
        # Ranked descending by score.
        assert [r.score for r in recs] == sorted((r.score for r in recs), reverse=True)

    def test_respects_owned_and_budget(self):
        df = _purchase_frame()
        tables = model_b.fit_local_scores(df, min_matches=40)
        state = model_b.GameState(
            hero_id=7, phase=0, souls_available=100_000,
            owned_item_ids=frozenset({1548066885}),
        )
        assert all(r.item_id != 1548066885 for r in model_b.recommend_local(state, tables))

    def test_unknown_cell_returns_empty(self):
        tables = model_b.fit_local_scores(_purchase_frame(), min_matches=40)
        state = model_b.GameState(hero_id=999, phase=3, souls_available=50_000)
        assert model_b.recommend_local(state, tables) == []


class TestPopularityBaseline:
    def test_ranks_by_frequency(self):
        df = _purchase_frame()
        state = model_b.GameState(hero_id=7, phase=0, souls_available=100_000)
        recs = model_b.popularity_baseline(df, state)
        assert recs
        assert recs[0].n >= recs[-1].n
        assert all(r.source == "popularity" for r in recs)

    def test_empty_cell_is_safe(self):
        df = _purchase_frame()
        state = model_b.GameState(hero_id=999, phase=0, souls_available=100_000)
        assert model_b.popularity_baseline(df, state) == []
