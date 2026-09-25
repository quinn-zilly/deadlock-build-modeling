"""The staple gate, order and overlap metrics, baselines, and next-item accuracy.

Most tests use made-up data and always run. `TestAgainstRealData` checks
Wraith's real staples and is skipped when the purchase table is missing.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from deadlock import evaluate

PURCHASES = Path("data/processed/purchases.parquet")

# The ten items bought by at least 70% of Wraith's 11,114 players, measured
# 2026-09-15. The old planner recommended none of them (docs/DIAGNOSIS.md).
#
# Spirit Lifesteal is only 0.0013 above the threshold, so it may drop out
# after the next data pull. The others are between 0.708 and 0.992.
WRAITH_STAPLES = [
    "Quicksilver Reload",
    "Monster Rounds",
    "Mercurial Magnum",
    "Ricochet",
    "Swift Striker",
    "Surge of Power",
    "Extra Spirit",
    "Rapid Rounds",
    "Tesla Bullets",
    "Spirit Lifesteal",
]


def purchases(builds: dict[int, list[int]]) -> pd.DataFrame:
    """A purchase table from {player: ordered item ids}."""
    rows = []
    for player, items in builds.items():
        for position, item in enumerate(items):
            rows.append(
                {
                    "match_id": 1000 + player,
                    "player_slot": player % 12,
                    "account_id": player,
                    "hero_id": 7,
                    "item_id": item,
                    "buy_index": position,
                }
            )
    return pd.DataFrame(rows)


def population(n: int = 400, staple: int = 1) -> pd.DataFrame:
    """Players who nearly all buy `staple`, and rarely item 99."""
    builds = {p: [staple, 2, 3] for p in range(n)}
    builds[0] = [2, 3, 99]  # one player skips the staple
    return purchases(builds)


class TestItemPrevalence:
    def test_counts_players_not_rows(self):
        df = population(n=100)
        assert evaluate.item_prevalence(df)[1] == pytest.approx(0.99)

    def test_sorted_descending(self):
        values = evaluate.item_prevalence(population()).tolist()
        assert values == sorted(values, reverse=True)

    def test_empty_frame_is_empty(self):
        empty = population().iloc[0:0]
        assert evaluate.item_prevalence(empty).empty


class TestPrevalenceGate:
    def test_fails_and_names_a_missing_staple(self):
        """A build missing a staple fails, and the message names the item."""
        result = evaluate.prevalence_gate([2, 3], population(), hero_id=7)
        assert not result.passed
        assert 1 in result.missing
        assert result.missing[1] == pytest.approx(0.9975, abs=1e-3)

    def test_passes_when_staples_present(self):
        assert evaluate.prevalence_gate([1, 2, 3], population(), hero_id=7).passed

    def test_ignores_rare_items(self):
        """Leaving out an item 0.25% of players buy doesn't fail the gate."""
        result = evaluate.prevalence_gate([1, 2, 3], population(), hero_id=7)
        assert 99 not in result.staples

    def test_extra_items_do_not_fail_it(self):
        assert evaluate.prevalence_gate([1, 2, 3, 99, 77], population(), hero_id=7).passed

    def test_thin_cell_is_inconclusive_not_passing(self):
        """A cell with too few players is inconclusive, not a pass."""
        result = evaluate.prevalence_gate([], population(n=50), hero_id=7)
        assert result.inconclusive
        assert not result.passed

    def test_threshold_is_configurable(self):
        result = evaluate.prevalence_gate([], population(), hero_id=7, threshold=0.999)
        assert 1 not in result.staples

    def test_describe_names_the_item(self):
        result = evaluate.prevalence_gate([2, 3], population(), hero_id=7)
        assert "Quicksilver Reload" in result.describe({1: "Quicksilver Reload"})

    def test_describe_reports_inconclusive(self):
        result = evaluate.prevalence_gate([], population(n=10), hero_id=7)
        assert "INCONCLUSIVE" in result.describe()


class TestOrderDistance:
    def test_identical_order_is_tau_one(self):
        result = evaluate.order_distance([1, 2, 3, 4, 5], [1, 2, 3, 4, 5])
        assert result.kendall_tau == pytest.approx(1.0)

    def test_reversed_order_is_tau_minus_one(self):
        result = evaluate.order_distance([5, 4, 3, 2, 1], [1, 2, 3, 4, 5])
        assert result.kendall_tau == pytest.approx(-1.0)

    def test_reports_shared_count(self):
        result = evaluate.order_distance([1, 2, 99], [1, 2, 3])
        assert result.n_shared == 2

    def test_flags_unreliable_when_few_shared(self):
        """Tau over three shared items is marked unreliable."""
        assert not evaluate.order_distance([1, 2, 3], [1, 2, 3]).reliable

    def test_reliable_when_enough_shared(self):
        assert evaluate.order_distance([1, 2, 3, 4, 5], [1, 2, 3, 4, 5]).reliable

    def test_disjoint_sets_are_nan_not_zero(self):
        assert np.isnan(evaluate.order_distance([1, 2], [3, 4]).kendall_tau)

    def test_jaccard_at_six(self):
        result = evaluate.order_distance([1, 2, 3, 4, 5, 6], [1, 2, 3, 7, 8, 9])
        assert result.jaccard_6 == pytest.approx(3 / 9)


