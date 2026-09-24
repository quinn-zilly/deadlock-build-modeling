"""Per-player spending features: cost, tier climb, and saving up.

Written for the discarded win-rate model. Nothing outside tests imports it.

Two patterns it measures, neither of which needs the corrupt
`net_worth_at_buy` field:

1. Tier climb. The first purchase is tier 1 97% of the time. By the tenth,
   39% are tier 3 and 11% are tier 4.
2. Saving up. The wait before a purchase grows with the tier jump: median 86s
   before a cheaper tier, 104s for the same tier, 183s for +2, 288s for +3.
   The data doesn't show souls held, but it does show the wait.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .assets import Item

# Feature names produced by economic_features(), in a stable order.
ECONOMIC_COLUMNS = [
    "total_spend",
    "mean_item_cost",
    "max_item_cost",
    "cost_slope",
    "tier_mean",
    "tier_max",
    "n_tier_jumps",
    "median_gap_s",
    "n_saved_up",
    "saved_up_fraction",
]

# A player who spent more had more. Correlation with rebuilt net worth over
# 8,000 matches:
#
#   total_spend      0.78   <- nearly the same as net worth
#   tier_mean        0.43
#   n_tier_jumps     0.40
#   mean_item_cost   0.36
#   n_saved_up       0.34
#   median_gap_s    -0.28
#   cost_slope      -0.25
#   saved_up_frac    0.17
#
# total_spend measures wealth, which is mostly a result of how the match went,
# so it is left out of BEHAVIOURAL_COLUMNS.
WEALTH_PROXY_COLUMNS = frozenset({"total_spend"})

# Features about how a player spent, not how much they had.
BEHAVIOURAL_COLUMNS = [c for c in ECONOMIC_COLUMNS if c not in WEALTH_PROXY_COLUMNS]

# A wait longer than this many times the player's own median wait counts as
# saving up. Using each player's own median works for fast and slow farmers.
SAVE_GAP_RATIO = 1.5


def annotate_costs(df: pd.DataFrame, items: dict[int, Item]) -> pd.DataFrame:
    """Attach item cost and tier to a purchase table."""
    out = df.copy()
    out["cost"] = out["item_id"].map({k: v.cost for k, v in items.items()})
    out["tier"] = out["item_id"].map({k: v.tier for k, v in items.items()})
    return out


def _gaps(times: np.ndarray) -> np.ndarray:
    """Seconds between consecutive purchases, one fewer than the purchase count."""
    if times.size < 2:
        return np.empty(0, dtype=float)
    return np.diff(np.sort(times))


def player_economics(group: pd.DataFrame) -> dict[str, float]:
    """Spending features for one player's purchases.

    `group` needs buy_time_s, cost, and tier columns, in any order.
    """
    order = np.argsort(group["buy_time_s"].to_numpy())
    times = group["buy_time_s"].to_numpy(dtype=float)[order]
    costs = group["cost"].to_numpy(dtype=float)[order]
    tiers = group["tier"].to_numpy(dtype=float)[order]

    costs = np.nan_to_num(costs, nan=0.0)
    valid_tiers = tiers[~np.isnan(tiers)]

    # How fast item cost rises. A flat slope means the player stayed on cheap
    # items.
    if costs.size >= 2:
        cost_slope = float(np.polyfit(np.arange(costs.size), costs, 1)[0])
    else:
        cost_slope = 0.0

    tier_diff = np.diff(valid_tiers) if valid_tiers.size >= 2 else np.empty(0)
    n_tier_jumps = int((tier_diff > 0).sum())

    gaps = _gaps(times)
    median_gap = float(np.median(gaps)) if gaps.size else 0.0

    # Saving up: a wait well above this player's median.
    if gaps.size and median_gap > 0:
        saved = gaps > (SAVE_GAP_RATIO * median_gap)
        n_saved_up = int(saved.sum())
        saved_fraction = float(saved.mean())
    else:
        n_saved_up, saved_fraction = 0, 0.0

    return {
        "total_spend": float(costs.sum()),
        "mean_item_cost": float(costs.mean()) if costs.size else 0.0,
        "max_item_cost": float(costs.max()) if costs.size else 0.0,
        "cost_slope": cost_slope,
        "tier_mean": float(valid_tiers.mean()) if valid_tiers.size else 0.0,
        "tier_max": float(valid_tiers.max()) if valid_tiers.size else 0.0,
        "n_tier_jumps": float(n_tier_jumps),
        "median_gap_s": median_gap,
        "n_saved_up": float(n_saved_up),
        "saved_up_fraction": saved_fraction,
    }


def economic_features(df: pd.DataFrame, items: dict[int, Item]) -> pd.DataFrame:
    """Spending features for every player, indexed by (match_id, player_slot).

    Gives the same results as `player_economics` per player, but vectorized.
    Over 5M purchases a per-player apply takes minutes; this takes seconds.
    """
    annotated = annotate_costs(df, items).sort_values(
        ["match_id", "player_slot", "buy_time_s"]
    )
    annotated["cost"] = annotated["cost"].fillna(0.0)

    keys = ["match_id", "player_slot"]
    grouped = annotated.groupby(keys, sort=False)

    out = grouped.agg(
        total_spend=("cost", "sum"),
        mean_item_cost=("cost", "mean"),
        max_item_cost=("cost", "max"),
        tier_mean=("tier", "mean"),
        tier_max=("tier", "max"),
    )

    # Gaps and tier jumps need each player's previous purchase.
    annotated["prev_time"] = grouped["buy_time_s"].shift()
    annotated["prev_tier"] = grouped["tier"].shift()
    annotated["gap"] = annotated["buy_time_s"] - annotated["prev_time"]
    annotated["tier_jump"] = annotated["tier"] - annotated["prev_tier"]

    gaps = annotated.dropna(subset=["gap"])
    gap_stats = gaps.groupby(keys, sort=False)["gap"].median().rename("median_gap_s")
    out = out.join(gap_stats)

    jumps = (
        annotated.assign(is_jump=(annotated["tier_jump"] > 0).astype("int8"))
        .groupby(keys, sort=False)["is_jump"]
        .sum()
        .rename("n_tier_jumps")
    )
    out = out.join(jumps)

    # Saving up: a gap above SAVE_GAP_RATIO times this player's median.
    gaps = gaps.join(gap_stats, on=keys)
    gaps = gaps.assign(
        saved=(gaps["gap"] > SAVE_GAP_RATIO * gaps["median_gap_s"]).astype("int8")
    )
    save_stats = gaps.groupby(keys, sort=False)["saved"].agg(["sum", "mean"])
    save_stats.columns = ["n_saved_up", "saved_up_fraction"]
    out = out.join(save_stats)

    # Least-squares slope of cost against purchase position.
    annotated["pos"] = grouped.cumcount()
    slope = (
        annotated.groupby(keys, sort=False)[["pos", "cost"]]
        .apply(_slope, include_groups=False)
        .rename("cost_slope")
    )
    out = out.join(slope)

    return out.fillna(0.0)[ECONOMIC_COLUMNS]


def _slope(group: pd.DataFrame) -> float:
    """Least-squares slope of cost against purchase position."""
    x = group["pos"].to_numpy(dtype=float)
    y = group["cost"].to_numpy(dtype=float)
    if x.size < 2:
        return 0.0
    var = ((x - x.mean()) ** 2).sum()
    if var == 0:
        return 0.0
    return float(((x - x.mean()) * (y - y.mean())).sum() / var)
