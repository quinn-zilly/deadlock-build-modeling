"""The decision point: time bucketing, and what counts as a legal move."""

from __future__ import annotations

import pytest

from deadlock import assets, state


class TestTimeBucket:
    @pytest.mark.parametrize(
        "seconds,expected",
        [
            (0, 0), (299, 0),
            (300, 1), (599, 1),
            (600, 2),
            (900, 3),
            (1200, 4), (1799, 4),
            (1800, 5), (5000, 5),
        ],
    )
    def test_boundaries(self, seconds, expected):
        assert state.time_bucket(seconds) == expected

    def test_labels_cover_every_bucket(self):
        assert len(state.TIME_BUCKET_LABELS) == len(state.TIME_BUCKET_BOUNDS_S) + 1

    def test_last_bucket_is_open_ended(self):
        """Match length varies, so the final bucket cannot have an upper bound."""
        assert state.time_bucket(10_000) == len(state.TIME_BUCKET_BOUNDS_S)


class TestGameState:
    def test_bucket_derives_from_time(self):
        s = state.GameState(hero_id=1, game_time_s=700, souls_available=0)
        assert s.bucket == 2

    def test_counts_owned(self):
        s = state.GameState(
            hero_id=1, game_time_s=0, souls_available=0,
            owned_item_ids=frozenset({1, 2, 3}),
        )
        assert s.n_owned == 3

    def test_posterior_defaults_empty_not_shared(self):
        """A mutable default would be shared across every state."""
        a = state.GameState(hero_id=1, game_time_s=0, souls_available=0)
        b = state.GameState(hero_id=2, game_time_s=0, souls_available=0)
        a.archetype_posterior[0] = 1.0
        assert b.archetype_posterior == {}


class TestCandidateFiltering:
    def test_excludes_owned(self):
        items = assets.load_items()
        owned = next(iter(items))
        s = state.GameState(
            hero_id=1, game_time_s=600, souls_available=100_000,
            owned_item_ids=frozenset({owned}),
        )
        assert owned not in state.candidate_items(s)

    def test_excludes_unaffordable(self):
        items = assets.load_items()
        s = state.GameState(hero_id=1, game_time_s=0, souls_available=800)
        assert all(items[i].cost <= 800 for i in state.candidate_items(s))

    def test_broke_player_has_no_candidates(self):
        s = state.GameState(hero_id=1, game_time_s=0, souls_available=0)
        assert state.candidate_items(s) == []

    def test_affordable_only_off_ignores_souls(self):
        """Pre-match planning asks what to buy eventually, not what is affordable now."""
        s = state.GameState(hero_id=1, game_time_s=0, souls_available=0)
        assert len(state.candidate_items(s, affordable_only=False)) > 100
