"""Archetypes: the different ways players build one hero.

Ivy is built either as a gun carry or as a spirit support. The two builds share
few items, and a recommendation averaged over both fits neither. So the model
conditions on archetype, fitted separately for each hero.

Some heroes have only one. Haze and Dynamo's k=2 splits are arbitrary cuts
through one group of players, so k is chosen per hero and k=1 is allowed.

Clustering runs on each player's build family shares: how their souls divide
across gun, spirit, melee, support, tank, sustain, control, and mobility (see
`semantics.py`). Not on item ids. Clusters of "who bought item X" would just
repeat what the model then predicts. With coarse inputs, a finding like "these
two clusters differ by 53 points on Extra Charge" is real information.

Shop-tab shares were used before. Build families raised mean separation from
0.321 to 0.429 over 38 heroes and found real splits on six heroes that shop
tabs missed, including Dynamo.

Three other inputs were tested and left out:

- Ability levels. Adding them made clustering worse on every hero tried. Ivy's
  separation fell 0.508, 0.421, 0.361, 0.274 as the ability weight went 0,
  0.25, 0.5, 1.0. Between Ivy's two clusters, the biggest gap in mean level at
  480s is 0.48 out of 4.
- Imbue targets. They split heroes on whether players bought an imbueable
  item, not on what they aimed it at. See ADR 0001.
- Ability order, in three forms (raw, minus the hero mean, as a percentile).
  Each lost splits on 4, 14, and 15 of 31 heroes and gained back fewer. See
  ADR 0003.

The shares are not standardized. They already sum to 1, and z-scoring would
blow up whichever family has low variance for that hero.

A split must pass four checks: silhouette, replication on held-out data,
separation (some item's pick rate differs by a visible margin), and a minimum
cluster size. If it fails any, the hero gets k=1.
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

# The four checks a split must pass.
#
# Separation is the main one. It ranks heroes the way a person does: Lady
# Geist (0.85), Ivy (0.63), and Bebop (0.62) above Dynamo (0.35), Haze (0.23),
# and Wraith (0.22). Silhouette put Dynamo (0.42) above heroes like Ivy. A
# player can also check separation by eye: "these two builds differ by 63
# points on Extra Charge".
MIN_SEPARATION = 0.45
# Only catches fits with no cluster structure at all. Silhouette falls as
# dimensions are added: splits that scored 0.4-0.7 on the three shop tabs
# score 0.19-0.61 on the eight families. A 0.35 bar would reject 21 of the 25
# heroes that pass separation and size.
MIN_SILHOUETTE = 0.15
MIN_REPLICATION = 0.90
# Every cluster must hold at least this share of the hero's players. At 12%,
# melee Sinclair (14.6%) passes. Several heroes have smaller clusters that pass
# every other check, such as a 3.1% gun Calico build, and this rejects them.
# Whether that removes false splits or real rare builds is issue #38.
MIN_CLUSTER_SHARE = 0.12

# Heroes with fewer players than this aren't clustered.
MIN_HERO_PLAYERS = 600

# Archetype names a person has accepted. Checked in so they survive a refit.
NAMES_PATH = Path("data/archetype_names.json")

SLOT_TYPES = ("weapon", "vitality", "spirit")

# Clustering uses build families. `slot_shares` is only for the review sheet.
def _feature_columns() -> list[str]:
    from . import semantics

    return list(semantics.FAMILIES)


@dataclass
class ArchetypeFit:
    """The result of fitting one hero, and why the split was accepted or rejected."""

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
    """Each player's spending share per shop tab, weighted by cost.

    Weighted by cost so six cheap vitality items don't outweigh three
    expensive spirit items.
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


def player_index(purchases: pd.DataFrame) -> pd.MultiIndex:
    """Every (match_id, player_slot) in a purchase table, once each.

    Reindex extra feature blocks on this, so players the block has no data
    for still get a row.
    """
    keys = ["match_id", "player_slot"]
    return purchases[keys].drop_duplicates().set_index(keys).index


def hero_of(purchases: pd.DataFrame) -> pd.Series:
    """The hero each player played, indexed by (match_id, player_slot)."""
    keys = ["match_id", "player_slot"]
    return purchases[keys + ["hero_id"]].drop_duplicates().set_index(keys)["hero_id"]


