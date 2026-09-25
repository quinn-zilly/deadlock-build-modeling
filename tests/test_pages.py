"""The methodology page: what it claims, checked at the one seam.

`pages.methodology` takes the facts the page states and returns HTML, so these
tests call it with known inputs and assert on the returned string. They check
the facts, not the markup: tag structure and wording are free to change.
"""

from __future__ import annotations

import datetime as dt
import inspect
import re
from html import unescape
from pathlib import Path

import pandas as pd
import pytest

from deadlock import assets, pages, sequence, tooltips

PURCHASES = Path("data/processed/purchases.parquet")

# The shape /v1/assets/ranks returned on 2026-09-25, without the images.
RANKS_PAYLOAD = [
    {"tier": tier, "name": name, "color": "#000000"}
    for tier, name in enumerate(
        [
            "Obscurus", "Initiate", "Seeker", "Acolyte", "Sentinel", "Mystic",
            "Ritualist", "Emissary", "Oracle", "Phantom", "Ascendant", "Eternus",
        ]
    )
]
RANKS = assets.parse_ranks(RANKS_PAYLOAD)

WINDOW = dt.date(2026, 8, 22)
ORACLE = pages.Bracket(tier_name="Oracle", share=0.296)


def page(bracket: pages.Bracket | None = ORACLE, window: dt.date = WINDOW) -> str:
    return pages.methodology(bracket=bracket, window_start=window)


def visible_text(html: str) -> str:
    """The words a reader sees: no style block, no tags, no attributes."""
    html = re.sub(r"<(style|script)\b.*?</\1>", " ", html, flags=re.S)
    html = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", unescape(html))


def in_order(text: str, names: list[str]) -> bool:
    """Whether the names appear in this order, each after the one before."""
    position = 0
    for name in names:
        position = text.find(name, position)
        if position < 0:
            return False
    return True


class TestRanks:
    def test_twelve_tiers(self):
        assert len(RANKS) == 12
        assert RANKS[0].name == "Obscurus"
        assert RANKS[11].name == "Eternus"

    def test_tier_name_is_the_tens_digit(self):
        assert sequence.badge_tier_name(80, RANKS) == "Oracle"
        assert sequence.badge_tier_name(61, RANKS) == "Ritualist"
        assert sequence.badge_tier_name(116, RANKS) == "Eternus"

    def test_a_badge_off_the_scale_is_an_error(self):
        with pytest.raises(KeyError):
            sequence.badge_tier_name(130, RANKS)


class TestBracketShare:
    def frame(self) -> pd.DataFrame:
        # Two player-matches at badge 85 buy one item each; one at 40 buys
        # eight. Per player-match the share is 2/3. Per purchase it would be
        # 2/10, which is the mistake this guards against.
        rows = [
            {"match_id": 1, "player_slot": 0, "average_badge": 85},
            {"match_id": 1, "player_slot": 1, "average_badge": 85},
        ] + [{"match_id": 2, "player_slot": 0, "average_badge": 40}] * 8
        return pd.DataFrame(rows)

    def test_counts_player_matches_not_purchases(self):
        assert sequence.bracket_share(self.frame(), 80) == pytest.approx(2 / 3)

    def test_counts_from_the_bottom_of_the_tier(self):
        # "Oracle and above" starts at 80 even when the target is 85.
        frame = pd.DataFrame(
            [
                {"match_id": 1, "player_slot": 0, "average_badge": 82},
                {"match_id": 2, "player_slot": 0, "average_badge": 70},
            ]
        )
        assert sequence.bracket_share(frame, 85) == pytest.approx(0.5)

    def test_a_player_match_without_a_badge_is_left_out(self):
        frame = pd.DataFrame(
            [
                {"match_id": 1, "player_slot": 0, "average_badge": 90},
                {"match_id": 2, "player_slot": 0, "average_badge": None},
                {"match_id": 3, "player_slot": 0, "average_badge": 30},
            ]
        )
        assert sequence.bracket_share(frame, 80) == pytest.approx(0.5)

    @pytest.mark.data
    @pytest.mark.skipif(not PURCHASES.exists(), reason="needs data/processed/*.parquet")
    def test_oracle_is_about_the_top_thirty_percent(self):
        frame = pd.read_parquet(
            PURCHASES, columns=["match_id", "player_slot", "average_badge"]
        )
        assert 0.25 < sequence.bracket_share(frame, 80) < 0.35


