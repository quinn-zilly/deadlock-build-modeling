"""Build archetypes: the different ways one hero gets played.

Ivy is either a gun carry or a spirit support. Those builds share few items,
and a recommendation averaged across both serves neither -- the same error as
the discarded paired design smearing a niche item across 38 heroes, one level
down. So archetype is a conditioning variable, fitted per hero.

Not every hero has one. Haze and Dynamo do not split: their k=2 partitions are
arbitrary slices of a single population. Forcing k=2 everywhere would invent
distinctions that do not exist, so k is selected per hero and 1 is an allowed
answer.

**The feature vector is souls-weighted BUILD FAMILY shares** -- how a player's
souls divided across gun, spirit, melee, support, tank, sustain, control and
mobility. Never item identities: clustering on those finds "who bought item X"
groups that are tautological with what the model then predicts. Keeping the
input coarse is what makes the readout ("these two clusters differ by 53 points
on Extra Charge") a falsifiable claim rather than a restatement of the input.

It used to be slot-type shares -- which shop tab the souls went to. That was
wrong for the same reason it was wrong for naming: half the items sit in a tab
that does not match what they do. Switching to families raised mean cluster
separation from 0.321 to 0.429 across 38 heroes and found real splits on six
heroes where slot shares found none, Dynamo among them.

**Abilities are deliberately excluded, against the original design.** Measured
on every hero tried, adding ability levels monotonically degrades the
clustering -- Ivy falls 0.508 -> 0.421 -> 0.361 -> 0.274 as ability weight goes
0 -> 0.25 -> 0.5 -> 1.0, and the same holds for Haze, Dynamo, Bebop and Wraith.
The reason is visible directly: between Ivy's two item clusters the largest
mean ability-level gap is 0.48 of 4. Abilities do vary with archetype, but far
too weakly to carry four extra dimensions, so they add noise. They remain
available in `abilities.py` for the sequence model.

Shares are left unstandardized. They already sum to 1, so they are commensurate;
z-scoring inflates whichever family happens to have low variance for that hero
and distorts the geometry.

**Acceptance is not silhouette alone.** A silhouette score is exactly the kind
of aggregate that passed while the old pipeline was wrong, so a split must also
reproduce itself on held-out data, separate some item by a visible margin, and
leave both sides large enough to model. All four, or k=1.
"""

from __future__ import annotations

import itertools
import json
import math
from typing import Iterable
import logging
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.exceptions import ConvergenceWarning
from sklearn.metrics import silhouette_score

from . import assets, semantics, splits

log = logging.getLogger(__name__)

ARCHETYPE_SEED = 0
CANDIDATE_K = (2, 3)

# Acceptance criteria. A split must clear every one of them.
#
# Separation leads, and silhouette is only a secondary guard, because
# separation is the criterion that matches judgement: it ranks Lady Geist
# (0.85), Ivy (0.63) and Bebop (0.62) above Dynamo (0.35), Haze (0.23) and
# Wraith (0.22), while silhouette puts Dynamo (0.42) above Ivy-like heroes and
# would split it. Separation is also the criterion a player can check by eye --
# "these two builds differ by 63 points on Extra Charge" is a claim about the
# game, where a silhouette coefficient is a claim about geometry.
MIN_SEPARATION = 0.45
# A floor, not a criterion. Silhouette degrades with dimensionality, and the
# family space has eight dimensions where the old slot space had three:
# splits that scored 0.4-0.7 there score 0.19-0.61 here for the same data. A
# 0.35 bar would reject 21 of the 25 heroes that clear separation and size.
# Separation is what matches judgement, so silhouette only catches fits with
# no geometric structure at all.
MIN_SILHOUETTE = 0.15
MIN_REPLICATION = 0.90
# A build nobody plays is not a build. The point of the project is to
# recommend how players -- especially good ones -- actually build, so a
# cluster has to be a real minority playstyle rather than one item pattern.
#
# 12% admits melee Sinclair (14.6%), a niche but genuine playstyle. It excludes
# Calico's 3.1% cluster, which separates at 0.92 purely on Lifestrike and
# Spirit Snatch -- items she buys in every build, which does not make those
# builds melee.
MIN_CLUSTER_SHARE = 0.12

# Below this a hero cannot support the fit at all.
MIN_HERO_PLAYERS = 600

# Human-accepted names, checked in so they survive a refit.
NAMES_PATH = Path("data/archetype_names.json")

SLOT_TYPES = ("weapon", "vitality", "spirit")

