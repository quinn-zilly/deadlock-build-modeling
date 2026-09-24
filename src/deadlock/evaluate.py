"""Checks on generated builds and next-item predictions.

The main check is per item, not an aggregate (`docs/DIAGNOSIS.md` explains
why):

    an item bought by at least 70% of a hero and archetype's players
    must appear in the build generated for them

It fails with the missing item's name.

Having the right items isn't enough. A build with all nine Wraith staples in a
senseless order still passes that check, so `order_distance` compares the
order to the players' median order with Kendall tau.

Item overlap is compared against real players (`membership_vs_players`), not
against the median order. See that function for why.

Next-item baselines, measured on Wraith with a split by match:

    popularity, excluding owned        0.144
    modal item at position k           0.198
    P(next | prev item), the bigram    0.328   <- the bar to beat
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

# An item bought by at least this share of a cell's players is a staple.
PREVALENCE_THRESHOLD = 0.70

# A cell with fewer players than this is reported as inconclusive, not passed.
MIN_CELL_OBSERVATIONS = 300


@dataclass
class GateResult:
    """Result of the staple gate for one hero and archetype."""

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
    """Share of player-matches that bought each item, highest first."""
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
    """Check that a generated build contains every staple of its cell.

    `df` must hold only the build's cell: one hero, and one archetype if the
    hero has more than one.
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
    """Median purchase position of each item, earliest first.

    The median, because a few very long matches would pull a mean later.
    """
    return (
        df.groupby("item_id")["buy_index"]
        .median()
        .rename("median_position")
        .sort_values()
    )


@dataclass
class OrderResult:
    """How closely a build's order matches a reference order."""

    kendall_tau: float
    n_shared: int
    jaccard_6: float
    jaccard_12: float

    @property
    def reliable(self) -> bool:
        """True when tau is computed over at least 5 shared items."""
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
    """Compare a generated build's order with a reference order.

    Kendall tau is computed over the items both lists contain. Always read it
    with `n_shared`: a high tau over three items means nothing.
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
    """Each player's purchase sequence in a cell.

    Drops players with fewer than `min_length` purchases. Jaccard@12 on a
    5-item sequence measures how short the match was, not the build.
    """
    grouped = (
        cell.sort_values("buy_index")
        .groupby(["match_id", "player_slot"])["item_id"]
        .apply(list)
    )
    return [seq for seq in grouped if len(seq) >= min_length]


@dataclass
class MembershipResult:
    """A build's item overlap with real players, and players' overlap with each other."""

    generated: float
    ceiling: float
    n_players: int

    @property
    def ratio(self) -> float:
        """Above 1.0, the build is closer to a player than players are to each other."""
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
    """Mean Jaccard@k of a build against sampled players, and of players against each other.

    Don't compare against `population_order` instead. Its top 12 are the
    items bought earliest, like Close Quarters and Headshot Booster, cheap
    components that are absorbed within minutes. Measured over 75 cells:

        median-order reference vs a player   0.140
        player vs player                     0.336   <- the ceiling
        generated build vs a player          0.412

    The build beat the ceiling in 72 of 75 cells. Scored against the median
    order, the same builds looked bad (0.143).

    Players differ from each other, so the ceiling is well below 1.0.
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
# Each takes the training purchases and returns a lookup from a hero and some
# context to a ranked list of items. The model has to beat them.


def popularity_baseline(train: pd.DataFrame) -> dict[int, list[int]]:
    """Rank items by the hero's pick rate."""
    return {
        hero: item_prevalence(g).index.tolist()
        for hero, g in train.groupby("hero_id")
    }


def positional_baseline(train: pd.DataFrame) -> dict[tuple[int, int], list[int]]:
    """Rank items by how often the hero buys them at this position."""
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
    """Rank items by how often the hero buys them right after the previous item.

    This is the baseline to beat (0.328 top-1 on Wraith). On Wraith it scores
    much higher than the positional baseline, so the previous item predicts
    the next better than the position does.
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
    """Share of decisions where the actual item is in the top k predictions."""
    if not actuals:
        return float("nan")
    hits = sum(1 for pred, actual in zip(predictions, actuals) if actual in pred[:k])
    return hits / len(actuals)


def score_baselines(train: pd.DataFrame, test: pd.DataFrame) -> pd.DataFrame:
    """Score all three baselines on the same held-out decisions.

    Predictions skip items the player already owns. Without that, the
    popularity baseline would keep predicting items already bought.
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
    """Next-item accuracy on held-out purchases.

    Each prediction starts from the player's real purchases so far, not from
    the model's own earlier predictions. `limit` caps the number of
    decisions. To compare two archetype fits, score both in the same run with
    the same test frame and limit.

    `min_badge` scores only decisions at or above that badge. Use it for a
    badge-weighted model, which is meant to do worse on the average player. A
    test frame with no badge column scores nothing under `min_badge`.
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
