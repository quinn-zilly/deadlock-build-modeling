"""The player's situation at a purchase, and the items they can buy.

This module doesn't judge items. It describes the state and lists the legal
purchases, and the model ranks them.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from . import assets

# Purchase-time buckets, in seconds. They are narrower early, where most
# purchases happen, and the last bucket is open-ended because late purchases
# are rare.
TIME_BUCKET_BOUNDS_S = (300, 600, 900, 1200, 1800)
TIME_BUCKET_LABELS = ("0-5", "5-10", "10-15", "15-20", "20-30", "30+")

# A recommendation backed by fewer observations than this is marked thin. It
# is still shown, because the item may be right, but the player sees how
# little data is behind it.
THIN_EVIDENCE = 30


def time_bucket(game_time_s: float) -> int:
    """Index into TIME_BUCKET_LABELS for a purchase time."""
    for i, bound in enumerate(TIME_BUCKET_BOUNDS_S):
        if game_time_s < bound:
            return i
    return len(TIME_BUCKET_BOUNDS_S)


@dataclass(frozen=True)
class GameState:
    """What is known at a purchase.

    `archetype_posterior` maps archetype_id to probability. Left empty, the
    model uses how often each archetype is played. A player who picks an
    archetype gets 1.0 on that archetype.
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
        """Number of purchases made, which can exceed the number of items held.

        About 31% of purchases are components that a composite later absorbs,
        so a player who has bought 15 items may hold 11. The model keys on
        this number, not `n_owned`.
        """
        return len(self.purchased) or len(self.owned_item_ids)

    @property
    def last_items(self) -> tuple[int, ...]:
        """The purchase sequence, most recent last.

        If no sequence was given, falls back to the owned items in arbitrary
        order. The state still works, but prev1 and prev2 become meaningless.
        """
        return self.purchased or tuple(self.owned_item_ids)

    def with_purchase(self, item_id: int, *, game_time_s: float | None = None) -> "GameState":
        """The state after buying one item. Build generation calls this per step."""
        return replace(
            self,
            owned_item_ids=self.owned_item_ids | {item_id},
            purchased=self.purchased + (item_id,),
            game_time_s=self.game_time_s if game_time_s is None else game_time_s,
        )


@dataclass(frozen=True)
class Recommendation:
    """One ranked item, with the backoff level and observation count behind it.

    `n` and `backoff_level` let a user check the number against the table.
    """

    item_id: int
    item_name: str
    probability: float
    n: int
    backoff_level: str
    cost: int

    @property
    def thin(self) -> bool:
        """True when fewer than THIN_EVIDENCE observations back this item."""
        return self.n < THIN_EVIDENCE

    def __str__(self) -> str:
        line = (
            f"{self.item_name:28s} p={self.probability:.4f}  "
            f"(n={self.n:,}, {self.backoff_level}, {self.cost} souls)"
        )
        return line + "  [thin]" if self.thin else line


def candidate_items(state: GameState, *, affordable_only: bool = True) -> list[int]:
    """Items the player can buy right now.

    Returns shop items the player doesn't own. Nobody in the data buys the
    same item twice, so owned items are always excluded. `load_items()` has
    251 entries but only 173 are in the shop.

    `affordable_only` drops items that cost more than the player's souls.
    Turn it off when generating a full build before a match.
    """
    items = assets.shopable_items()
    return [
        item_id
        for item_id, item in items.items()
        if item_id not in state.owned_item_ids
        and (not affordable_only or item.cost <= state.souls_available)
    ]
