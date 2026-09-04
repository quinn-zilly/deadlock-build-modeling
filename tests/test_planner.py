"""Tests for the build planner."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from deadlock import assets, planner


def _advantage_table():
    """A table spanning every cost tier, with plausible sample sizes."""
    items = assets.load_items()
    rows = []
    for cost in (800, 1600, 3200, 6400):
        tier = [i for i, v in items.items() if v.cost == cost][:8]
        for rank, item_id in enumerate(tier):
            rows.append({
                "item_id": item_id,
                "advantage": 0.05 - 0.005 * rank,
                "blended": 0.05 - 0.005 * rank,
                "n": 2000,
                "hero_n": 2000,
                "cost": cost,
                "significant": True,
            })
    return pd.DataFrame(rows).set_index("item_id")


class TestPlanBuild:
    def test_fills_every_section(self):
        build = planner.plan_build(_advantage_table(), 7)
        sections = build.by_section()
        assert set(sections) == {"lane", "early", "core", "late"}
        assert len(build.items) == sum(count for _, count, _ in planner.BUILD_SECTIONS)

    def test_no_duplicate_items(self):
        build = planner.plan_build(_advantage_table(), 7)
        ids = [item.item_id for item in build.items]
        assert len(ids) == len(set(ids))

    def test_sections_respect_price_bands(self):
        build = planner.plan_build(_advantage_table(), 7)
        allowed = {name: costs for name, _, costs in planner.BUILD_SECTIONS}
        for item in build.items:
            assert item.cost in allowed[item.section]

    def test_late_section_is_top_tier_only(self):
        # 3200-soul items have their own section; letting them into "late"
        # produced builds whose late game was not actually late.
        build = planner.plan_build(_advantage_table(), 7)
        late = [i for i in build.items if i.section == "late"]
        assert {i.cost for i in late} == {6400}

    def test_ranks_by_score_within_section(self):
        build = planner.plan_build(_advantage_table(), 7)
        for items in build.by_section().values():
            scores = [i.score for i in items]
            assert scores == sorted(scores, reverse=True)

    def test_total_cost_sums_items(self):
        build = planner.plan_build(_advantage_table(), 7)
        assert build.total_cost == sum(i.cost for i in build.items)

    def test_names_the_hero(self):
        build = planner.plan_build(_advantage_table(), 7)
        assert build.hero_name == assets.playable_heroes()[7].name


class TestEvidenceGate:
    """Items with no evidence must never be recommended.

    The gate must read the same count that gets reported. Checking the global
    `n` while displaying `hero_n` let items through with zero hero-specific
    observations, producing n=0 picks in real builds.
    """

    def test_excludes_under_evidenced_items(self):
        table = _advantage_table()
        table["hero_n"] = 5
        build = planner.plan_build(table, 7, min_observations=150)
        assert build.items == []

    def test_reported_n_is_the_gated_n(self):
        table = _advantage_table()
        table["hero_n"] = 900
        table["n"] = 50_000
        build = planner.plan_build(table, 7)
        assert all(item.n == 900 for item in build.items)

    def test_threshold_is_respected(self):
        table = _advantage_table()
        table["hero_n"] = 200
        assert planner.plan_build(table, 7, min_observations=100).items
        assert not planner.plan_build(table, 7, min_observations=500).items


class TestBlending:
    def test_weight_rises_with_hero_evidence(self):
        # An item seen often on this hero should trust its own estimate; a
        # rare one should defer to the global table.
        few = 50 / (50 + planner.SHRINKAGE_PRIOR_N)
        many = 5000 / (5000 + planner.SHRINKAGE_PRIOR_N)
        assert few < 0.2 < many

    def test_falls_back_to_global_when_hero_absent(self):
        rows = [{
            "match_id": 1, "player_slot": 1, "assigned_lane": 1, "team": "Team0",
            "won": True, "hero_id": 7, "item_id": 10, "phase": 0, "buy_time_s": 60,
        }]
        df = pd.DataFrame(rows)
        table = _advantage_table()
        blended = planner.blended_advantage(df, 999, global_table=table)
        assert (blended["blend_weight"] == 0).all()


class TestExport:
    def test_produces_deadlock_schema(self):
        build = planner.plan_build(_advantage_table(), 7)
        payload = planner.to_deadlock_json(build)
        assert "hero_build" in payload
        hero_build = payload["hero_build"]
        assert hero_build["hero_id"] == 7
        assert "mod_categories" in hero_build["details"]

    def test_every_item_becomes_a_mod(self):
        build = planner.plan_build(_advantage_table(), 7)
        payload = planner.to_deadlock_json(build)
        mods = [
            mod
            for category in payload["hero_build"]["details"]["mod_categories"]
            for mod in category["mods"]
        ]
        assert len(mods) == len(build.items)
        assert {m["ability_id"] for m in mods} == {i.item_id for i in build.items}

    def test_writes_valid_json(self, tmp_path):
        build = planner.plan_build(_advantage_table(), 7)
        path = planner.export_build(build, tmp_path / "build.json")
        loaded = json.loads(path.read_text())
        assert loaded["hero_build"]["hero_id"] == 7

    def test_accepts_a_custom_name(self):
        build = planner.plan_build(_advantage_table(), 7)
        payload = planner.to_deadlock_json(build, name="My Build")
        assert payload["hero_build"]["name"] == "My Build"
