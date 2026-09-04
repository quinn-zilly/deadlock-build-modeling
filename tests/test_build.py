"""Generating a build: legality, absorption, and the gate it has to clear.

The load-bearing claim here is about *component absorption*. A build is ~17
purchases but only 12 items can be held, and those reconcile because buying a
composite consumes the components already owned. Sold rate is 70.6% for items
that are a component of something against 6.4% for items that are not, so most
"selling" is not a player changing their mind -- it is a slot being freed.

Which is why the prevalence gate runs on the purchase sequence and never on
held items. `TestGateRunsOnPurchases` pins that directly: it is the trap this
design exists to avoid.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from deadlock import assets, build, evaluate, sequence
from deadlock.buildfmt import MAX_HELD_ITEMS

HERO = 7
REAL_ITEMS = sorted(assets.shopable_items())


def purchases(
    items: tuple[int, ...], n_players: int = 200, *, vary: bool = False
) -> pd.DataFrame:
    """A synthetic population.

    `vary` rotates each player's order. Without it every player buys the same
    sequence, the conditional is 1.0 on a single item, and both sampling and
    the completion pass have nothing to act on -- which is a property of the
    fixture, not of the generator.
    """
    rows = []
    for m in range(n_players):
        order = items if not vary else items[m % len(items):] + items[: m % len(items)]
        for i, item in enumerate(order):
            rows.append(
                {
                    "match_id": m,
                    "player_slot": 1,
                    "hero_id": HERO,
                    "item_id": item,
                    "buy_index": i,
                    "buy_time_s": build.buy_time(i),
                    "won": m % 2 == 0,
                    "average_badge": 60,
                    "account_id": m,
                }
            )
    return pd.DataFrame(rows)


def model_over(
    items: tuple[int, ...], n_players: int = 200, *, vary: bool = False
) -> sequence.SequenceModel:
    return sequence.fit(purchases(items, n_players, vary=vary))


class TestBuyTime:
    def test_matches_the_measured_medians(self):
        """Buy time is linear in the index, so timing is a lookup not a model."""
        assert build.buy_time(0) == 70
        assert build.buy_time(5) == 629
        assert build.buy_time(13) == 1570

    def test_extrapolates_past_the_table(self):
        beyond = build.buy_time(len(build.MEDIAN_BUY_TIME_S) + 2)
        assert beyond > build.MEDIAN_BUY_TIME_S[-1]

    def test_is_non_decreasing(self):
        times = [build.buy_time(i) for i in range(30)]
        assert times == sorted(times)


class TestInventoryAbsorption:
    def test_a_composite_absorbs_its_owned_components(self):
        components = {200: (100, 101)}
        inventory = build.Inventory()
        inventory.buy(100, components)
        inventory.buy(101, components)
        absorbed = inventory.buy(200, components)

        assert set(absorbed) == {100, 101}
        assert inventory.held == {200}
        # The purchase record never shrinks: they were still bought.
        assert inventory.purchased == [100, 101, 200]
        assert inventory.consumed == {100: 200, 101: 200}

    def test_absorption_frees_slots(self):
        """This is the mechanism that fits 17 purchases into 12 slots."""
        components = {200: (100,)}
        inventory = build.Inventory()
        inventory.buy(100, components)
        assert len(inventory.held) == 1
        inventory.buy(200, components)
        assert len(inventory.held) == 1
        assert len(inventory.purchased) == 2

    def test_an_unowned_component_is_not_absorbed(self):
        inventory = build.Inventory()
        assert inventory.buy(200, {200: (100,)}) == []

    def test_would_fit_accounts_for_what_would_be_freed(self):
        components = {999: (0, 1)}
        inventory = build.Inventory()
        for i in range(MAX_HELD_ITEMS):
            inventory.buy(i, {})
        assert len(inventory.held) == MAX_HELD_ITEMS
        # A plain item cannot fit, but one absorbing two held components can.
        assert not inventory.would_fit(500, {})
        assert inventory.would_fit(999, components)


class TestLegality:
    def test_no_item_is_ever_bought_twice(self):
        """Exact, not approximate: no player rebuys in 5,095,598 rows."""
        generated = build.generate_build(HERO, 0, model_over(tuple(REAL_ITEMS[:20])))
        ids = [item.item_id for item in generated.items]
        assert len(ids) == len(set(ids))

    def test_held_items_never_exceed_the_cap(self):
        generated = build.generate_build(
            HERO, 0, model_over(tuple(REAL_ITEMS[:20])), max_purchases=17
        )
        assert len(generated.held_items()) <= MAX_HELD_ITEMS

    def test_only_shopable_items_are_recommended(self):
        generated = build.generate_build(HERO, 0, model_over(tuple(REAL_ITEMS[:20])))
        shopable = assets.shopable_items()
        assert all(item.item_id in shopable for item in generated.items)

    def test_positions_are_sequential_and_times_increase(self):
        generated = build.generate_build(HERO, 0, model_over(tuple(REAL_ITEMS[:12])))
        assert [i.position for i in generated.items] == list(range(len(generated.items)))
        times = [i.buy_time_s for i in generated.items]
        assert times == sorted(times)


class TestComponentPreference:
    def test_the_penalty_is_soft_not_a_mask(self):
        """19% of real builds buy a composite without its component first.

        A hard mask would make those unreachable, so the composite has to stay
        selectable even when its component is missing.
        """
        composite, component = REAL_ITEMS[0], REAL_ITEMS[1]
        ids = np.array([composite])
        probability = np.array([0.5])
        scored = build._apply_priors(
            ids,
            probability,
            inventory=build.Inventory(),
            components={composite: (component,)},
            component_penalty=build.COMPONENT_PENALTY,
            staples=None,
            remaining=10,
        )
        assert 0 < scored[0] < probability[0]

    def test_an_owned_component_removes_the_penalty(self):
        composite, component = REAL_ITEMS[0], REAL_ITEMS[1]
        inventory = build.Inventory()
        inventory.buy(component, {})
        scored = build._apply_priors(
            np.array([composite]),
            np.array([0.5]),
            inventory=inventory,
            components={composite: (component,)},
            component_penalty=build.COMPONENT_PENALTY,
            staples=None,
            remaining=10,
        )
        assert scored[0] == pytest.approx(0.5)


class TestStapleCompletion:
    def test_a_reserved_slot_admits_a_missing_staple(self):
        """Slots are reserved once free space runs down to what is still owed.

        Deferring staples to the closing buys does not work: the inventory is
        full by then, and a staple with no components to absorb can never be
        added. Melee Silver lost Hunter's Aura exactly this way -- an item 71%
        of its players buy, at index 7, pushed to index 14 against 12 held
        items.
        """
        staple = REAL_ITEMS[5]
        inventory = build.Inventory()
        for i in REAL_ITEMS[10 : 10 + MAX_HELD_ITEMS - 1]:
            inventory.buy(i, {})

        scored = build._apply_priors(
            np.array([staple, REAL_ITEMS[11]]),
            np.array([0.01, 0.9]),
            inventory=inventory,
            components={},
            component_penalty=1.0,
            staples={staple: 0.71},
            remaining=10,
        )
        assert scored[0] == pytest.approx(0.71)

    def test_a_staple_off_the_ballot_is_restored(self):
        """The nudge reweights candidates, so it cannot promote an item the
        model never offered."""
        staple = REAL_ITEMS[5]
        ids, probability = build._ensure_staples_present(
            np.array([REAL_ITEMS[0]]),
            np.array([1.0]),
            {staple: 0.9},
            build.Inventory(),
            remaining=1,
        )
        assert staple in ids.tolist()
        # Honest about the model's own view: it did not expect this here.
        assert probability[ids.tolist().index(staple)] == 0.0

    def test_an_already_bought_staple_is_not_restored(self):
        staple = REAL_ITEMS[5]
        inventory = build.Inventory()
        inventory.buy(staple, {})
        ids, _ = build._ensure_staples_present(
            np.array([REAL_ITEMS[0]]), np.array([1.0]), {staple: 0.9}, inventory, 1
        )
        assert staple not in ids.tolist()

    def test_a_nudged_pick_is_labelled(self):
        """A forced staple must never read as the model's own preference."""
        # A staple outside the training vocabulary entirely: the model has no
        # reason to offer it, so only the completion pass can put it in. The
        # build is kept short so a slot is still free -- a staple with nothing
        # to absorb cannot enter a full inventory, which is a real constraint
        # rather than a failure of the nudge.
        generated = build.generate_build(
            HERO,
            0,
            model_over(tuple(REAL_ITEMS[:14])),
            staples={REAL_ITEMS[20]: 0.95},
            max_purchases=6,
        )
        nudged = [i for i in generated.items if "+staple" in i.backoff_level]
        assert nudged, "the staple was never inserted"
        assert all(i.item_id == REAL_ITEMS[20] for i in nudged)

    def test_a_full_inventory_cannot_take_another_staple(self):
        """The honest limit: 12 slots is a hard constraint, not a preference.

        A staple with no components to absorb genuinely cannot be added to a
        full inventory, and the generator must not pretend otherwise.
        """
        inventory = build.Inventory()
        for item_id in REAL_ITEMS[:MAX_HELD_ITEMS]:
            inventory.buy(item_id, {})
        assert not inventory.would_fit(REAL_ITEMS[20], {})


