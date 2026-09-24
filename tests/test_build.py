"""Build generation: legal purchases, absorption, staples, and the gate.

A build is about 17 purchases, but a player holds at most 12 items. Absorption
makes that work: buying a composite removes its held components. Items that
are a component of something are sold 70.6% of the time, against 6.4% for
other items, so most "selling" is absorption.

That is why the staple gate checks the purchase sequence, never held items.
`TestGateRunsOnPurchases` tests this directly.
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

# Two real composite/component pairs the staple forcing must order correctly.
# Given by id, not name, because two catalogue entries are both called
# "Silencer".
RADIANT_REGENERATION = 2947183272  # absorbs Mystic Regeneration
MYSTIC_REGENERATION = 1439347412
ENDURING_SPEED = 2447176615  # absorbs Sprint Boots
SPRINT_BOOTS = 3399065363


def purchases(
    items: tuple[int, ...], n_players: int = 200, *, vary: bool = False
) -> pd.DataFrame:
    """Made-up purchases.

    `vary` rotates each player's order. Without it every player buys the same
    sequence, each step has one item at probability 1.0, and sampling and
    staple forcing have nothing to do.
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
        """buy_time returns MEDIAN_BUY_TIME_S for each position."""
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
        # Absorbed components stay in `purchased`.
        assert inventory.purchased == [100, 101, 200]
        assert inventory.consumed == {100: 200, 101: 200}

    def test_absorption_frees_slots(self):
        """Buying a composite frees the slots of the components it absorbs."""
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
        """A build never has the same item twice. No player did in 5,119,990 purchases."""
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
        """A composite can still be picked when its component isn't held.

        19% of real composite purchases come without the component first.
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

    def test_the_penalty_survives_the_staple_force(self):
        """When a composite and its component are both staples, the component comes first.

        Gun Shiv has three such pairs, such as Radiant Regeneration and Mystic
        Regeneration. Ranked by prevalence alone the composite comes first,
        its component comes later and isn't absorbed, and 13 staples need 13
        slots when the cap is 12.
        """
        composite, component = RADIANT_REGENERATION, MYSTIC_REGENERATION
        scored = build._apply_priors(
            np.array([composite, component]),
            np.array([0.0, 0.0]),
            inventory=build.Inventory(),
            components={composite: (component,)},
            component_penalty=build.COMPONENT_PENALTY,
            # Gun Shiv's real prevalences (n=2,011). The composite is higher, as
            # in every real pair.
            staples={composite: 0.972, component: 0.959},
            remaining=2,
        )
        assert scored[1] > scored[0]

    def test_a_staple_is_not_demoted_for_a_component_nobody_buys(self):
        """A staple isn't pushed back for a component that isn't a staple.

        85% of Gun Victor players buy Enduring Speed, but its component Sprint
        Boots isn't a staple, so waiting for it would drop Enduring Speed.
        """
        composite, component = ENDURING_SPEED, SPRINT_BOOTS
        scored = build._apply_priors(
            np.array([composite]),
            np.array([0.0]),
            inventory=build.Inventory(),
            components={composite: (component,)},
            component_penalty=build.COMPONENT_PENALTY,
            # Gun Victor's real prevalence (n=1,568). Sprint Boots isn't one of
            # its staples.
            staples={composite: 0.848},
            remaining=1,
        )
        assert scored[0] == pytest.approx(0.848)


class TestStapleCompletion:
    def test_a_reserved_slot_admits_a_missing_staple(self):
        """Staples are forced in once free slots are down to the number still missing.

        Waiting until the last purchases fails, because the inventory is full
        by then. Melee Silver lost Hunter's Aura this way: 71% of those players
        buy it at position 7, and the generator pushed it to 14 with 12 items
        held.
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
        """A missing staple the model gives no probability is added to the candidates."""
        staple = REAL_ITEMS[5]
        ids, probability = build._ensure_staples_present(
            np.array([REAL_ITEMS[0]]),
            np.array([1.0]),
            {staple: 0.9},
            build.Inventory(),
            remaining=1,
        )
        assert staple in ids.tolist()
        # Its probability stays 0, which is what the model predicts.
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
        """A forced staple gets "+staple" in its backoff_level."""
        # A staple the model never saw, so only staple forcing can add it. The
        # build is short so a slot is still free.
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
        """A staple that absorbs nothing can't be added to a full 12-item inventory."""
        inventory = build.Inventory()
        for item_id in REAL_ITEMS[:MAX_HELD_ITEMS]:
            inventory.buy(item_id, {})
        assert not inventory.would_fit(REAL_ITEMS[20], {})


class TestGateRunsOnPurchases:
    def test_a_staple_absorbed_as_a_component_still_passes(self):
        """A staple that was bought and then absorbed still passes the gate.

        Hero 4's first archetype has 12 staples, and 7 are gone by match end
        more than half the time. Mystic Burst is bought by 96% and sold by
        95%. A gate on `held_items()` would fail a correct build.
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
        # ...but every player bought it, so a gate on held items would fail and
        # a gate on purchases passes.
        on_held = evaluate.prevalence_gate(
            [i.item_id for i in generated.held_items()], population, hero_id=HERO
        )
        on_purchases = evaluate.prevalence_gate(
            [i.item_id for i in generated.items], population, hero_id=HERO
        )
        assert not on_held.passed
        assert on_purchases.passed

    def test_absorption_sets_the_sell_time_to_the_parent_buy(self):
        """An absorbed component's sell time is the time its composite was bought."""
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
    """On real data, every generated build has all its staples, in every cell.

    `test_old_planner_build_fails_the_gate` shows the gate catches a bad
    build. This shows the generator makes good ones.
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
        """Real median purchase times still match MEDIAN_BUY_TIME_S.

        If a patch changes purchase pace, this fails instead of the build
        timings quietly going stale.
        """
        frame = pd.read_parquet(PARQUET, columns=["buy_index", "buy_time_s"])
        median = frame.groupby("buy_index")["buy_time_s"].median()
        for index, expected in enumerate(build.MEDIAN_BUY_TIME_S):
            assert abs(median.loc[index] - expected) <= 30, f"buy {index} moved"

    def test_component_consumption_explains_most_selling(self):
        """On real data, components are sold far more often than other items.

        Build generation relies on this. If a patch changes it, revisit how
        builds fit into 12 slots.
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
