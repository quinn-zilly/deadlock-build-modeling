"""Item recommendation: what should this player buy next?

Two scorers, deliberately built to be compared:

B1 queries the API's /v1/analytics/item-flow-stats and ranks by its
`adjusted_win_rate`, which standardizes an item's win rate to the net-worth
distribution of its stage. That adjustment is computed from the same
`net_worth_at_buy` field we measured as corrupt in ~9% of records (see
features.py), so B1 is a baseline to check, not to trust outright.

B2 scores candidates from our own wealth-stratified estimates over locally
cached matches, using net worth reconstructed from the stats series.

Where the two disagree is itself informative: it bounds how much the API's
adjustment differs from one built on data we control.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from . import api, assets, confound

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class GameState:
    """What is known at a buy decision."""

    hero_id: int
    phase: int
    souls_available: int
    owned_item_ids: frozenset[int] = frozenset()
    enemy_hero_ids: tuple[int, ...] = ()
    badge: int | None = None


@dataclass(frozen=True)
class Recommendation:
    item_id: int
    item_name: str
    score: float
    n: int
    source: str
    cost: int

    def __str__(self) -> str:
        return f"{self.item_name:28s} {self.score:.4f}  (n={self.n:,}, {self.cost} souls)"


def candidate_items(state: GameState) -> list[int]:
    """Items the player could legally buy right now.

    Filters to what is affordable and not already owned. Shop tier gating is
    approximated by cost, which is what actually constrains the choice.
    """
    items = assets.load_items()
    return [
        item_id
        for item_id, item in items.items()
        if item_id not in state.owned_item_ids and item.cost <= state.souls_available
    ]


def recommend_api(
    state: GameState,
    *,
    top_k: int = 10,
    min_matches: int = 20,
    cache_dir: Path | None = Path("data/raw/analytics"),
) -> list[Recommendation]:
    """B1: rank candidates by the API's adjusted_win_rate for this phase."""
    params: dict[str, object] = {
        "hero_ids": str(state.hero_id),
        "phase_count": 4,
        "phase_interval_s": 600,
        "min_matches": min_matches,
    }
    if state.badge is not None:
        # Compare against a similar skill band, +/- roughly one rank.
        params["min_average_badge"] = max(0, state.badge - 6)
        params["max_average_badge"] = min(116, state.badge + 6)

    payload = api.get("/v1/analytics/item-flow-stats", params, cache_dir=cache_dir)
    nodes = [n for n in payload.get("nodes", []) if n.get("column") == state.phase]

    allowed = set(candidate_items(state))
    items = assets.load_items()

    out: list[Recommendation] = []
    for node in nodes:
        item_id = node.get("item_id")
        if item_id not in allowed:
            continue
        item = items.get(item_id)
        out.append(
            Recommendation(
                item_id=item_id,
                item_name=item.name if item else str(item_id),
                score=float(node.get("adjusted_win_rate", 0.0)),
                n=int(node.get("matches", 0)),
                source="api_adjusted_win_rate",
                cost=item.cost if item else 0,
            )
        )
    out.sort(key=lambda r: r.score, reverse=True)
    return out[:top_k]


def fit_local_scores(
    df: pd.DataFrame, *, min_matches: int = 200
) -> dict[tuple[int, int], pd.DataFrame]:
    """B2: wealth-adjusted item win rates per (hero, phase).

    Built on stratified_item_winrate, so each item's rate is reweighted across
    net-worth strata to the population distribution rather than its own
    buyers'. Keyed by (hero_id, phase).
    """
    tables: dict[tuple[int, int], pd.DataFrame] = {}
    for (hero_id, phase), group in df.groupby(["hero_id", "phase"]):
        if len(group) < min_matches:
            continue
        rates = confound.stratified_item_winrate(group, min_matches=min_matches // 4)
        if not rates.empty:
            tables[(int(hero_id), int(phase))] = rates
    log.info("fitted local scores for %d (hero, phase) cells", len(tables))
    return tables


def recommend_local(
    state: GameState,
    tables: dict[tuple[int, int], pd.DataFrame],
    *,
    top_k: int = 10,
) -> list[Recommendation]:
    """B2: rank candidates by our own wealth-adjusted win rate."""
    table = tables.get((state.hero_id, state.phase))
    if table is None or table.empty:
        return []

    allowed = set(candidate_items(state))
    items = assets.load_items()

    out: list[Recommendation] = []
    for item_id, row in table.iterrows():
        if item_id not in allowed:
            continue
        item = items.get(int(item_id))
        out.append(
            Recommendation(
                item_id=int(item_id),
                item_name=item.name if item else str(item_id),
                score=float(row["adjusted_win_rate"]),
                n=int(row["n"]),
                source="local_stratified",
                cost=item.cost if item else 0,
            )
        )
    out.sort(key=lambda r: r.score, reverse=True)
    return out[:top_k]


def popularity_baseline(
    df: pd.DataFrame, state: GameState, *, top_k: int = 10
) -> list[Recommendation]:
    """The floor any recommender must beat: most-bought item for this cell.

    A recommender that cannot outperform "buy what everyone else buys" has
    not earned its complexity.
    """
    cell = df[(df.hero_id == state.hero_id) & (df.phase == state.phase)]
    if cell.empty:
        return []
    allowed = set(candidate_items(state))
    counts = cell[cell.item_id.isin(allowed)].item_id.value_counts()
    items = assets.load_items()
    return [
        Recommendation(
            item_id=int(i),
            item_name=items[int(i)].name if int(i) in items else str(i),
            score=float(c / len(cell)),
            n=int(c),
            source="popularity",
            cost=items[int(i)].cost if int(i) in items else 0,
        )
        for i, c in counts.head(top_k).items()
    ]
