"""Generate a full build by running the model forward one purchase at a time.

A build is about 17 purchases, but a player can hold only 12 items. Absorption
makes that work: buying a composite removes the components the player already
holds and frees their slots. The data shows it:

    sold rate for items that are a component of something   70.6%
    sold rate for items that are not                         6.4%
    by tier: t1 86.6%, t2 40.1%, t3 7.2%, t4 1.1%

So most "sold" items were absorbed into a bigger item. Only about 6% of
purchases are a real sell.

This is why the staple gate checks the purchase sequence, never held items.
Hero 4's first archetype has 12 staples, and 7 of them are gone by match end
more than half the time. Mystic Burst is bought by 96% of those players and
sold by 95%. No 12-slot inventory holds all 12 staples, so a gate on held
items would always fail.

Generation is greedy, not beam search. Beam search maximizes the likelihood of
the whole sequence, which picks the most stereotyped build. It also loses the
per-step evidence that `why` shows for each pick.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

from . import assets, sequence
from .buildfmt import MAX_HELD_ITEMS, Build, BuildItem
from .state import GameState

log = logging.getLogger(__name__)

# Median game time in seconds of each purchase by position, measured over
# 5,095,598 purchases. It is close to linear, about 110s per purchase.
#
# Re-measured on 2026-09-15 over 5,119,990 purchases. Every position was
# within 1% of these values (the largest change was 18s at position 18), so
# they were left alone rather than shift every build's times.
MEDIAN_BUY_TIME_S = (
    70, 191, 304, 420, 527, 629, 731, 838, 950, 1065,
    1194, 1318, 1441, 1570, 1684, 1795, 1910, 2022, 2129, 2232,
)
SECONDS_PER_PURCHASE = 110.0

# The median player makes 17 purchases (p10 13, p90 22).
DEFAULT_MAX_PURCHASES = 17

# Multiplier on a composite's score while the player doesn't hold all its
# components. 81% of composite purchases come after every component, but 19%
# don't, so this lowers the score instead of forbidding the purchase.
COMPONENT_PENALTY = 0.25

# Stop the build when the best candidate is less likely than this, instead of
# filling it out with items nobody buys.
MIN_PROBABILITY = 0.02

# Staples still missing get forced in once the remaining purchases are within
# this many of the number of missing staples.
PEAK_WINDOW = 2


def buy_time(index: int) -> float:
    """Median game time of the purchase at this position.

    Past the end of MEDIAN_BUY_TIME_S, adds SECONDS_PER_PURCHASE per position.
    """
    if index < len(MEDIAN_BUY_TIME_S):
        return float(MEDIAN_BUY_TIME_S[index])
    over = index - len(MEDIAN_BUY_TIME_S) + 1
    return float(MEDIAN_BUY_TIME_S[-1] + over * SECONDS_PER_PURCHASE)


@dataclass
class Inventory:
    """A player's items during build generation.

    `purchased` is every purchase in order. `held` is what occupies a slot
    now, which drops components when a composite absorbs them. `consumed`
    maps each absorbed component to the item that absorbed it.
    """

    held: set[int] = field(default_factory=set)
    purchased: list[int] = field(default_factory=list)
    consumed: dict[int, int] = field(default_factory=dict)

    def buy(self, item_id: int, components: dict[int, tuple[int, ...]]) -> list[int]:
        """Buy an item, absorbing any of its components that are held. Returns them."""
        absorbed = [c for c in components.get(item_id, ()) if c in self.held]
        for component in absorbed:
            self.held.discard(component)
            self.consumed[component] = item_id
        self.held.add(item_id)
        self.purchased.append(item_id)
        return absorbed

    def would_fit(self, item_id: int, components: dict[int, tuple[int, ...]]) -> bool:
        """Whether this item fits within MAX_HELD_ITEMS, after absorbing its components."""
        freed = sum(1 for c in components.get(item_id, ()) if c in self.held)
        return len(self.held) - freed + 1 <= MAX_HELD_ITEMS


def generate_build(
    hero_id: int,
    archetype_id: int,
    model: sequence.SequenceModel,
    *,
    max_purchases: int = DEFAULT_MAX_PURCHASES,
    temperature: float = 0.0,
    seed: int = 0,
    component_penalty: float = COMPONENT_PENALTY,
    staples: dict[int, float] | None = None,
    hero_name: str = "",
    archetype_name: str = "",
    min_probability: float = MIN_PROBABILITY,
) -> Build:
    """Generate a build from an empty inventory, one purchase at a time.

    `staples` maps each staple to its prevalence. As purchases run out,
    missing staples get pushed in, so a build doesn't miss an item 96% of
    players buy just because it was never the top pick at any single step.
    A pushed pick gets "+staple" added to its `backoff_level`.

    `temperature` 0 always takes the top item. Above 0 it samples from
    `P ** (1/T)` with the given seed. `sample_builds` uses this.
    """
    items = assets.shopable_items()
    components = assets.component_map()
    rng = np.random.default_rng(seed)

    inventory = Inventory()
    build = Build(
        hero_id=hero_id,
        hero_name=hero_name or _hero_name(hero_id),
        archetype_id=archetype_id,
        archetype_name=archetype_name,
    )

    for position in range(max_purchases):
        clock = buy_time(position)
        state = GameState(
            hero_id=hero_id,
            game_time_s=clock,
            # A pre-match build ignores what the player can afford.
            souls_available=10**9,
            owned_item_ids=frozenset(inventory.purchased),
            purchased=tuple(inventory.purchased),
            archetype_posterior={archetype_id: 1.0},
        )
        ids, probability = model.distribution(state)
        if not len(ids):
            break

        ids, probability = _ensure_staples_present(
            ids, probability, staples, inventory, max_purchases - position
        )
        scored = _apply_priors(
            ids,
            probability,
            inventory=inventory,
            components=components,
            component_penalty=component_penalty,
            staples=staples,
            remaining=max_purchases - position,
        )

        choice = _choose(ids, scored, items, inventory, components, temperature, rng)
        if choice is None:
            break
        index = int(choice)
        item_id = int(ids[index])
        if probability[index] < min_probability and not _is_missing_staple(
            item_id, staples, inventory
        ):
            break

        absorbed = inventory.buy(item_id, components)
        trace = model.evidence(state, item_id)
        nudged = _is_missing_staple(item_id, staples, inventory) and scored[index] > probability[index]
        build.items.append(
            BuildItem(
                item_id=item_id,
                name=items[item_id].name if item_id in items else str(item_id),
                cost=items[item_id].cost if item_id in items else 0,
                position=position,
                buy_time_s=clock,
                probability=float(probability[index]),
                n=trace.n if trace else 0,
                backoff_level=(trace.level if trace else "L5") + (" +staple" if nudged else ""),
            )
        )
        # Mark absorbed components as sold at this purchase's time.
        for component in absorbed:
            for earlier in build.items:
                if earlier.item_id == component and earlier.sell_time_s is None:
                    earlier.sell_time_s = clock

    return build


def _apply_priors(
    ids: np.ndarray,
    probability: np.ndarray,
    *,
    inventory: Inventory,
    components: dict[int, tuple[int, ...]],
    component_penalty: float,
    staples: dict[int, float] | None,
    remaining: int,
) -> np.ndarray:
    """Adjust the model's scores for components and staples. Never sets a score to zero."""
    scored = probability.copy()

    if component_penalty < 1.0:
        for i, item_id in enumerate(ids):
            if _awaits_components(int(item_id), inventory, components):
                scored[i] *= component_penalty

    if staples:
        missing = [s for s in staples if s not in inventory.purchased]
        # Force staples in when purchases are nearly used up, or when free
        # slots are down to the number of missing staples. Waiting for the
        # last purchases alone fails: the inventory is full by then, and a
        # staple that absorbs nothing can't fit. That is how Melee Silver lost
        # Hunter's Aura, which 71% of those players buy at position 7.
        free_slots = MAX_HELD_ITEMS - len(inventory.held)
        forced = missing and (
            remaining <= len(missing) + PEAK_WINDOW or free_slots <= len(missing)
        )
        if forced:
            owed = set(missing)
            for i, item_id in enumerate(ids):
                iid = int(item_id)
                if iid not in owed:
                    continue
                value = staples[iid]
                # When a composite and its component are both missing staples,
                # buy the component first so the composite can absorb it. Gun
                # Shiv has three such pairs and 13 staples. Composite first,
                # the 13 staples need 13 slots and the cap is 12.
                #
                # Only apply this when the component is itself a missing
                # staple. Enduring Speed's component, Sprint Boots, isn't a
                # staple for Gun Victor, so penalizing Enduring Speed there
                # would drop an item 85% of those players buy.
                if _awaits_components(iid, inventory, components, among=owed):
                    value *= component_penalty
                scored[i] = max(scored[i], value)

    return scored


