"""Train/test splits.

Each split tests something different:

- `split_by_match` is the default. It keeps a match's 12 players on one side.
- `split_by_account` keeps each player on one side. A player shows up in about
  three matches on average (100,176 accounts over 296,332 player-matches when
  measured), so a match split puts the same player in train and test. A model
  can then score well by remembering that one account always buys Leech. If a
  model scores much better by match than by account, it is memorizing players.
- `split_by_time` trains on older matches and tests on newer ones, the way the
  tool is used. A gap here means patch drift.

Report scores under all three.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Features that aren't known at the moment of a purchase. Don't use them to
# predict a purchase.
#
# duration_s: nobody knows the match length when buying, and the match ending
# cuts off any purchase that would have come later. n_purchases: it counts the
# thing being predicted.
LEAKY_FEATURES = frozenset({"duration_s", "nw_final", "sold_fraction", "n_purchases"})


def split_by_match(
    df: pd.DataFrame, test_frac: float = 0.25, seed: int = 0
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split on match_id, so each match's rows stay on one side.

    A row split would put some of a player's ~17 purchases in train and the
    rest in test, and the model would be tested on the match it trained on.
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

    This is the strictest split. Players repeat their builds, and when
    measured, 87% of player-rows came from accounts with more than one match.
    Under `split_by_match` a model can learn one player's habits instead of
    what players in general do.
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

    match_id increases over time, so sorting by it sorts by date. Patches
    change which items are good, so if a model scores much worse here than on
    a random split, the patch has moved.
    """
    ordered = np.sort(df["match_id"].unique())
    cut = int(len(ordered) * (1 - test_frac))
    train_ids = set(ordered[:cut])
    mask = df["match_id"].isin(train_ids)
    return df[mask], df[~mask]


def replication_corr(
    table_a: pd.DataFrame, table_b: pd.DataFrame, column: str
) -> float:
    """Correlation of one column between two tables fitted on disjoint halves.

    A table that doesn't reproduce on the other half is noise. The archetype
    code uses this to check that a hero's archetypes mean the same thing on
    data they weren't fitted on. Returns NaN when fewer than 3 rows match.
    """
    joined = table_a[[column]].join(
        table_b[[column]], rsuffix="_other", how="inner"
    ).dropna()
    if len(joined) < 3:
        return float("nan")
    return float(np.corrcoef(joined[column], joined[f"{column}_other"])[0, 1])
