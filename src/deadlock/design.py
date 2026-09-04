"""Build the player-level design matrix for the build -> win model.

The purchase table has one row per buy; the classifier needs one row per
player-match, with the build encoded across it. Item ownership is encoded as
item x phase rather than a flat "owned" flag, because *when* an item was
bought carries most of its information: a tier-4 item at 10 minutes means
something very different from the same item at 35.

Wealth controls are carried through at the player level by summarizing each
player's position across their purchases, so the model can condition on wealth
instead of inferring it from the build.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import scipy.sparse as sp

from . import features

log = logging.getLogger(__name__)

# Player-level controls.
#
# The distinction that matters here is mediator vs confounder. Net worth
# aggregated over the SAME window as the purchases is a mediator: items help a
# player win fights and farm, which raises net worth, which predicts winning.
# Conditioning on it removes the item effect by construction -- measured on 25k
# matches, item lift collapses to +0.0008 and the gate fails.
#
# A single PRE-DECISION reading leaves the causal path intact. Same data, same
# model: item lift +0.0052 on 780k test rows, gate passes.
#
# So the default controls describe what was known going in, not what happened
# during the window being modeled.
CONTROL_COLUMNS = [
    "nw_vs_enemy_avg_early",
    "average_badge",
    "assigned_lane",
]

# Window aggregates. Useful for describing a match, but they absorb the item
# effect, so they must not be used as controls when measuring item value.
MEDIATOR_COLUMNS = [
    "nw_vs_match_median_mean",
    "nw_vs_team_avg_mean",
    "nw_vs_enemy_avg_mean",
    "nw_rank_in_match_mean",
]


def player_level(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse the purchase table to one row per (match, player).

    Wealth is summarized two ways: averaged over the whole match, and
    restricted to phase 0. The early figure matters because it is closest to
    exogenous -- a player's wealth in the first ten minutes is less a
    consequence of the build than late-game wealth is.
    """
    early = (
        df[df.phase == 0]
        .groupby(["match_id", "player_slot"])["nw_vs_enemy_avg"]
        .mean()
        .rename("nw_vs_enemy_avg_early")
    )

    grouped = df.groupby(["match_id", "player_slot"])
    out = grouped.agg(
        won=("won", "first"),
        hero_id=("hero_id", "first"),
        team=("team", "first"),
        average_badge=("average_badge", "first"),
        duration_s=("duration_s", "first"),
        assigned_lane=("assigned_lane", "first"),
        nw_final=("final_net_worth", "first"),
        nw_vs_match_median_mean=("nw_vs_match_median", "mean"),
        nw_vs_team_avg_mean=("nw_vs_team_avg", "mean"),
        nw_vs_enemy_avg_mean=("nw_vs_enemy_avg", "mean"),
        nw_rank_in_match_mean=("nw_rank_in_match", "mean"),
        n_purchases=("item_id", "size"),
        sold_fraction=("sold", "mean"),
    )
    out = out.join(early)
    # A player with no phase-0 purchases has no early reading; fall back to
    # their match-wide position rather than dropping the row.
    out["nw_vs_enemy_avg_early"] = out["nw_vs_enemy_avg_early"].fillna(
        out["nw_vs_enemy_avg_mean"]
    )
    return out.reset_index()


def item_phase_matrix(
    df: pd.DataFrame, players: pd.DataFrame, item_ids: list[int]
) -> tuple[sp.csr_matrix, list[str]]:
    """Sparse item x phase ownership indicators, aligned to `players`.

    Column j encodes "bought item i during phase p". Roughly 17 purchases
    across ~1000 columns, so density is under 2% and a sparse matrix is the
    only sane representation.
    """
    key = pd.MultiIndex.from_frame(players[["match_id", "player_slot"]])
    row_of = {k: i for i, k in enumerate(key)}

    item_index = {item: i for i, item in enumerate(item_ids)}
    n_phases = features.N_PHASES
    n_cols = len(item_ids) * n_phases

    rows, cols = [], []
    for match_id, slot, item_id, phase in zip(
        df.match_id.to_numpy(),
        df.player_slot.to_numpy(),
        df.item_id.to_numpy(),
        df.phase.to_numpy(),
    ):
        r = row_of.get((match_id, slot))
        c = item_index.get(item_id)
        if r is None or c is None:
            continue
        rows.append(r)
        cols.append(c * n_phases + phase)

    data = np.ones(len(rows), dtype=np.float32)
    matrix = sp.csr_matrix(
        (data, (rows, cols)), shape=(len(players), n_cols), dtype=np.float32
    )
    matrix.data[:] = 1.0  # collapse duplicate buys to a single indicator

    names = [f"item_{i}_p{p}" for i in item_ids for p in range(n_phases)]
    return matrix, names


