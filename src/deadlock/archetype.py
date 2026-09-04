"""Build archetypes: the different ways one hero gets played.

Ivy is either a gun carry or a spirit support. Those builds share few items,
and a recommendation averaged across both serves neither -- the same error as
the discarded paired design smearing a niche item across 38 heroes, one level
down. So archetype is a conditioning variable, fitted per hero.

Not every hero has one. Haze and Dynamo do not split: their k=2 partitions are
arbitrary slices of a single population. Forcing k=2 everywhere would invent
distinctions that do not exist, so k is selected per hero and 1 is an allowed
answer.

**The feature vector is deliberately coarse:** souls-weighted item slot-type
shares (weapon / vitality / spirit), and nothing else. Clustering on item
identities finds "who bought item X" groups that are tautological with what the
model then predicts. Keeping the input coarse is what makes the readout ("these
two clusters differ by 53 points on Extra Charge") a falsifiable claim rather
than a restatement of the input.

**Abilities are deliberately excluded, against the original design.** Measured
on every hero tried, adding ability levels monotonically degrades the
clustering -- Ivy falls 0.508 -> 0.421 -> 0.361 -> 0.274 as ability weight goes
0 -> 0.25 -> 0.5 -> 1.0, and the same holds for Haze, Dynamo, Bebop and Wraith.
The reason is visible directly: between Ivy's two item clusters the largest
mean ability-level gap is 0.48 of 4. Abilities do vary with archetype, but far
too weakly to carry four extra dimensions, so they add noise. They remain
available in `abilities.py` for the sequence model.

Shares are also left unstandardized. Three fractions summing to 1 are already
commensurate; z-scoring them inflates whichever slot type happens to have low
variance for that hero and distorts the geometry (Ivy 0.508 raw vs 0.459
standardized).

**Acceptance is not silhouette alone.** A silhouette score is exactly the kind
of aggregate that passed while the old pipeline was wrong, so a split must also
reproduce itself on held-out data, separate some item by a visible margin, and
leave both sides large enough to model. All four, or k=1.
"""

from __future__ import annotations

import json
import logging
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.exceptions import ConvergenceWarning
from sklearn.metrics import silhouette_score

from . import assets, splits

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
MIN_SILHOUETTE = 0.35
MIN_REPLICATION = 0.90
MIN_CLUSTER_SHARE = 0.15

# Below this a hero cannot support the fit at all.
MIN_HERO_PLAYERS = 600

# Human-accepted names, checked in so they survive a refit.
NAMES_PATH = Path("data/archetype_names.json")

SLOT_TYPES = ("weapon", "vitality", "spirit")
FEATURE_COLUMNS = [f"share_{s}" for s in SLOT_TYPES]


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


def feature_matrix(purchases: pd.DataFrame) -> pd.DataFrame:
    """Per-player archetype features: souls-weighted slot-type shares.

    Left unstandardized on purpose -- see the module docstring. Three fractions
    summing to 1 are already on one scale, and z-scoring them measurably
    degrades every hero tried.
    """
    return slot_shares(purchases).fillna(0.0)


def _fit_k(features: pd.DataFrame, k: int) -> tuple[np.ndarray, float]:
    model = KMeans(n_clusters=k, n_init=10, random_state=ARCHETYPE_SEED)
    with warnings.catch_warnings():
        # A population too uniform to split is a valid answer here, not a
        # problem to warn about -- fit_hero reads it off the nan silhouette.
        warnings.simplefilter("ignore", ConvergenceWarning)
        labels = model.fit_predict(features.values)
    if len(set(labels)) < 2:
        return labels, float("nan")
    # Silhouette over the full matrix is O(n^2); sample for large heroes.
    n = len(features)
    if n > 4000:
        rng = np.random.default_rng(ARCHETYPE_SEED)
        idx = rng.choice(n, 4000, replace=False)
        score = silhouette_score(features.values[idx], labels[idx])
    else:
        score = silhouette_score(features.values, labels)
    return labels, float(score)


