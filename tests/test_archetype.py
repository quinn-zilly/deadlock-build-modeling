"""Archetype fitting and naming.

Checks which heroes split and which don't, that cluster ids stay the same
across refits, and that names are unique. Everything downstream depends on
the archetype labels.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from deadlock import archetype, assets, evaluate, semantics

ARCHETYPES = Path("data/processed/archetypes.parquet")
PURCHASES = Path("data/processed/purchases.parquet")

# Real item ids, so cost and slot type come from the real asset data.
ITEMS = assets.load_items()
WEAPON = [i for i, it in ITEMS.items() if it.slot_type == "weapon"][:6]
SPIRIT = [i for i, it in ITEMS.items() if it.slot_type == "spirit"][:6]


def build_population(
    n_per_group: int = 400, groups: list[list[int]] | None = None
) -> pd.DataFrame:
    """Players in groups, each group buying from its own item pool."""
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
    """Players who all buy the same mixed build, so there is nothing to split."""
    mixed = WEAPON[:2] + SPIRIT[:2]
    return build_population(n_per_group=n, groups=[mixed])


class TestFamilyShares:
    """Clustering features are build family shares, not shop tab shares."""

    def test_shares_sum_to_one(self):
        shares = archetype.family_shares(build_population(10))
        assert np.allclose(shares.sum(axis=1), 1.0)

    def test_columns_are_build_families(self):
        shares = archetype.family_shares(build_population(10))
        assert list(shares.columns) == list(semantics.FAMILIES)

    def test_an_item_splits_across_the_families_it_feeds(self):
        """Crushing Fists' cost is split across melee, gun, and tank."""
        crushing = next(
            i for i, it in ITEMS.items() if it.name == "Crushing Fists"
        )
        df = pd.DataFrame(
            [{"match_id": 1, "player_slot": 0, "hero_id": 1, "item_id": crushing, "buy_index": 0}]
        )
        shares = archetype.family_shares(df)
        assert shares["melee"].iloc[0] > shares["gun"].iloc[0] > 0

    def test_one_row_per_player(self):
        assert len(archetype.family_shares(build_population(50))) == 100


class TestSlotShares:
    def test_shares_sum_to_one(self):
        shares = archetype.slot_shares(build_population(10))
        assert np.allclose(shares.sum(axis=1), 1.0)

    def test_weapon_build_is_weapon_dominant(self):
        shares = archetype.slot_shares(build_population(10, [WEAPON[:4]]))
        assert (shares["share_weapon"] > 0.9).all()

    def test_weighted_by_souls_not_count(self):
        """Shares are weighted by item cost, not item count."""
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
        """Shares are not standardized. Each player's shares still sum to 1."""
        features = archetype.feature_matrix(build_population(10))
        assert np.allclose(features.sum(axis=1), 1.0)

    def test_clusters_on_families_not_slot_types(self):
        """The feature columns are the build families, not the shop tabs."""
        features = archetype.feature_matrix(build_population(10))
        assert list(features.columns) == list(semantics.FAMILIES)
        assert not any(c.startswith("share_") for c in features.columns)

    def test_excludes_ability_state(self):
        """Ability levels (`lvl_` columns) are not a clustering input.

        They made clustering worse (Ivy fell from 0.508 to 0.274). Ability
        order is a separate feature that can come in through `extra`, so this
        checks only for `lvl_` columns.
        """
        features = archetype.feature_matrix(build_population(10))
        assert not any(c.startswith("lvl_") for c in features.columns)

    def test_extra_blocks_join_on_the_player_index(self):
        base = archetype.feature_matrix(build_population(10))
        extra = pd.DataFrame(0.5, index=base.index, columns=["pt_1_l2"])
        joined = archetype.feature_matrix(build_population(10), extra)
        assert "pt_1_l2" in joined.columns
        assert len(joined) == len(base)

    def test_a_player_missing_from_an_extra_block_reads_zero(self):
        """A player missing from an extra block gets zeros, not dropped."""
        base = archetype.feature_matrix(build_population(10))
        extra = pd.DataFrame(0.5, index=base.index[:5], columns=["imb_active_1"])
        joined = archetype.feature_matrix(build_population(10), extra)
        assert len(joined) == len(base)
        assert joined["imb_active_1"].iloc[-1] == 0.0


