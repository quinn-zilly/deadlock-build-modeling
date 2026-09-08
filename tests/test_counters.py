"""Items bought because of who is on the other team.

The four matchups a player named all replicate, at r=0.91 across splits. That
number is the reason this module exists at all: the discarded counter/synergy
work measured r=0.05 for the same kind of claim, which is noise, and shipping
it anyway is the mistake this project is built to avoid repeating.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from deadlock import assets, counters, splits
from deadlock.state import Recommendation

PARQUET = Path("data/processed/purchases.parquet")


def matches(n_matches: int = 400) -> pd.DataFrame:
    """Two teams; one player always buys item 1 when facing hero 99."""
    rows = []
    for m in range(n_matches):
        enemy_hero = 99 if m % 2 == 0 else 50
        rows.append(
            {
                "match_id": m,
                "player_slot": 1,
                "hero_id": 7,
                "team": "Team0",
                "item_id": 1 if enemy_hero == 99 else 2,
            }
        )
        rows.append(
            {
                "match_id": m,
                "player_slot": 2,
                "hero_id": enemy_hero,
                "team": "Team1",
                "item_id": 3,
            }
        )
    return pd.DataFrame(rows)


class TestEnemyRosters:
    def test_only_the_other_team_counts(self):
        rosters = counters.enemy_rosters(matches(4))
        mine = rosters[rosters["hero_id"] == 7]
        assert set(mine["enemy_hero_id"]) <= {99, 50}
        # A player never faces themselves.
        assert not (rosters["hero_id"] == rosters["enemy_hero_id"]).any()


class TestLifts:
    def test_a_real_matchup_effect_is_found(self):
        lifts = counters.counter_lifts(matches(), min_facing=50)
        found = lifts[(lifts["item_id"] == 1) & (lifts["enemy_hero_id"] == 99)]
        assert len(found) == 1
        assert found.iloc[0]["lift"] > 0.3

    def test_thin_matchups_are_dropped(self):
        lifts = counters.counter_lifts(matches(20), min_facing=500)
        assert lifts.empty

    def test_negative_lifts_are_not_counters(self):
        """An item bought *less* against a hero is not a counter-pick.

        Reporting one as advice tells a player to buy something the population
        buys less of in exactly that matchup.
        """
        lifts = counters.counter_lifts(matches(), min_facing=50)
        assert (lifts["lift"] > 0).all()


class TestAnnotation:
    def test_annotation_does_not_reorder(self):
        """The probability stays the model's; the matchup is a separate claim."""
        lifts = counters.counter_lifts(matches(), min_facing=50)
        recommendations = [
            Recommendation(1, "Countered", 0.1, 500, "L1", 800),
            Recommendation(2, "Plain", 0.9, 500, "L1", 800),
        ]
        annotated = counters.annotate(recommendations, (99,), lifts)
        assert [rec.item_id for rec, _ in annotated] == [1, 2]
        assert annotated[0][1] is not None
        assert annotated[1][1] is None

    def test_no_enemies_means_no_annotations(self):
        lifts = counters.counter_lifts(matches(), min_facing=50)
        recommendations = [Recommendation(1, "Countered", 0.1, 500, "L1", 800)]
        assert counters.annotate(recommendations, (), lifts)[0][1] is None

    def test_describe_names_the_matchup(self):
        counter = counters.Counter(1, 99, 0.16, 0.085, 76718)
        text = counter.describe({1: "Counterspell"}, {99: "Lash"})
        assert "Counterspell" in text and "Lash" in text and "+7.5pp" in text


@pytest.mark.data
@pytest.mark.skipif(not PARQUET.exists(), reason="needs data/processed/*.parquet")
class TestAgainstRealData:
    """Each case is a matchup a Deadlock player named before it was measured."""

    @staticmethod
    def _frame(n_matches: int = 25000) -> pd.DataFrame:
        frame = pd.read_parquet(
            PARQUET,
            columns=["match_id", "player_slot", "hero_id", "team", "item_id"],
        )
        keep = frame["match_id"].drop_duplicates().head(n_matches)
        return frame[frame["match_id"].isin(keep)]

    @pytest.mark.parametrize(
        "item,hero",
        [
            ("Counterspell", "Lash"),
            ("Knockdown", "Vindicta"),
            ("Slowing Hex", "Apollo"),
            ("Healbane", "Victor"),
        ],
    )
    def test_the_named_counter_picks_are_real(self, item, hero):
        lifts = counters.counter_lifts(self._frame())
        found = lifts[
            (lifts["item_id"] == assets.resolve_item(item))
            & (lifts["enemy_hero_id"] == assets.resolve_hero(hero))
        ]
        assert len(found) == 1, f"{item} vs {hero} was not detected"
        assert found.iloc[0]["lift"] >= 0.04

    def test_lifts_replicate_across_a_split(self):
        """r=0.05 is what the discarded counter work measured. This is 0.91."""
        frame = self._frame(12000)
        train, test = splits.split_by_match(frame)
        assert counters.replicates(train, test, min_facing=200) > 0.5


class TestForBuild:
    """The counter-picks a finished build carries, with no enemy team named.

    `counters_for` answers "given these five enemies, which of my items are
    matchup picks". The site shows a build before a match exists, so the useful
    question is the other way round: for the items this build buys, which
    heroes make them a counter-pick.
    """

    @staticmethod
    def lifts() -> pd.DataFrame:
        return pd.DataFrame(
            [
                {"item_id": 1, "enemy_hero_id": 99, "facing_rate": 0.40,
                 "baseline_rate": 0.20, "lift": 0.20, "n_facing": 5000},
                {"item_id": 1, "enemy_hero_id": 50, "facing_rate": 0.26,
                 "baseline_rate": 0.20, "lift": 0.06, "n_facing": 5000},
                {"item_id": 2, "enemy_hero_id": 99, "facing_rate": 0.31,
                 "baseline_rate": 0.30, "lift": 0.01, "n_facing": 5000},
                {"item_id": 7, "enemy_hero_id": 99, "facing_rate": 0.50,
                 "baseline_rate": 0.20, "lift": 0.30, "n_facing": 5000},
            ]
        )

    def test_reports_only_the_items_the_build_buys(self):
        found = counters.for_build(self.lifts(), [1, 2])
        assert {c.item_id for c in found} == {1}

    def test_strongest_matchup_first(self):
        found = counters.for_build(self.lifts(), [1, 2, 7])
        assert [c.item_id for c in found] == [7, 1]

    def test_one_matchup_per_item(self):
        """Item 1 answers two heroes; only its strongest is worth the line."""
        found = counters.for_build(self.lifts(), [1])
        assert [(c.item_id, c.enemy_hero_id) for c in found] == [(1, 99)]

    def test_a_weak_lift_is_not_a_counter_pick(self):
        """Item 2 moves one point facing hero 99, which is not a matchup."""
        assert not any(c.item_id == 2 for c in counters.for_build(self.lifts(), [2]))

    def test_a_thin_matchup_is_dropped(self):
        thin = self.lifts().assign(n_facing=10)
        assert counters.for_build(thin, [1, 7]) == []

    def test_a_build_with_no_matchup_items_reports_nothing(self):
        assert counters.for_build(self.lifts(), [42]) == []

    def test_an_empty_lift_table_is_not_an_error(self):
        assert counters.for_build(pd.DataFrame(), [1]) == []

    def test_limit_caps_the_list(self):
        assert len(counters.for_build(self.lifts(), [1, 7], limit=1)) == 1
