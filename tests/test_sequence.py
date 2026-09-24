"""The backoff model: how levels mix, and whether its numbers can be checked.

Checks that distributions sum to 1, that a thin context barely moves the
result, and that `n` is a real count of matches, not a weighted one.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from deadlock import assets, sequence, state
from deadlock.state import GameState, time_bucket

HERO = 7


def purchases(
    n_players: int = 200, items: tuple[int, ...] = (101, 102, 103), hero: int = HERO
) -> pd.DataFrame:
    """Players who all buy the same items in the same order."""
    rows = [
        {
            "match_id": m,
            "player_slot": 1,
            "hero_id": hero,
            "item_id": item,
            "buy_index": i,
            "buy_time_s": 70 + 110 * i,
            "won": m % 2 == 0,
            "average_badge": 60,
            "account_id": m,
        }
        for m in range(n_players)
        for i, item in enumerate(items)
    ]
    return pd.DataFrame(rows)


def empty_state(**kwargs) -> GameState:
    defaults = dict(hero_id=HERO, game_time_s=70.0, souls_available=10**9)
    return GameState(**{**defaults, **kwargs})


class TestInterpolation:
    def test_lambda_is_one_half_at_kappa_observations(self):
        """A context with total weight equal to kappa gets lambda 0.5."""
        model = sequence.fit(purchases(n_players=20), kappa=60.0)
        # L5 sees 3 items x 20 players = 60 rows for the hero.
        _, weights, _ = model.levels[-1].lookup((HERO,))
        total = weights.sum()
        assert total == 60.0
        assert total / (total + model.kappa) == pytest.approx(0.5)

    def test_a_missing_context_falls_through_without_error(self):
        """An unseen context gets lambda 0 and passes the level below through."""
        model = sequence.fit(purchases())
        # prev1 = 999 was never observed, so L0 and L1 have nothing.
        st = empty_state(purchased=(999,), owned_item_ids=frozenset({999}))
        ids, probability = model.distribution(st)
        assert len(ids)
        assert probability.sum() == pytest.approx(1.0)

    def test_a_state_unknown_at_every_level_returns_no_distribution(self):
        """A hero with no data at any level gets an empty distribution, not a guess."""
        model = sequence.fit(purchases())
        ids, probability = model.distribution(empty_state(hero_id=999))
        assert not len(ids)
        assert not len(probability)

    def test_interpolated_probability_lies_between_the_mixed_levels(self):
        """The mixed probability lies between the probabilities of the levels mixed."""
        # Two populations: one always buys 102 after 101, the other 103.
        first = purchases(n_players=100, items=(101, 102))
        second = purchases(n_players=100, items=(101, 103))
        second["match_id"] += 1000
        model = sequence.fit(pd.concat([first, second], ignore_index=True))

        st = empty_state(purchased=(101,), owned_item_ids=frozenset({101}), game_time_s=180)
        ids, probability = model.distribution(st)
        got = dict(zip(ids.tolist(), probability.tolist()))
        assert got[102] == pytest.approx(got[103], abs=1e-9)
        assert 0.0 < got[102] < 1.0


class TestDistribution:
    def test_sums_to_one_before_and_after_masking(self):
        model = sequence.fit(purchases())
        st = empty_state()
        _, unmasked = model.distribution(st, mask_owned=False)
        assert unmasked.sum() == pytest.approx(1.0)

        after = st.with_purchase(101, game_time_s=180)
        _, masked = model.distribution(after)
        assert masked.sum() == pytest.approx(1.0)

    def test_owned_items_get_no_probability(self):
        """Owned items get probability 0, since nobody buys an item twice."""
        model = sequence.fit(purchases())
        st = empty_state().with_purchase(101, game_time_s=180)
        ids, _ = model.distribution(st)
        assert 101 not in ids.tolist()

    def test_unseen_items_stay_at_zero(self):
        """An item nobody buys gets probability 0. There is no smoothing floor."""
        model = sequence.fit(purchases())
        ids, _ = model.distribution(empty_state())
        assert set(ids.tolist()) <= {101, 102, 103}


class TestTimeBuckets:
    @pytest.mark.parametrize(
        "seconds", [0, 1, 299, 300, 301, 599, 600, 899, 900, 1199, 1200, 1799, 1800, 10_000]
    )
    def test_digitize_agrees_with_time_bucket(self, seconds):
        """np.digitize (used to build the tables) and time_bucket agree at every boundary.

        They agree because digitize's default right=False matches the strict
        `<` in time_bucket. If they disagreed, purchases on a boundary would
        land in the wrong bucket.
        """
        assert int(np.digitize(seconds, state.TIME_BUCKET_BOUNDS_S)) == time_bucket(seconds)


class TestRowWeights:
    def test_defaults_are_a_no_op(self):
        df = purchases()
        assert np.allclose(sequence.row_weights(df), 1.0)

    def test_weights_normalise_to_mean_one(self):
        df = purchases()
        weights = sequence.row_weights(df, win_weight=3.0)
        assert weights.mean() == pytest.approx(1.0)

    def test_badge_kernel_prefers_the_target(self):
        df = purchases()
        df.loc[df["match_id"] < 100, "average_badge"] = 100
        weights = sequence.row_weights(df, target_badge=100.0, badge_halfwidth=10.0)
        high = weights[(df["average_badge"] == 100).to_numpy()]
        low = weights[(df["average_badge"] == 60).to_numpy()]
        assert high.mean() > low.mean()

    def test_reported_n_is_a_raw_count_not_a_weighted_one(self):
        """`n` stays a raw count when rows are weighted, so a person can check it."""
        df = purchases()
        plain = sequence.fit(df)
        weighted = sequence.fit(df, weights=sequence.row_weights(df, win_weight=3.0))
        st = empty_state()
        assert plain.evidence(st, 101).n == weighted.evidence(st, 101).n


class TestArchetypeMarginalisation:
    def test_one_hot_posterior_equals_direct_conditioning(self):
        df = purchases()
        df["archetype_id"] = 0
        model = sequence.fit(df)
        declared = empty_state(archetype_posterior={0: 1.0})
        _, with_posterior = model.distribution(declared)
        _, without = model.distribution(empty_state())
        assert np.allclose(with_posterior, without)

    def test_posterior_over_identical_archetypes_matches_either(self):
        df = purchases()
        df["archetype_id"] = (df["match_id"] % 2).astype(int)
        model = sequence.fit(df)
        _, blended = model.distribution(empty_state(archetype_posterior={0: 0.5, 1: 0.5}))
        _, single = model.distribution(empty_state(archetype_posterior={0: 1.0}))
        assert np.allclose(blended, single)

    def test_absent_posterior_falls_back_to_population_shares(self):
        """With no posterior given, archetypes are weighted by how often they're played."""
        df = purchases()
        df["archetype_id"] = (df["match_id"] < 150).astype(int)
        model = sequence.fit(df)
        shares = model.archetype_shares[HERO]
        assert shares[1] == pytest.approx(0.75)
        assert shares[0] == pytest.approx(0.25)