def family_shares(
    purchases: pd.DataFrame, items: dict[int, assets.Item] | None = None
) -> pd.DataFrame:
    """Each player's spending share per build family, weighted by cost.

    Each item's cost is divided across its families in proportion to its
    family scores, so Crushing Fists counts mostly as melee and a little as
    gun and tank. These are the clustering features.
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
    """The share of one item's cost that goes to a family."""
    scores = families.get(item_id)
    if not scores:
        return 0.0
    total = sum(scores.values())
    return scores.get(family, 0) / total if total else 0.0


def partial_family_shares(
    item_ids: Iterable[int], items: dict[int, assets.Item] | None = None
) -> pd.Series:
    """`family_shares` for one unfinished build, given as a list of item ids."""
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
    """Probability of each archetype, given the items bought so far.

    Each archetype's share of players, times exp(-distance / temperature),
    where distance is the squared distance from the build's family shares to
    the archetype's centroid. With nothing bought, it is just the shares.

    Probabilities, not a single pick, because early purchases don't identify
    the build. On Ivy (k=3, so 33% by chance), the nearest centroid is right
    55% of the time after 3 purchases, 57% after 5, 64% after 8, and 79% after
    12.

    The temperature barely changes accuracy between 0.05 and 0.40. 0.10 gives
    the lowest log-loss at 8 purchases, which matters because the
    probabilities are shown to the player and averaged over.
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
    """Scale an extra feature block to match the family shares, times `weight`.

    Family shares sum to 1 per player. The block is divided by its mean row
    sum of absolute values and multiplied by `weight`, so `weight=1.0` gives
    the block as much total weight as the families, whatever its width.

    Scaled, never z-scored, for the same reason the family shares aren't
    standardized (see the module docstring).
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
    """Clustering features per player: build family shares, plus `extra` if given.

    Pass `extra` through `scale_block` first. Otherwise a wider block gets
    more weight just for having more columns.
    """
    features = family_shares(purchases).fillna(0.0)
    if extra is None or not len(extra):
        return features
    return features.join(extra.reindex(features.index).fillna(0.0), how="left").fillna(0.0)


def _silhouette(features: pd.DataFrame, labels: np.ndarray) -> float:
    """Silhouette score, on a 4,000-player sample for large heroes since it is O(n^2)."""
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
        # Players too uniform to split is a normal result. fit_hero sees it
        # as a NaN silhouette.
        warnings.simplefilter("ignore", ConvergenceWarning)
        labels = model.fit_predict(features.values)
    return labels, _silhouette(features, labels)