class TestScaleBlock:
    """`scale_block` scales a block to match the family shares. It never z-scores."""

    def frame(self, value: float = 2.0, columns: int = 4) -> pd.DataFrame:
        return pd.DataFrame(
            value, index=pd.RangeIndex(10), columns=[f"c{i}" for i in range(columns)]
        )

    def test_weight_one_matches_the_family_block_mass(self):
        """At weight 1, the block's mean row sum of absolute values is 1.0, like the shares."""
        scaled = archetype.scale_block(self.frame(), 1.0)
        assert scaled.abs().sum(axis=1).mean() == pytest.approx(1.0)

    def test_weight_scales_linearly(self):
        half = archetype.scale_block(self.frame(), 0.5)
        assert half.abs().sum(axis=1).mean() == pytest.approx(0.5)

    def test_width_does_not_decide_influence(self):
        """A 12-column block and a 4-column block get the same total weight."""
        narrow = archetype.scale_block(self.frame(columns=4), 1.0)
        wide = archetype.scale_block(self.frame(columns=12), 1.0)
        assert narrow.abs().sum(axis=1).mean() == pytest.approx(
            wide.abs().sum(axis=1).mean()
        )

    def test_zero_weight_is_no_block_at_all(self):
        assert archetype.scale_block(self.frame(), 0.0) is None

    def test_an_all_zero_block_is_dropped_rather_than_dividing_by_zero(self):
        assert archetype.scale_block(self.frame(value=0.0), 1.0) is None


