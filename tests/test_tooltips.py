"""Item tooltips: the game's own tooltip text and stats, made safe to publish.

Fixtures are cut down from real /v1/assets/items entries, so the tests pin the
field shapes the site depends on without a network fetch.
"""

from __future__ import annotations

from deadlock import tooltips

TOXIC_BULLETS = {
    "id": 1,
    "name": "Toxic Bullets",
    "tooltip_sections": [
        {
            "section_attributes": [
                {
                    "loc_string": 'Your bullets build up a <span class="highlight">Bleed</span>.',
                    "properties": ["DotDuration", "BuildUpPerShot"],
                    "important_properties": [
                        "DotHealthPercent",
                        "HealAmpReceivePenaltyPercent",
                    ],
                }
            ]
        }
    ],
    "properties": {
        "DotHealthPercent": {"value": "1.9", "label": "Bleed Damage", "postfix": "%/sec"},
        "HealAmpReceivePenaltyPercent": {
            "value": "-35", "prefix": "", "label": "Healing Reduction", "postfix": "%",
        },
        "DotDuration": {"value": "4", "label": "Duration", "postfix": "s"},
        "BuildUpPerShot": {"value": "1.28", "label": "Buildup Per Shot", "postfix": "%"},
        "AbilityCooldown": {"value": "0", "label": "Cooldown", "postfix": "s"},
    },
}

EXTENDED_MAGAZINE = {
    "id": 2,
    "name": "Extended Magazine",
    "description": {},
    "tooltip_sections": [
        {
            "section_type": "innate",
            "section_attributes": [
                {
                    "properties": ["BaseAttackDamagePercent"],
                    "elevated_properties": ["BonusClipSizePercent"],
                }
            ],
        }
    ],
    "properties": {
        "BonusClipSizePercent": {
            "value": "30", "prefix": "{s:sign}", "label": "Max Ammo", "postfix": "%",
        },
        "BaseAttackDamagePercent": {
            "value": "8", "prefix": "{s:sign}", "label": "Weapon Damage", "postfix": "%",
        },
    },
}

CURSED_RELIC = {
    "id": 3,
    "name": "Cursed Relic",
    "tooltip_sections": [
        {
            "section_type": "active",
            "section_attributes": [
                {
                    "loc_string": "Curses an enemy.<br><br>Your own damage is reduced.",
                    "properties": ["AbilityCooldown"],
                    "important_properties": ["StatusEffectEMP"],
                    "important_properties_with_icon": [
                        {"name": "StatusEffectEMP", "icon": "x.svg", "localized_name": "Silenced"},
                        {"name": "StatusEffectDisarmed", "icon": "y.svg", "localized_name": "Disarm"},
                    ],
                }
            ],
        }
    ],
    "properties": {
        "AbilityCooldown": {"value": "90", "label": "Cooldown", "postfix": "s"},
        "StatusEffectEMP": {"value": "", "label": ""},
    },
}

PROSE_ONLY = {
    "id": 4,
    "name": "Refresher",
    "tooltip_sections": [
        {
            "section_type": "active",
            "section_attributes": [
                {"loc_string": "Resets the cooldowns of your abilities. Not items."}
            ],
        }
    ],
    "properties": {},
}


class TestStats:
    def test_ranked_stats_come_first(self):
        tip = tooltips.item_tooltip(TOXIC_BULLETS)
        labels = [s.label for s in tip.sections[0].stats]
        assert labels[:2] == ["Bleed Damage", "Healing Reduction"]

    def test_values_carry_their_units_and_sign(self):
        tip = tooltips.item_tooltip(EXTENDED_MAGAZINE)
        values = {s.label: s.value for s in tip.sections[0].stats}
        assert values == {"Max Ammo": "+30%", "Weapon Damage": "+8%"}

    def test_a_negative_value_keeps_its_own_sign(self):
        tip = tooltips.item_tooltip(TOXIC_BULLETS)
        values = {s.label: s.value for s in tip.sections[0].stats}
        assert values["Healing Reduction"] == "-35%"
        assert values["Bleed Damage"] == "1.9%/sec"

    def test_only_the_sections_own_properties_are_listed(self):
        # AbilityCooldown is in the item's properties at 0 but not in the
        # section: a placeholder the game doesn't show.
        tip = tooltips.item_tooltip(TOXIC_BULLETS)
        assert "Cooldown" not in [s.label for s in tip.sections[0].stats]

    def test_named_conditions_are_listed_by_their_names(self):
        tip = tooltips.item_tooltip(CURSED_RELIC)
        assert tip.sections[0].conditions == ("Silenced", "Disarm")

    def test_section_kind_is_kept(self):
        assert tooltips.item_tooltip(CURSED_RELIC).sections[0].kind == "active"