def _canonical_order(features: pd.DataFrame, labels: np.ndarray) -> np.ndarray:
    """Renumber clusters from highest to lowest mean spirit share.

    KMeans numbers clusters arbitrarily, so without this the ids could change
    between refits.
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
    """Each item's pick rate in each cluster, as a cluster x item table."""
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
    """Whether the clusters mean the same thing on data they weren't fitted on.

    Fits on half the matches, assigns the other half to the nearest centroid,
    and returns the mean correlation of each cluster's item pick rates between
    the halves.
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
        # A constant pick-rate vector gives a NaN correlation, which counts
        # as failing replication.
        warnings.simplefilter("ignore", RuntimeWarning)
        scores = [splits.replication_corr(a[[c]], b[[c]], c) for c in shared]
    scores = [s for s in scores if not np.isnan(s)]
    return float(np.mean(scores)) if scores else float("nan")


def _separation(prevalence: pd.DataFrame) -> float:
    """Separation of the least distinct pair of clusters.

    For each pair of clusters, takes the largest pick-rate gap on any item.
    Returns the smallest of those.

    Using the least distinct pair means every pair must be different builds.
    With the most distinct pair, one real cluster would let two
    near-duplicates through. Kelvin's k=3 fit had two spirit clusters that
    differed on no item by more than 23 points (0.226), and Infernus (0.222)
    and Sinclair (0.233) had the same problem.
    """
    if len(prevalence) < 2:
        return float("nan")
    clusters = list(prevalence.index)
    gaps = [
        float((prevalence.loc[a] - prevalence.loc[b]).abs().max())
        for a, b in itertools.combinations(clusters, 2)
    ]
    return min(gaps) if gaps else float("nan")


def separating_item(prevalence: pd.DataFrame) -> tuple[int, float] | None:
    """(item id, gap) for the item that separates the least distinct pair.

    Shows which item a split rests on. That is how the imbue experiment was
    judged: the splits rested on the imbueable items themselves (ADR 0001).
    """
    if len(prevalence) < 2:
        return None
    pairs = [
        (a, b, float((prevalence.loc[a] - prevalence.loc[b]).abs().max()))
        for a, b in itertools.combinations(sorted(prevalence.index), 2)
    ]
    if not pairs:
        return None
    a, b, gap = min(pairs, key=lambda p: p[2])
    diffs = (prevalence.loc[a] - prevalence.loc[b]).abs()
    return int(diffs.idxmax()), gap


def merge_indistinct(
    purchases: pd.DataFrame, labels: pd.Series, *, threshold: float = MIN_SEPARATION
) -> pd.Series:
    """Merge cluster pairs whose separation is below `threshold`.

    Merges the least distinct pair until every pair passes, renumbering
    clusters from 0. This keeps real archetypes that rejecting the whole fit
    would lose. Kelvin's k=3 fit has two spirit clusters that barely differ
    and a real support build (Rescue Beam 46%, Healing Tempo 42%). Merging the
    two spirit clusters keeps the support build.

    Infernus and Silver merge down to one cluster.
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
    """Cluster one hero's players, keeping a split only if it passes all four checks.

    Tries the largest k first and merges clusters that are too similar.
    Starting from the smallest k would also give Ivy k=2, but would miss
    Kelvin's support build, which only appears in a k=3 fit.

    If no split passes, returns k=1 with the scores of the best rejected split.
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

        # Merge clusters that are too similar, then score what's left.
        series = merge_indistinct(purchases, series)
        if series.nunique() < 2:
            # Everything merged into one. Record why for the review sheet.
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
    """The items one cluster picks most above the mean of the hero's other clusters.

    Gives both rates, not a ratio: "81% vs 30%" is easier to check than "2.7x".
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
    """Propose a name for a cluster from the build families of its distinctive items.

    Returns (name, margin). If the margin is too small, the name is just the
    hero name. A person can override the result in NAMES_PATH.

    `centroid` is unused. Naming from shop-tab centroids called Lash's gun
    build, Abrams' melee build, and Kelvin's support build all "Tank".
    """
    if len(prevalence) < 2 or cluster not in prevalence.index:
        return hero_name, 0.0
    mine = prevalence.loc[cluster]
    others = prevalence.drop(index=cluster).mean(axis=0)
    lifts = (mine - others).to_dict()
    name, _, margin = semantics.name_cluster(lifts, hero_name)
    return name, margin


# Thresholds for `ability_focus`. The ability must stand out against the
# hero's other clusters, not just be common. One Dynamo cluster imbues
# Singularity 95% of the time, against 8% in the others.
MIN_FOCUS_SHARE = 0.50
MIN_FOCUS_LIFT = 0.20
MIN_FOCUS_ROWS = 30


