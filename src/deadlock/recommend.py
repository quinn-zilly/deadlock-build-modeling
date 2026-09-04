"""Item recommendation built on the paired design.

Scoring uses within-lane differences because that is the only method measured
to detect early-game item effects at all:

    cross-match controls   -0.0009 AUC
    counter features       -0.0093
    synergy features       -0.0003
    within-lane paired     +0.0169   (3.4 SE)

The estimand follows from that design. `item_advantage()` answers "when one
lane side bought this item and the opposing side did not, how much more often
did that side win?" -- a contrast against real opposition in the same match,
not a raw win rate. Items both sides bought cancel and cannot contribute.

Two limits are structural, and are surfaced rather than hidden:

- The label is the match outcome, shared by both players on a lane side, so
  these are lane-level advantages, not individual contributions.
- Purchase tempo outweighs item identity everywhere it has been measured.
  `median_gap_s` is the strongest single feature in every model built here, so
  the recommender reports tempo alongside item choice rather than implying the
  item is the whole decision.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import assets, economy, paired
from .model_b import GameState, Recommendation, candidate_items

log = logging.getLogger(__name__)

MIN_LANE_OBSERVATIONS = 200

# Deadlock's shop tiers, in souls.
TIER_COSTS = (800, 1600, 3200, 6400)

# Roughly one win-rate point per minute of souls left unspent. Souls in the
# bank are strength not on the board, which is the same tempo effect that
# dominates every model built here.
IDLE_PENALTY_PER_MINUTE = 0.01


@dataclass(frozen=True)
class Advice:
    """A ranked recommendation plus the tempo context it depends on."""

    items: list[Recommendation]
    save_option: Recommendation | None
    tempo_note: str

    def __str__(self) -> str:
        lines = [f"  {r}" for r in self.items]
        if self.save_option is not None:
            lines.append(f"  {self.save_option}")
        lines.append("")
        lines.append(f"  {self.tempo_note}")
        return "\n".join(lines)


def _empty_advantage() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "win_rate", "n", "raw_advantage", "stderr", "cost",
            "shrinkage", "advantage", "unshrunk_advantage", "significant",
        ]
    ).rename_axis("item_id")


def item_advantage(
    df: pd.DataFrame,
    *,
    hero_id: int | None = None,
    min_n: int = MIN_LANE_OBSERVATIONS,
) -> pd.DataFrame:
    """Win-rate advantage of holding an item when the opposing side does not.

    Built from lane sides: for each item, keep the lanes where exactly one
    side held it, and measure how often that side won. Because both sides
    played the same match, match-level confounders cancel.

    Returns advantage in win-rate points, centred within cost tier so items
    compete against equally-priced alternatives rather than against the wealth
    of the side that bought them, then shrunk toward zero by each estimate's
    own precision. `raw_advantage` keeps the uncentred figure and
    `unshrunk_advantage` the centred-but-unshrunk one, for inspection.
    """
    sides = paired.lane_sides(df)
    if hero_id is not None:
        lanes = sides[sides["hero_id"] == hero_id][["match_id", "lane"]].drop_duplicates()
        sides = sides.merge(lanes, on=["match_id", "lane"])
    if sides.empty:
        return _empty_advantage()

    buys = df[["match_id", "player_slot", "item_id"]].drop_duplicates()
    held = buys.merge(
        sides[["match_id", "player_slot", "lane", "team", "won"]],
        on=["match_id", "player_slot"],
    )

    # One row per (lane, side, item): this side held the item.
    side_items = (
        held.groupby(["match_id", "lane", "team", "item_id"])["won"]
        .first()
        .reset_index()
    )

    # An item held by BOTH sides of a lane cannot explain that lane's result,
    # so keep only the one-sided cases. Counting how many sides hold each item
    # per lane is cheaper than a self-join.
    per_lane = (
        side_items.groupby(["match_id", "lane", "item_id"])["team"]
        .size()
        .rename("n_sides")
        .reset_index()
    )
    exclusive = side_items.merge(
        per_lane[per_lane["n_sides"] == 1][["match_id", "lane", "item_id"]],
        on=["match_id", "lane", "item_id"],
    )

    stats = (
        exclusive.groupby("item_id")["won"]
        .agg(["mean", "size"])
        .rename(columns={"mean": "win_rate", "size": "n"})
    )
    stats = stats[stats["n"] >= min_n]
    if stats.empty:
        return _empty_advantage()

    stats["raw_advantage"] = stats["win_rate"] - 0.5
    stats["stderr"] = np.sqrt(0.25 / stats["n"])

    # Centre within cost tier. A side that exclusively holds a 6400-soul item
    # is usually just the richer side: raw advantage correlates 0.68 with cost
    # and climbs from -0.002 at 800 souls to +0.060 at 6400. Comparing an item
    # against others at its own price makes the ranking a choice between real
    # alternatives instead of a restatement of who was ahead.
    costs = assets.load_items()
    stats["cost"] = [costs[int(i)].cost if int(i) in costs else 0 for i in stats.index]
    tier_mean = stats.groupby("cost")["raw_advantage"].transform("mean")
    centred = stats["raw_advantage"] - tier_mean

    # Empirical-Bayes shrinkage toward zero. Ranking by an unshrunk estimate
    # selects whichever item got the luckiest sample: measured on held-out
    # data, 60% of the top-10 effect vanishes, and items with n < 200
    # replicate at r=0.40 against r=0.77 for n > 1000. Shrinking each estimate
    # by its own precision costs almost nothing on well-sampled items while
    # pulling rare ones back to where the evidence supports.
    signal_var = max(float(centred.var() - (stats["stderr"] ** 2).mean()), 1e-6)
    stats["shrinkage"] = signal_var / (signal_var + stats["stderr"] ** 2)
    stats["advantage"] = centred * stats["shrinkage"]
    stats["unshrunk_advantage"] = centred
    stats["significant"] = stats["advantage"].abs() > 2 * stats["stderr"]

    log.info("item advantage table: %d items", len(stats))
    return stats.sort_values("advantage", ascending=False)


def tempo_percentile(gaps: pd.Series, median_gap_s: float) -> float:
    """Where a purchase gap sits in the population: 0 is slow, 1 is fast.

    Reported because tempo outweighs item choice in every model measured here.
    A player buying far slower than their peers should hear that before any
    item advice.
    """
    gaps = gaps[gaps > 0]
    if gaps.empty:
        return 0.5
    return float((gaps > median_gap_s).mean())


def population_gaps(df: pd.DataFrame) -> pd.Series:
    """Median inter-purchase gap for every player, for tempo comparison."""
    return economy.economic_features(df, assets.load_items())["median_gap_s"]


def next_tier_cost(souls: int) -> int | None:
    """Cost of the cheapest tier the player cannot yet afford."""
    for cost in TIER_COSTS:
        if cost > souls:
            return cost
    return None


def save_option(
    state: GameState,
    advantages: pd.DataFrame,
    *,
    souls_per_minute: float = 1000.0,
) -> Recommendation | None:
    """Whether banking souls for the next tier beats buying now.

    Scored as the best advantage reachable at the next tier, discounted for
    the time spent holding unspent souls. Returns None when the player can
    already afford the top tier, or when no higher-tier item has a measured
    advantage.
    """
    target_cost = next_tier_cost(state.souls_available)
    if target_cost is None:
        return None

    items = assets.load_items()
    reachable = [
        item_id
        for item_id, item in items.items()
        if item_id not in state.owned_item_ids and item.cost == target_cost
    ]
    scored = advantages.reindex(reachable).dropna(subset=["advantage"])
    if scored.empty:
        return None

    best_id = int(scored["advantage"].idxmax())
    best = scored.loc[best_id]

    shortfall = target_cost - state.souls_available
    wait_minutes = shortfall / max(souls_per_minute, 1.0)
    penalty = IDLE_PENALTY_PER_MINUTE * wait_minutes

    return Recommendation(
        item_id=best_id,
        item_name=f"SAVE for {items[best_id].name}",
        score=float(best["advantage"]) - penalty,
        n=int(best["n"]),
        source="save_option",
        cost=target_cost,
    )


def recommend(
    state: GameState,
    advantages: pd.DataFrame,
    *,
    top_k: int = 5,
    median_gap_s: float | None = None,
    gaps: pd.Series | None = None,
) -> Advice:
    """Rank affordable items by measured lane advantage, plus a save option.

    `advantages` must be fitted on training data only: it is learned from
    outcomes, so fitting it on the data a recommendation is evaluated against
    leaks the answer.
    """
    items = assets.load_items()
    allowed = candidate_items(state)
    scored = advantages.reindex(allowed).dropna(subset=["advantage"])

    ranked: list[Recommendation] = []
    top = scored.sort_values("advantage", ascending=False).head(top_k)
    for item_id, row in top.iterrows():
        item = items[int(item_id)]
        ranked.append(
            Recommendation(
                item_id=int(item_id),
                item_name=item.name,
                score=float(row["advantage"]),
                n=int(row["n"]),
                source="lane_advantage" + ("" if row["significant"] else " (weak)"),
                cost=item.cost,
            )
        )

    note = "tempo: not measured"
    if median_gap_s is not None and gaps is not None:
        pct = tempo_percentile(gaps, median_gap_s)
        if pct < 0.35:
            note = (
                f"tempo: slower than {(1 - pct) * 100:.0f}% of players "
                f"({median_gap_s:.0f}s between buys). Spending sooner likely "
                f"matters more than which item you pick."
            )
        else:
            note = (
                f"tempo: {pct * 100:.0f}th percentile purchase speed "
                f"({median_gap_s:.0f}s between buys)."
            )

    return Advice(
        items=ranked,
        save_option=save_option(state, advantages),
        tempo_note=note,
    )