class TestHeadline:
    def test_elevated_stat_wins(self):
        assert tooltips.item_tooltip(EXTENDED_MAGAZINE).headline == "+30% Max Ammo"

    def test_important_stats_when_nothing_is_elevated(self):
        assert tooltips.item_tooltip(TOXIC_BULLETS).headline == "1.9%/sec Bleed Damage"

    def test_named_conditions_before_plain_important_stats(self):
        assert tooltips.item_tooltip(CURSED_RELIC).headline == "Silenced"

    def test_what_the_item_does_beats_its_shop_stat(self):
        entry = {
            "tooltip_sections": [
                {
                    "section_type": "innate",
                    "section_attributes": [{"elevated_properties": ["Spirit"]}],
                },
                {
                    "section_type": "passive",
                    "section_attributes": [{"important_properties": ["Heal"]}],
                },
            ],
            "properties": {
                "Spirit": {"value": "7", "prefix": "{s:sign}", "label": "Spirit Power"},
                "Heal": {"value": "-35", "label": "Healing Reduction", "postfix": "%"},
            },
        }
        assert tooltips.item_tooltip(entry).headline == "-35% Healing Reduction"

    def test_a_unit_already_on_the_value_is_not_doubled(self):
        entry = {
            "tooltip_sections": [
                {"section_attributes": [{"properties": ["Range"]}]}
            ],
            "properties": {
                "Range": {"value": "20m", "label": "Cast Range", "postfix": "m"},
            },
        }
        stat = tooltips.item_tooltip(entry).sections[0].stats[0]
        assert stat.value == "20m"

    def test_falls_back_to_the_first_sentence(self):
        assert (
            tooltips.item_tooltip(PROSE_ONLY).headline
            == "Resets the cooldowns of your abilities."
        )


class TestSanitize:
    def test_keeps_the_games_emphasis(self):
        out = tooltips.sanitize('A <span class="highlight">Bleed</span>.<br>Next')
        assert out == 'A <span class="highlight">Bleed</span>.<br>Next'

    def test_drops_scripts_and_handlers(self):
        out = tooltips.sanitize(
            '<span onclick="x()">hi</span><script>alert(1)</script>'
            '<img src="https://evil.example/a.png" onerror="x()">'
        )
        assert "onclick" not in out
        assert "script" not in out
        assert "alert" not in out
        assert "onerror" not in out
        assert "evil.example" not in out
        assert "hi" in out

    def test_keeps_inline_svg_glyphs(self):
        out = tooltips.sanitize(
            '<svg width="128" viewBox="0 0 128 128" fill="white" '
            'xmlns="http://www.w3.org/2000/svg"><path d="M1 2Z" fill="white"/></svg>'
        )
        assert out.startswith("<svg")
        assert 'd="M1 2Z"' in out

    def test_keeps_asset_icons_only_from_the_asset_host(self):
        out = tooltips.sanitize(
            '<img src="https://assets-bucket.deadlock-api.com/icons/a.svg" alt="">'
        )
        assert "assets-bucket.deadlock-api.com" in out

    def test_drops_style_that_loads_anything(self):
        out = tooltips.sanitize('<span style="background:url(x)">a</span>')
        assert "url" not in out

    def test_escapes_text(self):
        assert tooltips.sanitize("a < b & c") == "a &lt; b &amp; c"

    def test_prose_is_sanitized_in_the_tooltip(self):
        entry = dict(PROSE_ONLY)
        entry["tooltip_sections"] = [
            {"section_attributes": [{"loc_string": "Hi<script>x()</script>"}]}
        ]
        assert "script" not in tooltips.item_tooltip(entry).sections[0].prose