class TestPopulationOrder:
    def test_orders_by_median_position(self):
        order = evaluate.population_order(population())
        assert order.index.tolist()[:3] == [1, 2, 3]


class TestBaselines:
    def test_popularity_ranks_by_pick_rate(self):
        """Items 2 and 3 are universal; item 1 is skipped by one player."""
        ranked = evaluate.popularity_baseline(population())[7]
        assert set(ranked[:2]) == {2, 3}
        assert ranked[2] == 1

    def test_positional_keys_on_hero_and_position(self):
        table = evaluate.positional_baseline(population())
        assert table[(7, 0)][0] == 1

    def test_bigram_keys_on_previous_item(self):
        table = evaluate.bigram_baseline(population())
        assert table[(7, 1)][0] == 2

    def test_bigram_skips_first_purchase(self):
        """There is no previous item before the first buy."""
        df = purchases({0: [1, 2], 1: [1, 2]})
        assert all(prev != 0 for _, prev in evaluate.bigram_baseline(df))

    def test_top_k_accuracy_counts_hits(self):
        assert evaluate.top_k_accuracy([[1, 2], [3, 4]], [1, 4], k=2) == 1.0

    def test_top_k_respects_k(self):
        assert evaluate.top_k_accuracy([[1, 2], [3, 4]], [2, 4], k=1) == 0.0

    def test_top_k_on_empty_is_nan(self):
        assert np.isnan(evaluate.top_k_accuracy([], []))

    def test_score_baselines_excludes_owned(self):
        """Baselines never predict an item the player already owns."""
        df = purchases({p: [1, 2, 3] for p in range(80)})
        result = evaluate.score_baselines(df, df)
        assert set(result["baseline"]) == {"popularity", "positional", "bigram"}
        assert (result["n_decisions"] == 240).all()


@pytest.mark.data
@pytest.mark.skipif(not PURCHASES.exists(), reason="needs purchases.parquet")
class TestMembershipVsPlayers:
    """Item overlap between a build and real players."""

    CORE = list(range(1, 9))
    TAIL = list(range(100, 108))

    @classmethod
    def cell(cls, n: int = 200) -> pd.DataFrame:
        """Players who share 8 core items and pick 4 more from an uneven pool.

        The differences must be within the first 12 purchases, or Jaccard@12
        can't see them. The pool must be uneven: if every player picked
        uniformly, a consensus build would be no closer to players than they
        are to each other.
        """
        rng = np.random.default_rng(1)
        weights = np.arange(len(cls.TAIL), 0, -1, dtype=float)
        weights /= weights.sum()
        builds = {
            p: cls.CORE + list(rng.choice(cls.TAIL, 4, replace=False, p=weights))
            for p in range(n)
        }
        return purchases(builds)

    @staticmethod
    def consensus(cell: pd.DataFrame, k: int = 12) -> list[int]:
        """The k most commonly bought items."""
        return (
            cell.drop_duplicates(["match_id", "player_slot", "item_id"])
            .item_id.value_counts()
            .index[:k]
            .tolist()
        )

    def test_a_consensus_build_beats_the_ceiling(self):
        """A consensus build overlaps players more than players overlap each other."""
        cell = self.cell()
        result = evaluate.membership_vs_players(self.consensus(cell), cell)
        assert result.generated > result.ceiling
        assert result.ratio > 1.0

    def test_identical_players_give_a_ceiling_of_one(self):
        """If every player buys the same items, the ceiling is 1.0."""
        builds = {p: list(range(1, 13)) for p in range(20)}
        result = evaluate.membership_vs_players(list(range(1, 13)), purchases(builds))
        assert result.ceiling == pytest.approx(1.0)
        assert result.generated == pytest.approx(1.0)
        assert result.ratio == pytest.approx(1.0)

    def test_a_disjoint_build_scores_zero(self):
        result = evaluate.membership_vs_players(list(range(900, 912)), self.cell())
        assert result.generated == pytest.approx(0.0)
        assert result.ceiling > 0.0

    def test_too_few_players_is_nan_not_a_number(self):
        result = evaluate.membership_vs_players([1, 2], purchases({0: list(range(1, 13))}))
        assert np.isnan(result.generated)
        assert result.n_players == 1

    def test_short_sequences_are_dropped(self):
        """Players with fewer than 12 purchases are left out."""
        builds = {p: list(range(1, 13)) for p in range(10)}
        builds.update({50 + p: [1, 2, 3] for p in range(10)})
        assert len(evaluate.player_sequences(purchases(builds))) == 10

    def test_median_order_reference_understates_membership(self):
        """On real data, comparing with the median order makes builds look worse than they are.

        `population_order`'s top 12 are the cheap components bought first.
        Against it, builds scored J@12 0.143. Against real players, the same
        builds beat the player-vs-player ceiling.
        """
        if not PURCHASES.exists():
            pytest.skip("requires the processed purchase table")
        from deadlock import assets

        heroes = assets.load_heroes()
        hero_id = next(h for h, v in heroes.items() if v.name == "Wraith")
        df = pd.read_parquet(
            PURCHASES,
            columns=["match_id", "player_slot", "hero_id", "item_id", "buy_index"],
        )
        cell = df[df.hero_id == hero_id]
        sequences = evaluate.player_sequences(cell)
        consensus = (
            cell.drop_duplicates(["match_id", "player_slot", "item_id"])
            .item_id.value_counts()
            .index[:12]
            .tolist()
        )
        median_order = evaluate.population_order(cell).index.tolist()

        against_players = evaluate.membership_vs_players(consensus, cell)
        against_median = np.mean(
            [evaluate._jaccard(median_order, seq, 12) for seq in sequences[:300]]
        )
        assert against_players.generated > against_players.ceiling
        assert against_median < against_players.ceiling


