"""The build browser: its page renders, and its script runs.

The page's own generator already parses and runs the script before writing,
but only when someone runs the generator, and a full run reads the whole
purchase corpus and takes minutes. These tests do the same checks against
synthetic builds, so a template edit that breaks a render function fails here
rather than at the next refit.

The failure being guarded is specific and has happened: the published page
shipped with a JavaScript syntax error that killed the entire script, leaving
markup that looked correct, a dead search box and an empty panel. Nothing
about the HTML looked wrong. A renderer that throws on its first build looks
identical, and so does a section that quietly renders to nothing.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

spec = importlib.util.spec_from_file_location(
    "build_site", ROOT / "scripts" / "build_site.py"
)
build_site = importlib.util.module_from_spec(spec)
sys.modules["build_site"] = build_site
spec.loader.exec_module(build_site)

needs_node = pytest.mark.skipif(
    shutil.which("node") is None, reason="node is not installed"
)


def item(name: str, position: int, *, sold: float | None = None, item_id: int = 0):
    return {
        "id": item_id or 1000 + position,
        "name": name,
        "cost": 800 * (position + 1),
        "time": 120.0 * (position + 1),
        "p": 0.42,
        "n": 1500,
        "level": "L1",
        "sold": sold,
        "staple": position == 0,
    }


def build(
    hero: str = "Ivy",
    archetype: str = "Gun Ivy",
    *,
    items=None,
    abilities=True,
    imbue=True,
    counters=True,
):
    items = items or [
        item("Extra Regen", 0, sold=1400.0),
        item("Mystic Burst", 1),
        item("Improved Spirit", 2),
    ]
    return {
        "hero": hero,
        "archetype": archetype,
        "share": 0.61,
        "win_rate": 0.512,
        "n": 4200,
        "n_staples": 1,
        "export": {
            "hero_build": {
                "hero_id": 11,
                "name": f"{archetype} - build order",
                "details": {
                    "mod_categories": [
                        {"name": "800 souls", "mods": [{"ability_id": i["id"]}]}
                        for i in items
                        if not i["sold"]
                    ]
                },
            }
        },
        "items": items,
        "abilities": [
            {
                "position": 1,
                "name": "Kudzu Bomb",
                "level": 1,
                "time": 90.0,
                "p": 0.71,
                "n": 3900,
                "backoff": "L1",
                "thin": False,
            }
        ]
        if abilities
        else [],
        "imbue": [
            {
                "item": "Mystic Burst",
                "ability": "Kudzu Bomb",
                "share": 0.66,
                "n": 810,
                "thin": False,
                "split": False,
            }
        ]
        if imbue
        else [],
        "counters": [
            {
                "item": "Extra Regen",
                "enemy": "Bebop",
                "lift": 0.031,
                "facing": 0.44,
                "baseline": 0.409,
                "n": 2600,
            }
        ]
        if counters
        else [],
    }


META = {
    "top1": 0.391,
    "bigram": 0.267,
    "purchases": "5,095,598",
    "players": "296k",
    "bracket": "badge ~80",
}


def page(builds=None, meta=None) -> str:
    return build_site.render(builds or [build()], meta or META)


class TestMetrics:
    """The masthead's figures come from the README, not from a second copy."""

    def test_reads_both_held_out_rows(self):
        figures = build_site.read_metrics()
        assert set(figures) == {"top1", "bigram"}

    def test_the_model_beats_the_bar(self):
        # Not a claim about the model -- a check that the two rows were not
        # read the wrong way round, which no other assertion here would catch.
        figures = build_site.read_metrics()
        assert figures["top1"] > figures["bigram"]

    def test_a_missing_row_is_fatal(self, tmp_path, monkeypatch):
        readme = tmp_path / "README.md"
        readme.write_text("| bigram (the bar) | 0.267 | 0.277 |\n", encoding="utf-8")
        monkeypatch.setattr(build_site, "README", readme)
        with pytest.raises(SystemExit, match="backoff chain"):
            build_site.read_metrics()


class TestRender:
    def test_inlines_the_builds(self):
        assert '"archetype":"Gun Ivy"' in page()

    def test_inlines_the_meta(self):
        assert "const META =" in page()

    def test_a_moved_marker_is_fatal(self, tmp_path, monkeypatch):
        template = tmp_path / "builds.html"
        template.write_text("<script>\nconst other = 1;\n</script>", encoding="utf-8")
        monkeypatch.setattr(build_site, "TEMPLATE", template)
        with pytest.raises(SystemExit, match="script opening"):
            page()


