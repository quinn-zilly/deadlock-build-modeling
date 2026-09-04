"""Rolling the model forward into a full build.

A build is ~17 purchases but only ~12 items can be held at once. Those
reconcile through *component absorption*: buying a composite consumes the
components already owned, freeing their slots. That is not a detail of the
export format -- it is the mechanism that makes a real build fit in the
inventory, and it is measurable:

    sold rate for items that are a component of something   70.6%
    sold rate for items that are not                         6.4%
    by tier: t1 86.6%, t2 40.1%, t3 7.2%, t4 1.1%

So of the 37.3% of purchases eventually sold, most are not a player changing
their mind -- they are cheap items being folded into expensive ones. Only about
6% are genuine strategic sells.

The consequence that matters for correctness: **the prevalence gate must run on
the purchase sequence, never on held items.** Hero 4's first archetype has 12
staples, 7 of them sold more than half the time -- Mystic Burst is bought by 96%
of its players and sold by 95%. A 12-slot inventory cannot contain them, so
gating held items would fail that build no matter how good the model is.

Generation is greedy, not beam search. Beam search optimises total sequence
likelihood, which finds the single most stereotyped build and strips the
variation that makes a build read as sensible -- and it destroys the per-step
attribution that makes each pick explainable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

from . import assets, sequence
from .buildfmt import MAX_HELD_ITEMS, Build, BuildItem
from .state import GameState

log = logging.getLogger(__name__)

# Median seconds at each buy index, measured over 5,095,598 purchases. Buy time
# is essentially linear in the index (~110s per purchase), so timing is a
# lookup rather than a model of its own.
MEDIAN_BUY_TIME_S = (
    70, 191, 304, 420, 527, 629, 731, 838, 950, 1065,
    1194, 1318, 1441, 1570, 1684, 1795, 1910, 2022, 2129, 2232,
)
SECONDS_PER_PURCHASE = 110.0

# The median player makes 17 purchases (p10 13, p90 22).
DEFAULT_MAX_PURCHASES = 17

# How much to discount a composite whose components are not owned. 81% of
# composite purchases have every component bought earlier, so the preference is
# real -- but ~19% skip it, and a hard mask would make those builds
# unreachable. A penalty, never a filter.
COMPONENT_PENALTY = 0.25

# Stop once no candidate is more likely than this. A build should not pad
# itself out to a fixed length with items nobody buys.
MIN_PROBABILITY = 0.02

# How many buys before the end the completion pass starts forcing missing
# staples in outright.
PEAK_WINDOW = 2


def buy_time(index: int) -> float:
    """Median clock time at a buy index, extrapolating past the measured table."""
    if index < len(MEDIAN_BUY_TIME_S):
        return float(MEDIAN_BUY_TIME_S[index])
    over = index - len(MEDIAN_BUY_TIME_S) + 1
    return float(MEDIAN_BUY_TIME_S[-1] + over * SECONDS_PER_PURCHASE)


@dataclass
class Inventory:
    """Items held right now, with components absorbed as composites are bought.

    `purchased` is every buy in order and never shrinks; `held` is what is
    occupying a slot. The two diverge exactly when a composite absorbs a
    component, which is what lets a 17-purchase build respect a 12-slot cap.
    """

    held: set[int] = field(default_factory=set)
    purchased: list[int] = field(default_factory=list)
    consumed: dict[int, int] = field(default_factory=dict)

    def buy(self, item_id: int, components: dict[int, tuple[int, ...]]) -> list[int]:
        """Add an item, absorbing any owned components. Returns what it absorbed."""
        absorbed = [c for c in components.get(item_id, ()) if c in self.held]
        for component in absorbed:
            self.held.discard(component)
            self.consumed[component] = item_id
        self.held.add(item_id)
        self.purchased.append(item_id)
        return absorbed

    def would_fit(self, item_id: int, components: dict[int, tuple[int, ...]]) -> bool:
        """Whether buying this keeps the held count legal after absorption."""
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
    """Roll the model forward from an empty inventory into a full build.

    `staples` is the completion pass: items the population buys at or above the
    prevalence threshold get a nudge as the purchase budget runs out, so a
    build does not end up missing an item 96% of players buy simply because it
    was never the single most likely pick at any one step. A nudged pick is
    labelled in its `backoff_level` so it is never mistaken for the model's own
    preference.

    `temperature` 0 is greedy and deterministic. Above 0 it samples from
    `P ** (1/T)` with a seeded generator, for the diagnostic that checks
    staples appear in nearly every sampled build.
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
            # Pre-match planning asks what to buy eventually, not what is
            # affordable this second.
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
        # An absorbed component leaves the inventory when its parent arrives.
        # That is a fact about this build, not an estimate.
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
    """Soft preferences over the model's distribution. Never a hard filter."""
    scored = probability.copy()

    if component_penalty < 1.0:
        for i, item_id in enumerate(ids):
            needed = components.get(int(item_id), ())
            if needed and not all(c in inventory.held for c in needed):
                scored[i] *= component_penalty

    if staples:
        missing = [s for s in staples if s not in inventory.purchased]
        # Reserve a slot per missing staple. Deferring them to the last few
        # buys does not work: the inventory is full by then and a staple with
        # no components to absorb can never be added. Melee Silver kept losing
        # Hunter's Aura this way -- an item 71% of its players buy, and buy at
        # index 7, which the generator was pushing to index 14 against a full
        # inventory.
        #
        # Once free slots have run down to the number of staples still owed,
        # every remaining slot belongs to a staple.
        free_slots = MAX_HELD_ITEMS - len(inventory.held)
        forced = missing and (
            remaining <= len(missing) + PEAK_WINDOW or free_slots <= len(missing)
        )
        if forced:
            for i, item_id in enumerate(ids):
                if int(item_id) in missing:
                    scored[i] = max(scored[i], staples[int(item_id)])
    return scored


def _ensure_staples_present(
    ids: np.ndarray,
    probability: np.ndarray,
    staples: dict[int, float] | None,
    inventory: Inventory,
    remaining: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Put a still-missing staple back on the ballot when the budget runs out.

    The completion pass reweights candidates, so it can only promote an item
    the model already offered. An item the model never surfaces in this context
    is invisible to it -- which is how Melee Silver kept missing Hunter's Aura,
    an item 71% of its players buy: by the closing buys its conditional
    probability had decayed below the candidate set entirely.

    Appending it at probability 0 keeps the reported number honest -- the model
    really does not expect it here -- while `_apply_priors` supplies the
    prevalence that justifies buying it, and the build labels the pick
    `+staple` so it is never read as the model's own preference.
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
    """Pick a legal index: never re-buy, never exceed the held cap."""
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
    """Many sampled builds, for the calibration diagnostic.

    A staple appearing in only 60% of samples is a calibration problem that
    greedy generation would have hidden, since greedy shows one build and says
    nothing about how stable it is.
    """
    return [
        generate_build(
            hero_id, archetype_id, model, temperature=temperature, seed=i, **kwargs
        )
        for i in range(n)
    ]