class TestAgainstRealData:
    """The gate on Wraith's real data."""

    @staticmethod
    def wraith() -> tuple[pd.DataFrame, dict[int, str], dict[str, int]]:
        from deadlock import assets

        items = assets.load_items()
        heroes = assets.load_heroes()
        hero_id = next(h for h, v in heroes.items() if v.name == "Wraith")
        df = pd.read_parquet(
            PURCHASES,
            columns=["match_id", "player_slot", "hero_id", "item_id", "buy_index"],
        )
        names = {k: v.name for k, v in items.items()}
        return df[df.hero_id == hero_id], names, {v: k for k, v in names.items()}

    def test_old_planner_build_fails_the_gate(self):
        """The gate fails the old planner's Wraith build, which had none of the staples.

        See docs/DIAGNOSIS.md.
        """
        df, names, by_name = self.wraith()
        old_build = [
            by_name[n]
            for n in ["Golden Goose Egg", "Split Shot", "Infuser", "Escalating Exposure"]
            if n in by_name
        ]
        result = evaluate.prevalence_gate(old_build, df, hero_id=7)
        assert not result.passed
        assert len(result.missing) == len(WRAITH_STAPLES)

    def test_wraith_staples_are_stable(self):
        """Wraith's staples match the list above, so a patch that changes them shows up."""
        df, names, _ = self.wraith()
        result = evaluate.prevalence_gate([], df, hero_id=7)
        found = {names[i] for i in result.staples}
        assert found == set(WRAITH_STAPLES)

    def test_quicksilver_reload_is_near_universal(self):
        df, _, by_name = self.wraith()
        prevalence = evaluate.item_prevalence(df)
        assert prevalence[by_name["Quicksilver Reload"]] > 0.98

    def test_a_build_of_the_staples_passes(self):
        df, _, by_name = self.wraith()
        build = [by_name[n] for n in WRAITH_STAPLES]
        assert evaluate.prevalence_gate(build, df, hero_id=7).passed


class FakeModel:
    """A fake model that always returns `ranking`, so scores are easy to work out by hand."""

    def __init__(self, ranking: list[int]):
        self.ranking = ranking
        self.seen: list[frozenset[int]] = []

    def distribution(self, state):
        self.seen.append(state.owned_item_ids)
        ids = np.array(self.ranking, dtype=np.int64)
        probability = np.linspace(1.0, 0.1, len(ids))
        return ids, probability

    def evidence(self, state, item_id):
        """Always None: the fake model has no backoff trace."""
        return None


