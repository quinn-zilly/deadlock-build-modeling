"""Economic features: what buy position was actually standing in for.

Encoding items by purchase position measurably hurts the model (AUC -0.0055
against a plain unordered item set). The reason is that position is largely a
price proxy -- `corr(buy_index, cost) = 0.435`, with median item cost rising
800 -> 1600 across the first eight buys -- so splitting an item across position
columns fragments its samples along a variable that mostly restates the item's
own price.

This module states the economics directly instead. Two things are worth
capturing, neither of which needs the corrupt `net_worth_at_buy` field:

1. The **tier ladder**. Buy #1 is 97% tier 1; by buy #10 it is 39% tier 3 and
   11% tier 4. How fast a player climbs that ladder is a real signal.
2. **Saving behaviour**. The gap before a purchase scales monotonically with
   the size of the tier jump -- median 86s for a tier drop, 104s for a
   same-tier buy, 183s for +2, 288s for +3. Players visibly bank souls, and the
   waiting is observable even though the souls are not.
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

# Spending is not independent of wealth: a player who spent more souls had more
# souls. Measured against reconstructed net worth on 8,000 matches:
#
#   total_spend      0.78   <- effectively a restatement of net worth
#   tier_mean        0.43
#   n_tier_jumps     0.40
#   mean_item_cost   0.36
#   n_saved_up       0.34
#   median_gap_s    -0.28
#   cost_slope      -0.25
#   saved_up_frac    0.17
#
# total_spend crosses into being a wealth proxy rather than a behavioural
# feature, and carries the same problem as nw_final: it is largely an outcome.
# It is kept for description but excluded from BEHAVIOURAL_COLUMNS, which is
# what belongs in a gated model.
WEALTH_PROXY_COLUMNS = frozenset({"total_spend"})

# Features describing HOW a player spent rather than HOW MUCH they had. These
# are the ones that can enter a model whose lift is being measured against the
# wealth baseline.
BEHAVIOURAL_COLUMNS = [c for c in ECONOMIC_COLUMNS if c not in WEALTH_PROXY_COLUMNS]

# A gap this many times the player's own median marks deliberate saving. Using
# the player's own median rather than a global constant keeps the measure
# meaningful for fast and slow farmers alike.
SAVE_GAP_RATIO = 1.5


def annotate_costs(df: pd.DataFrame, items: dict[int, Item]) -> pd.DataFrame:
    """Attach item cost and tier to a purchase table."""
    out = df.copy()
    out["cost"] = out["item_id"].map({k: v.cost for k, v in items.items()})
    out["tier"] = out["item_id"].map({k: v.tier for k, v in items.items()})
    return out


def _gaps(times: np.ndarray) -> np.ndarray:
    """Seconds between consecutive purchases. First buy has no predecessor."""
    if times.size < 2:
        return np.empty(0, dtype=float)
    return np.diff(np.sort(times))


def player_economics(group: pd.DataFrame) -> dict[str, float]:
    """Economic summary for one player's purchase sequence.

    `group` must carry buy_time_s, cost, and tier, ordered or not -- times are
    sorted here so callers need not guarantee it.
    """
    order = np.argsort(group["buy_time_s"].to_numpy())
    times = group["buy_time_s"].to_numpy(dtype=float)[order]
    costs = group["cost"].to_numpy(dtype=float)[order]
    tiers = group["tier"].to_numpy(dtype=float)[order]

    costs = np.nan_to_num(costs, nan=0.0)
    valid_tiers = tiers[~np.isnan(tiers)]

    # How steeply spending ramps. A positive slope is the normal build-up; a
    # flat one means the player never climbed past cheap items.
    if costs.size >= 2:
        cost_slope = float(np.polyfit(np.arange(costs.size), costs, 1)[0])
    else:
        cost_slope = 0.0

    tier_diff = np.diff(valid_tiers) if valid_tiers.size >= 2 else np.empty(0)
    n_tier_jumps = int((tier_diff > 0).sum())

    gaps = _gaps(times)
    median_gap = float(np.median(gaps)) if gaps.size else 0.0

    # Saving shows up as a gap well above this player's own typical pace.
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
    """Per-player economic features, indexed by (match_id, player_slot).

    Vectorized rather than per-group: at 5M purchases a groupby-apply over
    ~300k players is minutes of work, while the aggregations below are seconds.
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

    # Gaps and tier jumps need lagged values within each player.
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

    # Saving: a gap above SAVE_GAP_RATIO x this player's own median.
    gaps = gaps.join(gap_stats, on=keys)
    gaps = gaps.assign(
        saved=(gaps["gap"] > SAVE_GAP_RATIO * gaps["median_gap_s"]).astype("int8")
    )
    save_stats = gaps.groupby(keys, sort=False)["saved"].agg(["sum", "mean"])
    save_stats.columns = ["n_saved_up", "saved_up_fraction"]
    out = out.join(save_stats)

    # Cost ramp: correlation of cost against position, a cheap stand-in for the
    # per-player regression slope and far faster over 300k groups.
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