class TestEvidence:
    def test_evidence_names_the_level_carrying_the_mass(self):
        model = sequence.fit(purchases())
        st = empty_state().with_purchase(101, game_time_s=180)
        trace = model.evidence(st, 102)
        assert trace is not None
        assert trace.level in sequence.LEVEL_NAMES
        assert trace.n > 0
        # The dominant level must be the one with the largest contribution.
        assert trace.contributions[sequence.LEVEL_NAMES.index(trace.level)] == max(
            trace.contributions
        )

    def test_evidence_is_none_for_an_item_no_level_has_seen(self):
        model = sequence.fit(purchases())
        assert model.evidence(empty_state(), 555) is None

    def test_explain_prints_every_level(self):
        model = sequence.fit(purchases())
        text = model.explain(empty_state(), 101)
        for name in sequence.LEVEL_NAMES:
            assert name in text
        assert "lambda=" in text and "dominant" in text

    def test_recommendations_carry_their_provenance(self):
        """Each recommendation has its `backoff_level` and `n` filled in.

        Uses real item ids because `predict` looks up names and costs in the
        shop assets and skips unknown items.
        """
        real_items = sorted(assets.shopable_items())[:3]
        model = sequence.fit(purchases(items=tuple(real_items)))
        recs = model.predict(empty_state(), candidates=real_items)
        assert recs
        assert all(r.backoff_level in sequence.LEVEL_NAMES for r in recs)
        assert all(r.n > 0 for r in recs)