# Clustering runs on build families, not slot types. `slot_shares` is kept
# because the review sheet still reports souls-by-shop-tab for reference.
def _feature_columns() -> list[str]:
    from . import semantics

    return list(semantics.FAMILIES)


@dataclass
class ArchetypeFit:
    """The outcome of fitting one hero, and why it was accepted or refused."""

    hero_id: int
    hero_name: str
    k: int
    n: int
    labels: pd.Series = field(default_factory=lambda: pd.Series(dtype=int))
    centroids: pd.DataFrame = field(default_factory=pd.DataFrame)
    silhouette: float = float("nan")
    replication: float = float("nan")
    separation: float = float("nan")
    smallest_share: float = float("nan")
    reason: str = ""

    @property
    def split(self) -> bool:
        return self.k > 1

    def criteria(self) -> dict[str, tuple[float, float, bool]]:
        """Each criterion as (value, threshold, passed), for the review sheet."""
        return {
            "silhouette": (self.silhouette, MIN_SILHOUETTE, self.silhouette >= MIN_SILHOUETTE),
            "replication": (self.replication, MIN_REPLICATION, self.replication >= MIN_REPLICATION),
            "separation": (self.separation, MIN_SEPARATION, self.separation >= MIN_SEPARATION),
            "smallest share": (
                self.smallest_share, MIN_CLUSTER_SHARE, self.smallest_share >= MIN_CLUSTER_SHARE,
            ),
        }


def slot_shares(purchases: pd.DataFrame, items: dict[int, assets.Item] | None = None) -> pd.DataFrame:
    """Souls-weighted share of each slot type in a player's purchases.

    Weighted by cost rather than counted, because a build's character is set by
    where its souls went. Counting would let six cheap vitality items outvote
    three expensive spirit ones.
    """
    items = assets.load_items() if items is None else items
    df = purchases.assign(
        cost=purchases["item_id"].map({i: it.cost for i, it in items.items()}),
        slot=purchases["item_id"].map({i: it.slot_type for i, it in items.items()}),
    ).dropna(subset=["slot"])

    keys = ["match_id", "player_slot"]
    spend = df.groupby(keys + ["slot"])["cost"].sum().unstack("slot")
    spend = spend.reindex(columns=list(SLOT_TYPES)).fillna(0.0)
    total = spend.sum(axis=1).replace(0.0, np.nan)
    shares = spend.div(total, axis=0).fillna(0.0)
    shares.columns = [f"share_{c}" for c in shares.columns]
    return shares


def family_shares(
    purchases: pd.DataFrame, items: dict[int, assets.Item] | None = None
) -> pd.DataFrame:
    """Souls-weighted share of each BUILD FAMILY in a player's purchases.

    The semantic replacement for `slot_shares`. Slot type is a shop tab, and
    half the items sit in a tab that does not match what they do; a build
    family is what the item is for. Each item divides its cost across the
    families it feeds, so Crushing Fists contributes mostly to melee and a
    little to gun and tank.

    Measured against slot shares over 38 heroes, this raises mean cluster
    separation from 0.321 to 0.429 and finds real splits on six heroes where
    slot shares found none -- Dynamo among them, which a player had named as
    having distinct builds.
    """
    from . import semantics

    items = assets.load_items() if items is None else items
    families = semantics.item_families()
    columns = list(semantics.FAMILIES)

    df = purchases.assign(cost=purchases["item_id"].map({i: it.cost for i, it in items.items()}))
    df = df[df["cost"].fillna(0) > 0]

    keys = ["match_id", "player_slot"]
    weights = []
    for family in columns:
        share = df["item_id"].map(
            lambda item_id, f=family: _family_weight(families, item_id, f)
        )
        weights.append((df["cost"] * share).rename(family))

    spend = pd.concat([df[keys]] + weights, axis=1).groupby(keys)[columns].sum()
    total = spend.sum(axis=1).replace(0.0, np.nan)
    return spend.div(total, axis=0).dropna()


def _family_weight(
    families: dict[int, dict[str, int]], item_id: int, family: str
) -> float:
    """What fraction of one item's cost belongs to a family."""
    scores = families.get(item_id)
    if not scores:
        return 0.0
    total = sum(scores.values())
    return scores.get(family, 0) / total if total else 0.0