class TestSkillLevel:
    def test_states_the_tier_and_the_percentile_it_was_given(self):
        text = visible_text(page())
        assert "Oracle" in text
        assert "30%" in text

    def test_another_bracket_names_another_rank(self):
        text = visible_text(page(pages.Bracket(tier_name="Ritualist", share=0.62)))
        assert "Ritualist" in text
        assert "62%" in text
        assert "Oracle" not in text
        assert "30%" not in text

    def test_neither_number_is_typed_into_the_module(self):
        source = inspect.getsource(pages)
        assert "Oracle" not in source
        assert "30%" not in source

    def test_unweighted_builds_claim_no_bracket(self):
        text = visible_text(page(bracket=None))
        assert "Oracle" not in text
        assert "%" not in text

    def test_unweighted_builds_are_not_called_strong_play(self):
        text = visible_text(page(bracket=None)).lower()
        assert "strong players" not in text
        assert "strong play " not in text


class TestDataWindow:
    def test_states_the_window_it_was_given(self):
        assert "22 August 2026" in visible_text(page())

    def test_another_window_is_another_date(self):
        text = visible_text(page(window=dt.date(2026, 10, 3)))
        assert "3 October 2026" in text
        assert "22 August 2026" not in text


class TestWhatThePageLeavesOut:
    def test_states_no_number_it_was_not_given(self):
        # The page's numbers are the percentile and the window date. Any other
        # figure is an accuracy score, a tau, a gap, a count, or a split ratio
        # creeping back in.
        numbers = set(re.findall(r"\d+(?:\.\d+)?", visible_text(page())))
        assert numbers <= {"30", "22", "2026"}

    def test_names_no_cut_metric(self):
        text = visible_text(page()).lower()
        for word in ("accuracy", "tau", "kendall", "top-1", "held-out", "baseline"):
            assert word not in text

    def test_no_in_match_advisor_and_no_diagnosis(self):
        html = page().lower()
        for word in ("advisor", "in-match", "diagnosis"):
            assert word not in html

    def test_is_javascript_free(self):
        assert "<script" not in page().lower()


class TestWhatThePageSays:
    def test_disclaims_causation(self):
        assert "cause" in visible_text(page()).lower()

    def test_uses_ivy_as_the_split_example(self):
        assert "Ivy" in visible_text(page())

    def test_defines_win_rate(self):
        assert "win rate" in visible_text(page()).lower()

    def test_links_the_public_repo(self):
        assert f'href="{pages.REPO_URL}"' in page()


# --- the hero surface: chooser, build page, home ---------------------------

PHASES = ("Lane", "Mid game", "Late game", "Very late")


def column(*entries: tuple[int, str, float, float | None]) -> tuple:
    return tuple(
        pages.ColumnEntry(item_id=i, name=name, rate=rate, elsewhere=other)
        for i, name, rate, other in entries
    )


COMMON = column((1, "Extra Spirit", 0.97, None), (2, "Mystic Burst", 0.91, None))


def card(
    name: str,
    *,
    share: float = 0.334,
    win_rate: float = 0.558,
    n: int = 2731,
    most_common: tuple = COMMON,
    defining: tuple = (),
    imbues: tuple = (),
) -> pages.Card:
    return pages.Card(
        archetype=name,
        href=f"{name.lower().replace(' ', '-')}/index.html",
        share=share,
        win_rate=win_rate,
        n=n,
        most_common=most_common,
        defining=defining,
        imbues=imbues,
    )


def chooser_page(cards: list[pages.Card]) -> str:
    return pages.chooser(
        hero="Ivy",
        hero_id=20,
        cards=cards,
        bracket=ORACLE,
        window_start=WINDOW,
        root="../",
    )


def card_texts(html: str, names: list[str]) -> dict[str, str]:
    """Each card's visible text, from its name to the next card's name."""
    text = visible_text(html)
    bounds = sorted((text.index(name + " "), name) for name in names)
    ends = [start for start, _ in bounds[1:]] + [len(text)]
    return {name: text[start:end] for (start, name), end in zip(bounds, ends)}


