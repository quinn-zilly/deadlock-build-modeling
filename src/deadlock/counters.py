"""Items bought because of who is on the other team.

Players buy Counterspell against Lash and Knockdown against Vindicta. The
effect is large and it replicates:

    Counterspell vs Lash        16.0% facing vs  8.5% not   +7.5pp  n=76,718
    Knockdown    vs Vindicta    11.8% facing vs  4.1% not   +7.7pp  n=51,237
    Slowing Hex  vs Apollo      21.1% facing vs 14.6% not   +6.5pp  n=30,690
    Healbane     vs Victor      29.6% facing vs 24.1% not   +5.5pp  n=49,220

This stays *outside* the backoff key. Enemy roster is a 12-dimensional
condition and the median cell holds 3,313 player-matches; keying on it would
fragment the tables past usefulness, which is the whole reason covariates enter
as row weights elsewhere. A counter-pick also is not an archetype -- it varies
by matchup, not by playstyle, so a model that folded it into the archetype
would manufacture playstyles out of who you happened to face.

So counters annotate a ranking rather than reorder it. The lift, both base
rates, and the sample size are all reported, because "+7.5pp against Lash" is
a claim a player can check against their own experience and a reordered list
is not.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .state import Recommendation

# Below this many player-matches facing the hero, a lift is noise.
MIN_FACING = 500

# Report a counter only when facing the hero raises the pick rate this much.
MIN_LIFT = 0.03


@dataclass(frozen=True)
class Counter:
    """One measured matchup effect, with everything needed to judge it."""

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
    """Which heroes each player faced, one row per (player, enemy hero).

    Teams are named, not numbered, so "the other team" is whichever label is
    not the player's own.
    """
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
    """How much facing each hero moves each item's pick rate.

    Measured over players, not purchase rows, since no item is bought twice.
    """
    players = purchases[["match_id", "player_slot"]].drop_duplicates()
    bought = (
        purchases[["match_id", "player_slot", "item_id"]]
        .drop_duplicates()
        .assign(bought=1)
    )
    facing = enemy_rosters(purchases)

    baseline = bought.groupby("item_id").size() / len(players)

    # Every (player, enemy) pair crossed with whether that player bought each
    # item. Done as a merge on the item so the frame stays proportional to
    # purchases rather than players x items.
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
        # Positive only: an item bought *less* against a hero is not a
        # counter-pick, and surfacing it as one is noise dressed as advice.
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
    """The strongest counter per item, given who is on the enemy team."""
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
    """The matchups the items in a build are picks against, strongest first.

    The mirror of `counters_for`: that one starts from an enemy team and asks
    which items answer it, which is the in-match question. A build exists
    before there is an enemy team, so the question there is which heroes make
    the items it already buys a matchup pick.

    One row per item, its strongest matchup, the same shape `counters_for`
    returns: an item that answers four heroes would otherwise fill the panel
    by itself and push the rest of the build's matchups out of view.

    Same two bars as everywhere else -- a lift under `MIN_LIFT` is not a
    matchup and a matchup seen under `MIN_FACING` times is not measured -- so
    nothing appears here that the CLI would not also report.
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
    """Pair each recommendation with its counter evidence, if any.

    Deliberately returns pairs rather than reordering: the probability stays
    the model's, and the matchup effect stays a separate, checkable claim
    beside it.
    """
    best = counters_for(lifts, enemy_hero_ids)
    return [(rec, best.get(rec.item_id)) for rec in recommendations]


def replicates(
    train: pd.DataFrame, test: pd.DataFrame, *, min_facing: int = MIN_FACING
) -> float:
    """Correlation of measured lifts across two splits.

    A counter table that does not replicate is a table of coincidences. The
    old counter/synergy work measured r=0.05 for exactly this and was
    discarded; anything similar here should be too.
    """
    a = counter_lifts(train, min_facing=min_facing, min_lift=-1.0)
    b = counter_lifts(test, min_facing=min_facing, min_lift=-1.0)
    if not len(a) or not len(b):
        return float("nan")
    merged = a.merge(b, on=["item_id", "enemy_hero_id"], suffixes=("_a", "_b"))
    if len(merged) < 3:
        return float("nan")
    return float(np.corrcoef(merged["lift_a"], merged["lift_b"])[0, 1])