def partial_family_shares(
    item_ids: Iterable[int], items: dict[int, assets.Item] | None = None
) -> pd.Series:
    """Build-family shares for an in-progress build.

    The same arithmetic as `family_shares`, over a bare list of items rather
    than a purchase frame -- the clustering is fit on finished builds, but
    inference has to work on partial ones.
    """
    from . import semantics

    items = assets.load_items() if items is None else items
    families = semantics.item_families()
    columns = list(semantics.FAMILIES)

    spend = {family: 0.0 for family in columns}
    for item_id in item_ids:
        item = items.get(int(item_id))
        if item is None or not item.cost:
            continue
        for family in columns:
            spend[family] += item.cost * _family_weight(families, int(item_id), family)

    total = sum(spend.values())
    if total <= 0:
        return pd.Series({family: 0.0 for family in columns})
    return pd.Series({family: value / total for family, value in spend.items()})


def archetype_posterior(
    item_ids: Iterable[int],
    hero_id: int,
    meta: dict,
    *,
    temperature: float = 0.10,
) -> dict[int, float]:
    """How likely each archetype is, given the items bought so far.

    Soft nearest-centroid rather than a hard assignment, because early in a
    match the evidence genuinely does not identify the build. Measured on Ivy
    (k=3, so a 33% floor), assignment accuracy runs 55% after 3 buys, 57% after
    5, 64% after 8 and 79% after 12. Committing to one archetype at buy 3 would
    be wrong nearly half the time, so the posterior stays spread and the
    advisor shows the split.

    With nothing bought, the honest answer is the population share of each
    archetype -- how often people play it -- not a flat prior.

    The default temperature is calibrated: accuracy is flat across 0.05-0.40
    (the ranking barely moves), so it is chosen by log-loss at 8 buys, which
    is minimised at 0.10. That matters because the posterior is displayed and
    marginalised over, not just argmaxed.
    """
    hero_meta = (meta.get("heroes") or {}).get(str(int(hero_id)))
    if not hero_meta:
        return {0: 1.0}
    entries = hero_meta.get("archetypes") or []
    if len(entries) <= 1:
        return {int(entries[0]["archetype_id"]) if entries else 0: 1.0}

    prior = {int(e["archetype_id"]): float(e.get("share", 1.0)) for e in entries}
    item_ids = list(item_ids)
    if not item_ids:
        total = sum(prior.values()) or 1.0
        return {a: p / total for a, p in prior.items()}

    shares = partial_family_shares(item_ids)
    scores: dict[int, float] = {}
    for entry in entries:
        centroid = entry.get("centroid") or {}
        distance = sum(
            (shares.get(family, 0.0) - float(value)) ** 2
            for family, value in centroid.items()
        )
        archetype_id = int(entry["archetype_id"])
        scores[archetype_id] = prior[archetype_id] * math.exp(-distance / temperature)

    total = sum(scores.values())
    if total <= 0:
        total = sum(prior.values()) or 1.0
        return {a: p / total for a, p in prior.items()}
    return {a: score / total for a, score in scores.items()}


def scale_block(block: pd.DataFrame, weight: float) -> pd.DataFrame | None:
    """Put an extra feature block on the same footing as the family shares.

    Family shares sum to 1 for every player, so their mean row L1 norm is
    exactly 1. A block is divided by its own mean row L1 and multiplied by
    `weight`, which makes `weight=1.0` mean "this block carries as much total
    mass as the families do" and makes a sweep over weights comparable across
    blocks of different widths.

    Scaled, never z-scored. Z-scoring inflates whichever column happens to have
    low variance for a hero, which is the same reason the family shares are
    left unstandardized -- see the module docstring.
    """
    if block is None or weight <= 0 or not len(block):
        return None
    scale = float(block.abs().sum(axis=1).mean())
    if scale <= 0:
        return None
    return block * (weight / scale)


def feature_matrix(
    purchases: pd.DataFrame, extra: pd.DataFrame | None = None
) -> pd.DataFrame:
    """Per-player archetype features: souls-weighted build-family shares.

    Left unstandardized on purpose -- see the module docstring. The shares
    already sum to 1, and z-scoring them measurably degrades every hero tried.

    `extra` carries already-scaled ability blocks. Pass them through
    `scale_block` first; joining a raw block would let its width rather than
    its content decide how much it moves the fit.
    """
    features = family_shares(purchases).fillna(0.0)
    if extra is None or not len(extra):
        return features
    return features.join(extra.reindex(features.index).fillna(0.0), how="left").fillna(0.0)


def _silhouette(features: pd.DataFrame, labels: np.ndarray) -> float:
    """Silhouette over the full matrix is O(n^2); sample for large heroes."""
    if len(set(labels)) < 2:
        return float("nan")
    n = len(features)
    if n > 4000:
        rng = np.random.default_rng(ARCHETYPE_SEED)
        idx = rng.choice(n, 4000, replace=False)
        return float(silhouette_score(features.values[idx], np.asarray(labels)[idx]))
    return float(silhouette_score(features.values, labels))