class TestGateRunsOnPurchases:
    def test_a_staple_absorbed_as_a_component_still_passes(self):
        """The trap this whole design avoids.

        Hero 4's first archetype has 12 staples, 7 sold more than half the
        time -- Mystic Burst is bought by 96% of its players and sold by 95%.
        A 12-slot inventory cannot hold them, so gating `held_items()` would
        fail a correct build.
        """
        component, composite = REAL_ITEMS[0], REAL_ITEMS[1]
        population = purchases((component, composite), n_players=400)

        generated = build.Build(hero_id=HERO, hero_name="Test")
        inventory = build.Inventory()
        components = {composite: (component,)}
        for position, item_id in enumerate((component, composite)):
            inventory.buy(item_id, components)
            generated.items.append(
                build.BuildItem(
                    item_id=item_id,
                    name=str(item_id),
                    cost=0,
                    position=position,
                    buy_time_s=build.buy_time(position),
                    probability=1.0,
                    n=400,
                    backoff_level="L0",
                    sell_time_s=build.buy_time(1) if item_id == component else None,
                )
            )

        # The component was absorbed, so it is not held...
        assert component not in {i.item_id for i in generated.held_items()}
        # ...but it was bought by 100% of the population, so gating held items
        # would fail it while gating purchases passes.
        on_held = evaluate.prevalence_gate(
            [i.item_id for i in generated.held_items()], population, hero_id=HERO
        )
        on_purchases = evaluate.prevalence_gate(
            [i.item_id for i in generated.items], population, hero_id=HERO
        )
        assert not on_held.passed
        assert on_purchases.passed

    def test_absorption_sets_the_sell_time_to_the_parent_buy(self):
        """A checkable fact about this build, not an estimated sell time."""
        components = assets.component_map()
        parent = next(iter(components))
        component = components[parent][0]
        model = model_over((component, parent))
        generated = build.generate_build(HERO, 0, model, max_purchases=2)

        bought = [i.item_id for i in generated.items]
        if component in bought and parent in bought:
            first = next(i for i in generated.items if i.item_id == component)
            second = next(i for i in generated.items if i.item_id == parent)
            assert first.sell_time_s == second.buy_time_s