class TestPrepare:
    def test_sequence_start_is_a_real_context_not_a_dropped_row(self):
        """The first purchase of a match gets a prediction (the bigram baseline can't make one)."""
        prepared = sequence.prepare(purchases())
        first = prepared[prepared["buy_index"] == 0]
        assert (first["prev1"] == sequence.NO_ITEM).all()
        assert len(first) == 200

    def test_n_owned_is_the_buy_index(self):
        prepared = sequence.prepare(purchases())
        assert (prepared["n_owned"] == prepared["buy_index"]).all()


class TestPersistence:
    def test_round_trip_gives_an_identical_distribution(self, tmp_path: Path):
        model = sequence.fit(purchases())
        model.save(tmp_path / "m.npz")
        reloaded = sequence.SequenceModel.load(tmp_path / "m.npz")

        st = empty_state().with_purchase(101, game_time_s=180)
        before_ids, before_p = model.distribution(st)
        after_ids, after_p = reloaded.distribution(st)
        assert before_ids.tolist() == after_ids.tolist()
        assert np.allclose(before_p, after_p)
        assert reloaded.kappa == model.kappa

    def test_saved_index_is_readable_json(self, tmp_path: Path):
        """The saved index is plain JSON a person can open."""
        import json

        model = sequence.fit(purchases())
        model.save(tmp_path / "m.npz")
        index = json.loads((tmp_path / "m.index.json").read_text())
        assert [level["name"] for level in index["levels"]] == list(sequence.LEVEL_NAMES)


class TestFitValidation:
    def test_mismatched_weights_are_rejected(self):
        df = purchases()
        with pytest.raises(ValueError, match="weights"):
            sequence.fit(df, weights=np.ones(3))

class TestLargeItemIds:
    """Item ids larger than int32 survive fitting, prediction, and saving.

    73 of the 173 shop item ids don't fit in int32. When the tables stored
    them as int32, they wrapped to negative numbers without an error and the
    model recommended items that don't exist. The only symptom was scoring
    below the bigram baseline.
    """

    BIG = 4204808176  # the largest real shop item id

    def test_a_large_id_survives_the_round_trip(self):
        df = purchases(items=(self.BIG, 102))
        model = sequence.fit(df)
        ids, _ = model.distribution(empty_state())
        assert self.BIG in ids.tolist()

    def test_a_large_id_is_never_negative(self):
        model = sequence.fit(purchases(items=(self.BIG, 102)))
        for level in model.levels:
            assert (level.item_ids >= 0).all(), f"{level.name} wrapped an id negative"

    def test_a_large_id_survives_save_and_load(self, tmp_path: Path):
        model = sequence.fit(purchases(items=(self.BIG, 102)))
        model.save(tmp_path / "m.npz")
        reloaded = sequence.SequenceModel.load(tmp_path / "m.npz")
        ids, _ = reloaded.distribution(empty_state())
        assert self.BIG in ids.tolist()

    def test_every_real_shopable_id_round_trips(self):
        """Every one of the 173 real shop ids comes back unchanged, not just the largest."""
        real = sorted(assets.shopable_items())
        model = sequence.fit(purchases(n_players=5, items=tuple(real)))
        stored = set()
        for level in model.levels:
            stored.update(int(i) for i in level.item_ids)
        assert stored == set(real)