def _fit_k(features: pd.DataFrame, k: int) -> tuple[np.ndarray, float]:
    model = KMeans(n_clusters=k, n_init=10, random_state=ARCHETYPE_SEED)
    with warnings.catch_warnings():
        # A population too uniform to split is a valid answer here, not a
        # problem to warn about -- fit_hero reads it off the nan silhouette.
        warnings.simplefilter("ignore", ConvergenceWarning)
        labels = model.fit_predict(features.values)
    return labels, _silhouette(features, labels)


def _canonical_order(features: pd.DataFrame, labels: np.ndarray) -> np.ndarray:
    """Relabel clusters by descending spirit share.

    KMeans label indices are arbitrary across runs, so without this every
    downstream artifact silently permutes whenever the fit is repeated.
    """
    spirit = features["spirit"] if "spirit" in features else None
    if spirit is None:
        return labels
    order = (
        pd.DataFrame({"label": labels, "spirit": spirit.values})
        .groupby("label")["spirit"]
        .mean()
        .sort_values(ascending=False)
        .index.tolist()
    )
    remap = {old: new for new, old in enumerate(order)}
    return np.array([remap[l] for l in labels])


def cluster_prevalence(purchases: pd.DataFrame, labels: pd.Series) -> pd.DataFrame:
    """Item pick rate within each cluster, as a cluster x item table."""
    keys = ["match_id", "player_slot"]
    tagged = purchases.join(labels.rename("archetype"), on=keys, how="inner")
    sizes = labels.groupby(labels).size()

    counts = (
        tagged[keys + ["item_id", "archetype"]]
        .drop_duplicates()
        .groupby(["archetype", "item_id"])
        .size()
        .unstack("item_id")
        .fillna(0.0)
    )
    return counts.div(sizes.reindex(counts.index), axis=0)


def _replication(
    purchases: pd.DataFrame, features: pd.DataFrame, k: int
) -> float:
    """Do these clusters mean the same thing on data they were not fitted on?

    Fit on one half, assign the other by nearest centroid, then correlate the
    per-cluster item prevalence vectors. A partition that does not reproduce
    itself is a slice of noise.
    """
    players = features.index.to_frame(index=False)
    train_players, test_players = splits.split_by_match(players, test_frac=0.5)
    train_idx = pd.MultiIndex.from_frame(train_players)
    test_idx = pd.MultiIndex.from_frame(test_players)
    if len(train_idx) < k * 50 or len(test_idx) < k * 50:
        return float("nan")

    model = KMeans(n_clusters=k, n_init=10, random_state=ARCHETYPE_SEED)
    model.fit(features.loc[train_idx].values)

    prevalences = []
    for idx in (train_idx, test_idx):
        labels = pd.Series(
            model.predict(features.loc[idx].values), index=idx, name="archetype"
        )
        table = cluster_prevalence(purchases, labels)
        prevalences.append(table.T.add_prefix("c"))

    a, b = prevalences
    shared = [c for c in a.columns if c in b.columns]
    if not shared:
        return float("nan")
    with warnings.catch_warnings():
        # A constant prevalence vector correlates with nothing; that is a
        # failed replication, which the caller reads as nan, not an error.
        warnings.simplefilter("ignore", RuntimeWarning)
        scores = [splits.replication_corr(a[[c]], b[[c]], c) for c in shared]
    scores = [s for s in scores if not np.isnan(s)]
    return float(np.mean(scores)) if scores else float("nan")


def _separation(prevalence: pd.DataFrame) -> float:
    """How distinguishable the LEAST distinct pair of clusters is.

    For each pair, the largest pick-rate gap on any item -- the criterion a
    player can check, since "these two builds differ by 60 points on Extra
    Charge" is a claim about the game. The score is then the WEAKEST pair.

    Taking the weakest pair rather than the strongest is load-bearing. Under a
    max, one genuinely distinct cluster drags near-duplicates through with it:
    Kelvin's support build carried two spirit clusters that share identical
    ability investment and differ on no item by more than 23 points. Every k=3
    hero had a pair below threshold that way -- Kelvin 0.226, Infernus 0.222,
    Sinclair 0.233. Two clusters are two archetypes only if a player would call
    them different builds, so every pair must qualify.
    """
    if len(prevalence) < 2:
        return float("nan")
    clusters = list(prevalence.index)
    gaps = [
        float((prevalence.loc[a] - prevalence.loc[b]).abs().max())
        for a, b in itertools.combinations(clusters, 2)
    ]
    return min(gaps) if gaps else float("nan")