def ability_focus(
    members: pd.Index,
    others: pd.Index,
    imbues: pd.DataFrame | None,
    first_maxed: pd.Series | None,
) -> tuple[int, float] | None:
    """The signature slot this cluster focuses on, or None.

    Returns (slot, lift) for an ability the cluster favors far more than the
    hero's other clusters. Checks imbue targets first, then the ability maxed
    first, since clusters that buy no imbueable items have no imbue data.

    Needs at least MIN_FOCUS_ROWS rows: a Bebop cluster of 5,110 players had
    only 24 imbues, and 23 agreeing looked like a 96% signal. Also needs a
    lift over the other clusters, not only a high share. Every Wraith imbues
    Card Trick, so that says nothing about which Wraith build it is.
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
    """The name word for a build focused on this slot.

    Slot 4 (the ultimate) is "Ult", because players say "ult build" (see
    CONTEXT.md). Other slots use the ability's name.
    """
    if slot == 4:
        return "Ult"
    ability = signatures.get(slot)
    return getattr(ability, "name", f"Slot {slot}")


def item_label(prevalence: pd.DataFrame, cluster: int, item_names: dict[int, str]) -> str | None:
    """The last word of this cluster's most distinctive item's name, or None.

    Players say "the Reverb build", not "the Mystic Reverb build".
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
    fixed: dict[int, str] | None = None,
) -> dict[int, str]:
    """Make every cluster name for one hero unique.

    With two clusters sharing a name, `--archetype Spirit` picks the first,
    and a third of Lady Geist players couldn't select their build.

    Duplicates get a prefix from `focus` (the ability the build centers on),
    or failing that from `items` (its most distinctive item). If neither
    gives distinct names, a number is appended. Needing a number suggests the
    clusters may not be different builds.

    `fixed` holds names a person accepted. They are never changed, and
    generated names are adjusted so they don't collide with them.
    """
    focus = focus or {}
    items = items or {}
    fixed = fixed or {}

    # Two accepted names that are the same can't be fixed automatically, so
    # stop the refit and let a person fix the names file.
    claimed: dict[str, list[int]] = {}
    for cluster, chosen in sorted(fixed.items()):
        claimed.setdefault(chosen, []).append(cluster)
    clashes = {n: c for n, c in claimed.items() if len(c) > 1}
    if clashes:
        detail = "; ".join(
            f"{n!r} on clusters {', '.join(str(c) for c in cs)}"
            for n, cs in sorted(clashes.items())
        )
        raise ValueError(
            f"{hero_name}: two accepted names in data/archetype_names.json are "
            f"the same, so neither selects a build -- {detail}"
        )

    proposed = {c: fixed.get(c, n) for c, n in proposed.items()}
    counts: dict[str, list[int]] = {}
    for cluster, name in proposed.items():
        counts.setdefault(name, []).append(cluster)

    out = dict(proposed)
    for name, clusters in counts.items():
        if len(clusters) < 2:
            continue
        movable = [c for c in clusters if c not in fixed]
        if not movable:
            continue
        for source in (focus, items):
            candidates = {c: source.get(c) for c in movable}
            distinct = [v for v in candidates.values() if v]
            if len(set(distinct)) == len(movable) and not (
                set(distinct) & {fixed.get(c) for c in clusters}
            ):
                for cluster, extra in candidates.items():
                    out[cluster] = f"{extra} {name}" if extra else out[cluster]
                break
        else:
            for index, cluster in enumerate(sorted(movable), start=1):
                out[cluster] = f"{name} {index}"

    # Renaming one group can collide with another group's name. Count fixed
    # names first so a generated name always gives way to an accepted one.
    seen: dict[str, int] = {}
    for cluster in sorted(out):
        if cluster in fixed:
            name = out[cluster]
            seen[name] = seen.get(name, 0) + 1
    for cluster in sorted(out):
        if cluster in fixed:
            continue
        name = out[cluster]
        if name in seen:
            out[cluster] = f"{name} {seen[name] + 1}"
        seen[name] = seen.get(name, 0) + 1
    return out


def load_name_overrides(path: Path = NAMES_PATH) -> dict[str, str]:
    """Accepted archetype names from NAMES_PATH, keyed "<hero_id>:<archetype_id>".

    Keys starting with an underscore are notes and are skipped. Cluster ids
    only stay the same while the fit does, so check this file after a refit.
    """
    if not Path(path).exists():
        return {}
    loaded = json.loads(Path(path).read_text())
    return {k: v for k, v in loaded.items() if not k.startswith("_")}


def fit_all(
    purchases: pd.DataFrame,
    *,
    hero_names: dict[int, str] | None = None,
    overrides: dict[str, str] | None = None,
    extra: pd.DataFrame | None = None,
    imbues: pd.DataFrame | None = None,
    first_maxed: pd.Series | None = None,
) -> tuple[pd.DataFrame, list[ArchetypeFit], dict]:
    """Fit every hero. Returns (labels, per-hero fits, metadata for the review sheet)."""
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

        # Name all of this hero's clusters together, so duplicates can be
        # found and fixed.
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

        # This hero's accepted names, by cluster.
        fixed = {
            cluster: overrides[f"{hero_id}:{cluster}"]
            for cluster in proposed_names
            if f"{hero_id}:{cluster}" in overrides
        }
        unique = make_unique(
            proposed_names,
            name,
            focus=focus_labels,
            items=item_labels,
            fixed=fixed,
        )
        # The names without overrides, so a reviewer can see what an accepted
        # name replaced.
        rule_names = (
            make_unique(proposed_names, name, focus=focus_labels, items=item_labels)
            if fixed
            else unique
        )

        clusters = []
        for cluster in sorted(fit.labels.unique()):
            centroid = fit.centroids.loc[cluster] if fit.split else pd.Series(dtype=float)
            proposed = unique[cluster]
            margin = margins[cluster]
            top = (
                discriminative_items(prevalence, cluster)
                if fit.split
                else pd.DataFrame(columns=["item_id", "in_cluster", "elsewhere", "lift"])
            )
            clusters.append(
                {
                    "archetype_id": int(cluster),
                    "name": proposed,
                    "proposed_name": rule_names[cluster],
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
    """NaN to None, since JSON has no NaN."""
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
