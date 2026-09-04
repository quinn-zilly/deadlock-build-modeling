"""Archetype fitting: what must split, what must not, and what must be stable.

The design guards here are as important as the numeric ones. A fit that
silently permutes its own labels on refit, or that splits a hero with one real
build, poisons everything downstream.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from deadlock import archetype, assets, evaluate

ARCHETYPES = Path("data/processed/archetypes.parquet")
PURCHASES = Path("data/processed/purchases.parquet")

# Real ids, so cost and slot_type come from the actual asset table.
ITEMS = assets.load_items()
WEAPON = [i for i, it in ITEMS.items() if it.slot_type == "weapon"][:6]
SPIRIT = [i for i, it in ITEMS.items() if it.slot_type == "spirit"][:6]


def build_population(
    n_per_group: int = 400, groups: list[list[int]] | None = None
) -> pd.DataFrame:
    """Players drawn from distinct item pools, one pool per group."""
    groups = groups or [WEAPON[:4], SPIRIT[:4]]
    rows = []
    player = 0
    for items in groups:
        for _ in range(n_per_group):
            for position, item in enumerate(items):
                rows.append(
                    {
                        "match_id": 1000 + player,
                        "player_slot": player % 12,
                        "hero_id": 1,
                        "item_id": item,
                        "buy_index": position,
                    }
                )
            player += 1
    return pd.DataFrame(rows)


def one_population(n: int = 800) -> pd.DataFrame:
    """Players who all buy the same mixed build -- no real split exists."""
    mixed = WEAPON[:2] + SPIRIT[:2]
    return build_population(n_per_group=n, groups=[mixed])


class TestSlotShares:
    def test_shares_sum_to_one(self):
        shares = archetype.slot_shares(build_population(10))
        assert np.allclose(shares.sum(axis=1), 1.0)

    def test_weapon_build_is_weapon_dominant(self):
        shares = archetype.slot_shares(build_population(10, [WEAPON[:4]]))
        assert (shares["share_weapon"] > 0.9).all()

    def test_weighted_by_souls_not_count(self):
        """A build's character is set by where its souls went."""
        cheap = min(WEAPON, key=lambda i: ITEMS[i].cost)
        dear = max(SPIRIT, key=lambda i: ITEMS[i].cost)
        df = pd.DataFrame(
            [
                {"match_id": 1, "player_slot": 0, "hero_id": 1, "item_id": cheap, "buy_index": 0},
                {"match_id": 1, "player_slot": 0, "hero_id": 1, "item_id": cheap, "buy_index": 1},
                {"match_id": 1, "player_slot": 0, "hero_id": 1, "item_id": dear, "buy_index": 2},
            ]
        )
        shares = archetype.slot_shares(df)
        assert shares["share_spirit"].iloc[0] > shares["share_weapon"].iloc[0]

    def test_one_row_per_player(self):
        assert len(archetype.slot_shares(build_population(50))) == 100


class TestFeatureMatrix:
    def test_is_unstandardized(self):
        """Z-scoring three fractions that sum to 1 degrades every hero tried."""
        features = archetype.feature_matrix(build_population(10, [WEAPON[:4]]))
        assert (features["share_weapon"] > 0.9).all()

    def test_columns_are_the_three_slot_types(self):
        features = archetype.feature_matrix(build_population(10))
        assert list(features.columns) == archetype.FEATURE_COLUMNS

    def test_excludes_abilities(self):
        """Abilities measurably degrade the clustering; they are not inputs."""
        features = archetype.feature_matrix(build_population(10))
        assert not any(c.startswith("lvl_") for c in features.columns)


