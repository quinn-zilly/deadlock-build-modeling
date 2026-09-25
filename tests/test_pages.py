"""The methodology page: what it claims, checked at the one seam.

`pages.methodology` takes the facts the page states and returns HTML, so these
tests call it with known inputs and assert on the returned string. They check
the facts, not the markup: tag structure and wording are free to change.
"""

from __future__ import annotations

import datetime as dt
import inspect
import re
from pathlib import Path

import pandas as pd
import pytest

from deadlock import assets, pages, sequence

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
    html = re.sub(r"<style.*?</style>", " ", html, flags=re.S)
    html = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", html)


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