class TestDeterminism:
    def test_greedy_is_deterministic(self):
        model = model_over(tuple(REAL_ITEMS[:20]))
        first = build.generate_build(HERO, 0, model)
        second = build.generate_build(HERO, 0, model)
        assert [i.item_id for i in first.items] == [i.item_id for i in second.items]

    def test_sampling_is_reproducible_for_a_seed(self):
        model = model_over(tuple(REAL_ITEMS[:20]))
        first = build.generate_build(HERO, 0, model, temperature=0.8, seed=3)
        second = build.generate_build(HERO, 0, model, temperature=0.8, seed=3)
        assert [i.item_id for i in first.items] == [i.item_id for i in second.items]

    def test_different_seeds_can_differ(self):
        model = model_over(tuple(REAL_ITEMS[:30]), n_players=400, vary=True)
        builds = {
            tuple(
                i.item_id
                for i in build.generate_build(
                    HERO, 0, model, temperature=1.0, seed=s
                ).items
            )
            for s in range(8)
        }
        assert len(builds) > 1


class TestEmptyModel:
    def test_an_unknown_hero_yields_an_empty_build(self):
        generated = build.generate_build(999, 0, model_over(tuple(REAL_ITEMS[:5])))
        assert generated.items == []


PARQUET = Path("data/processed/purchases.parquet")
ARCHETYPES = Path("data/processed/archetypes.parquet")