class TestChooser:
    def test_every_archetype_appears_with_its_numbers(self):
        cards = [
            card("Spirit Ivy", share=0.335, win_rate=0.558, n=2869),
            card("Hybrid Ivy", share=0.332, win_rate=0.561, n=2836),
            card("Gun Ivy", share=0.333, win_rate=0.513, n=2839),
        ]
        text = visible_text(chooser_page(cards))
        for name, share, win, n in [
            ("Spirit Ivy", "34%", "55.8%", "2,869"),
            ("Hybrid Ivy", "33%", "56.1%", "2,836"),
            ("Gun Ivy", "33%", "51.3%", "2,839"),
        ]:
            assert name in text
            assert share in text
            assert win in text
            assert n in text

    def test_links_every_build(self):
        html = chooser_page([card("Spirit Ivy"), card("Gun Ivy")])
        assert 'href="spirit-ivy/index.html"' in html
        assert 'href="gun-ivy/index.html"' in html

    def test_identical_columns_still_render_both_labels(self):
        same = card("Spirit Ivy", most_common=COMMON, defining=COMMON)
        texts = card_texts(
            chooser_page([same, card("Gun Ivy")]), ["Spirit Ivy", "Gun Ivy"]
        )
        assert "Most common" in texts["Spirit Ivy"]
        assert "Defining" in texts["Spirit Ivy"]
        assert texts["Spirit Ivy"].count("Extra Spirit") == 2

    def test_defining_items_show_both_rates(self):
        defining = column((7, "Healing Nova", 0.62, 0.08))
        text = visible_text(
            chooser_page([card("Spirit Ivy", defining=defining), card("Gun Ivy")])
        )
        assert "62%" in text
        assert "8%" in text

    def test_an_item_in_one_archetypes_column_is_marked(self):
        only_spirit = column((7, "Healing Nova", 0.62, 0.08))
        texts = card_texts(
            chooser_page([card("Spirit Ivy", defining=only_spirit), card("Gun Ivy")]),
            ["Spirit Ivy", "Gun Ivy"],
        )
        assert "only in this build" in texts["Spirit Ivy"]

    def test_an_item_in_two_archetypes_columns_is_not_marked(self):
        shared = column((7, "Healing Nova", 0.62, 0.08))
        text = visible_text(
            chooser_page(
                [card("Spirit Ivy", defining=shared), card("Gun Ivy", defining=shared)]
            )
        )
        # Most common is identical too, so nothing on the page is marked.
        assert "only in this build" not in text

    def test_marking_is_per_column(self):
        # Extra Spirit is in both Most common columns, so it isn't marked
        # there, but it is marked in the one Defining column that lists it.
        defining = column((1, "Extra Spirit", 0.97, 0.5))
        texts = card_texts(
            chooser_page([card("Spirit Ivy", defining=defining), card("Gun Ivy")]),
            ["Spirit Ivy", "Gun Ivy"],
        )
        assert texts["Spirit Ivy"].count("only in this build") == 1

    def test_no_imbue_line_when_every_archetype_agrees(self):
        # Ivy's case: two archetypes imbue the same pair.
        pair = (pages.Imbue(item="Mystic Reach", ability="Kudzu Bomb", share=0.99, n=900),)
        html = chooser_page(
            [card("Spirit Ivy", imbues=pair), card("Gun Ivy", imbues=pair)]
        )
        assert "Mystic Reach" not in visible_text(html)

    def test_imbue_line_when_the_targets_differ(self):
        kudzu = (pages.Imbue(item="Mystic Reach", ability="Kudzu Bomb", share=0.99, n=900),)
        drop = (pages.Imbue(item="Mystic Reach", ability="Air Drop", share=0.8, n=400),)
        texts = card_texts(
            chooser_page(
                [card("Spirit Ivy", imbues=kudzu), card("Gun Ivy", imbues=drop)]
            ),
            ["Spirit Ivy", "Gun Ivy"],
        )
        assert "Kudzu Bomb" in texts["Spirit Ivy"]
        assert "Air Drop" in texts["Gun Ivy"]

    def test_only_the_card_that_departs_shows_its_target(self):
        kudzu = (pages.Imbue(item="Mystic Reach", ability="Kudzu Bomb", share=0.99, n=900),)
        drop = (pages.Imbue(item="Mystic Reach", ability="Air Drop", share=0.8, n=400),)
        names = ["Spirit Ivy", "Hybrid Ivy", "Gun Ivy"]
        texts = card_texts(
            chooser_page(
                [
                    card("Spirit Ivy", imbues=kudzu),
                    card("Hybrid Ivy", imbues=kudzu),
                    card("Gun Ivy", imbues=drop),
                ]
            ),
            names,
        )
        assert "Mystic Reach" not in texts["Spirit Ivy"]
        assert "Mystic Reach" not in texts["Hybrid Ivy"]
        assert "Air Drop" in texts["Gun Ivy"]

    def test_an_item_only_one_archetype_imbues_is_no_disagreement(self):
        pair = (pages.Imbue(item="Mystic Reach", ability="Kudzu Bomb", share=0.99, n=900),)
        html = chooser_page([card("Spirit Ivy", imbues=pair), card("Gun Ivy")])
        assert "Mystic Reach" not in visible_text(html)

    def test_a_single_archetype_hero_gets_no_chooser(self):
        with pytest.raises(ValueError):
            chooser_page([card("Gun Wraith")])

    def test_states_absolute_win_rate_only(self):
        text = visible_text(chooser_page([card("Spirit Ivy"), card("Gun Ivy")]))
        assert "average" not in text.lower()
        assert not re.search(r"[+−]\d+(\.\d+)?\s*(%|pp)", text)


