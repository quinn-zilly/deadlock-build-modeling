"""The delivery surface: name resolution, clock parsing, archetype choice.

These are the parts a player touches directly. Nobody types 4008176313 or
thinks in seconds since match start, so a wrong answer here makes the tool
unusable regardless of how good the model underneath is.
"""

from __future__ import annotations

import pytest

from deadlock import archetype, assets, cli


class TestParseTime:
    @pytest.mark.parametrize(
        "text,seconds", [("8:30", 510), ("0:00", 0), ("12:05", 725), ("510", 510)]
    )
    def test_reads_a_clock_or_a_count(self, text, seconds):
        assert cli.parse_time(text) == seconds

    def test_tolerates_surrounding_space(self):
        assert cli.parse_time("  8:30 ") == 510


class TestResolveHero:
    def test_exact_and_case_insensitive(self):
        assert assets.resolve_hero("Wraith") == assets.resolve_hero("wraith")

    def test_unique_prefix(self):
        assert assets.resolve_hero("Wrai") == assets.resolve_hero("Wraith")

    def test_unknown_name_suggests_alternatives(self):
        with pytest.raises(KeyError, match="no hero matching"):
            assets.resolve_hero("Zzzzz")

    def test_only_playable_heroes_resolve(self):
        playable = set(assets.playable_heroes())
        assert assets.resolve_hero("Ivy") in playable


class TestResolveItem:
    def test_resolves_a_full_name(self):
        item_id = assets.resolve_item("Quicksilver Reload")
        assert assets.shopable_items()[item_id].name == "Quicksilver Reload"

    def test_ambiguous_query_lists_the_candidates(self):
        with pytest.raises(KeyError, match="matches several"):
            assets.resolve_item("Spirit")

    def test_unknown_item_is_reported(self):
        with pytest.raises(KeyError, match="no item matching"):
            assets.resolve_item("Zzzzz")


class TestSplit:
    def test_splits_and_trims_a_comma_list(self):
        assert cli._split(" Monster Rounds , Extra Spirit ") == [
            "Monster Rounds",
            "Extra Spirit",
        ]

    def test_empty_input_is_no_items(self):
        assert cli._split("") == []
        assert cli._split(None) == []


class TestResolveArchetype:
    META = {
        "heroes": {
            "7": {
                "archetypes": [
                    {"archetype_id": 0, "name": "Gun Wraith"},
                    {"archetype_id": 1, "name": "Spirit Wraith"},
                ]
            },
            "9": {"archetypes": [{"archetype_id": 0, "name": "Haze"}]},
        }
    }

    def test_matches_by_prefix(self):
        assert cli.resolve_archetype(7, "gun", self.META) == (0, "Gun Wraith")

    def test_matches_by_substring(self):
        assert cli.resolve_archetype(7, "spirit", self.META) == (1, "Spirit Wraith")

    def test_a_single_archetype_needs_no_declaration(self):
        assert cli.resolve_archetype(9, None, self.META) == (0, "Haze")

    def test_multiple_archetypes_require_a_choice(self):
        """Silently picking one would answer a question the player did not ask."""
        with pytest.raises(SystemExit, match="pick one"):
            cli.resolve_archetype(7, None, self.META)

    def test_an_unknown_archetype_lists_the_options(self):
        with pytest.raises(SystemExit, match="Gun Wraith"):
            cli.resolve_archetype(7, "melee", self.META)


class TestArchetypePosterior:
    META = {
        "heroes": {
            "20": {
                "archetypes": [
                    {
                        "archetype_id": 0,
                        "name": "Gun Ivy",
                        "share": 0.6,
                        "centroid": {"gun": 1.0, "spirit": 0.0},
                    },
                    {
                        "archetype_id": 1,
                        "name": "Spirit Ivy",
                        "share": 0.4,
                        "centroid": {"gun": 0.0, "spirit": 1.0},
                    },
                ]
            },
            "9": {"archetypes": [{"archetype_id": 0, "name": "Haze", "share": 1.0}]},
        }
    }

    def test_no_items_gives_the_population_share(self):
        """Before any evidence the honest prior is how often people play it."""
        posterior = archetype.archetype_posterior([], 20, self.META)
        assert posterior[0] == pytest.approx(0.6)
        assert posterior[1] == pytest.approx(0.4)

    def test_a_single_archetype_hero_is_certain(self):
        assert archetype.archetype_posterior([], 9, self.META) == {0: 1.0}

    def test_an_unknown_hero_does_not_raise(self):
        assert archetype.archetype_posterior([], 12345, self.META) == {0: 1.0}

    def test_posterior_sums_to_one(self):
        items = list(assets.shopable_items())[:4]
        posterior = archetype.archetype_posterior(items, 20, self.META)
        assert sum(posterior.values()) == pytest.approx(1.0)
        assert all(0.0 <= p <= 1.0 for p in posterior.values())


class TestPartialFamilyShares:
    def test_an_empty_build_has_no_shares(self):
        shares = archetype.partial_family_shares([])
        assert shares.sum() == 0.0

    def test_shares_sum_to_one_for_a_real_build(self):
        items = list(assets.shopable_items())[:5]
        shares = archetype.partial_family_shares(items)
        assert shares.sum() == pytest.approx(1.0)


class TestThinEvidence:
    def test_a_thin_recommendation_says_so(self):
        """A probability from 2 observations is not the same claim as one from
        1,635, and printing them identically invites misplaced confidence."""
        from deadlock.state import Recommendation

        thin = Recommendation(1, "Rare", 0.08, 2, "L0", 1600)
        solid = Recommendation(2, "Common", 0.37, 1635, "L2", 3200)
        assert thin.thin and "[thin]" in str(thin)
        assert not solid.thin and "[thin]" not in str(solid)


class TestAbilityPointArguments:
    """The guardrails on `--points`, which the model cannot enforce itself."""

    class Args:
        def __init__(self, points, time="5:00", refit=False):
            self.points = points
            self.time = time
            self.refit = refit

    def hero(self) -> int:
        return assets.resolve_hero("Holliday")

    def test_no_points_prints_nothing(self, capsys):
        cli._print_ability_points(self.hero(), 0, self.Args(""))
        assert capsys.readouterr().out == ""

    def test_an_unknown_ability_names_the_real_ones(self):
        with pytest.raises(SystemExit, match="Powder Keg"):
            cli._print_ability_points(self.hero(), 0, self.Args("Fireball"))

    def test_a_fifth_point_in_one_ability_is_refused(self):
        """Four levels is the cap, and a fifth point is not a legal build."""
        with pytest.raises(SystemExit, match="more than four"):
            cli._print_ability_points(
                self.hero(), 0, self.Args("Powder Keg," * 5)
            )
