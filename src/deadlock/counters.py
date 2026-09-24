"""Items bought because of who is on the other team.

Players buy Counterspell against Lash and Knockdown against Vindicta. The
effect is large and it replicates:

    Counterspell vs Lash        16.0% facing vs  8.5% not   +7.5pp  n=76,718
    Knockdown    vs Vindicta    11.8% facing vs  4.1% not   +7.7pp  n=51,237
    Slowing Hex  vs Apollo      21.1% facing vs 14.6% not   +6.5pp  n=30,690
    Healbane     vs Victor      29.6% facing vs 24.1% not   +5.5pp  n=49,220

The enemy team is not part of the backoff key. The median cell holds about
3,200 player-matches, and splitting it by six enemy heroes would leave almost
nothing in each. A counter-pick is also not an archetype: it depends on the
matchup, not the playstyle.

So counters are shown next to a ranking and never change its order. The
output gives the lift, both pick rates, and the sample size, so a player can
check "+7.5pp against Lash" against their own games.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .state import Recommendation

# Ignore enemy heroes faced in fewer player-matches than this.
MIN_FACING = 500

# Report a counter only when facing the hero raises the pick rate by at least
# this much (3 percentage points).
MIN_LIFT = 0.03


@dataclass(frozen=True)
class Counter:
    """How much facing one enemy hero raises one item's pick rate."""

    item_id: int
    enemy_hero_id: int
    facing_rate: float
    baseline_rate: float
    n_facing: int

    @property
    def lift(self) -> float:
        return self.facing_rate - self.baseline_rate

    def describe(self, item_names: dict[int, str], hero_names: dict[int, str]) -> str:
        return (
            f"{item_names.get(self.item_id, self.item_id)} "
            f"{self.lift * 100:+.1f}pp vs {hero_names.get(self.enemy_hero_id, '?')}"
        )


def enemy_rosters(purchases: pd.DataFrame) -> pd.DataFrame:
    """The heroes each player faced, one row per (player, enemy hero)."""
    roster = purchases[
        ["match_id", "player_slot", "hero_id", "team"]
    ].drop_duplicates()
    pairs = roster.merge(roster, on="match_id", suffixes=("", "_other"))
    enemies = pairs[pairs["team"] != pairs["team_other"]]
    return enemies[
        ["match_id", "player_slot", "hero_id", "hero_id_other"]
    ].rename(columns={"hero_id_other": "enemy_hero_id"})


def counter_lifts(
    purchases: pd.DataFrame,
    *,
    min_facing: int = MIN_FACING,
    min_lift: float = MIN_LIFT,
) -> pd.DataFrame:
    """For each (enemy hero, item), the pick rate when facing that hero vs overall.

    Rates are per player, not per purchase row. Keeps only pairs that pass
    `min_facing` and `min_lift`, sorted by lift.
    """
    players = purchases[["match_id", "player_slot"]].drop_duplicates()
    bought = (
        purchases[["match_id", "player_slot", "item_id"]]
        .drop_duplicates()
        .assign(bought=1)
    )
    facing = enemy_rosters(purchases)

    baseline = bought.groupby("item_id").size() / len(players)

    # Join each (player, enemy) pair to the items that player bought. Joining
    # on purchases keeps the frame far smaller than players x items.
    matched = facing.merge(bought, on=["match_id", "player_slot"], how="inner")
    facing_counts = matched.groupby(["enemy_hero_id", "item_id"]).size()
    facing_players = facing.groupby("enemy_hero_id").size()

    rows = []
    for (enemy, item_id), n_bought in facing_counts.items():
        n_facing = int(facing_players.loc[enemy])
        if n_facing < min_facing:
            continue
        facing_rate = n_bought / n_facing
        base = float(baseline.get(item_id, 0.0))
        # An item bought less against a hero is not a counter-pick.
        if facing_rate - base < min_lift:
            continue
        rows.append(
            {
                "item_id": int(item_id),
                "enemy_hero_id": int(enemy),
                "facing_rate": facing_rate,
                "baseline_rate": base,
                "lift": facing_rate - base,
                "n_facing": n_facing,
            }
        )
    frame = pd.DataFrame(rows)
    return frame.sort_values("lift", ascending=False) if len(frame) else frame


def counters_for(
    lifts: pd.DataFrame, enemy_hero_ids: list[int] | tuple[int, ...]
) -> dict[int, Counter]:
    """For each item, its strongest counter against the given enemy heroes."""
    if not len(lifts) or not enemy_hero_ids:
        return {}
    relevant = lifts[lifts["enemy_hero_id"].isin(list(enemy_hero_ids))]
    best: dict[int, Counter] = {}
    for row in relevant.itertuples():
        current = best.get(int(row.item_id))
        if current is None or row.lift > current.lift:
            best[int(row.item_id)] = Counter(
                item_id=int(row.item_id),
                enemy_hero_id=int(row.enemy_hero_id),
                facing_rate=float(row.facing_rate),
                baseline_rate=float(row.baseline_rate),
                n_facing=int(row.n_facing),
            )
    return best


def for_build(
    lifts: pd.DataFrame,
    item_ids: list[int] | tuple[int, ...],
    *,
    limit: int = 8,
) -> list[Counter]:
    """For the items in a build, the enemy heroes they counter, strongest first.

    `counters_for` starts from a known enemy team, which only exists during a
    match. A build is made before the match, so this starts from the build's
    items instead.

    Returns at most one counter per item, its strongest, so one item that
    counters four heroes doesn't crowd out the rest. Applies the same
    `MIN_LIFT` and `MIN_FACING` thresholds as the CLI.
    """
    if not len(lifts) or not len(item_ids):
        return []
    relevant = lifts[
        lifts["item_id"].isin(list(item_ids))
        & (lifts["lift"] >= MIN_LIFT)
        & (lifts["n_facing"] >= MIN_FACING)
    ].sort_values("lift", ascending=False).drop_duplicates(subset=["item_id"])
    return [
        Counter(
            item_id=int(row.item_id),
            enemy_hero_id=int(row.enemy_hero_id),
            facing_rate=float(row.facing_rate),
            baseline_rate=float(row.baseline_rate),
            n_facing=int(row.n_facing),
        )
        for row in relevant.head(limit).itertuples()
    ]


def annotate(
    recommendations: list[Recommendation],
    enemy_hero_ids: list[int] | tuple[int, ...],
    lifts: pd.DataFrame,
) -> list[tuple[Recommendation, Counter | None]]:
    """Pair each recommendation with its counter, or None.

    Keeps the model's order. The counter is shown beside the probability, not
    folded into it.
    """
    best = counters_for(lifts, enemy_hero_ids)
    return [(rec, best.get(rec.item_id)) for rec in recommendations]


def replicates(
    train: pd.DataFrame, test: pd.DataFrame, *, min_facing: int = MIN_FACING
) -> float:
    """Correlation of the lifts measured on two disjoint splits.

    Low correlation means the lifts are noise. An earlier counter table scored
    r=0.05 on this check and was dropped.
    """
    a = counter_lifts(train, min_facing=min_facing, min_lift=-1.0)
    b = counter_lifts(test, min_facing=min_facing, min_lift=-1.0)
    if not len(a) or not len(b):
        return float("nan")
    merged = a.merge(b, on=["item_id", "enemy_hero_id"], suffixes=("_a", "_b"))
    if len(merged) < 3:
        return float("nan")
    return float(np.corrcoef(merged["lift_a"], merged["lift_b"])[0, 1])
