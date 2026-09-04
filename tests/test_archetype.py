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

from deadlock import archetype, assets, evaluate, semantics

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

    def test_separation_is_the_weakest_pair(self):
        """One distinct cluster must not drag near-duplicates through with it.

        Kelvin's support build carried two spirit clusters that share identical
        ability investment and differ on no item by more than 23 points.
        """
        prevalence = pd.DataFrame(
            {
                "a": [1.0, 0.95, 0.0],  # 0 vs 1 differ by 0.05; 0 vs 2 by 1.0
                "b": [0.0, 0.02, 0.9],
            },
            index=[0, 1, 2],
        )
        assert archetype._separation(prevalence) == pytest.approx(0.05)

    def test_two_near_duplicate_clusters_do_not_split(self):
        """Differing only slightly is one archetype on a gradient, not two.

        Both halves buy the same core; a tenth of one half adds one extra item,
        so no item's prevalence differs by more than 10 points.
        """
        core = WEAPON[:3]
        rows = []
        for player in range(800):
            items = list(core)
            if player < 40:
                items.append(SPIRIT[0])
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
        fit = archetype.fit_hero(pd.DataFrame(rows), hero_id=1, hero_name="T")
        assert fit.k == 1

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
    """Naming reads the cluster's distinguishing items, not its centroid."""

    @staticmethod
    def prevalence_favouring(item_ids: list[int]) -> pd.DataFrame:
        """Cluster 0 buys `item_ids` heavily; cluster 1 barely touches them."""
        columns = sorted(set(item_ids) | set(WEAPON) | set(SPIRIT))
        rows = []
        for cluster in (0, 1):
            rows.append(
                {i: (0.9 if (i in item_ids) == (cluster == 0) else 0.05) for i in columns}
            )
        return pd.DataFrame(rows, index=[0, 1])

    def test_names_from_items_not_centroid(self):
        """A vitality-heavy centroid must not force "Tank" when items say gun."""
        gun = [i for i, fams in semantics.item_families().items() if "gun" in fams][:5]
        centroid = pd.Series({k: 0.1 for k in archetype.FEATURE_COLUMNS})
        centroid["share_vitality"] = 0.8
        name, _ = archetype.propose_name(
            centroid, "Lash", self.prevalence_favouring(gun), 0
        )
        assert name == "Gun Lash"

    def test_melee_is_reachable(self):
        """Melee items are weapon-slotted, so slot type could never name this."""
        melee = [i for i, fams in semantics.item_families().items() if fams.get("melee", 0) >= 6]
        name, _ = archetype.propose_name(
            pd.Series(dtype=float), "Abrams", self.prevalence_favouring(melee), 0
        )
        assert name == "Melee Abrams"

    def test_single_cluster_gets_the_bare_hero_name(self):
        single = pd.DataFrame([{1: 0.9}], index=[0])
        assert archetype.propose_name(pd.Series(dtype=float), "Haze", single, 0) == (
            "Haze",
            0.0,
        )

    def test_returns_a_margin(self):
        gun = [i for i, fams in semantics.item_families().items() if "gun" in fams][:5]
        _, margin = archetype.propose_name(
            pd.Series(dtype=float), "Lash", self.prevalence_favouring(gun), 0
        )
        assert margin >= semantics.MIN_NAMING_MARGIN


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
        assert meta["heroes"][str(heroes["Ivy"])]["k"] >= 2

    def test_ivy_has_a_gun_and_a_spirit_build(self):
        _, meta, heroes = self.load()
        names = {a["name"] for a in meta["heroes"][str(heroes["Ivy"])]["archetypes"]}
        assert {"Gun Ivy", "Spirit Ivy"} <= names

    @pytest.mark.parametrize(
        "hero,expected",
        [
            ("Lash", "Gun Lash"),
            ("Abrams", "Melee Abrams"),
            ("Sinclair", "Melee Sinclair"),
            ("Kelvin", "Support Kelvin"),
            ("Bebop", "Gun Bebop"),
            ("Calico", "Melee Calico"),
            ("Yamato", "Melee Yamato"),
        ],
    )
    def test_player_corrections_are_reproduced(self, hero, expected):
        """Every name a Deadlock player supplied, back from the rule.

        Each of these was previously "Tank X" or a duplicate "Spirit X".
        """
        _, meta, heroes = self.load()
        names = {a["name"] for a in meta["heroes"][str(heroes[hero])]["archetypes"]}
        assert expected in names

    def test_duplicate_names_are_rare(self):
        """The old rule gave one hero three clusters all called "Spirit X".

        Family naming cannot separate two builds of the SAME family, and three
        heroes genuinely have such a pair: Venator has two gun builds (one
        hybrid gun/spirit, one bullet-lifesteal), Celeste two spirit, Drifter
        two. This bounds the problem rather than forbidding it. Splitting those
        needs ability focus -- "ult" versus "stomp" -- which is not
        implemented.
        """
        _, meta, _ = self.load()
        duplicated = 0
        for entry in meta["heroes"].values():
            named = [a["name"] for a in entry["archetypes"] if a["name"] != entry["hero_name"]]
            if len(named) != len(set(named)):
                duplicated += 1
        assert duplicated <= 3

    def test_thin_margins_decline_to_label(self):
        """A near-tie is a coin flip; the rule keeps the bare hero name."""
        _, meta, _ = self.load()
        for entry in meta["heroes"].values():
            for cluster in entry["archetypes"]:
                margin = cluster.get("naming_margin", 0.0)
                if 0 < margin < semantics.MIN_NAMING_MARGIN:
                    assert cluster["name"] == entry["hero_name"]

    def test_venator_is_not_support(self):
        """A player correction: Venator's healing items are self-sustain for a
        gun carry -- Mystic/Radiant Regeneration heal you for dealing spirit
        damage, and Healing Tempo grants fire rate. Reading them as support
        made a hybrid gun build look like a support build."""
        _, meta, heroes = self.load()
        names = {a["name"] for a in meta["heroes"][str(heroes["Venator"])]["archetypes"]}
        assert not any(n.startswith("Support") for n in names)

    def test_tank_no_longer_dominates(self):
        """Slot-share naming produced 10 "Tank" labels, most of them wrong."""
        _, meta, _ = self.load()
        labels = [
            a["name"].split()[0]
            for e in meta["heroes"].values()
            for a in e["archetypes"]
            if a["name"] != e["hero_name"]
        ]
        assert labels.count("Tank") <= 3
        assert labels.count("Melee") >= 4

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
