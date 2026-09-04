"""Train/test splits, and the leakage rules that make them meaningful.

Three splits, each answering a different question about a model:

- `split_by_match` is the default. One match contributes 12 correlated
  player-rows sharing an outcome, so a row-level split leaks the label.
- `split_by_account` is the one that matters for an imitation model. There are
  100,176 accounts across 296,332 player-matches (mean 2.96 appearances, max
  38), so a match-level split leaves the same player on both sides. A model
  can then score well by memorizing that account #X always buys Leech, which
  is not a strategy anyone can follow. A large match-vs-account gap IS the
  memorization signal.
- `split_by_time` mirrors deployment and exposes patch drift.

Report metrics under all three. They disagree in informative ways.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Features that encode match outcome rather than pre-purchase state. Never
# place these in a model that claims to predict a decision made mid-match.
#
# duration_s is the sharpest of these for a timing model: match length is not
# known when buying, and the match ending is the censoring event for any
# "when was this bought" question. n_purchases is the count of the very
# process being modeled.
LEAKY_FEATURES = frozenset({"duration_s", "nw_final", "sold_fraction", "n_purchases"})


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


def split_by_account(
    df: pd.DataFrame, test_frac: float = 0.25, seed: int = 0
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split on account_id, so no player appears on both sides.

    The strictest split available here, and the honest one for a model trained
    to imitate players. Build habits are strongly autocorrelated within an
    account: 61% of accounts appear in more than one match, and 87% of
    player-rows belong to such accounts. Under `split_by_match` a model can
    recall a specific player's preferences rather than learning what anyone
    should do.
    """
    accounts = df["account_id"].unique()
    rng = np.random.default_rng(seed)
    rng.shuffle(accounts)
    cut = int(len(accounts) * (1 - test_frac))
    train_ids = set(accounts[:cut])
    mask = df["account_id"].isin(train_ids)
    return df[mask], df[~mask]


def split_by_time(
    df: pd.DataFrame, test_frac: float = 0.25
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Train on older matches, test on newer.

    match_id increases with time, so it orders matches without a timestamp.
    This mirrors deployment and exposes patch drift; a large gap between this
    and the random split IS the drift signal. Item viability moves between
    patches, and so do the archetypes built on it.
    """
    ordered = np.sort(df["match_id"].unique())
    cut = int(len(ordered) * (1 - test_frac))
    train_ids = set(ordered[:cut])
    mask = df["match_id"].isin(train_ids)
    return df[mask], df[~mask]


def replication_corr(
    table_a: pd.DataFrame, table_b: pd.DataFrame, column: str
) -> float:
    """Correlation between the same statistic fitted on two disjoint splits.

    The cheapest guard against feeding noise to a model. A table that does not
    reproduce itself on held-out data cannot carry signal into one. Used here
    to decide whether a hero's archetypes mean the same thing on data they
    were not fitted on.
    """
    joined = table_a[[column]].join(
        table_b[[column]], rsuffix="_other", how="inner"
    ).dropna()
    if len(joined) < 3:
        return float("nan")
    return float(np.corrcoef(joined[column], joined[f"{column}_other"])[0, 1])