class TestBadgeWeightedFit:
    """`fit(target_badge=...)` changes the tables.

    For a long time `row_weights` existed but nothing passed it a badge, so
    the tool imitated the average player.
    """

    def two_brackets(self) -> pd.DataFrame:
        """High- and low-badge players of one hero who buy different second items."""
        rows = []
        for m in range(200):
            high = m % 2 == 0
            second = 102 if high else 103
            for i, item in enumerate((101, second)):
                rows.append(
                    {
                        "match_id": m,
                        "player_slot": 1,
                        "hero_id": HERO,
                        "item_id": item,
                        "buy_index": i,
                        "buy_time_s": 70 + 110 * i,
                        "won": True,
                        "average_badge": 100 if high else 40,
                        "account_id": m,
                    }
                )
        return pd.DataFrame(rows)

    def test_target_badge_shifts_the_recommendation(self):
        df = self.two_brackets()
        after = empty_state().with_purchase(101, game_time_s=180)

        def top(model):
            ids, probability = model.distribution(after)
            return int(ids[int(np.argmax(probability))])

        assert top(sequence.fit(df, target_badge=100.0, badge_halfwidth=20.0)) == 102
        assert top(sequence.fit(df, target_badge=40.0, badge_halfwidth=20.0)) == 103

    def test_weights_are_computed_on_the_sorted_frame(self):
        """Badge weights land on the right rows even when the input isn't in fit's sort order."""
        df = self.two_brackets().sort_values("item_id", kind="stable")
        after = empty_state().with_purchase(101, game_time_s=180)
        model = sequence.fit(df, target_badge=100.0, badge_halfwidth=20.0)
        ids, probability = model.distribution(after)
        assert int(ids[int(np.argmax(probability))]) == 102

    def test_weights_and_target_badge_are_mutually_exclusive(self):
        df = self.two_brackets()
        with pytest.raises(ValueError):
            sequence.fit(df, weights=np.ones(len(df)), target_badge=80.0)

    def test_reported_n_stays_a_raw_count_under_badge_weighting(self):
        df = self.two_brackets()
        weighted = sequence.fit(df, target_badge=100.0, badge_halfwidth=20.0)
        plain = sequence.fit(df)
        st = empty_state()
        assert weighted.evidence(st, 101).n == plain.evidence(st, 101).n

    def test_the_default_target_is_above_the_median_badge(self):
        """The default badge is well above the median badge."""
        assert sequence.DEFAULT_TARGET_BADGE > 61


class TestModelRecordsItsBracket:
    """A saved model records the badge it was fitted for, and keeps it after loading."""

    def test_target_badge_survives_a_round_trip(self, tmp_path):
        model = sequence.fit(purchases(), target_badge=80.0)
        loaded = sequence.SequenceModel.load(model.save(tmp_path / "m.npz"))
        assert loaded.target_badge == 80.0

    def test_an_unweighted_model_records_no_bracket(self, tmp_path):
        model = sequence.fit(purchases())
        loaded = sequence.SequenceModel.load(model.save(tmp_path / "m.npz"))
        assert loaded.target_badge is None


class TestBadgeArgumentParsing:
    """`parse_target_badge` and `describe_badge`, which every command uses."""

    def test_a_number_is_a_bracket(self):
        assert sequence.parse_target_badge("55") == 55.0

    def test_all_means_the_whole_population(self):
        assert sequence.parse_target_badge("all") is None
        assert sequence.parse_target_badge(" ALL ") is None

    def test_nonsense_is_refused(self):
        with pytest.raises(ValueError):
            sequence.parse_target_badge("gold")

    def test_the_phrasing_names_the_bracket(self):
        assert sequence.describe_badge(80.0) == "badge ~80"
        assert sequence.describe_badge(None) == "all badges"