def composition_matrix(players: pd.DataFrame, hero_ids: list[int]) -> tuple[sp.csr_matrix, list[str]]:
    """Own hero, ally composition, and enemy composition indicators."""
    hero_index = {h: i for i, h in enumerate(hero_ids)}
    n_heroes = len(hero_ids)

    # Roster per match, indexed by team. Nested by match so each player looks
    # up only their own match's teams rather than scanning every roster.
    teams_of: dict[int, dict[str, list[int]]] = {}
    for match_id, team, hero in zip(
        players.match_id.to_numpy(), players.team.to_numpy(), players.hero_id.to_numpy()
    ):
        teams_of.setdefault(match_id, {}).setdefault(team, []).append(hero)

    rows, cols = [], []
    for r, (match_id, team, hero) in enumerate(
        zip(players.match_id.to_numpy(), players.team.to_numpy(), players.hero_id.to_numpy())
    ):
        own = hero_index.get(hero)
        if own is not None:
            rows.append(r); cols.append(own)

        for tm, heroes in teams_of[match_id].items():
            block = n_heroes if tm == team else 2 * n_heroes
            for h in heroes:
                idx = hero_index.get(h)
                if idx is None:
                    continue
                rows.append(r); cols.append(block + idx)

    matrix = sp.csr_matrix(
        (np.ones(len(rows), dtype=np.float32), (rows, cols)),
        shape=(len(players), 3 * n_heroes),
        dtype=np.float32,
    )
    matrix.data[:] = 1.0

    names = (
        [f"hero_{h}" for h in hero_ids]
        + [f"ally_{h}" for h in hero_ids]
        + [f"enemy_{h}" for h in hero_ids]
    )
    return matrix, names


def restrict_phases(df: pd.DataFrame, max_phase: int) -> pd.DataFrame:
    """Keep only purchases up to `max_phase`.

    The reason to model the early game is that wealth is closest to exogenous
    there. Wealth relative to enemies correlates 0.16 with winning in phase 0
    but 0.60 by phase 3 -- at that point it is not a confounder to adjust for,
    it is the outcome restated. Restricting to early phases also matches when
    a recommendation is actually actionable.
    """
    return df[df.phase <= max_phase]


def build_design(
    df: pd.DataFrame,
    item_ids: list[int],
    hero_ids: list[int],
    *,
    include_items: bool = True,
) -> tuple[sp.csr_matrix, np.ndarray, list[str], pd.DataFrame]:
    """Assemble the full sparse design matrix.

    include_items=False yields the controls-only matrix, which is how the
    wealth baseline is computed on identical rows -- making the AUC comparison
    a like-for-like test of what the item features add.
    """
    players = player_level(df)
    controls = players[CONTROL_COLUMNS].astype(float).fillna(0.0).to_numpy(dtype=np.float32)

    blocks: list[sp.csr_matrix] = [sp.csr_matrix(controls)]
    names: list[str] = list(CONTROL_COLUMNS)

    comp, comp_names = composition_matrix(players, hero_ids)
    blocks.append(comp)
    names.extend(comp_names)

    if include_items:
        items, item_names = item_phase_matrix(df, players, item_ids)
        blocks.append(items)
        names.extend(item_names)

    matrix = sp.hstack(blocks, format="csr")
    labels = players["won"].to_numpy(dtype=np.int8)
    log.info(
        "design matrix %s (%.2f%% dense), %d labels",
        matrix.shape,
        100 * matrix.nnz / (matrix.shape[0] * matrix.shape[1]),
        len(labels),
    )
    return matrix, labels, names, players