def merge_indistinct(
    purchases: pd.DataFrame, labels: pd.Series, *, threshold: float = MIN_SEPARATION
) -> pd.Series:
    """Fold together cluster pairs no player would call different builds.

    Repeatedly merges the weakest pair while any pair sits below `threshold`,
    relabelling to stay contiguous. This recovers real archetypes that a
    whole-fit rejection would throw away: Kelvin's k=3 has two spirit clusters
    differing on no item by more than 23 points, but the third is a genuine
    support build (Rescue Beam 46%, Healing Tempo 42%). Merging the first two
    keeps the support build; rejecting k=3 outright loses it.

    Infernus and Silver merge all the way down to one, which is the right
    answer for them -- their k=3 was noise throughout.
    """
    labels = labels.copy()
    while labels.nunique() > 1:
        prevalence = cluster_prevalence(purchases, labels)
        clusters = sorted(prevalence.index)
        gaps = {
            (a, b): float((prevalence.loc[a] - prevalence.loc[b]).abs().max())
            for a, b in itertools.combinations(clusters, 2)
        }
        weakest = min(gaps, key=gaps.get)
        if gaps[weakest] >= threshold:
            break
        labels = labels.replace({weakest[1]: weakest[0]})
        remap = {old: new for new, old in enumerate(sorted(labels.unique()))}
        labels = labels.map(remap)
    return labels


def fit_hero(
    purchases: pd.DataFrame,
    *,
    hero_id: int,
    hero_name: str = "",
    candidate_k: tuple[int, ...] = CANDIDATE_K,
    extra: pd.DataFrame | None = None,
) -> ArchetypeFit:
    """Select k for one hero, accepting a split only on all four criteria.

    Tries the largest k first and merges indistinguishable clusters back
    together, rather than trying the smallest and stopping. Both orders land on
    k=2 for Ivy, but only this one finds Kelvin's support build -- it lives in a
    k=3 fit whose other two clusters are one archetype on a gradient.
    """
    features = feature_matrix(purchases, extra)
    n = len(features)
    single = ArchetypeFit(
        hero_id=hero_id,
        hero_name=hero_name,
        k=1,
        n=n,
        labels=pd.Series(0, index=features.index, dtype=int),
    )

    if n < MIN_HERO_PLAYERS:
        single.reason = f"only {n:,} players (<{MIN_HERO_PLAYERS:,})"
        return single

    best_rejected = None
    for k in sorted(candidate_k, reverse=True):
        labels, _ = _fit_k(features, k)
        labels = _canonical_order(features, labels)
        series = pd.Series(labels, index=features.index, name="archetype")

        # Fold away pairs that are one build on a gradient, then re-score what
        # survives. A k=3 fit carrying one real cluster becomes a k=2 fit.
        series = merge_indistinct(purchases, series)
        if series.nunique() < 2:
            # Everything folded into one: the clusters were a gradient, not
            # builds. Record it so the review sheet says why.
            if best_rejected is None:
                best_rejected = ArchetypeFit(
                    hero_id=hero_id, hero_name=hero_name, k=1, n=n,
                    reason=f"k={k} fails separation (all clusters merged)",
                )
            continue
        series = pd.Series(
            _canonical_order(features, series.values), index=series.index, name="archetype"
        )
        score = _silhouette(features, series.values)

        prevalence = cluster_prevalence(purchases, series)
        separation = _separation(prevalence)
        shares = series.value_counts(normalize=True)
        smallest = float(shares.min())
        replication = _replication(purchases, features, k)

        centroids = features.groupby(series).mean()
        candidate = ArchetypeFit(
            hero_id=hero_id,
            hero_name=hero_name,
            k=int(series.nunique()),
            n=n,
            labels=series,
            centroids=centroids,
            silhouette=score,
            replication=replication,
            separation=separation,
            smallest_share=smallest,
        )

        failures = [name for name, (_, _, ok) in candidate.criteria().items() if not ok]
        if not failures:
            merged = f" (merged from k={k})" if candidate.k < k else ""
            candidate.reason = f"k={candidate.k} clears every criterion{merged}"
            return candidate
        if best_rejected is None or candidate.separation > best_rejected.separation:
            candidate.reason = "fails " + ", ".join(failures)
            best_rejected = candidate

    if best_rejected is not None:
        single.silhouette = best_rejected.silhouette
        single.replication = best_rejected.replication
        single.separation = best_rejected.separation
        single.smallest_share = best_rejected.smallest_share
        single.reason = f"single archetype: best split {best_rejected.reason}"
    return single


