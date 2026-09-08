"""The gate that would have caught the last failure, and the metrics behind it.

Two tiers. The unit tier pins the gate logic on synthetic data and always
runs. The data tier pins the actual Wraith outcome against the real table and
skips when it is absent -- see `pytest.ini_options` markers in pyproject.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from deadlock import evaluate

PURCHASES = Path("data/processed/purchases.parquet")

# The nine items >=70% of Wraith players buy, measured 2026-09-04 on 25k
# matches. docs/DIAGNOSIS.md records that the old planner recommended none of
# them while every aggregate metric passed.
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
]


def purchases(builds: dict[int, list[int]]) -> pd.DataFrame:
    """A purchase table from {player -> ordered item ids}."""
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
    """A population where `staple` is near-universal and item 99 is rare."""
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
        """The gate's whole purpose: say which item is missing, by name."""
        result = evaluate.prevalence_gate([2, 3], population(), hero_id=7)
        assert not result.passed
        assert 1 in result.missing
        assert result.missing[1] == pytest.approx(0.9975, abs=1e-3)

    def test_passes_when_staples_present(self):
        assert evaluate.prevalence_gate([1, 2, 3], population(), hero_id=7).passed

    def test_ignores_rare_items(self):
        """A 0.25% item is a choice, not a staple; omitting it is not an error."""
        result = evaluate.prevalence_gate([1, 2, 3], population(), hero_id=7)
        assert 99 not in result.staples

    def test_extra_items_do_not_fail_it(self):
        assert evaluate.prevalence_gate([1, 2, 3, 99, 77], population(), hero_id=7).passed

    def test_thin_cell_is_inconclusive_not_passing(self):
        """A gate that passes on no evidence is how the last pipeline stayed green."""
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
        """Tau on three shared items is not evidence; callers must see that."""
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
        """Re-buying is not a legal move, so an owned item is never a prediction."""
        df = purchases({p: [1, 2, 3] for p in range(80)})
        result = evaluate.score_baselines(df, df)
        assert set(result["baseline"]) == {"popularity", "positional", "bigram"}
        assert (result["n_decisions"] == 240).all()


@pytest.mark.data
@pytest.mark.skipif(not PURCHASES.exists(), reason="needs purchases.parquet")
class TestMembershipVsPlayers:
    """Membership must be scored against players, not the median-order list."""

    CORE = list(range(1, 9))
    TAIL = list(range(100, 108))

    @classmethod
    def cell(cls, n: int = 200) -> pd.DataFrame:
        """Players sharing 8 core items and picking 4 tail items unevenly.

        Two properties matter, and the first two versions of this fixture each
        missed one. The disagreement must fall inside the Jaccard@12 window --
        players who differ only from buy 13 onward are identical to this
        metric. And the tail must be *skewed*: when every player draws tail
        items uniformly, a consensus build and another player are equally close,
        so the fixture cannot show the effect it exists to show.
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
        """The k most prevalent items -- what a good build should look like."""
        return (
            cell.drop_duplicates(["match_id", "player_slot", "item_id"])
            .item_id.value_counts()
            .index[:k]
            .tolist()
        )

    def test_a_consensus_build_beats_the_ceiling(self):
        """The point of the metric: a consensus build beats any one player.

        Players agree on a core and disagree on a skewed tail, so two players
        overlap less than the consensus overlaps either of them. A metric that
        cannot show this cannot tell a good build from a bad one -- which is
        exactly how J@12 0.143 went unquestioned.
        """
        cell = self.cell()
        result = evaluate.membership_vs_players(self.consensus(cell), cell)
        assert result.generated > result.ceiling
        assert result.ratio > 1.0

    def test_identical_players_give_a_ceiling_of_one(self):
        """A population with no disagreement has nothing above it to reach."""
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
        """Jaccard@12 over a 5-buy match measures match length, not the build."""
        builds = {p: list(range(1, 13)) for p in range(10)}
        builds.update({50 + p: [1, 2, 3] for p in range(10)})
        assert len(evaluate.player_sequences(purchases(builds))) == 10

    def test_median_order_reference_understates_membership(self):
        """The bug this metric replaces, pinned on real data.

        `population_order`'s top 12 are the items bought earliest -- cheap
        components that are absorbed. Scoring against it reported J@12 0.143;
        against real players the same builds beat the player-vs-player ceiling.
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
    """The regression the pivot exists to prevent."""

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
        """docs/DIAGNOSIS.md: the old planner chose none of Wraith's staples.

        If this ever passes, the gate has lost the sensitivity that motivated
        the entire pivot.
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
        """Pins the staple set itself, so a patch shift is visible."""
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
    """A model that always ranks `ranking`, so scoring is checkable by hand."""

    def __init__(self, ranking: list[int]):
        self.ranking = ranking
        self.seen: list[frozenset[int]] = []

    def distribution(self, state):
        self.seen.append(state.owned_item_ids)
        ids = np.array(self.ranking, dtype=np.int64)
        probability = np.linspace(1.0, 0.1, len(ids))
        return ids, probability

    def evidence(self, state, item_id):
        """The backoff trace, which this stand-in has nothing to say about."""
        return None


class TestNextItemAccuracy:
    """Teacher-forced next-item accuracy, shared by every script that scores.

    Two archetype fits are only comparable when they are scored on the same
    held-out decisions in the same run, so the loop lives here rather than in
    whichever script measured it last.
    """

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
        """Teacher forcing: each decision is made from the real prefix."""
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
