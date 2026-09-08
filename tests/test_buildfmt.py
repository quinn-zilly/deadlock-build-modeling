"""Build representation and the export schema the game accepts.

The load-bearing distinction is purchases vs. held items: a build is a
sequence of ~17 buys, but only 11-12 survive to the end, and the export
schema has no way to represent a sale.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from deadlock import buildfmt, imbue


def item(item_id: int, position: int, cost: int = 800, sell: float | None = None):
    return buildfmt.BuildItem(
        item_id=item_id,
        name=f"Item {item_id}",
        cost=cost,
        position=position,
        buy_time_s=120.0 * (position + 1),
        probability=0.4,
        n=1200,
        backoff_level="L1",
        sell_time_s=sell,
    )


def build(**kwargs) -> buildfmt.Build:
    items = kwargs.pop("items", None)
    if items is None:
        items = [item(10, 0), item(20, 1, cost=1600), item(30, 2, cost=3200)]
    return buildfmt.Build(hero_id=7, hero_name="Wraith", items=items, **kwargs)


class TestConstants:
    def test_tier_costs_stop_at_four(self):
        """Tier 5 exists in assets but is never purchased -- 0 of 5.1M rows."""
        assert buildfmt.TIER_COSTS == (800, 1600, 3200, 6400)

    def test_held_cap_is_twelve(self):
        """Measured on items held at match end: max 12, mean 10.78."""
        assert buildfmt.MAX_HELD_ITEMS == 12


class TestBuildItem:
    def test_unsold_by_default(self):
        assert not item(1, 0).sold

    def test_sold_when_sell_time_set(self):
        assert item(1, 0, sell=1200.0).sold

    def test_str_shows_clock_time(self):
        assert "2:00" in str(item(1, 0))

    def test_str_flags_a_sale(self):
        assert "sold" in str(item(1, 0, sell=1230.0))


class TestBuild:
    def test_total_cost_sums_purchases(self):
        assert build().total_cost == 800 + 1600 + 3200

    def test_held_excludes_sold(self):
        b = build(items=[item(10, 0), item(20, 1, sell=900.0), item(30, 2)])
        assert [i.item_id for i in b.held_items()] == [10, 30]

    def test_total_cost_counts_sold_items(self):
        """Souls spent on a sold item were still spent."""
        b = build(items=[item(10, 0), item(20, 1, cost=1600, sell=900.0)])
        assert b.total_cost == 2400

    def test_label_prefers_archetype(self):
        b = build(archetype_id=1, archetype_name="Gun Ivy")
        assert b.label == "Gun Ivy"

    def test_label_falls_back_to_hero(self):
        assert build().label == "Wraith"


class TestExport:
    def test_carries_hero_id(self):
        assert buildfmt.to_deadlock_json(build())["hero_build"]["hero_id"] == 7

    def test_exports_only_held_items(self):
        b = build(items=[item(10, 0), item(20, 1, sell=900.0), item(30, 2)])
        payload = buildfmt.to_deadlock_json(b)
        ids = [
            mod["ability_id"]
            for cat in payload["hero_build"]["details"]["mod_categories"]
            for mod in cat["mods"]
        ]
        assert ids == [10, 30]

    def test_groups_ascend_by_cost(self):
        payload = buildfmt.to_deadlock_json(build())
        names = [c["name"] for c in payload["hero_build"]["details"]["mod_categories"]]
        assert names == ["800 souls", "1600 souls", "3200 souls"]

    def test_annotation_carries_evidence(self):
        payload = buildfmt.to_deadlock_json(build())
        mod = payload["hero_build"]["details"]["mod_categories"][0]["mods"][0]
        assert "n=1200" in mod["annotation"]

    def test_name_can_be_overridden(self):
        payload = buildfmt.to_deadlock_json(build(), name="Custom")
        assert payload["hero_build"]["name"] == "Custom"

    def test_archetype_names_the_build(self):
        b = build(archetype_name="Spirit Ivy")
        assert "Spirit Ivy" in buildfmt.to_deadlock_json(b)["hero_build"]["name"]

    def test_writes_valid_json(self, tmp_path):
        path = buildfmt.export_build(build(), tmp_path / "out" / "wraith.json")
        assert json.loads(path.read_text())["hero_build"]["hero_id"] == 7

    def test_creates_parent_directory(self, tmp_path):
        path = buildfmt.export_build(build(), tmp_path / "deep" / "nested" / "b.json")
        assert path.exists()


BUILDS = Path("data/builds")


class TestAgainstRealData:
    """The exported builds themselves, as a player would import them.

    A build the game accepts but that says nothing about ability points or
    imbue targets is half a build, and the half it drops is the half a player
    cannot look up elsewhere.
    """

    @staticmethod
    def exports() -> list[dict]:
        if not BUILDS.exists():
            pytest.skip("requires generated builds; run scripts/generate_builds.py")
        files = sorted(BUILDS.glob("*.json"))
        if not files:
            pytest.skip("no generated builds")
        return [json.loads(f.read_text())["hero_build"] for f in files]

    def test_every_export_carries_an_ability_order(self):
        for hero_build in self.exports():
            order = hero_build["details"].get("ability_order", {})
            points = order.get("currency_changes") or []
            assert points, f"{hero_build['name']} exports no ability order"

    def test_an_ability_order_never_takes_a_slot_past_four(self):
        """The one hard constraint an ability order has."""
        for hero_build in self.exports():
            points = hero_build["details"]["ability_order"]["currency_changes"]
            taken: dict[int, int] = {}
            for point in points:
                taken[point["ability_id"]] = taken.get(point["ability_id"], 0) + 1
            assert max(taken.values()) <= 4, hero_build["name"]

    def test_every_held_imbueable_item_names_its_target(self):
        """An imbueable item with a null target is the advice half-given.

        Only held items are exported -- an imbueable item absorbed into a
        composite is not in the file at all -- so the claim is about the ones
        that survive to the end of the match.
        """
        imbueable = set(imbue.imbueable_items())
        checked = 0
        for hero_build in self.exports():
            mods = [
                mod
                for category in hero_build["details"]["mod_categories"]
                for mod in category["mods"]
            ]
            for mod in mods:
                if mod["ability_id"] not in imbueable:
                    continue
                checked += 1
                assert mod["imbue_target_ability_id"], (
                    f"{hero_build['name']} buys "
                    f"{mod['ability_id']} and does not say what to imbue it into"
                )
        assert checked, "no exported build holds an imbueable item"