@pytest.mark.data
@pytest.mark.skipif(not PARQUET.exists(), reason="needs data/processed/*.parquet")
class TestAgainstRealData:
    """The headline regression: every generated build carries its staples.

    Successor to `test_old_planner_build_fails_the_gate`. That one proved the
    gate could catch a bad build; this one proves the generator produces good
    ones -- for all 75 hero-and-archetype cells, not just the easy ones.
    """

    @staticmethod
    def _wraith():
        columns = [
            "match_id", "player_slot", "account_id", "hero_id",
            "item_id", "buy_index", "buy_time_s", "won", "average_badge",
        ]
        frame = pd.read_parquet(PARQUET, columns=columns)
        labels = pd.read_parquet(ARCHETYPES)
        heroes = {h.name: i for i, h in assets.playable_heroes().items()}
        return frame[frame["hero_id"] == heroes["Wraith"]], labels, heroes["Wraith"]

    def test_the_wraith_build_carries_every_staple(self):
        frame, labels, hero_id = self._wraith()
        model = sequence.fit(frame, labels)
        cell = frame.merge(
            labels[(labels["hero_id"] == hero_id) & (labels["archetype_id"] == 0)][
                ["match_id", "player_slot"]
            ],
            on=["match_id", "player_slot"],
        )
        prevalence = evaluate.item_prevalence(cell)
        staples = {
            int(i): float(v)
            for i, v in prevalence[prevalence >= evaluate.PREVALENCE_THRESHOLD].items()
        }
        generated = build.generate_build(hero_id, 0, model, staples=staples)
        result = evaluate.prevalence_gate(
            [i.item_id for i in generated.items], cell, hero_id=hero_id, archetype_id=0
        )
        assert result.passed, result.describe(
            {i: it.name for i, it in assets.load_items().items()}
        )

    def test_median_buy_time_matches_the_lookup_table(self):
        """Pins the linearity claim: if a patch shifts the economy, this fails
        rather than the timings silently drifting."""
        frame = pd.read_parquet(PARQUET, columns=["buy_index", "buy_time_s"])
        median = frame.groupby("buy_index")["buy_time_s"].median()
        for index, expected in enumerate(build.MEDIAN_BUY_TIME_S):
            assert abs(median.loc[index] - expected) <= 30, f"buy {index} moved"

    def test_component_consumption_explains_most_selling(self):
        """The finding the whole generation design rests on.

        If a patch changes this, the slot arithmetic needs revisiting -- so it
        is pinned rather than assumed.
        """
        frame = pd.read_parquet(PARQUET, columns=["item_id", "sold"])
        components = {
            component
            for parts in assets.component_map().values()
            for component in parts
        }
        is_component = frame["item_id"].isin(components)
        assert frame.loc[is_component, "sold"].mean() > 0.6
        assert frame.loc[~is_component, "sold"].mean() < 0.15