TOOLTIP = tooltips.ItemTooltip(
    sections=(
        tooltips.Section(
            kind="passive",
            prose='Adds <span class="highlight">Spirit Power</span>.',
            stats=(tooltips.Stat(label="Spirit Power", value="+10"),),
            conditions=(),
        ),
    ),
    headline="+10 Spirit Power",
)

KUDZU = pages.Imbue(
    item="Mystic Reach", ability="Kudzu Bomb", share=0.99, n=900, ability_id=11
)


def item(
    item_id: int,
    name: str,
    cost: int,
    phase: int,
    builds_into: str | None = None,
    imbue: pages.Imbue | None = None,
    tooltip: tooltips.ItemTooltip | None = None,
) -> pages.Item:
    return pages.Item(
        item_id=item_id,
        name=name,
        cost=cost,
        phase=phase,
        buyers=1234,
        players=1788,
        position=3,
        builds_into=builds_into,
        imbue=imbue,
        tooltip=tooltip,
    )


ITEMS = (
    item(1, "Extra Spirit", 800, 0, builds_into="Improved Spirit", tooltip=TOOLTIP),
    item(2, "Mystic Burst", 800, 0, tooltip=TOOLTIP),
    item(3, "Improved Spirit", 1600, 1),
    item(4, "Superior Duration", 6400, 2),
    item(5, "Mystic Reach", 1600, 2, imbue=KUDZU),
)
POINTS = (
    pages.AbilityPoint(ability_id=11, name="Kudzu Bomb", cost=None),
    pages.AbilityPoint(ability_id=12, name="Watcher's Covenant", cost=None),
    pages.AbilityPoint(ability_id=11, name="Kudzu Bomb", cost=1),
    pages.AbilityPoint(ability_id=11, name="Kudzu Bomb", cost=2),
    pages.AbilityPoint(ability_id=11, name="Kudzu Bomb", cost=5),
)


def facts(**overrides) -> pages.BuildFacts:
    base = dict(
        hero="Ivy",
        hero_id=20,
        archetype="Spirit Ivy",
        share=0.335,
        n=2869,
        items=ITEMS,
        phases=PHASES,
        abilities=POINTS,
        counter_picks=(
            pages.CounterPick(
                enemy="Lash", item="Counterspell", facing=0.16, baseline=0.085, n=412
            ),
        ),
        chooser_href="../index.html",
    )
    base.update(overrides)
    return pages.BuildFacts(**base)


def build_html(**overrides) -> str:
    return pages.build_page(
        facts(**overrides), bracket=ORACLE, window_start=WINDOW, root="../../"
    )