def discriminative_items(
    prevalence: pd.DataFrame, cluster: int, *, top: int = 15
) -> pd.DataFrame:
    """Items most over-picked by one cluster relative to the others.

    The readout a human checks. Reported as both rates, not a ratio, because
    "81% versus 30%" is checkable by eye and "2.7x" is not.
    """
    if len(prevalence) < 2:
        return pd.DataFrame(columns=["item_id", "in_cluster", "elsewhere", "lift"])
    mine = prevalence.loc[cluster]
    others = prevalence.drop(index=cluster).mean(axis=0)
    lift = (mine - others).sort_values(ascending=False)
    return pd.DataFrame(
        {
            "item_id": lift.index[:top],
            "in_cluster": mine.reindex(lift.index[:top]).values,
            "elsewhere": others.reindex(lift.index[:top]).values,
            "lift": lift.values[:top],
        }
    )


def propose_name(
    centroid: pd.Series, hero_name: str, prevalence: pd.DataFrame, cluster: int
) -> tuple[str, float]:
    """Auto-label a cluster from what its distinguishing items DO.

    Not from the centroid. Slot shares measure which shop tab the souls went
    into, and 84 of 170 shopable items sit in a tab that does not match their
    role -- so centroid naming called Lash's gun build "Tank" (Siphon Bullets
    is vitality-slotted), Abrams' melee build "Tank" (melee items are
    weapon-slotted), and Kelvin's support build "Tank" too. It also produced
    duplicate names: three clusters of one hero all reading "Spirit X".

    The label comes from the cluster's discriminative items, scored into build
    families and weighted by how rare each family's evidence is. Returns the
    name and the margin over the runner-up; a thin margin means the rule
    declined to assert a family and the bare hero name came back.

    A proposal for a human to accept or overrule, not an answer.
    """
    if len(prevalence) < 2 or cluster not in prevalence.index:
        return hero_name, 0.0
    mine = prevalence.loc[cluster]
    others = prevalence.drop(index=cluster).mean(axis=0)
    lifts = (mine - others).to_dict()
    name, _, margin = semantics.name_cluster(lifts, hero_name)
    return name, margin


# A cluster's ability focus has to be its own, not the hero's. Every Dynamo
# imbues something; only one of Dynamo's clusters imbues Singularity 95% of the
# time against 8% elsewhere.
MIN_FOCUS_SHARE = 0.50
MIN_FOCUS_LIFT = 0.20
MIN_FOCUS_ROWS = 30


def ability_focus(
    members: pd.Index,
    others: pd.Index,
    imbues: pd.DataFrame | None,
    first_maxed: pd.Series | None,
) -> tuple[int, float] | None:
    """Which signature slot a cluster is built around, if any.

    Returns (slot, share) for the ability this cluster points at far more than
    the hero's other clusters do, or None when no ability stands out.

    Imbue leads, and the ability levelled first is the fallback. Imbue is the
    sharper statement -- a player spends 6,400 souls to put Mystic Reverb on
    one ability -- but only builds that buy imbueable items make it, so a
    cluster that buys none is read from its levelling instead.

    Two guards, both learned the hard way. `MIN_FOCUS_ROWS` because a share
    over 24 rows is not a finding: a Bebop cluster of 5,110 players had 24
    imbues, and 23 of them agreeing looked like a 96% signal. And a *lift*
    requirement, not just a share, because "every Wraith imbues Card Trick"
    describes the hero, not the build, and would name both of its clusters the
    same thing.
    """
    for source, dominant in (
        ("imbue", _dominant_imbue(members, others, imbues)),
        ("levelling", _dominant_first_maxed(members, others, first_maxed)),
    ):
        if dominant is not None:
            return dominant
    return None


def _dominant_imbue(
    members: pd.Index, others: pd.Index, imbues: pd.DataFrame | None
) -> tuple[int, float] | None:
    if imbues is None or not len(imbues):
        return None
    mine = imbues[imbues.index.isin(members)]
    if len(mine) < MIN_FOCUS_ROWS:
        return None
    theirs = imbues[imbues.index.isin(others)]
    shares = mine["signature_slot"].value_counts(normalize=True)
    slot = int(shares.index[0])
    share = float(shares.iloc[0])
    elsewhere = 0.0
    if len(theirs):
        other_shares = theirs["signature_slot"].value_counts(normalize=True)
        elsewhere = float(other_shares.get(slot, 0.0))
    if share < MIN_FOCUS_SHARE or share - elsewhere < MIN_FOCUS_LIFT:
        return None
    return slot, share - elsewhere