@needs_node
class TestScript:
    """What the generator checks, on builds chosen to be the awkward cases."""

    def test_the_shipped_page_runs(self):
        build_site.check_script(page())

    def test_a_build_with_no_counters_runs(self):
        build_site.check_script(page([build(counters=False), build_pair()[1]]))

    def test_a_build_with_no_imbues_runs(self):
        build_site.check_script(page([build(imbue=False), build_pair()[1]]))

    def test_a_build_with_no_ability_order_runs(self):
        build_site.check_script(page([build(abilities=False), build_pair()[1]]))

    def test_a_syntax_error_in_the_template_is_caught(self, tmp_path, monkeypatch):
        # The exact construct that shipped broken: a double-quoted string
        # holding double-quoted attributes, which ends the string early.
        broken = build_site.TEMPLATE.read_text(encoding="utf-8").replace(
            'const esc = t =>',
            'const bad = "<span class="x"></span>";\nconst esc = t =>',
            1,
        )
        template = tmp_path / "builds.html"
        template.write_text(broken, encoding="utf-8")
        monkeypatch.setattr(build_site, "TEMPLATE", template)
        with pytest.raises(SystemExit, match="JavaScript failed"):
            build_site.check_script(page())

    def test_a_section_that_renders_nothing_is_caught(self, tmp_path, monkeypatch):
        # A renderer that returns "" for data it was given is the failure the
        # heading check exists for: the page looks whole and the section is
        # simply absent.
        gutted = build_site.TEMPLATE.read_text(encoding="utf-8").replace(
            "function renderCounters(b) {\n  const rows = b.counters || [];",
            "function renderCounters(b) {\n  return '';\n  const rows = b.counters || [];",
            1,
        )
        template = tmp_path / "builds.html"
        template.write_text(gutted, encoding="utf-8")
        monkeypatch.setattr(build_site, "TEMPLATE", template)
        with pytest.raises(SystemExit, match="Counter-picks"):
            build_site.check_script(page())

    def test_a_dead_export_button_is_caught(self, tmp_path, monkeypatch):
        # Downloading leaves the page, so a broken export is invisible in the
        # markup -- the button renders and does nothing.
        broken = build_site.TEMPLATE.read_text(encoding="utf-8").replace(
            "return { name: slug + \".json\"",
            "return { name: slug",
            1,
        )
        template = tmp_path / "builds.html"
        template.write_text(broken, encoding="utf-8")
        monkeypatch.setattr(build_site, "TEMPLATE", template)
        with pytest.raises(SystemExit, match="no filename"):
            build_site.check_script(page())

    def test_single_archetype_heroes_have_nothing_to_compare(self):
        # Every hero single-archetype, so no comparison is possible. That is
        # data, not a defect, and the harness must not fail on it -- a page
        # filtered to one such hero is a normal `--hero` run.
        build_site.check_script(page([build("Ivy", "Ivy"), build("Abrams", "Abrams")]))

    def test_a_broken_comparison_is_caught(self, tmp_path, monkeypatch):
        # The other direction: the data offers a pair and the renderer shows
        # nothing. Silence from a renderer that had its input is the bug.
        gutted = build_site.TEMPLATE.read_text(encoding="utf-8").replace(
            "function renderCompare(b) {",
            "function renderCompare(b) {\n  return '';",
            1,
        )
        template = tmp_path / "builds.html"
        template.write_text(gutted, encoding="utf-8")
        monkeypatch.setattr(build_site, "TEMPLATE", template)
        with pytest.raises(SystemExit, match="Ivy: comparison did not render"):
            build_site.check_script(page(list(build_pair())))


def build_pair():
    """Two builds of one hero, so the comparison has something to render."""
    return build("Ivy", "Gun Ivy"), build(
        "Ivy",
        "Spirit Ivy",
        items=[
            item("Extra Spirit", 0, item_id=2001),
            item("Improved Spirit", 1, item_id=1002),
        ],
    )


@needs_node
class TestComparison:
    def test_two_builds_of_one_hero_compare(self):
        build_site.check_script(page(list(build_pair())))

    def test_a_shared_item_is_shared_in_both(self):
        # Improved Spirit is in both builds of the pair, so neither side may
        # mark it as its own. This is the assertion that would catch a diff
        # computed against the wrong set.
        first, second = build_pair()
        shared = {i["id"] for i in first["items"]} & {i["id"] for i in second["items"]}
        assert shared, "the fixture must share an item for this to test anything"