class TestBuildPage:
    def test_every_purchase_in_order_with_its_cost(self):
        text = visible_text(build_html())
        assert in_order(text, [i.name for i in ITEMS])
        for cost in ("800", "1,600", "6,400"):
            assert cost in text

    def test_each_purchase_sits_in_its_phase_band(self):
        text = visible_text(build_html())
        assert in_order(text, ["Lane", "Extra Spirit", "Mystic Burst", "Mid game"])
        assert in_order(text, ["Mid game", "Improved Spirit", "Late game"])
        assert in_order(text, ["Late game", "Superior Duration"])

    def test_an_empty_phase_has_no_band(self):
        assert "Very late" not in visible_text(build_html())

    def test_names_what_a_component_builds_into(self):
        assert "builds into Improved Spirit" in visible_text(build_html())

    def test_item_detail_states_buyers_of_players_and_position(self):
        text = visible_text(build_html())
        assert "69%" in text
        assert "1,234 of 1,788" in text
        assert "purchase 3" in text

    def test_every_item_row_is_a_disclosure(self):
        html = build_html()
        assert html.count("<details") == len(ITEMS)
        assert html.count('role="button"') == len(ITEMS)
        assert html.count('aria-expanded="false"') == len(ITEMS)

    def test_the_copy_block_lists_every_item_in_order(self):
        html = build_html()
        block = visible_text(html[html.index("build browser"):])
        assert in_order(block, [i.name for i in ITEMS])

    def test_the_ability_order_names_each_ability(self):
        text = visible_text(build_html())
        assert "Kudzu Bomb" in text
        assert "Watcher's Covenant" in text

    def test_states_no_clock(self):
        assert not re.search(r"\b\d{1,2}:\d{2}\b", visible_text(build_html()))

    def test_no_counter_picks_means_no_counter_pick_heading(self):
        assert "facing" in visible_text(build_html()).lower()
        assert "facing" not in visible_text(build_html(counter_picks=())).lower()

    def test_an_imbued_item_carries_its_target_on_the_row(self):
        html = build_html()
        # The badge's alt text is the closed row's only imbue signal.
        assert 'alt="imbued into Kudzu Bomb"' in html
        assert html.count('class="badge"') == 1

    def test_the_disclosure_states_the_target_and_its_evidence(self):
        text = visible_text(build_html())
        assert "Imbue into Kudzu Bomb" in text
        assert "99% of 900 imbues" in text

    def test_a_split_target_reads_as_a_preference(self):
        split = pages.Imbue(
            item="Mystic Reach", ability="Kudzu Bomb", share=0.35, n=1602,
            ability_id=11, split=True,
        )
        items = ITEMS[:-1] + (item(5, "Mystic Reach", 1600, 2, imbue=split),)
        text = visible_text(build_html(items=items))
        assert "not most players'" in text
        assert "35% of 1,602" in text

    def test_no_imbued_item_means_no_imbue_text(self):
        text = visible_text(build_html(items=ITEMS[:-1])).lower()
        assert "imbue" not in text

    def test_there_is_no_separate_imbue_section(self):
        assert "What to imbue" not in build_html()

    def test_the_disclosure_carries_the_games_tooltip(self):
        html = build_html()
        assert 'Adds <span class="highlight">Spirit Power</span>.' in html
        text = visible_text(html)
        assert "Passive" in text
        assert "Spirit Power +10" in text

    def test_the_headline_stat_fills_the_subline_only_without_builds_into(self):
        html = build_html()
        # Mystic Burst has no "builds into", so its row shows the stat;
        # Extra Spirit builds into something, so its row shows that instead.
        assert html.count('class="sub stat"') == 1
        assert "builds into Improved Spirit" in visible_text(html)

    def test_the_page_has_one_tooltip(self):
        html = build_html()
        assert html.count('role="tooltip"') == 1
        assert html.count('class="tiphead"') == len(ITEMS)

    def test_the_ability_track_numbers_points_and_marks_costs(self):
        html = build_html()
        track = visible_text(html[html.index("Ability order"):])
        # Point numbers across the top, then AP cost on each upgrade marker;
        # an unlock has no number, as in the game's build browser.
        assert in_order(track, ["1", "2", "3", "4", "5", "Kudzu Bomb"])
        assert html.count('class="on unlock"') == 2

    def test_counter_picks_state_both_rates_and_the_count(self):
        text = visible_text(build_html())
        assert "16%" in text and "8.5%" in text and "412" in text

    def test_states_the_bracket_and_the_window(self):
        text = visible_text(build_html())
        assert "Oracle" in text
        assert "22 August 2026" in text

    def test_links_the_methodology_page(self):
        assert 'href="../../methodology.html"' in build_html()

    def test_a_split_hero_links_back_to_its_chooser(self):
        assert 'href="../index.html"' in build_html()

    def test_a_single_archetype_build_states_no_share(self):
        assert "100%" not in visible_text(build_html(chooser_href=None, share=1.0))

    def test_states_no_win_rate(self):
        # The chooser spent it; relative framings were dropped in #21.
        text = visible_text(build_html()).lower()
        assert "average" not in text
        assert "win rate" not in text


class TestHome:
    def test_lists_every_hero_with_a_link(self):
        heroes = [
            pages.HeroLink(hero="Ivy", hero_id=20, href="ivy/index.html", builds=3),
            pages.HeroLink(hero="Wraith", hero_id=7, href="wraith/index.html", builds=1),
        ]
        html = pages.home(heroes=heroes, bracket=ORACLE, window_start=WINDOW)
        assert 'href="ivy/index.html"' in html
        assert 'href="wraith/index.html"' in html
        text = visible_text(html)
        assert "Ivy" in text and "Wraith" in text

    def test_links_the_methodology_page(self):
        html = pages.home(heroes=[], bracket=ORACLE, window_start=WINDOW)
        assert 'href="methodology.html"' in html
