"""Counter and synergy features.

These exist because the model does not find them on its own. Given raw enemy
multi-hot columns alongside the item set, the measured interaction gain beyond
additive is -0.0030 to +0.0005 depending on model capacity -- indistinguishable
from zero, and sign-unstable. Yet the counter effects are real and highly
significant in the raw statistics (Mystic Burst, p=1.6e-47). An effect that
exists but that trees cannot recover at this sample size has to be supplied
explicitly.

Two corrections are essential and both are easy to get wrong:

1. **Remove both main effects.** Facing a given hero is worth up to 12.9
   win-rate points regardless of what you buy, and a strong item wins more
   against everyone. A counter is the *interaction* -- what is left after both
   are subtracted. Removing only the enemy baseline puts strong items at the
   top of the table against every hero alike.
2. **Fit on training data only.** These tables are learned from outcomes, so
   fitting them on the full dataset leaks test labels into the features.

## Measured outcome: these features did NOT help

Tested on the early-game window with tables fit train-only, added on top of
controls + economics + item set:

    counter_score   -0.0093 AUC
    pair_score      -0.0003 AUC

The replication check explains why. Fitting the tables independently on the
train and test halves and correlating the two estimates:

    counter lifts     r = 0.05   <- essentially noise
    pair deviations   r = 0.68   <- real, reproducible structure

Counter effects are significant *in aggregate* (chi-square p ~ 1e-47 that item
win rates vary by opponent) but the per-cell estimates do not replicate: at
n >= 500 per cell the sampling error swamps a ~4-point effect. Feeding those
estimates to a model adds variance and costs nearly a point of AUC.

Pair deviations replicate well but still add nothing, because the model
already sees both items in the set encoding and can represent the combination
itself.

`counter_lift` and `pair_deviation` are kept -- they are honest descriptive
statistics, and the pair table is reliable enough to inform a recommender's
explanations. But `score_counters` output should not enter a predictive model
without first passing `replication_corr` at a threshold well above 0.05.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

MIN_COUNTER_N = 500
MIN_PAIR_N = 800


def enemy_rosters(df: pd.DataFrame) -> pd.DataFrame:
    """Per (match_id, player_slot), the heroes on the opposing team.

    Returned long-form -- one row per (player, enemy hero) -- which is what the
    counter aggregations join against.
    """
    players = (
        df.groupby(["match_id", "player_slot"])
        .agg(hero_id=("hero_id", "first"), team=("team", "first"), won=("won", "first"))
        .reset_index()
    )
    # Self-join within match, keeping opposing pairs only.
    pairs = players.merge(players, on="match_id", suffixes=("", "_opp"))
    pairs = pairs[pairs["team"] != pairs["team_opp"]]
    return pairs[
        ["match_id", "player_slot", "hero_id", "won", "hero_id_opp"]
    ].rename(columns={"hero_id_opp": "enemy_hero_id"})


def enemy_baselines(df: pd.DataFrame, min_n: int = 2000) -> pd.Series:
    """Win rate when facing each hero, ignoring items entirely.

    This is the confound that must come out of any counter estimate: some
    heroes are simply stronger, and an item bought against them inherits that
    win rate without countering anything.
    """
    rosters = enemy_rosters(df)
    stats = rosters.groupby("enemy_hero_id")["won"].agg(["mean", "size"])
    return stats[stats["size"] >= min_n]["mean"].rename("enemy_baseline")


def item_baselines(df: pd.DataFrame, min_n: int = MIN_COUNTER_N) -> pd.Series:
    """Win rate of players who bought each item, across all opponents."""
    owned = df[["match_id", "player_slot", "item_id"]].drop_duplicates()
    outcomes = df.groupby(["match_id", "player_slot"])["won"].first()
    joined = owned.join(outcomes, on=["match_id", "player_slot"])
    stats = joined.groupby("item_id")["won"].agg(["mean", "size"])
    return stats[stats["size"] >= min_n]["mean"].rename("item_baseline")


def counter_lift(
    df: pd.DataFrame,
    baselines: pd.Series | None = None,
    item_base: pd.Series | None = None,
    min_n: int = MIN_COUNTER_N,
) -> pd.DataFrame:
    """Per (item_id, enemy_hero_id): the INTERACTION, not either main effect.

    A counter is an item that does better against a specific hero than both
    its own general strength and that hero's general strength would predict.
    Both main effects must therefore come out:

        lift = wr(item, enemy) - wr(item) - wr(enemy) + wr(overall)

    Subtracting only the enemy baseline is not enough. Doing so puts strong
    items at the top of the table against every hero alike -- Infuser appeared
    against six different heroes at +0.11 to +0.14, which is Infuser being a
    good item, not a counter to anything.

    Pass `baselines` and `item_base` fitted on training data when scoring a
    test split.
    """
    if baselines is None:
        baselines = enemy_baselines(df)
    if item_base is None:
        item_base = item_baselines(df, min_n=min_n)

    rosters = enemy_rosters(df)
    buys = df[["match_id", "player_slot", "item_id"]].drop_duplicates()
    joined = buys.merge(rosters, on=["match_id", "player_slot"])
    overall = float(joined["won"].mean())

    stats = (
        joined.groupby(["item_id", "enemy_hero_id"])["won"]
        .agg(["mean", "size"])
        .rename(columns={"mean": "win_rate", "size": "n"})
        .reset_index()
    )
    stats = stats[stats["n"] >= min_n]
    stats["enemy_baseline"] = stats["enemy_hero_id"].map(baselines)
    stats["item_baseline"] = stats["item_id"].map(item_base)
    stats = stats.dropna(subset=["enemy_baseline", "item_baseline"])

    # Interaction: observed minus both main effects, plus the grand mean back.
    stats["lift"] = (
        stats["win_rate"]
        - stats["item_baseline"]
        - stats["enemy_baseline"]
        + overall
    )

    log.info("counter table: %d (item, enemy) cells", len(stats))
    return stats.set_index(["item_id", "enemy_hero_id"]).sort_values(
        "lift", ascending=False
    )


def pair_deviation(
    df: pd.DataFrame, min_n: int = MIN_PAIR_N, top_items: int = 60
) -> pd.DataFrame:
    """Per item pair: observed win rate minus the additive expectation.

    Expectation is `wr(a) + wr(b) - base`, so a pair that merely combines two
    good items scores zero. Negative values -- redundant stat-stacking -- are
    as informative as positive ones, and empirically they are the larger
    effects.
    """
    owned = (
        df.groupby(["match_id", "player_slot"])
        .agg(items=("item_id", frozenset), won=("won", "first"))
    )
    base = float(owned["won"].mean())

    common = df["item_id"].value_counts().head(top_items).index
    solo: dict[int, float] = {}
    for item in common:
        mask = owned["items"].map(lambda s, i=item: i in s)
        if mask.sum() >= min_n:
            solo[int(item)] = float(owned.loc[mask, "won"].mean())

    rows = []
    keys = sorted(solo)
    for idx, a in enumerate(keys):
        has_a = owned["items"].map(lambda s, i=a: i in s)
        if not has_a.any():
            continue
        subset = owned[has_a]
        for b in keys[idx + 1 :]:
            mask = subset["items"].map(lambda s, i=b: i in s)
            n = int(mask.sum())
            if n < min_n:
                continue
            observed = float(subset.loc[mask, "won"].mean())
            expected = solo[a] + solo[b] - base
            rows.append(
                {
                    "item_a": a,
                    "item_b": b,
                    "observed": observed,
                    "expected": expected,
                    "deviation": observed - expected,
                    "n": n,
                }
            )

    if not rows:
        return pd.DataFrame(
            columns=["item_a", "item_b", "observed", "expected", "deviation", "n"]
        ).set_index(["item_a", "item_b"])

    out = pd.DataFrame(rows).set_index(["item_a", "item_b"])
    log.info("pair table: %d pairs", len(out))
    return out.sort_values("deviation")


def score_counters(
    df: pd.DataFrame, counters: pd.DataFrame
) -> pd.Series:
    """Summed counter lift for each player's build against their real enemies.

    One number per player: how well their items match the specific opposition
    they faced. Items or matchups absent from the table contribute nothing.
    """
    rosters = enemy_rosters(df)
    buys = df[["match_id", "player_slot", "item_id"]].drop_duplicates()
    joined = buys.merge(rosters, on=["match_id", "player_slot"])

    lifts = counters["lift"]
    joined["lift"] = pd.MultiIndex.from_arrays(
        [joined["item_id"], joined["enemy_hero_id"]]
    ).map(lifts)

    return (
        joined.groupby(["match_id", "player_slot"])["lift"]
        .sum()
        .rename("counter_score")
    )


def score_pairs(df: pd.DataFrame, pairs: pd.DataFrame) -> pd.Series:
    """Summed pair deviation over the item combinations a player actually held.

    Captures redundancy as well as synergy: a build stacking overlapping stats
    scores negative.
    """
    if pairs.empty:
        idx = df.groupby(["match_id", "player_slot"]).size().index
        return pd.Series(0.0, index=idx, name="pair_score")

    lookup = pairs["deviation"].to_dict()
    owned = df.groupby(["match_id", "player_slot"])["item_id"].apply(
        lambda s: sorted(set(s))
    )

    scores = []
    for items in owned:
        total = 0.0
        for i, a in enumerate(items):
            for b in items[i + 1 :]:
                total += lookup.get((a, b), 0.0)
        scores.append(total)

    # Preserve the (match_id, player_slot) index names, or callers cannot join.
    return pd.Series(scores, index=owned.index, name="pair_score")


def replication_corr(
    table_a: pd.DataFrame, table_b: pd.DataFrame, column: str
) -> float:
    """Correlation between the same statistic fitted on two disjoint splits.

    The cheapest guard against feeding noise to a model. A table that does not
    reproduce itself on held-out data cannot carry signal into one. Counter
    lifts score 0.05 here; pair deviations score 0.68.
    """
    joined = table_a[[column]].join(
        table_b[[column]], rsuffix="_other", how="inner"
    ).dropna()
    if len(joined) < 3:
        return float("nan")
    return float(np.corrcoef(joined[column], joined[f"{column}_other"])[0, 1])