def _dominant_first_maxed(
    members: pd.Index, others: pd.Index, first_maxed: pd.Series | None
) -> tuple[int, float] | None:
    if first_maxed is None or not len(first_maxed):
        return None
    mine = first_maxed[first_maxed.index.isin(members)]
    mine = mine[mine > 0]
    if len(mine) < MIN_FOCUS_ROWS:
        return None
    theirs = first_maxed[first_maxed.index.isin(others)]
    theirs = theirs[theirs > 0]
    shares = mine.value_counts(normalize=True)
    slot = int(shares.index[0])
    share = float(shares.iloc[0])
    elsewhere = float(theirs.value_counts(normalize=True).get(slot, 0.0)) if len(theirs) else 0.0
    if share < MIN_FOCUS_SHARE or share - elsewhere < MIN_FOCUS_LIFT:
        return None
    return slot, share - elsewhere


def focus_label(slot: int, signatures: dict) -> str:
    """What a player calls a build aimed at this ability.

    Slot 4 is the ultimate, and `CONTEXT.md` records that players say "ult
    build" rather than naming the ability. Every other slot is called by the
    ability's own name.
    """
    if slot == 4:
        return "Ult"
    ability = signatures.get(slot)
    return getattr(ability, "name", f"Slot {slot}")


def item_label(prevalence: pd.DataFrame, cluster: int, item_names: dict[int, str]) -> str | None:
    """The one item that most separates this cluster, in a form a player says.

    The last word of the item name: a player says "the Reverb build", not "the
    Mystic Reverb build". Discriminative items are the honest signal about what
    a cluster is -- more so than its centroid, which measures only where souls
    went.
    """
    top = discriminative_items(prevalence, cluster, top=1)
    if not len(top):
        return None
    name = item_names.get(int(top.iloc[0]["item_id"]))
    return name.split()[-1] if name else None


def make_unique(
    proposed: dict[int, str],
    hero_name: str,
    *,
    focus: dict[int, str] | None = None,
    items: dict[int, str] | None = None,
) -> dict[int, str]:
    """Give every cluster of one hero a name that selects only it.

    Two clusters sharing a name is a user-visible defect, not an aesthetic
    one: `--archetype Spirit` silently picks the first, so a third of Lady
    Geist players had a build they could not reach. Uniqueness is the floor.

    Disambiguation runs in the order a player would find informative:
    the build family first, then what the build is aimed at, then the item that
    most sets it apart. A trailing number is the last resort and means the rule
    ran out of things to say -- which is a signal the clusters may not be two
    builds at all.
    """
    focus = focus or {}
    items = items or {}
    counts: dict[str, list[int]] = {}
    for cluster, name in proposed.items():
        counts.setdefault(name, []).append(cluster)

    out = dict(proposed)
    for name, clusters in counts.items():
        if len(clusters) < 2:
            continue
        for source in (focus, items):
            candidates = {c: source.get(c) for c in clusters}
            distinct = [v for v in candidates.values() if v]
            if len(set(distinct)) == len(clusters):
                for cluster, extra in candidates.items():
                    out[cluster] = f"{extra} {name}" if extra else out[cluster]
                break
        else:
            for index, cluster in enumerate(sorted(clusters), start=1):
                out[cluster] = f"{name} {index}"

    # Disambiguating one group can collide with another group's name.
    seen: dict[str, int] = {}
    for cluster in sorted(out):
        name = out[cluster]
        if name in seen:
            out[cluster] = f"{name} {seen[name] + 1}"
        seen[name] = seen.get(name, 0) + 1
    return out


def load_name_overrides(path: Path = NAMES_PATH) -> dict[str, str]:
    """Human-accepted archetype names, keyed "<hero_id>:<archetype_id>".

    The auto-labels are a proposal. This file is where a person overrules them,
    and it is checked in so the naming survives a refit.
    """
    if not Path(path).exists():
        return {}
    return json.loads(Path(path).read_text())


