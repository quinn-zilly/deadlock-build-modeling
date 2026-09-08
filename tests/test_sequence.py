"""The backoff model: does the mixture behave, and can it be read back.

The properties pinned here are the ones that make the chain trustworthy rather
than merely accurate. A distribution that does not sum to 1, a level that
silently swallows a thin context, or an `n` that reports a weighted
pseudo-count instead of real matches would each reproduce the failure in
`docs/DIAGNOSIS.md` -- a number with no recourse behind it.
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
    """A population where everyone buys the same items in the same order."""
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
        """The one number that gives kappa its meaning."""
        model = sequence.fit(purchases(n_players=20), kappa=60.0)
        # L5 sees 3 items x 20 players = 60 rows for the hero.
        _, weights, _ = model.levels[-1].lookup((HERO,))
        total = weights.sum()
        assert total == 60.0
        assert total / (total + model.kappa) == pytest.approx(0.5)

    def test_a_missing_context_falls_through_without_error(self):
        """lambda = 0 for an unseen context, so the level is a no-op."""
        model = sequence.fit(purchases())
        # prev1 = 999 was never observed, so L0 and L1 have nothing.
        st = empty_state(purchased=(999,), owned_item_ids=frozenset({999}))
        ids, probability = model.distribution(st)
        assert len(ids)
        assert probability.sum() == pytest.approx(1.0)

    def test_a_state_unknown_at_every_level_returns_no_distribution(self):
        """An unseen hero has no evidence anywhere; say so rather than guess."""
        model = sequence.fit(purchases())
        ids, probability = model.distribution(empty_state(hero_id=999))
        assert not len(ids)
        assert not len(probability)

    def test_interpolated_probability_lies_between_the_mixed_levels(self):
        """A convex combination cannot leave the interval it mixes over."""
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
        """No item is ever bought twice in the observed data."""
        model = sequence.fit(purchases())
        st = empty_state().with_purchase(101, game_time_s=180)
        ids, _ = model.distribution(st)
        assert 101 not in ids.tolist()

    def test_unseen_items_stay_at_zero(self):
        """No uniform floor: an item nobody buys must never be recommended."""
        model = sequence.fit(purchases())
        ids, _ = model.distribution(empty_state())
        assert set(ids.tolist()) <= {101, 102, 103}


class TestTimeBuckets:
    @pytest.mark.parametrize(
        "seconds", [0, 1, 299, 300, 301, 599, 600, 899, 900, 1199, 1200, 1799, 1800, 10_000]
    )
    def test_digitize_agrees_with_time_bucket(self, seconds):
        """The tables are built with np.digitize and read with time_bucket.

        They agree only because digitize defaults to right=False, matching the
        strict `<` in time_bucket. Pin it, or a silent disagreement would
        misfile every purchase near a boundary.
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
        """`n` is what a person checks against the prevalence table.

        If weighting inflated it, the number would no longer be a count of
        matches and could not be verified by hand.
        """
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
        """Before any evidence, how often each archetype is played is the
        honest prior -- not a flat one."""
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
        """`backoff_level` and `n` were dead fields until the model filled them.

        Uses real item ids because `predict` resolves names and costs through
        the asset table -- a recommendation for an item that does not exist in
        the shop is not a legal move.
        """
        real_items = sorted(assets.shopable_items())[:3]
        model = sequence.fit(purchases(items=tuple(real_items)))
        recs = model.predict(empty_state(), candidates=real_items)
        assert recs
        assert all(r.backoff_level in sequence.LEVEL_NAMES for r in recs)
        assert all(r.n > 0 for r in recs)


class TestPrepare:
    def test_sequence_start_is_a_real_context_not_a_dropped_row(self):
        """The bigram baseline forfeits the first purchase; this must not."""
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
        """Not a pickle: a person can open the index and see the contexts."""
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
    """Deadlock item ids do not fit in int32, and a wrapped id ranks first.

    73 of the 173 shopable ids exceed int32. When the tables stored ids
    narrower, those wrapped to negative numbers that still sorted, still
    aggregated, and still won the argmax -- so the model recommended items that
    do not exist and scored 0.238 where a plain bigram scored 0.277. Nothing
    raised; the only symptom was being quietly worse than the baseline.
    """

    BIG = 4204808176  # the largest real shopable id

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
        """Not just the max -- any of the 173 could be the one that wraps."""
        real = sorted(assets.shopable_items())
        model = sequence.fit(purchases(n_players=5, items=tuple(real)))
        stored = set()
        for level in model.levels:
            stored.update(int(i) for i in level.item_ids)
        assert stored == set(real)


class TestBadgeWeightedFit:
    """The badge kernel has to reach the tables, not merely exist.

    `row_weights` was implemented and tested for a long time while no caller
    ever passed `target_badge`, so every recommendation the tool made imitated
    the median player. The wiring is what these tests pin.
    """

    def two_brackets(self) -> pd.DataFrame:
        """Two populations of the same hero that buy opposite second items."""
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
        """`fit` sorts before building, so a caller's own weights misalign.

        Passing `target_badge` is the only way to weight rows correctly, which
        is why it exists alongside `weights` rather than being left to callers.
        """
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
        """61 is the population median; the default aims at the top 30%."""
        assert sequence.DEFAULT_TARGET_BADGE > 61


class TestModelRecordsItsBracket:
    """A cached model has to say which bracket it was fitted for.

    Without it a cache fitted for the median player and one fitted for the top
    30% are the same file on disk, and the tool would serve whichever it found
    while claiming the bracket the caller asked for.
    """

    def test_target_badge_survives_a_round_trip(self, tmp_path):
        model = sequence.fit(purchases(), target_badge=80.0)
        loaded = sequence.SequenceModel.load(model.save(tmp_path / "m.npz"))
        assert loaded.target_badge == 80.0

    def test_an_unweighted_model_records_no_bracket(self, tmp_path):
        model = sequence.fit(purchases())
        loaded = sequence.SequenceModel.load(model.save(tmp_path / "m.npz"))
        assert loaded.target_badge is None


class TestBadgeArgumentParsing:
    """One parser and one phrasing for the bracket, shared by every entry point.

    The CLI, the build generator, the scoring script and the page generator all
    take a badge from the command line. Four copies of "None if it says all,
    else float" is four places for the brackets to drift apart -- and a page
    rendered from one bracket while claiming another is exactly the untraceable
    number this project exists to avoid.
    """

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