class TestNextItemAccuracy:
    """`next_item_accuracy`, which every scoring script uses."""

    @staticmethod
    def frame(items: list[int]) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "match_id": 1,
                    "player_slot": 0,
                    "hero_id": 7,
                    "item_id": item,
                    "buy_index": i,
                    "buy_time_s": 60.0 * i,
                }
                for i, item in enumerate(items)
            ]
        )

    @staticmethod
    def labels(archetype_id: int = 0) -> pd.DataFrame:
        return pd.DataFrame(
            [{"match_id": 1, "player_slot": 0, "archetype_id": archetype_id}]
        )

    def test_counts_a_hit_only_when_the_top_item_is_the_one_bought(self):
        model = FakeModel([11, 22, 33])
        got = evaluate.next_item_accuracy(model, self.frame([11, 44]), self.labels())
        assert got["n_decisions"] == 2
        assert got["top1"] == pytest.approx(0.5)

    def test_top3_is_looser_than_top1(self):
        model = FakeModel([11, 22, 33])
        got = evaluate.next_item_accuracy(model, self.frame([33, 33]), self.labels())
        assert got["top1"] == 0.0
        assert got["top3"] == pytest.approx(1.0)

    def test_the_model_sees_what_the_player_already_owns(self):
        """Each prediction starts from the player's real purchases so far."""
        model = FakeModel([11, 22])
        evaluate.next_item_accuracy(model, self.frame([11, 22, 33]), self.labels())
        assert model.seen == [frozenset(), frozenset({11}), frozenset({11, 22})]

    def test_limit_stops_early_so_two_fits_score_the_same_decisions(self):
        model = FakeModel([11])
        got = evaluate.next_item_accuracy(
            model, self.frame([11, 11, 11, 11]), self.labels(), limit=2
        )
        assert got["n_decisions"] == 2

    def test_an_unlabelled_player_falls_back_to_the_hero_wide_archetype(self):
        model = FakeModel([11])
        got = evaluate.next_item_accuracy(
            model, self.frame([11]), pd.DataFrame(columns=["match_id", "player_slot", "archetype_id"])
        )
        assert got["top1"] == pytest.approx(1.0)

    @staticmethod
    def two_players(badges: tuple[int, int]) -> pd.DataFrame:
        """Two held-out players at different badges who buy different items."""
        rows = []
        for slot, (badge, item) in enumerate(zip(badges, (11, 22))):
            rows.append(
                {
                    "match_id": slot + 1,
                    "player_slot": 0,
                    "hero_id": 7,
                    "item_id": item,
                    "buy_index": 0,
                    "buy_time_s": 60.0,
                    "average_badge": badge,
                }
            )
        return pd.DataFrame(rows)

    def test_min_badge_scores_only_the_bracket_asked_for(self):
        """With min_badge, only decisions at or above that badge are scored."""
        model = FakeModel([11])
        both = evaluate.next_item_accuracy(
            model, self.two_players((40, 100)), self.labels()
        )
        high = evaluate.next_item_accuracy(
            model, self.two_players((40, 100)), self.labels(), min_badge=80
        )
        assert both["n_decisions"] == 2
        assert high["n_decisions"] == 1
        assert high["top1"] == pytest.approx(0.0)

    def test_min_badge_on_a_frame_with_no_badge_column_scores_nothing(self):
        """With min_badge and no badge column, nothing is scored, rather than everything."""
        model = FakeModel([11])
        got = evaluate.next_item_accuracy(
            model, self.frame([11]), self.labels(), min_badge=80
        )
        assert got["n_decisions"] == 0


class TestItemColumns:
    """The chooser's two columns: most common, and defining."""

    def candidate(self, item_id: int, here: float, elsewhere: float) -> dict:
        return {"item_id": item_id, "in_cluster": here, "elsewhere": elsewhere}

    def test_defining_ranks_by_the_gap_not_by_either_rate(self):
        # Item 1 is the most bought here, but nearly as common elsewhere.
        # Item 2 is bought less here and hardly at all elsewhere.
        candidates = [self.candidate(1, 0.95, 0.90), self.candidate(2, 0.60, 0.10)]
        columns = evaluate.item_columns(population(), candidates)
        assert [c.item_id for c in columns.defining] == [2, 1]

    def test_defining_keeps_both_rates(self):
        columns = evaluate.item_columns(population(), [self.candidate(2, 0.6, 0.1)])
        assert columns.defining[0].rate == pytest.approx(0.6)
        assert columns.defining[0].elsewhere == pytest.approx(0.1)

    def test_the_cap_is_applied(self):
        candidates = [self.candidate(i, 0.5, 0.01 * i) for i in range(10)]
        columns = evaluate.item_columns(population(), candidates, cap=6)
        assert len(columns.defining) == 6

    def test_fewer_candidates_than_the_cap_are_not_padded(self):
        candidates = [self.candidate(1, 0.5, 0.1), self.candidate(2, 0.5, 0.2)]
        assert len(evaluate.item_columns(population(), candidates).defining) == 2

    def test_most_common_is_prevalence_highest_first(self):
        builds = {p: [1, 2] + ([3] if p % 2 else []) for p in range(10)}
        columns = evaluate.item_columns(purchases(builds), [])
        assert [c.item_id for c in columns.most_common] == [1, 2, 3]
        assert columns.most_common[2].rate == pytest.approx(0.5)

    def test_most_common_is_capped(self):
        builds = {p: list(range(10)) for p in range(5)}
        assert len(evaluate.item_columns(purchases(builds), [], cap=6).most_common) == 6