class TestFitHero:
    def test_splits_two_real_builds(self):
        fit = archetype.fit_hero(build_population(), hero_id=1, hero_name="Test")
        assert fit.k == 2
        assert fit.split

    def test_does_not_split_one_build(self):
        """Players who all build the same way stay one archetype."""
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
        """MIN_SEPARATION is 0.45. See its comment for why separation is the main check."""
        assert archetype.MIN_SEPARATION == 0.45

    def test_separation_is_the_weakest_pair(self):
        """Separation is the score of the least distinct pair of clusters.

        Otherwise one distinct cluster would let two near-duplicates through,
        as happened with Kelvin's two spirit clusters.
        """
        prevalence = pd.DataFrame(
            {
                "a": [1.0, 0.95, 0.0],  # 0 vs 1 differ by 0.05; 0 vs 2 by 1.0
                "b": [0.0, 0.02, 0.9],
            },
            index=[0, 1, 2],
        )
        assert archetype._separation(prevalence) == pytest.approx(0.05)

    def test_separating_item_names_what_carries_the_weakest_pair(self):
        """separating_item returns the item behind the least distinct pair's separation.

        Seeing the item shows what a split rests on. For the imbue block it
        was the imbueable items themselves.
        """
        prevalence = pd.DataFrame(
            {
                11: [1.0, 0.95, 0.0],  # 0 vs 1 differ by 0.05; 0 vs 2 by 1.0
                22: [0.0, 0.02, 0.9],
            },
            index=[0, 1, 2],
        )
        item_id, gap = archetype.separating_item(prevalence)
        assert item_id == 11
        assert gap == pytest.approx(0.05)

    def test_separating_item_is_absent_when_there_is_no_pair(self):
        prevalence = pd.DataFrame({11: [1.0]}, index=[0])
        assert archetype.separating_item(prevalence) is None

    def test_separating_item_agrees_with_the_separation_score(self):
        df = build_population()
        fit = archetype.fit_hero(df, hero_id=1, hero_name="Test")
        prevalence = archetype.cluster_prevalence(df, fit.labels)
        _, gap = archetype.separating_item(prevalence)
        assert gap == pytest.approx(fit.separation)

    def test_two_near_duplicate_clusters_do_not_split(self):
        """Two clusters that differ only slightly stay one archetype.

        Both halves buy the same core, and a tenth of one half adds one item,
        so no item's pick rate differs by more than 10 points.
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
        """Two real builds give k=2, not 3."""
        fit = archetype.fit_hero(build_population(), hero_id=1, hero_name="Test")
        assert fit.k == 2


class TestReproducibility:
    def test_same_input_same_labels(self):
        df = build_population()
        a = archetype.fit_hero(df, hero_id=1, hero_name="T").labels
        b = archetype.fit_hero(df, hero_id=1, hero_name="T").labels
        pd.testing.assert_series_equal(a, b)

    def test_cluster_zero_is_always_the_spirit_side(self):
        """Cluster 0 is always the higher-spirit cluster, so ids don't change between refits."""
        fit = archetype.fit_hero(build_population(), hero_id=1, hero_name="T")
        spirit_by_cluster = fit.centroids["spirit"]
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
    """Names come from a cluster's distinctive items, not its centroid."""

    @staticmethod
    def prevalence_favouring(item_ids: list[int]) -> pd.DataFrame:
        """A pick-rate table where cluster 0 buys `item_ids` often and cluster 1 rarely."""
        columns = sorted(set(item_ids) | set(WEAPON) | set(SPIRIT))
        rows = []
        for cluster in (0, 1):
            rows.append(
                {i: (0.9 if (i in item_ids) == (cluster == 0) else 0.05) for i in columns}
            )
        return pd.DataFrame(rows, index=[0, 1])

    def test_names_from_items_not_centroid(self):
        """A tank-heavy centroid with gun items is named gun, not tank."""
        gun = [i for i, fams in semantics.item_families().items() if "gun" in fams][:5]
        centroid = pd.Series({k: 0.1 for k in semantics.FAMILIES})
        centroid["tank"] = 0.8
        name, _ = archetype.propose_name(
            centroid, "Lash", self.prevalence_favouring(gun), 0
        )
        assert name == "Gun Lash"

    def test_melee_is_reachable(self):
        """A cluster can be named melee, even though melee items are in the weapon tab."""
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
        json.dumps(meta)  # fails if a NaN criterion isn't converted to null

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

    def test_two_accepted_names_that_collide_are_an_error(self):
        """Two identical accepted names for one hero raise an error.

        Both came from a person, so the code can't choose which to change.
        """
        with pytest.raises(ValueError, match="Ivy"):
            archetype.make_unique(
                {0: "Spirit Ivy", 1: "Gun Ivy"},
                "Ivy",
                fixed={0: "Same Name", 1: "Same Name"},
            )

    def test_an_override_cannot_collide_with_a_generated_sibling(self):
        """An accepted name equal to a sibling's generated name makes the sibling's name change.

        If overrides were applied after deduplication, they could bring back
        duplicate names like Lady Geist's.
        """
        _, _, meta = archetype.fit_all(
            build_population(), hero_names={1: "Ivy"}, overrides={}
        )
        sibling = meta["heroes"]["1"]["archetypes"][1]["name"]

        _, _, meta = archetype.fit_all(
            build_population(), hero_names={1: "Ivy"}, overrides={"1:0": sibling}
        )
        names = [a["name"] for a in meta["heroes"]["1"]["archetypes"]]
        assert len(names) == len(set(names)), names


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
def qualifier_words(name: str, hero_name: str) -> list[str]:
    """The words an archetype name puts before the hero name.

    "Gun Ivy" gives ["Gun"], "Stalker's Mark Melee Drifter" gives
    ["Stalker's", "Mark", "Melee"], and "Ivy" gives []. Asserts that the name
    ends with the hero name.
    """
    assert name.endswith(hero_name), f"{name!r} does not end in {hero_name!r}"
    return name[: -len(hero_name)].strip().split()