class TestFitHero:
    def test_splits_two_real_builds(self):
        fit = archetype.fit_hero(build_population(), hero_id=1, hero_name="Test")
        assert fit.k == 2
        assert fit.split

    def test_does_not_split_one_build(self):
        """The failure that matters: inventing a distinction that is not there."""
        fit = archetype.fit_hero(one_population(), hero_id=1, hero_name="Test")
        assert fit.k == 1
        assert not fit.split

    def test_thin_hero_stays_single(self):
        fit = archetype.fit_hero(build_population(50), hero_id=1, hero_name="Test")
        assert fit.k == 1
        assert "players" in fit.reason

    def test_refusal_explains_itself(self):
        fit = archetype.fit_hero(one_population(), hero_id=1, hero_name="Test")
        assert "fails" in fit.reason

    def test_acceptance_explains_itself(self):
        fit = archetype.fit_hero(build_population(), hero_id=1, hero_name="Test")
        assert "clears every criterion" in fit.reason

    def test_labels_cover_every_player(self):
        df = build_population()
        fit = archetype.fit_hero(df, hero_id=1, hero_name="Test")
        assert len(fit.labels) == len(df[["match_id", "player_slot"]].drop_duplicates())

    def test_separation_leads_over_silhouette(self):
        """Separation is what matches judgement; silhouette would split Dynamo."""
        assert archetype.MIN_SEPARATION == 0.45

    def test_prefers_smaller_k(self):
        """Two real builds must not be cut into three."""
        fit = archetype.fit_hero(build_population(), hero_id=1, hero_name="Test")
        assert fit.k == 2


class TestReproducibility:
    def test_same_input_same_labels(self):
        df = build_population()
        a = archetype.fit_hero(df, hero_id=1, hero_name="T").labels
        b = archetype.fit_hero(df, hero_id=1, hero_name="T").labels
        pd.testing.assert_series_equal(a, b)

    def test_cluster_zero_is_always_the_spirit_side(self):
        """KMeans indices are arbitrary; without canonical order every
        downstream artifact permutes silently on refit."""
        fit = archetype.fit_hero(build_population(), hero_id=1, hero_name="T")
        spirit_by_cluster = fit.centroids["share_spirit"]
        assert spirit_by_cluster.loc[0] == spirit_by_cluster.max()

    def test_seed_is_pinned(self):
        assert archetype.ARCHETYPE_SEED == 0


class TestClusterPrevalence:
    def test_rates_are_within_cluster(self):
        df = build_population()
        fit = archetype.fit_hero(df, hero_id=1, hero_name="T")
        prevalence = archetype.cluster_prevalence(df, fit.labels)
        assert ((prevalence >= 0) & (prevalence <= 1)).all().all()

    def test_separated_pools_show_extreme_rates(self):
        df = build_population()
        fit = archetype.fit_hero(df, hero_id=1, hero_name="T")
        prevalence = archetype.cluster_prevalence(df, fit.labels)
        assert prevalence.max().max() > 0.95


class TestDiscriminativeItems:
    def test_reports_both_rates(self):
        df = build_population()
        fit = archetype.fit_hero(df, hero_id=1, hero_name="T")
        prevalence = archetype.cluster_prevalence(df, fit.labels)
        top = archetype.discriminative_items(prevalence, 0, top=3)
        assert {"in_cluster", "elsewhere"} <= set(top.columns)

    def test_sorted_by_lift(self):
        df = build_population()
        fit = archetype.fit_hero(df, hero_id=1, hero_name="T")
        prevalence = archetype.cluster_prevalence(df, fit.labels)
        lifts = archetype.discriminative_items(prevalence, 0)["lift"].tolist()
        assert lifts == sorted(lifts, reverse=True)

    def test_single_cluster_returns_empty(self):
        empty = archetype.discriminative_items(pd.DataFrame([[0.5]]), 0)
        assert empty.empty


class TestProposeName:
    @pytest.mark.parametrize(
        "dominant,expected",
        [("share_spirit", "Spirit Ivy"), ("share_weapon", "Gun Ivy"), ("share_vitality", "Tank Ivy")],
    )
    def test_names_from_dominant_slot(self, dominant, expected):
        centroid = pd.Series({k: 0.1 for k in archetype.FEATURE_COLUMNS})
        centroid[dominant] = 0.8
        assert archetype.propose_name(centroid, "Ivy", pd.DataFrame(), 0) == expected