def fit_all(
    purchases: pd.DataFrame,
    *,
    hero_names: dict[int, str] | None = None,
    overrides: dict[str, str] | None = None,
    extra: pd.DataFrame | None = None,
    imbues: pd.DataFrame | None = None,
    first_maxed: pd.Series | None = None,
) -> tuple[pd.DataFrame, list[ArchetypeFit], dict]:
    """Fit every hero, returning labels, per-hero fits, and reviewable metadata."""
    hero_names = hero_names or {h: v.name for h, v in assets.load_heroes().items()}
    overrides = load_name_overrides() if overrides is None else overrides
    item_names = {i: it.name for i, it in assets.load_items().items()}
    all_signatures = assets.hero_signatures()

    labels: list[pd.DataFrame] = []
    fits: list[ArchetypeFit] = []
    meta: dict = {"seed": ARCHETYPE_SEED, "heroes": {}}

    for hero_id, group in purchases.groupby("hero_id"):
        name = hero_names.get(int(hero_id), str(hero_id))
        fit = fit_hero(group, hero_id=int(hero_id), hero_name=name, extra=extra)
        fits.append(fit)

        frame = fit.labels.rename("archetype_id").reset_index()
        frame["hero_id"] = int(hero_id)
        labels.append(frame)

        prevalence = cluster_prevalence(group, fit.labels) if fit.split else pd.DataFrame()
        signatures = all_signatures.get(int(hero_id), {})

        # Name every cluster of this hero together, not one at a time. Two
        # clusters sharing a name is only visible across the hero, and it is
        # what made a third of Lady Geist players unable to select their build.
        proposed_names: dict[int, str] = {}
        margins: dict[int, float] = {}
        focus_labels: dict[int, str] = {}
        item_labels: dict[int, str] = {}
        for cluster in sorted(fit.labels.unique()):
            centroid = fit.centroids.loc[cluster] if fit.split else pd.Series(dtype=float)
            proposed_names[cluster], margins[cluster] = (
                propose_name(centroid, name, prevalence, cluster)
                if fit.split
                else (name, 0.0)
            )
            if not fit.split:
                continue
            members = fit.labels[fit.labels == cluster].index
            others = fit.labels[fit.labels != cluster].index
            found = ability_focus(members, others, imbues, first_maxed)
            if found is not None:
                focus_labels[cluster] = focus_label(found[0], signatures)
            label = item_label(prevalence, cluster, item_names)
            if label:
                item_labels[cluster] = label

        unique = make_unique(
            proposed_names, name, focus=focus_labels, items=item_labels
        )

        clusters = []
        for cluster in sorted(fit.labels.unique()):
            centroid = fit.centroids.loc[cluster] if fit.split else pd.Series(dtype=float)
            proposed = unique[cluster]
            margin = margins[cluster]
            key = f"{hero_id}:{cluster}"
            top = (
                discriminative_items(prevalence, cluster)
                if fit.split
                else pd.DataFrame(columns=["item_id", "in_cluster", "elsewhere", "lift"])
            )
            clusters.append(
                {
                    "archetype_id": int(cluster),
                    "name": overrides.get(key, proposed),
                    "proposed_name": proposed,
                    "family_name": proposed_names[cluster],
                    "ability_focus": focus_labels.get(cluster),
                    "naming_margin": float(margin),
                    "n": int((fit.labels == cluster).sum()),
                    "share": float((fit.labels == cluster).mean()),
                    "centroid": {k: float(v) for k, v in centroid.items()},
                    "top_items": [
                        {
                            "item_id": int(r.item_id),
                            "name": item_names.get(int(r.item_id), str(int(r.item_id))),
                            "in_cluster": float(r.in_cluster),
                            "elsewhere": float(r.elsewhere),
                        }
                        for r in top.itertuples()
                    ],
                }
            )

        meta["heroes"][str(hero_id)] = {
            "hero_name": name,
            "k": fit.k,
            "n": fit.n,
            "reason": fit.reason,
            "criteria": {
                name_: {"value": _clean(value), "threshold": threshold, "passed": bool(ok)}
                for name_, (value, threshold, ok) in fit.criteria().items()
            },
            "archetypes": clusters,
        }

    return pd.concat(labels, ignore_index=True), fits, meta


def _clean(value: float) -> float | None:
    """JSON has no NaN; a criterion that could not be computed is null."""
    return None if value is None or np.isnan(value) else float(value)


def save(labels: pd.DataFrame, meta: dict, *, out_dir: Path = Path("data/processed")) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    labels.to_parquet(out_dir / "archetypes.parquet", index=False)
    (out_dir / "archetype_meta.json").write_text(json.dumps(meta, indent=2))


def load(out_dir: Path = Path("data/processed")) -> tuple[pd.DataFrame, dict]:
    out_dir = Path(out_dir)
    labels = pd.read_parquet(out_dir / "archetypes.parquet")
    meta = json.loads((out_dir / "archetype_meta.json").read_text())
    return labels, meta