def _canonical_order(features: pd.DataFrame, labels: np.ndarray) -> np.ndarray:
    """Relabel clusters by descending spirit share.

    KMeans label indices are arbitrary across runs, so without this every
    downstream artifact silently permutes whenever the fit is repeated.
    """
    spirit = features["share_spirit"] if "share_spirit" in features else None
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
    """Largest pick-rate gap between any two clusters, over all items.

    The criterion a human can check: "these two builds differ by 60 points on
    Extra Charge" is a claim about the game, not about the statistics.
    """
    if len(prevalence) < 2:
        return float("nan")
    return float((prevalence.max(axis=0) - prevalence.min(axis=0)).max())


def fit_hero(
    purchases: pd.DataFrame,
    *,
    hero_id: int,
    hero_name: str = "",
    candidate_k: tuple[int, ...] = CANDIDATE_K,
) -> ArchetypeFit:
    """Select k for one hero, accepting a split only on all four criteria.

    Prefers the smallest k that qualifies: a hero with two real builds should
    not be cut into three because the third scored marginally better.
    """
    features = feature_matrix(purchases)
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
    for k in candidate_k:
        labels, score = _fit_k(features, k)
        labels = _canonical_order(features, labels)
        series = pd.Series(labels, index=features.index, name="archetype")

        prevalence = cluster_prevalence(purchases, series)
        separation = _separation(prevalence)
        shares = series.value_counts(normalize=True)
        smallest = float(shares.min())
        replication = _replication(purchases, features, k)

        centroids = features.groupby(series).mean()
        candidate = ArchetypeFit(
            hero_id=hero_id,
            hero_name=hero_name,
            k=k,
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
            candidate.reason = f"k={k} clears every criterion"
            return candidate
        if best_rejected is None:
            candidate.reason = "fails " + ", ".join(failures)
            best_rejected = candidate

    if best_rejected is not None:
        single.silhouette = best_rejected.silhouette
        single.replication = best_rejected.replication
        single.separation = best_rejected.separation
        single.smallest_share = best_rejected.smallest_share
        single.reason = f"single archetype: best k=2 {best_rejected.reason}"
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
) -> str:
    """Auto-label a cluster from its dominant slot type.

    A proposal for a human to accept or overrule, not an answer. Ivy's two
    clusters come back "Spirit Ivy" and "Gun Ivy", which is what a player
    would call them.
    """
    labels = {"share_spirit": "Spirit", "share_weapon": "Gun", "share_vitality": "Tank"}
    shares = {k: centroid.get(k, float("-inf")) for k in labels}
    dominant = max(shares, key=shares.get)
    return f"{labels[dominant]} {hero_name}"


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
) -> tuple[pd.DataFrame, list[ArchetypeFit], dict]:
    """Fit every hero, returning labels, per-hero fits, and reviewable metadata."""
    hero_names = hero_names or {h: v.name for h, v in assets.load_heroes().items()}
    overrides = load_name_overrides() if overrides is None else overrides
    item_names = {i: it.name for i, it in assets.load_items().items()}

    labels: list[pd.DataFrame] = []
    fits: list[ArchetypeFit] = []
    meta: dict = {"seed": ARCHETYPE_SEED, "heroes": {}}

    for hero_id, group in purchases.groupby("hero_id"):
        name = hero_names.get(int(hero_id), str(hero_id))
        fit = fit_hero(group, hero_id=int(hero_id), hero_name=name)
        fits.append(fit)

        frame = fit.labels.rename("archetype_id").reset_index()
        frame["hero_id"] = int(hero_id)
        labels.append(frame)

        prevalence = cluster_prevalence(group, fit.labels) if fit.split else pd.DataFrame()
        clusters = []
        for cluster in sorted(fit.labels.unique()):
            centroid = fit.centroids.loc[cluster] if fit.split else pd.Series(dtype=float)
            proposed = (
                propose_name(centroid, name, prevalence, cluster) if fit.split else name
            )
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
