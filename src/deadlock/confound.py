"""The honesty check: can an item model beat a model that only knows wealth?

Deadlock snowballs on souls, so item ownership is entangled with economic
lead. A model given item features will happily reach a respectable AUC by
inferring wealth from them -- expensive items imply a rich player, and rich
players win -- while learning nothing about item value.

This module builds the baseline that makes that failure visible. Two gates:

1. wealth_baseline() trains on net worth, badge, and duration with NO item
   features. Its AUC is the floor. An item model that does not clear it by
   more than cross-validation noise has not learned anything about items.
2. placebo_test() scores items chosen for having no plausible causal effect
   on winning. After adjustment these should sit near 0.5; large "effects"
   mean the wealth adjustment is leaking.

Both gates are allowed to fail. If they do, the finding is that the item
signal is weak once wealth is controlled -- report it rather than tuning
until it disappears.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

log = logging.getLogger(__name__)

# Wealth/context known AT THE MOMENT OF PURCHASE. Two exclusions matter:
#
#   duration_s  -- how long the match ran is not known when buying, and it
#                  leaks the outcome (stomps end early).
#   nw_final    -- the player's end-of-match net worth is the scoreline.
#
# Including either produces a baseline near 0.92 AUC that no item model can
# beat, because the outcome has already been given away. Restricted to
# genuinely pre-decision state the baseline lands near 0.73, and on early-game
# purchases alone near 0.60 -- a floor an item model can meaningfully clear.
BASELINE_FEATURES = [
    "nw_at_buy",
    "nw_vs_match_median",
    "nw_vs_team_avg",
    "nw_vs_enemy_avg",
    "nw_rank_in_match",
    "average_badge",
    "buy_time_s",
    "phase",
]

# Features that encode match outcome rather than pre-purchase state. Never
# place these in a model whose AUC is being compared against the gate.
LEAKY_FEATURES = frozenset({"duration_s", "nw_final", "sold_fraction", "n_purchases"})


@dataclass
class BaselineResult:
    auc: float
    n_train: int
    n_test: int
    coefficients: pd.Series

    def __str__(self) -> str:
        return (
            f"wealth baseline AUC={self.auc:.4f} "
            f"(train={self.n_train:,}, test={self.n_test:,})"
        )


def split_by_match(
    df: pd.DataFrame, test_frac: float = 0.25, seed: int = 0
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split on match_id, never on rows.

    One match contributes 12 correlated player-rows sharing an outcome, and a
    player contributes ~17 purchase-rows sharing theirs. A row-level split
    puts a player's own purchases on both sides and leaks the label directly.
    """
    matches = df["match_id"].unique()
    rng = np.random.default_rng(seed)
    rng.shuffle(matches)
    cut = int(len(matches) * (1 - test_frac))
    train_ids = set(matches[:cut])
    mask = df["match_id"].isin(train_ids)
    return df[mask], df[~mask]


