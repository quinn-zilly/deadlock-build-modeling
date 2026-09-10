# Item icons, hero portraits, and where tooltip text comes from

Research for issue #19 (part of the #15 map), carried forward into #20.
Established against the community assets API's live responses and the 75
generated builds, not against any wiki page.

**Bottom line.** Nothing here needs scraping. The assets API the model already
joins against by id carries **every icon, every hero portrait, and the tooltip
prose itself** as fields on the same records. Using it instead of
[deadlock.wiki](https://deadlock.wiki/) is not merely more convenient: the wiki
is keyed by item *name*, and this project keys everything by *id* — 57 of the
138 items appearing in real builds exceed int32, and names change across
patches. A name-matched icon can drift from the id the recommendation was
computed on; a field on the asset record cannot.

Three separate findings, each with a caveat that changes the spec:

1. **Icons: use `shop_image`, not `image`.** `image` is missing for six items
   real builds buy; `shop_image` covers all 138.
2. **Tooltips: `description.desc` is real prose, but only for 108 of 138.** The
   other 30 are stat-only passives that need a fallback built from
   `properties`. The prose carries embedded HTML and inline SVG.
   **Corrected by [#23](touch-item-disclosure.md) on two points:** `desc` is the
   *weaker* prose field — `tooltip_sections[].loc_string` covers more items, and
   13 items have prose only there — and the `properties` fallback is a 4-item
   edge case, not a 30-item path, once the game's own stat-ranking fields are
   read. See §7 there.
3. **"Builds into X" is derivable but ambiguous in the catalogue.** Resolving it
   against the build's own later purchases fixes 96.6% of cases.

## 1. Icons

Every upgrade record carries two image fields:

```json
{
  "id": 1548066885,
  "name": "Extended Magazine",
  "class_name": "upgrade_clip_size",
  "image":      ".../images/upgrades/mods_weapon/clip_size.png",
  "shop_image": ".../images/upgrades/mods_weapon/clip_size.png"
}
```

Coverage differs, and the difference matters:

| field | upgrades covered (of 251) | items in real builds covered (of 138) |
|---|---|---|
| `image` | 232 | 132 |
| `shop_image` | 251 | **138** |

The six build items with no `image` are Cultist Sacrifice, Stalker, Blood
Tribute, Spellslinger, Express Shot and Transcendent Cooldown. **So
`shop_image` is the source, with `image` as fallback** — the reverse of the
obvious choice.

`scripts/pull_assets.py` downloads them to `data/assets/`, **named by item id**
rather than name, for the int32 and patch-stability reasons above. Measured:
246 item icons and 38 hero portraits, with every one of the 138 build items
covered. Two upgrades fail to download (Toughness, Endless Magazine) because
their URL is a literal `panorama:""` placeholder; both are `disabled` and
`shopable: false` and appear in zero builds.

## 2. Hero portraits

All 38 selectable heroes carry a full set under `images`:

| key | what it is |
|---|---|
| `icon_hero_card` | framed bust — **what the game's own build browser uses** |
| `icon_image_small` | small circular icon, for a hero picker |
| `top_bar_vertical_image` | tall in-match top-bar crop |
| `minimap_image` | minimap dot |
| `background_image` | full-bleed hero art |
| `name_image` | the hero's name as an SVG wordmark |

`icon_hero_card` is the portrait for the build page masthead, because the site
is read *beside* the build browser and should show the same crop the player is
looking at there. `name_image` is worth knowing about: the hero's name set as
Valve's own lettering, which beats setting it in a webfont.

Every image also exists as `_webp`.

## 3. Tooltip text

**`description.desc` is the item's real in-game description**, present for 152
of 251 upgrades and **108 of the 138 items real builds buy**. Twelve items also
carry `description.active` and eight `description.passive`.

The 30 build items with no prose are pure-stat passives — Extended Magazine,
Titanic Magazine, Fleetfoot, High-Velocity Rounds, Extra Regen, Sprint Boots
and so on. For these the tooltip must be built from `properties`, which is
where the labelled numbers live:

```json
"BonusClipSizePercent":  { "value": "30", "label": "Max Ammo",       "postfix": "%" },
"BaseAttackDamagePercent": { "value": "8", "label": "Weapon Damage", "postfix": "%" }
```

So the tooltip is **prose when it exists, labelled stats always** — and the
stats are what the 30 stat-only items show on their own.

### The prose is HTML, and it is safe to render under an allowlist

`desc` is not plain text. Measured across every upgrade:

| tag | count | what it is |
|---|---|---|
| `span` | 343 | `class="highlight"` (307) and `class="diminish"` (22) — styling hooks |
| `path` | 173 | inside the SVGs |
| `br` | 55 | line breaks |
| `svg` | 55 | inline damage-type glyphs, self-contained, `fill="white"` |
| `img` | 7 | absolute CDN URLs for resist/melee icons |

The complete attribute set is `span@class`, `span@style`, `path@d`,
`path@fill`, `path@fill-rule`, `path@clip-rule`, `svg@width|height|viewBox|fill|xmlns`,
`img@src|class|alt`, `g@clip-path`, `clipPath@id`, `rect@width|height|fill|transform`.

**There are zero `<script>` tags and zero `on*` event handlers in the entire
catalogue.** That is a measurement of today's data, not a guarantee about
tomorrow's, so the renderer allowlists that tag and attribute set rather than
injecting the string raw — this is third-party content reaching a published
page.

Two rendering notes:

- The inline SVGs are white-filled glyphs. Set `fill: currentColor` so they
  take the palette instead of punching white holes in a dark page.
- `span.highlight` is the game's own emphasis (brass); `span.diminish` is its
  de-emphasis (muted). The seven `<img>` icons are absolute CDN URLs, so either
  allow that host or pull those few files local like the rest.

## 4. "Builds into X" replaces "absorbed"

`component_items` names an item's prerequisites by `class_name`; reversing it
gives the parents an item builds into. 46 upgrades build into something, and 44
of the 138 build items have a parent.

**The catalogue answer is often ambiguous.** Grit builds into four different
items (Weapon Shielding, Spirit Shielding, Guardian Ward, Reactive Barrier);
Extended Magazine into two. So "builds into X" cannot be answered from the
catalogue alone.

**It can be answered from the build.** Resolving against parents *the build
itself buys later* is nearly always unique. Measured over all 441 sold
purchases across the 75 builds:

| outcome | count | share |
|---|---|---|
| exactly one later parent | 426 | **96.6%** |
| two or more later parents | 15 | 3.4% |
| **no later parent** | **0** | **0%** |

No sold purchase is left unexplained, which is what makes the phrasing safe:
every faded item on the page can name the thing it became. The 15 ambiguous
cases are a handful of repeated pairs — Rapid Rounds into Burst Fire or Swift
Striker, High-Velocity Rounds into Sharpshooter or Express Shot, Sprint Boots
into Trophy Collector or Veil Walker. Naming the earliest later parent resolves
them; naming both is also honest.

This is the mechanism [[CONTEXT.md]] calls **absorption**, and the measured
sold-rate split (70.6% for components against 6.4% for non-components) is why
the player-facing word should be "builds into" rather than "sold": for 96.6% of
these purchases the item was not sold, it became something.

## What this settles for the build page

- Item icons come from `shop_image`, saved by id under `data/assets/items/`.
- Hero portraits come from `icon_hero_card`, under `data/assets/heroes/`.
- Hover text is prose rendered under a tag allowlist, with labelled
  `properties` appended. **Read `tooltip_sections[].loc_string` first and
  `description.desc` as the fallback** — see the correction in
  [#23's §7](touch-item-disclosure.md), which also supplies the row's one-line
  summary from the game's own stat-ranking fields.
- A faded item reads "builds into Titanic Magazine", resolved against the
  build's own later purchases.
- Percentages next to an item are prevalence — the share of that archetype's
  players who buy it — explained once in a footnote rather than repeated per row.