class TestFitAll:
    def test_labels_every_player(self):
        df = build_population()
        labels, fits, meta = archetype.fit_all(df, hero_names={1: "Test"}, overrides={})
        assert len(labels) == len(df[["match_id", "player_slot"]].drop_duplicates())

    def test_meta_records_criteria(self):
        _, _, meta = archetype.fit_all(build_population(), hero_names={1: "T"}, overrides={})
        assert "separation" in meta["heroes"]["1"]["criteria"]

    def test_meta_is_json_safe(self):
        import json

        _, _, meta = archetype.fit_all(one_population(), hero_names={1: "T"}, overrides={})
        json.dumps(meta)  # NaN criteria must serialize as null

    def test_overrides_replace_proposed_names(self):
        _, _, meta = archetype.fit_all(
            build_population(), hero_names={1: "Ivy"}, overrides={"1:0": "My Name"}
        )
        names = [a["name"] for a in meta["heroes"]["1"]["archetypes"]]
        assert "My Name" in names

    def test_proposed_name_is_kept_alongside_override(self):
        _, _, meta = archetype.fit_all(
            build_population(), hero_names={1: "Ivy"}, overrides={"1:0": "My Name"}
        )
        first = meta["heroes"]["1"]["archetypes"][0]
        assert first["proposed_name"] != "My Name"


class TestRoundTrip:
    def test_save_and_load(self, tmp_path):
        labels, _, meta = archetype.fit_all(
            build_population(), hero_names={1: "T"}, overrides={}
        )
        archetype.save(labels, meta, out_dir=tmp_path)
        back_labels, back_meta = archetype.load(tmp_path)
        assert len(back_labels) == len(labels)
        assert back_meta["heroes"]["1"]["k"] == meta["heroes"]["1"]["k"]


@pytest.mark.data
@pytest.mark.skipif(not ARCHETYPES.exists(), reason="needs archetypes.parquet")
class TestAgainstRealData:
    @staticmethod
    def load():
        labels, meta = archetype.load()
        return labels, meta, {v.name: k for k, v in assets.load_heroes().items()}

    def test_ivy_splits(self):
        """The hero the whole design rests on."""
        _, meta, heroes = self.load()
        assert meta["heroes"][str(heroes["Ivy"])]["k"] == 2

    def test_ivy_names_read_as_gun_and_spirit(self):
        _, meta, heroes = self.load()
        names = {a["name"] for a in meta["heroes"][str(heroes["Ivy"])]["archetypes"]}
        assert names == {"Gun Ivy", "Spirit Ivy"}

    @pytest.mark.parametrize("hero", ["Haze", "Dynamo", "Wraith"])
    def test_heroes_with_one_build_do_not_split(self, hero):
        _, meta, heroes = self.load()
        assert meta["heroes"][str(heroes[hero])]["k"] == 1

    def test_every_player_is_labelled(self):
        labels, _, _ = self.load()
        assert len(labels) > 290_000

    def test_archetype_ids_start_at_zero(self):
        labels, _, _ = self.load()
        by_hero = labels.groupby("hero_id")["archetype_id"]
        assert (by_hero.min() == 0).all()

    @pytest.mark.skipif(not PURCHASES.exists(), reason="needs purchases.parquet")
    def test_splitting_recovers_hidden_staples(self):
        """Pooled, Ivy has one item over 70%; split, each build has several.

        This is the concrete payoff of conditioning on archetype -- averaging
        two builds hides the staples of both.
        """
        labels, _, heroes = self.load()
        hero_id = heroes["Ivy"]
        purchases = pd.read_parquet(
            PURCHASES, columns=["match_id", "player_slot", "hero_id", "item_id", "buy_index"]
        )
        ivy = purchases[purchases.hero_id == hero_id]
        pooled = evaluate.prevalence_gate([], ivy, hero_id=hero_id)

        tagged = ivy.merge(
            labels[labels.hero_id == hero_id][["match_id", "player_slot", "archetype_id"]],
            on=["match_id", "player_slot"],
        )
        per_archetype = [
            len(evaluate.prevalence_gate([], g, hero_id=hero_id, archetype_id=int(a)).staples)
            for a, g in tagged.groupby("archetype_id")
        ]
        assert len(pooled.staples) <= 1
        assert all(count > 1 for count in per_archetype)