def split_by_time(
    df: pd.DataFrame, test_frac: float = 0.25
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Train on older matches, test on newer.

    match_id increases with time, so it orders matches without a timestamp.
    This mirrors deployment and exposes patch drift; a large gap between this
    and the random split IS the drift signal.
    """
    ordered = np.sort(df["match_id"].unique())
    cut = int(len(ordered) * (1 - test_frac))
    train_ids = set(ordered[:cut])
    mask = df["match_id"].isin(train_ids)
    return df[mask], df[~mask]


def wealth_baseline(
    train: pd.DataFrame,
    test: pd.DataFrame,
    features: list[str] | None = None,
) -> BaselineResult:
    """Logistic regression on wealth and context only. No item features."""
    features = features or BASELINE_FEATURES
    missing = [f for f in features if f not in train.columns]
    if missing:
        raise KeyError(f"missing baseline features: {missing}")
    leaks = LEAKY_FEATURES.intersection(features)
    if leaks:
        raise ValueError(
            f"outcome-leaking features in baseline: {sorted(leaks)}. These "
            f"encode how the match ended, not what was known at purchase time."
        )

    x_train = train[features].astype(float).fillna(0.0)
    x_test = test[features].astype(float).fillna(0.0)

    model = make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=2000),
    )
    model.fit(x_train, train["won"].astype(int))
    probs = model.predict_proba(x_test)[:, 1]
    auc = float(roc_auc_score(test["won"].astype(int), probs))

    coefs = pd.Series(
        model[-1].coef_[0], index=features, name="coefficient"
    ).sort_values(key=abs, ascending=False)

    return BaselineResult(auc, len(x_train), len(x_test), coefs)


def stratified_item_winrate(
    df: pd.DataFrame,
    min_matches: int = 50,
) -> pd.DataFrame:
    """Model-free item win rates, standardized across wealth strata.

    For each item, compute the win rate within every (phase, net-worth
    quintile) cell, then average those cells weighting by the *population*
    share of each cell rather than the item's own. That removes the effect of
    an item being bought disproportionately by rich players -- the same
    reweighting idea behind the API's adjusted_win_rate, computed here on
    reconstructed net worth we control.

    Returns raw and adjusted rates so the gap is visible: a large positive gap
    means the item's raw rate was flattered by wealthy buyers.
    """
    strata = ["phase", "nw_quintile"]
    population = df.groupby(strata).size().rename("stratum_n")
    weights = population / population.sum()

    cells = (
        df.groupby(["item_id", *strata])["won"]
        .agg(["mean", "size"])
        .rename(columns={"mean": "cell_win_rate", "size": "cell_n"})
        .reset_index()
    )
    cells = cells.merge(weights.rename("weight"), on=strata, how="left")

    def _adjust(group: pd.DataFrame) -> pd.Series:
        w = group["weight"]
        # Renormalize: an item absent from some strata must not be penalized.
        w = w / w.sum() if w.sum() > 0 else w
        return pd.Series(
            {
                "adjusted_win_rate": float((group["cell_win_rate"] * w).sum()),
                "n": int(group["cell_n"].sum()),
                "n_strata": len(group),
            }
        )

    adjusted = cells.groupby("item_id").apply(_adjust, include_groups=False)
    raw = df.groupby("item_id")["won"].mean().rename("raw_win_rate")

    out = adjusted.join(raw)
    out["wealth_inflation"] = out["raw_win_rate"] - out["adjusted_win_rate"]
    out = out[out["n"] >= min_matches]
    return out.sort_values("adjusted_win_rate", ascending=False)


def placebo_test(
    df: pd.DataFrame, item_ids: list[int], min_matches: int = 50
) -> pd.DataFrame:
    """Adjusted win rates for items expected to have no real effect.

    These should land near 0.5. Systematic deviation means the wealth
    adjustment is leaking and the item effects elsewhere are overstated.
    """
    rates = stratified_item_winrate(df, min_matches=min_matches)
    return rates[rates.index.isin(item_ids)]


def report_gate(item_auc: float, baseline: BaselineResult, tolerance: float = 0.005) -> str:
    """One-line verdict on whether an item model cleared the wealth floor."""
    lift = item_auc - baseline.auc
    # math.isclose guards the boundary: 0.705 - 0.700 evaluates to
    # 0.0050000000000000044, so a bare <= would call that a pass.
    if lift < tolerance or math.isclose(lift, tolerance, rel_tol=1e-9):
        return (
            f"FAILED GATE: item AUC {item_auc:.4f} vs wealth baseline "
            f"{baseline.auc:.4f} (lift {lift:+.4f}). The item model has not "
            f"demonstrably learned anything beyond wealth."
        )
    return (
        f"passed gate: item AUC {item_auc:.4f} vs wealth baseline "
        f"{baseline.auc:.4f} (lift {lift:+.4f})."
    )