def _awaits_components(
    item_id: int,
    inventory: Inventory,
    components: dict[int, tuple[int, ...]],
    *,
    among: set[int] | None = None,
) -> bool:
    """Whether this composite has a component the player doesn't hold yet.

    With `among`, only components in that set count. The staple forcing in
    `_apply_priors` passes the missing staples, since a component that isn't a
    staple may never be bought.
    """
    needed = components.get(item_id, ())
    if not needed:
        return False
    if among is None:
        return not all(c in inventory.held for c in needed)
    return any(c in among and c not in inventory.held for c in needed)


def _ensure_staples_present(
    ids: np.ndarray,
    probability: np.ndarray,
    staples: dict[int, float] | None,
    inventory: Inventory,
    remaining: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Add missing staples to the candidates when purchases are running out.

    `_apply_priors` can only raise the score of an item the model returned.
    If the model gives a staple no probability in this context, it isn't a
    candidate at all. Melee Silver lost Hunter's Aura this way.

    Added staples get probability 0, which is what the model predicts, and
    `_apply_priors` gives them their prevalence as a score.
    """
    if not staples:
        return ids, probability
    missing = [
        s
        for s in staples
        if s not in inventory.purchased and s not in set(ids.tolist())
    ]
    if not missing or remaining > len(missing) + PEAK_WINDOW:
        return ids, probability
    return (
        np.concatenate([ids, np.array(missing, dtype=ids.dtype)]),
        np.concatenate([probability, np.zeros(len(missing))]),
    )


def _choose(
    ids: np.ndarray,
    scored: np.ndarray,
    items: dict,
    inventory: Inventory,
    components: dict[int, tuple[int, ...]],
    temperature: float,
    rng: np.random.Generator,
) -> int | None:
    """Index of the chosen item, skipping items already bought or that don't fit.

    Returns None if nothing can be bought.
    """
    legal = np.array(
        [
            int(item_id) in items
            and int(item_id) not in inventory.purchased
            and inventory.would_fit(int(item_id), components)
            for item_id in ids
        ]
    )
    if not legal.any():
        return None
    masked = np.where(legal, scored, 0.0)
    if masked.sum() <= 0:
        return None

    if temperature <= 0:
        return int(np.argmax(masked))
    weights = masked ** (1.0 / temperature)
    total = weights.sum()
    if total <= 0:
        return int(np.argmax(masked))
    return int(rng.choice(len(ids), p=weights / total))


def _is_missing_staple(
    item_id: int, staples: dict[int, float] | None, inventory: Inventory
) -> bool:
    return bool(staples) and item_id in staples


def _hero_name(hero_id: int) -> str:
    hero = assets.load_heroes().get(hero_id)
    return hero.name if hero else str(hero_id)


def sample_builds(
    hero_id: int,
    archetype_id: int,
    model: sequence.SequenceModel,
    *,
    n: int = 100,
    temperature: float = 0.7,
    **kwargs,
) -> list[Build]:
    """Generate `n` builds by sampling, each with a different seed.

    Checks how stable a build is. A staple that shows up in only 60% of
    samples is a problem that a single greedy build would hide.
    """
    return [
        generate_build(
            hero_id, archetype_id, model, temperature=temperature, seed=i, **kwargs
        )
        for i in range(n)
    ]
