"""What is known at a buy decision, and what could legally be bought.

The decision point, not an estimand. This module says nothing about which item
is good -- it describes the situation a player is in and enumerates the legal
moves, so a scorer can rank them.

`GameState` carries `game_time_s` at full resolution rather than only the
coarse 4-bin phase the old design matrix used. A timing model needs to
distinguish a 7-minute buy from a 3-minute one, and phase cannot.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from . import assets

# Purchase-time buckets for conditioning. Finer early, where decisions are
# dense and consequential, and open-ended at the end because match length
# varies and late buys are sparse.
TIME_BUCKET_BOUNDS_S = (300, 600, 900, 1200, 1800)
TIME_BUCKET_LABELS = ("0-5", "5-10", "10-15", "15-20", "20-30", "30+")


def time_bucket(game_time_s: float) -> int:
    """Index into TIME_BUCKET_LABELS for a purchase time."""
    for i, bound in enumerate(TIME_BUCKET_BOUNDS_S):
        if game_time_s < bound:
            return i
    return len(TIME_BUCKET_BOUNDS_S)


@dataclass(frozen=True)
class GameState:
    """What is known at a buy decision.

    `archetype_posterior` maps archetype_id -> probability. Early in a match it
    is genuinely flat: archetype is inferred from items bought so far, and
    before any purchases there is nothing to infer from. Hedging across a flat
    posterior is the honest response, since the player may not have committed
    to a playstyle either. A player who has declared their intent gets a
    one-hot posterior instead.
    """

    hero_id: int
    game_time_s: float
    souls_available: int
    owned_item_ids: frozenset[int] = frozenset()
    purchased: tuple[int, ...] = ()
    enemy_hero_ids: tuple[int, ...] = ()
    badge: int | None = None
    archetype_posterior: dict[int, float] = field(default_factory=dict)

    @property
    def bucket(self) -> int:
        return time_bucket(self.game_time_s)

    @property
    def n_owned(self) -> int:
        return len(self.owned_item_ids)

    @property
    def n_bought(self) -> int:
        """Purchases made, which is not the same as items held.

        About 31% of purchases are components later absorbed into a composite,
        so a player who has bought 15 items may hold only 11. Models keyed on
        buy position want this number, not `n_owned`.
        """
        return len(self.purchased) or len(self.owned_item_ids)

    @property
    def last_items(self) -> tuple[int, ...]:
        """The purchase sequence, most recent last.

        Order carries the signal a bigram exploits, and a set cannot express
        it. Falls back to the owned set when no order was supplied, which loses
        the ordering but keeps the state usable.
        """
        return self.purchased or tuple(self.owned_item_ids)

    def with_purchase(self, item_id: int, *, game_time_s: float | None = None) -> "GameState":
        """The state after buying one item. The roll-forward step."""
        return replace(
            self,
            owned_item_ids=self.owned_item_ids | {item_id},
            purchased=self.purchased + (item_id,),
            game_time_s=self.game_time_s if game_time_s is None else game_time_s,
        )


@dataclass(frozen=True)
class Recommendation:
    """One ranked candidate, with the evidence behind it.

    `n` and `backoff_level` are not decoration. This project was burned once by
    a model that produced a number with no recourse, so every recommendation
    names the cell it came from and how many observations backed it.
    """

    item_id: int
    item_name: str
    probability: float
    n: int
    backoff_level: str
    cost: int

    def __str__(self) -> str:
        return (
            f"{self.item_name:28s} p={self.probability:.4f}  "
            f"(n={self.n:,}, {self.backoff_level}, {self.cost} souls)"
        )


def candidate_items(state: GameState, *, affordable_only: bool = True) -> list[int]:
    """Items the player could legally buy right now.

    Filters to shopable items not already owned. No item is ever bought twice
    in the observed data, so ownership is a hard exclusion.

    Shopable, not every asset: `load_items()` carries 251 entries, of which only
    173 can be bought. The rest are components-as-assets and non-purchasable
    entries, and recommending one is not a legal move.

    `affordable_only` gates on current souls. Turn it off when generating a
    full build ahead of a match, where the question is what to buy eventually
    rather than what is affordable this second.
    """
    items = assets.shopable_items()
    return [
        item_id
        for item_id, item in items.items()
        if item_id not in state.owned_item_ids
        and (not affordable_only or item.cost <= state.souls_available)
    ]
