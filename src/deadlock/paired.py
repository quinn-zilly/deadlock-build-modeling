"""Within-lane paired design.

The strongest available control. Comparing the two sides of one lane holds
constant everything that varies between matches -- map state, match length,
overall lobby skill, patch, server -- because both sides experienced the same
match. Differencing their features cancels those confounders outright rather
than trying to model them.

Two facts about Deadlock's structure shape this module:

1. **Lanes are 2v2, not 1v1.** There are three lanes (ids 1, 4 and 6) with two
   players per team in each. 97.1% of lanes are cleanly formed this way
   (72,825 of 74,997), giving ~2.9 usable matchups per match. The unit is
   therefore a lane *side*, not an individual duel, and features are summed
   across the two players on a side.

2. **The label is the match outcome, shared by both players on a side.** So
   this identifies lane-level item advantage, not individual contribution --
   a strong lane on a losing team is still labelled a loss. That limit is
   accepted and stated rather than papered over.

A caution that governs the whole module: lane net-worth advantage computed
from FINAL net worth correlates 0.79 with the match result. That is not a
finding, it is the outcome restated. Everything here is built from early-game,
pre-decision features only.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# Deadlock's three lanes. Any other value indicates malformed data.
VALID_LANES = (1, 4, 6)
PLAYERS_PER_SIDE = 2


def lane_sides(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (match, lane, team), for cleanly formed 2v2 lanes only.

    A lane is kept when it has exactly two teams with exactly two players
    each. The 2.9% that fail this are abandons and malformed records.
    """
    players = (
        df.groupby(["match_id", "player_slot"])
        .agg(
            lane=("assigned_lane", "first"),
            team=("team", "first"),
            hero_id=("hero_id", "first"),
            won=("won", "first"),
        )
        .reset_index()
    )
    players = players[players["lane"].isin(VALID_LANES)]

    shape = players.groupby(["match_id", "lane"]).agg(
        n_players=("player_slot", "size"), n_teams=("team", "nunique")
    )
    clean = shape[(shape["n_players"] == 2 * PLAYERS_PER_SIDE) & (shape["n_teams"] == 2)]

    kept = players.merge(clean.reset_index()[["match_id", "lane"]], on=["match_id", "lane"])
    sizes = kept.groupby(["match_id", "lane", "team"]).size()
    balanced = sizes[sizes == PLAYERS_PER_SIDE].reset_index()[["match_id", "lane", "team"]]

    out = kept.merge(balanced, on=["match_id", "lane", "team"])
    log.info(
        "lane sides: %d players across %d lanes",
        len(out),
        out.groupby(["match_id", "lane"]).ngroups,
    )
    return out


def side_features(
    df: pd.DataFrame, feature_columns: list[str], player_features: pd.DataFrame
) -> pd.DataFrame:
    """Sum player features to the lane-side level.

    `player_features` is indexed by (match_id, player_slot); the two players on
    a side are summed, since what opposes the enemy duo is the pair's combined
    build, not either player's alone.
    """
    sides = lane_sides(df)
    joined = sides.join(
        player_features[feature_columns], on=["match_id", "player_slot"]
    )
    aggregated = (
        joined.groupby(["match_id", "lane", "team"])[feature_columns]
        .sum()
        .reset_index()
    )
    outcomes = (
        sides.groupby(["match_id", "lane", "team"])["won"].first().reset_index()
    )
    return aggregated.merge(outcomes, on=["match_id", "lane", "team"])


def difference_lanes(
    sides: pd.DataFrame, feature_columns: list[str], seed: int = 0
) -> pd.DataFrame:
    """Difference the two sides of each lane into one row.

    Which side becomes "A" is randomized, so the label is balanced at ~50% and
    the model cannot learn a constant. Without this, always taking Team0 as A
    would bake in whatever side advantage the game has.
    """
    rng = np.random.default_rng(seed)
    rows = []

    for (match_id, lane), group in sides.groupby(["match_id", "lane"]):
        if len(group) != 2:
            continue
        order = [0, 1] if rng.random() < 0.5 else [1, 0]
        a, b = group.iloc[order[0]], group.iloc[order[1]]

        row = {
            "match_id": match_id,
            "lane": lane,
            "a_team": a["team"],
            "a_won": bool(a["won"]),
        }
        for column in feature_columns:
            row[f"d_{column}"] = float(a[column]) - float(b[column])
        rows.append(row)

    out = pd.DataFrame(rows)
    log.info("paired lanes: %d rows, %.1f%% a_won", len(out), 100 * out["a_won"].mean())
    return out


def item_difference_matrix(
    df: pd.DataFrame, paired: pd.DataFrame, item_ids: list[int]
) -> tuple[np.ndarray, list[str]]:
    """Per-item count difference between the two sides of each lane.

    Entry (lane, item) is (times side A bought it) - (times side B bought it),
    so 0 means both sides bought it equally often and it cannot explain the
    result. This is where the design earns its keep: an item common to both
    sides contributes nothing, leaving only genuine build divergence.
    """
    sides = lane_sides(df)
    buys = df[["match_id", "player_slot", "item_id"]].drop_duplicates()
    joined = buys.merge(
        sides[["match_id", "player_slot", "lane", "team"]],
        on=["match_id", "player_slot"],
    )

    counts = (
        joined.groupby(["match_id", "lane", "team", "item_id"])
        .size()
        .rename("n")
        .reset_index()
    )

    item_index = {item: i for i, item in enumerate(item_ids)}
    lane_index = {
        (m, l): i for i, (m, l) in enumerate(zip(paired["match_id"], paired["lane"]))
    }

    # The A-side team is carried on the paired frame itself, so the item
    # difference uses the same sign convention as the label. Replaying the RNG
    # to recover it would break silently if grouping order ever changed.
    a_team = dict(
        zip(zip(paired["match_id"], paired["lane"]), paired["a_team"])
    )

    matrix = np.zeros((len(paired), len(item_ids)), dtype=np.float32)
    for match_id, lane, team, item_id, n in counts.itertuples(index=False):
        row = lane_index.get((match_id, lane))
        col = item_index.get(item_id)
        if row is None or col is None:
            continue
        sign = 1.0 if team == a_team.get((match_id, lane)) else -1.0
        matrix[row, col] += sign * n

    return matrix, [f"d_item_{i}" for i in item_ids]