class TestAgainstRealData:
    @staticmethod
    def load():
        labels, meta = archetype.load()
        return labels, meta, {v.name: k for k, v in assets.load_heroes().items()}

    def test_ivy_splits(self):
        """Ivy, the original example of a hero with two builds, splits."""
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
        ],
    )
    def test_player_corrections_are_reproduced(self, hero, expected):
        """The naming rule produces every name a Deadlock player gave.

        Each was once named "Tank X" or a duplicate "Spirit X".
        """
        _, meta, heroes = self.load()
        names = {a["name"] for a in meta["heroes"][str(heroes[hero])]["archetypes"]}
        assert expected in names

    def test_archetype_names_are_unique_within_a_hero(self):
        """No two archetypes of one hero share a name.

        Lady Geist once had two clusters called "Spirit Lady Geist", so the 35%
        of players in the second one got the first one's build.
        """
        _, meta, _ = self.load()
        collisions = {}
        for entry in meta["heroes"].values():
            names = [a["name"] for a in entry["archetypes"]]
            if len(names) != len(set(names)):
                collisions[entry["hero_name"]] = names
        assert collisions == {}

    def test_every_archetype_of_a_split_hero_says_what_it_is(self):
        """No archetype name ends in a number.

        A number is the last resort in `make_unique`. Needing one suggests the
        clusters may not be different builds, so this test flags it.
        """
        _, meta, _ = self.load()
        numbered = [
            a["name"]
            for entry in meta["heroes"].values()
            for a in entry["archetypes"]
            if a["name"].rsplit(" ", 1)[-1].isdigit()
        ]
        assert numbered == []

    def test_no_hero_has_two_archetypes_sharing_a_name(self):
        """No hero has a duplicate archetype name. Zero, with no tolerance.

        This test once allowed three heroes to have duplicates, which hid the
        Lady Geist bug.
        """
        _, meta, _ = self.load()
        duplicated = {}
        for entry in meta["heroes"].values():
            named = [a["name"] for a in entry["archetypes"] if a["name"] != entry["hero_name"]]
            if len(named) != len(set(named)):
                duplicated[entry["hero_name"]] = named
        assert duplicated == {}

    def test_thin_margins_decline_to_label(self):
        """When the margin is too small, no word of the name is a family.

        The name can still have a distinguishing word from `make_unique`: an
        ability ("Ult Dynamo", "Kinetic Pulse Dynamo") or an item ("Grit
        Celeste", "Spellslinger Celeste"). Neither is a family.
        """
        _, meta, _ = self.load()
        families = set(semantics.DISPLAY.values())
        for entry in meta["heroes"].values():
            hero_name = entry["hero_name"]
            for cluster in entry["archetypes"]:
                margin = cluster.get("naming_margin", 0.0)
                if not 0 < margin < semantics.MIN_NAMING_MARGIN:
                    continue
                assert cluster["family_name"] == hero_name
                name = cluster["name"]
                claimed = [w for w in qualifier_words(name, hero_name) if w in families]
                assert not claimed, (
                    f"{name!r} claims {claimed} on a {margin:.2f} margin"
                )

    def test_venator_has_a_gun_build_and_a_hybrid(self):
        """Venator has two archetypes, one named "Gun Venator".

        A player described them as a gun build and a gun/spirit hybrid.
        """
        _, meta, heroes = self.load()
        entry = meta["heroes"][str(heroes["Venator"])]
        names = {a["name"] for a in entry["archetypes"]}
        assert "Gun Venator" in names
        assert entry["k"] == 2

    def test_venator_is_not_support(self):
        """No Venator archetype is named support.

        Its healing items heal the buyer or give fire rate, as a player pointed
        out.
        """
        _, meta, heroes = self.load()
        names = {a["name"] for a in meta["heroes"][str(heroes["Venator"])]["archetypes"]}
        assert not any(n.startswith("Support") for n in names)

    def test_yamato_splits(self):
        """Yamato splits in two. A player confirmed Yamato has a melee build."""
        _, meta, heroes = self.load()
        assert meta["heroes"][str(heroes["Yamato"])]["k"] == 2

    def test_hybrid_labels_are_rare(self):
        """At most 8 archetypes are named "Hybrid-"."""
        _, meta, _ = self.load()
        hybrids = sum(
            1
            for e in meta["heroes"].values()
            for a in e["archetypes"]
            if a["name"].startswith("Hybrid-")
        )
        assert hybrids <= 8

    def test_tank_no_longer_dominates(self):
        """At most 3 names say Tank, and at least 4 say Melee.

        Naming from shop tabs gave 10 "Tank" names, most of them wrong.

        A family word counts anywhere before the hero name, so "Stalker's Mark
        Melee Drifter" counts as Melee. "Hybrid-Melee" is one word and doesn't
        count; `test_hybrid_labels_are_rare` covers hybrids. Measured
        2026-09-15: Tank 3, Melee 5.
        """
        _, meta, _ = self.load()
        claimed: list[str] = []
        for e in meta["heroes"].values():
            hero_name = e["hero_name"]
            for a in e["archetypes"]:
                if a["name"] == hero_name:
                    continue
                claimed += qualifier_words(a["name"], hero_name)
        assert claimed.count("Tank") <= 3
        assert claimed.count("Melee") >= 4

    @pytest.mark.parametrize("hero", ["Wraith", "Calico"])
    def test_heroes_with_one_build_do_not_split(self, hero):
        """Wraith and Calico stay one archetype.

        Calico's best split has a 3% cluster, below MIN_CLUSTER_SHARE. Whether
        that cluster is a real rare build is issue #38.
        """
        _, meta, heroes = self.load()
        assert meta["heroes"][str(heroes[hero])]["k"] == 1

    def test_dynamo_splits_on_families(self):
        """Dynamo splits in two with family shares (shop-tab shares didn't split it).

        A player confirmed the larger cluster, with Refresher 76%, Warp Stone
        65%, and Duration Extender 64%, is the ult build.
        """
        _, meta, heroes = self.load()
        assert meta["heroes"][str(heroes["Dynamo"])]["k"] == 2

    def test_every_player_is_labelled(self):
        labels, _, _ = self.load()
        assert len(labels) > 290_000

    def test_archetype_ids_start_at_zero(self):
        labels, _, _ = self.load()
        by_hero = labels.groupby("hero_id")["archetype_id"]
        assert (by_hero.min() == 0).all()

    @pytest.mark.skipif(not PURCHASES.exists(), reason="needs purchases.parquet")
    def test_splitting_recovers_hidden_staples(self):
        """All Ivy players together have one item above 70%; each archetype has several.

        Averaging two builds hides the staples of both.
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


class TestNameOverridesFile:
    """data/archetype_names.json, the checked-in names a person accepted.

    These override the proposed names and must survive a refit.
    """

    def test_the_shipped_file_is_valid_and_applied(self):
        overrides = archetype.load_name_overrides()
        assert overrides, "no accepted names are recorded"
        _, meta = archetype.load()
        for key, name in overrides.items():
            hero_id, archetype_id = key.split(":")
            entry = meta["heroes"].get(hero_id)
            if entry is None:
                continue
            matching = [
                a for a in entry["archetypes"]
                if int(a["archetype_id"]) == int(archetype_id)
            ]
            assert matching, f"{key} names no cluster of hero {hero_id}"
            assert matching[0]["name"] == name

    def test_comment_keys_are_not_names(self, tmp_path):
        """Keys starting with an underscore are notes, not names."""
        path = tmp_path / "names.json"
        path.write_text('{"_note": "why", "31:2": "Gun Lash"}')
        assert archetype.load_name_overrides(path) == {"31:2": "Gun Lash"}
