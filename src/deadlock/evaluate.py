"""The checks that would have caught the last failure.

This module exists because of `docs/DIAGNOSIS.md`: the previous model passed an
AUC gate, a replication guard, a popularity floor, a shuffled-label test and an
antisymmetry test, and its builds were still unusable. Every one of those was an
aggregate over the whole item table. None of them ever asked the question a
player asks in one glance -- "where is Quicksilver Reload?"

So the primary gate here is not an aggregate. It is a named, per-item
assertion:

    an item bought by >=70% of this hero+archetype's players
    must appear in the build generated for them

That is trivially automatable, it fails loudly with the item's name, and it
reproduces the exact judgement a human made when they rejected the old builds.

The order metrics answer the question the product actually claims to answer.
Membership is necessary but not sufficient: a build carrying all nine Wraith
staples in a nonsensical order passes the prevalence gate and is still wrong.
Kendall tau against the population's median order is what catches that.

Membership is measured against real players, never against that median order.
The median-order reference ranks items by when they are bought, so its top 12
are the earliest -- cheap components that are absorbed within minutes. Scoring
set overlap against it reported J@12 0.143 for builds that beat the
player-vs-player ceiling in 72 of 75 cells. See `membership_vs_players`.

Baselines are measured, not assumed. On Wraith, held out by match:

    popularity, excluding owned        0.144
    modal item at position k           0.198
    P(next | position k, prev item)    0.328   <- the bar to beat
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats

from typing import TYPE_CHECKING

from .state import GameState

if TYPE_CHECKING:  # pragma: no cover - import only for the annotation
    from . import sequence

log = logging.getLogger(__name__)

# An item bought by this fraction of a population is a staple for it. Below
# this the item is a real choice and its absence from a build is not an error.
PREVALENCE_THRESHOLD = 0.70

# Cells thinner than this cannot support a prevalence claim. Report the gate as
# inconclusive rather than passing it -- a gate that passes on no evidence is
# how the last pipeline stayed green.
MIN_CELL_OBSERVATIONS = 300


@dataclass
class GateResult:
    """Outcome of the prevalence gate for one hero+archetype build."""

    hero_id: int
    archetype_id: int
    n: int
    staples: dict[int, float] = field(default_factory=dict)
    missing: dict[int, float] = field(default_factory=dict)
    inconclusive: bool = False

    @property
    def passed(self) -> bool:
        return not self.inconclusive and not self.missing

    def describe(self, item_names: dict[int, str] | None = None) -> str:
        name = (item_names or {}).get
        if self.inconclusive:
            return (
                f"INCONCLUSIVE hero={self.hero_id} archetype={self.archetype_id}: "
                f"n={self.n:,} < {MIN_CELL_OBSERVATIONS}"
            )
        if self.passed:
            return (
                f"PASS hero={self.hero_id} archetype={self.archetype_id}: "
                f"all {len(self.staples)} staples present (n={self.n:,})"
            )
        missing = ", ".join(
            f"{name(i, i)} ({p:.1%})"
            for i, p in sorted(self.missing.items(), key=lambda kv: -kv[1])
        )
        return (
            f"FAIL hero={self.hero_id} archetype={self.archetype_id}: "
            f"missing {len(self.missing)} of {len(self.staples)} staples -- {missing}"
        )


def item_prevalence(df: pd.DataFrame) -> pd.Series:
    """Fraction of player-matches that ever bought each item.

    Computed over player-matches, not purchase rows: an item is either in a
    player's build or it is not, and no item is ever bought twice.
    """
    players = df[["match_id", "player_slot"]].drop_duplicates()
    n_players = len(players)
    if n_players == 0:
        return pd.Series(dtype=float, name="prevalence")
    buyers = (
        df[["item_id", "match_id", "player_slot"]]
        .drop_duplicates()
        .groupby("item_id")
        .size()
    )
    return (buyers / n_players).rename("prevalence").sort_values(ascending=False)


def prevalence_gate(
    build_item_ids: list[int] | set[int],
    df: pd.DataFrame,
    *,
    hero_id: int,
    archetype_id: int = 0,
    threshold: float = PREVALENCE_THRESHOLD,
    min_observations: int = MIN_CELL_OBSERVATIONS,
) -> GateResult:
    """Assert that a generated build contains its population's staples.

    `df` must already be restricted to the population the build claims to
    describe -- one hero, and one archetype where the hero has more than one.
    """
    n = len(df[["match_id", "player_slot"]].drop_duplicates())
    if n < min_observations:
        return GateResult(hero_id, archetype_id, n, inconclusive=True)

    prevalence = item_prevalence(df)
    staples = prevalence[prevalence >= threshold].to_dict()
    owned = set(build_item_ids)
    missing = {i: p for i, p in staples.items() if i not in owned}
    return GateResult(hero_id, archetype_id, n, staples=staples, missing=missing)


def population_order(df: pd.DataFrame) -> pd.Series:
    """Median buy position of each item across a population.

    The reference ordering a generated build is compared against. Median rather
    than mean because buy_index is bounded below but not above, and a few very
    long matches would otherwise drag every staple later.
    """
    return (
        df.groupby("item_id")["buy_index"]
        .median()
        .rename("median_position")
        .sort_values()
    )


@dataclass
class OrderResult:
    """How closely a build's ordering tracks the population's."""

    kendall_tau: float
    n_shared: int
    jaccard_6: float
    jaccard_12: float

    @property
    def reliable(self) -> bool:
        """Tau over a handful of items is not evidence of anything."""
        return self.n_shared >= 5

    def __str__(self) -> str:
        tau = f"{self.kendall_tau:+.3f}" if not np.isnan(self.kendall_tau) else "n/a"
        flag = "" if self.reliable else "  [too few shared items]"
        return (
            f"tau={tau} on {self.n_shared} shared  "
            f"J@6={self.jaccard_6:.2f} J@12={self.jaccard_12:.2f}{flag}"
        )


def _jaccard(a: list[int], b: list[int], k: int) -> float:
    top_a, top_b = set(a[:k]), set(b[:k])
    if not top_a and not top_b:
        return float("nan")
    return len(top_a & top_b) / len(top_a | top_b)


def order_distance(generated: list[int], reference: list[int]) -> OrderResult:
    """Compare a generated build's ordering against a reference ordering.

    Kendall tau runs over the items the two have in common, since tau is
    undefined on disjoint sets. `n_shared` is reported alongside because a high
    tau on three shared items says nothing -- callers must not read the
    coefficient without it.
    """
    reference_set = set(reference)
    shared = [i for i in generated if i in reference_set]
    n_shared = len(shared)
    if n_shared < 2:
        tau = float("nan")
    else:
        gen_rank = {item: r for r, item in enumerate(generated)}
        ref_rank = {item: r for r, item in enumerate(reference)}
        tau, _ = stats.kendalltau(
            [gen_rank[i] for i in shared], [ref_rank[i] for i in shared]
        )
    return OrderResult(
        kendall_tau=float(tau),
        n_shared=n_shared,
        jaccard_6=_jaccard(generated, reference, 6),
        jaccard_12=_jaccard(generated, reference, 12),
    )


def player_sequences(cell: pd.DataFrame, *, min_length: int = 12) -> list[list[int]]:
    """Each player's purchase sequence in a cell, longest-first ties by buy order.

    Players with fewer than `min_length` purchases are dropped, since Jaccard@12
    over a 5-item sequence measures how short the match was, not how the player
    built.
    """
    grouped = (
        cell.sort_values("buy_index")
        .groupby(["match_id", "player_slot"])["item_id"]
        .apply(list)
    )
    return [seq for seq in grouped if len(seq) >= min_length]


@dataclass
class MembershipResult:
    """Set overlap against real players, with the ceiling real players set."""

    generated: float
    ceiling: float
    n_players: int

    @property
    def ratio(self) -> float:
        """Above 1.0 the build matches a player better than players match."""
        return self.generated / self.ceiling if self.ceiling else float("nan")

    def __str__(self) -> str:
        return (
            f"J@12 {self.generated:.3f} vs ceiling {self.ceiling:.3f} "
            f"({self.ratio:.2f}x, n={self.n_players})"
        )


def membership_vs_players(
    generated: list[int],
    cell: pd.DataFrame,
    *,
    k: int = 12,
    sample: int = 300,
    seed: int = 0,
) -> MembershipResult:
    """Jaccard@k of a build against real players, against the player-vs-player bar.

    **Do not score membership against `population_order`.** That ranks items by
    median buy position, so its top 12 are the twelve items bought *earliest* --
    Close Quarters, Headshot Booster, Healing Rite, cheap tier 1 components that
    are absorbed almost immediately. A real player's first twelve purchases are
    their staples. The two sets cannot overlap much whatever the model does, and
    scoring that way reported J@12 0.143 for builds that are in fact closer to a
    real player than two real players are to each other:

        reference by median buy position, vs a player   0.140
        real player vs real player                      0.336   <- the ceiling
        generated build vs a player                     0.412

    Measured over all 75 cells; the build beat the ceiling in 72 of them. The
    same correction `docs/DIAGNOSIS.md` records for the next-item baselines --
    a metric is only a bar once you know what the honest bar is.

    Players disagree with each other, so the ceiling is not 1.0 and a build that
    reached 1.0 would be overfitting to one player rather than describing the
    population.
    """
    rng = np.random.default_rng(seed)
    sequences = player_sequences(cell, min_length=k)
    if len(sequences) < 2:
        return MembershipResult(float("nan"), float("nan"), len(sequences))

    size = min(sample, len(sequences))
    drawn = [sequences[i] for i in rng.choice(len(sequences), size, replace=False)]
    against = float(np.mean([_jaccard(generated, seq, k) for seq in drawn]))

    pairs = rng.choice(size, (sample, 2))
    ceiling = float(
        np.mean([_jaccard(drawn[i], drawn[j], k) for i, j in pairs if i != j])
    )
    return MembershipResult(against, ceiling, len(sequences))


# --- Next-item baselines -------------------------------------------------
#
# Each takes the training purchases and returns a lookup: given a hero and
# some context, a ranked list of candidates. They exist to be beaten, and to
# make "the model works" a comparative claim rather than an absolute one.


def popularity_baseline(train: pd.DataFrame) -> dict[int, list[int]]:
    """Rank by hero-level pick rate. The floor."""
    return {
        hero: item_prevalence(g).index.tolist()
        for hero, g in train.groupby("hero_id")
    }


def positional_baseline(train: pd.DataFrame) -> dict[tuple[int, int], list[int]]:
    """Rank by what is most often bought at this position for this hero."""
    counts = (
        train.groupby(["hero_id", "buy_index", "item_id"])
        .size()
        .rename("n")
        .reset_index()
        .sort_values("n", ascending=False)
    )
    return {
        (hero, pos): g["item_id"].tolist()
        for (hero, pos), g in counts.groupby(["hero_id", "buy_index"])
    }


def bigram_baseline(train: pd.DataFrame) -> dict[tuple[int, int], list[int]]:
    """Rank by what follows the previous item for this hero. The bar: 0.328.

    Keyed on (hero, previous item) rather than (hero, position) -- measured on
    Wraith this nearly doubles positional accuracy, which is the main evidence
    that purchase signal is local rather than positional.
    """
    df = train.sort_values(["match_id", "player_slot", "buy_index"])
    prev = df.groupby(["match_id", "player_slot"])["item_id"].shift(1)
    pairs = df.assign(prev_item=prev).dropna(subset=["prev_item"])
    pairs["prev_item"] = pairs["prev_item"].astype(int)
    counts = (
        pairs.groupby(["hero_id", "prev_item", "item_id"])
        .size()
        .rename("n")
        .reset_index()
        .sort_values("n", ascending=False)
    )
    return {
        (hero, prev_item): g["item_id"].tolist()
        for (hero, prev_item), g in counts.groupby(["hero_id", "prev_item"])
    }


def top_k_accuracy(
    predictions: list[list[int]], actuals: list[int], k: int = 1
) -> float:
    """Fraction of decisions where the actual item is in the top k predicted."""
    if not actuals:
        return float("nan")
    hits = sum(1 for pred, actual in zip(predictions, actuals) if actual in pred[:k])
    return hits / len(actuals)


def score_baselines(train: pd.DataFrame, test: pd.DataFrame) -> pd.DataFrame:
    """Run all three baselines over the same held-out decisions.

    Each prediction excludes items the player already owns, since re-buying is
    not a legal move -- without that exclusion the popularity baseline scores
    against itself.
    """
    popularity = popularity_baseline(train)
    positional = positional_baseline(train)
    bigram = bigram_baseline(train)

    test = test.sort_values(["match_id", "player_slot", "buy_index"])
    grouped = test.groupby(["match_id", "player_slot"], sort=False)

    rows: dict[str, list[list[int]]] = {"popularity": [], "positional": [], "bigram": []}
    actuals: list[int] = []

    for _, g in grouped:
        hero = int(g["hero_id"].iloc[0])
        items = g["item_id"].tolist()
        positions = g["buy_index"].tolist()
        owned: set[int] = set()
        for idx, (item, pos) in enumerate(zip(items, positions)):
            prev_item = items[idx - 1] if idx else None
            def drop_owned(ranked: list[int]) -> list[int]:
                return [i for i in ranked if i not in owned]

            rows["popularity"].append(drop_owned(popularity.get(hero, [])))
            rows["positional"].append(drop_owned(positional.get((hero, pos), [])))
            rows["bigram"].append(
                drop_owned(bigram.get((hero, prev_item), [])) if prev_item is not None else []
            )
            actuals.append(item)
            owned.add(item)

    return pd.DataFrame(
        [
            {
                "baseline": name,
                "top1": top_k_accuracy(preds, actuals, k=1),
                "top3": top_k_accuracy(preds, actuals, k=3),
                "n_decisions": len(actuals),
            }
            for name, preds in rows.items()
        ]
    )


def next_item_accuracy(
    model: "sequence.SequenceModel",
    test: pd.DataFrame,
    archetypes: pd.DataFrame,
    *,
    limit: int | None = None,
    min_badge: float | None = None,
) -> dict:
    """Teacher-forced next-item accuracy over held-out decisions.

    Every decision is made from the player's real prefix, so a model is never
    scored on a trajectory it invented. `limit` caps the number of decisions,
    which is what makes two archetype fits comparable: the same run, the same
    test frame and the same cap score the same decisions under both.

    Lives here rather than in a script because a figure recorded from one run
    configuration and compared against another is not a comparison -- and that
    mistake has already been made once in this work.

    `min_badge` restricts the scored decisions to a bracket, which is how a
    badge-weighted model has to be judged: weighting the tables toward strong
    play makes general-population accuracy worse on purpose, so the
    all-comers figure would report the intended change as a regression. A test
    frame carrying no badge column scores nothing under `min_badge` rather
    than quietly scoring everything.
    """
    if min_badge is not None:
        if "average_badge" not in test:
            test = test.iloc[:0]
        else:
            badge = pd.to_numeric(test["average_badge"], errors="coerce")
            test = test[badge >= min_badge]

    labels = (
        archetypes.set_index(["match_id", "player_slot"])["archetype_id"]
        if len(archetypes)
        else pd.Series(dtype=int)
    )
    test = test.sort_values(["match_id", "player_slot", "buy_index"])

    hits1 = hits3 = total = 0
    levels: dict[str, int] = {}
    for (match_id, slot), g in test.groupby(["match_id", "player_slot"], sort=False):
        if limit and total >= limit:
            break
        hero = int(g["hero_id"].iloc[0])
        archetype = int(labels.get((match_id, slot), 0)) if len(labels) else 0
        items = g["item_id"].tolist()
        times = g["buy_time_s"].tolist()

        for idx, actual in enumerate(items):
            if limit and total >= limit:
                break
            state = GameState(
                hero_id=hero,
                game_time_s=float(times[idx]),
                souls_available=10**9,
                owned_item_ids=frozenset(items[:idx]),
                purchased=tuple(items[:idx]),
                archetype_posterior={archetype: 1.0},
            )
            ids, probability = model.distribution(state)
            if not len(ids):
                total += 1
                continue
            order = np.argsort(-probability)
            ranked = ids[order][:3].tolist()
            if ranked[0] == actual:
                hits1 += 1
                trace = model.evidence(state, actual)
                if trace is not None:
                    levels[trace.level] = levels.get(trace.level, 0) + 1
            if actual in ranked:
                hits3 += 1
            total += 1

    return {
        "top1": hits1 / total if total else float("nan"),
        "top3": hits3 / total if total else float("nan"),
        "n_decisions": total,
        "levels": levels,
    }
