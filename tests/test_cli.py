"""The delivery surface: name resolution, clock parsing, archetype choice.

These are the parts a player touches directly. Nobody types 4008176313 or
thinks in seconds since match start, so a wrong answer here makes the tool
unusable regardless of how good the model underneath is.
"""

from __future__ import annotations

import pandas as pd
import pytest

from deadlock import archetype, assets, cli, sequence


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


class TestPointsWithoutADeclaredArchetype:
    """`--points` must not be silently ignored mid-match.

    Ability advice needs an archetype, and a player mid-match often has not
    declared one -- the tool infers it from what they have bought. Dropping
    the advice in that case is the exact situation `--points` exists for.
    """

    class Args:
        def __init__(self, **kwargs):
            defaults = dict(
                hero="Holliday", archetype=None, owned="", time="5:00", souls=0,
                enemies="", top=3, points="Powder Keg", min_share=0.25,
                refit=False, badge=sequence.DEFAULT_TARGET_BADGE,
            )
            self.__dict__.update({**defaults, **kwargs})

    def test_inferred_archetype_still_gets_ability_advice(self, capsys):
        cli.cmd_next(self.Args())
        assert "next ability point" in capsys.readouterr().out

    def test_a_declared_archetype_still_gets_it(self, capsys):
        _, meta = archetype.load()
        hero_id = assets.resolve_hero("Holliday")
        name = meta["heroes"][str(hero_id)]["archetypes"][0]["name"]
        cli.cmd_next(self.Args(archetype=name))
        assert "next ability point" in capsys.readouterr().out


class TestImbueTargets:
    """`deadlock build` has to say what to do with an imbueable item.

    The exported JSON has carried the target since it was built, but the
    command line printed nothing about it -- and the command line is what a
    player reads before a match.
    """

    def test_no_cell_means_no_targets(self):
        """No purchase table is item-only advice, not a crash."""
        assert cli.load_imbue_targets(None, [1, 2, 3]) == []

    def test_a_build_with_no_imbueable_item_prints_nothing(self):
        """Guarded: without the table this passes through the absent-file
        branch instead of the filter it is here to cover, and `data/` is
        gitignored, so on a fresh clone it would pass having tested nothing."""
        if not cli.IMBUES_PATH.exists():
            pytest.skip("requires the imbue table")
        cell = pd.DataFrame({"match_id": [1], "player_slot": [0]})
        monster_rounds = assets.resolve_item("Monster Rounds")
        assert cli.load_imbue_targets(cell, [monster_rounds]) == []

    def test_a_real_cell_names_an_ability(self):
        if not cli.IMBUES_PATH.exists() or not cli.PURCHASES.exists():
            pytest.skip("requires the imbue and purchase tables")
        imbues = pd.read_parquet(cli.IMBUES_PATH)
        item_id = int(imbues["item_id"].value_counts().idxmax())
        cell = imbues[["match_id", "player_slot"]].drop_duplicates().head(5000)
        got = cli.load_imbue_targets(cell, [item_id])
        assert len(got) == 1
        assert got[0].ability_id is not None and got[0].ability_id > 0
        assert got[0].ability_name and not got[0].ability_name.isdigit()
        assert 0.0 < got[0].share <= 1.0


class TestBadgeArgument:
    """Which bracket the advice imitates, and how a player asks for another.

    The default is the point of the whole feature: without it the tool serves
    the median player, which is not what anyone opens a build tool for.
    """

    @staticmethod
    def parsed(argv):
        return cli.build_parser().parse_args(argv)

    def test_build_defaults_to_the_high_badge_bracket(self):
        args = self.parsed(["build", "--hero", "Ivy"])
        assert cli.target_badge(args) == sequence.DEFAULT_TARGET_BADGE

    def test_a_player_can_ask_for_their_own_bracket(self):
        args = self.parsed(["build", "--hero", "Ivy", "--badge", "55"])
        assert cli.target_badge(args) == 55.0

    def test_all_asks_for_the_whole_population(self):
        args = self.parsed(["build", "--hero", "Ivy", "--badge", "all"])
        assert cli.target_badge(args) is None

    def test_a_nonsense_bracket_is_refused(self):
        with pytest.raises(SystemExit):
            self.parsed(["build", "--hero", "Ivy", "--badge", "gold"])

    @pytest.mark.parametrize("command", ["build", "next", "watch", "why"])
    def test_every_advice_command_takes_the_flag(self, command):
        argv = [command, "--hero", "Ivy", "--badge", "70"]
        if command == "why":
            argv += ["--item", "Ricochet"]
        assert cli.target_badge(self.parsed(argv)) == 70.0


class TestModelCachePaths:
    """One cached file per bracket, so two brackets cannot share a cache."""

    def test_each_bracket_gets_its_own_file(self):
        assert cli.model_path(80.0) != cli.model_path(55.0)

    def test_the_whole_population_has_its_own_file(self):
        assert cli.model_path(None) != cli.model_path(80.0)

    def test_the_default_bracket_keeps_the_shipped_name(self):
        assert cli.model_path(sequence.DEFAULT_TARGET_BADGE) == cli.MODEL_PATH

    def test_the_ability_model_is_cached_per_bracket_too(self):
        assert cli.ability_model_path(80.0) != cli.ability_model_path(55.0)
        assert cli.ability_model_path(sequence.DEFAULT_TARGET_BADGE) == cli.ABILITY_MODEL_PATH
