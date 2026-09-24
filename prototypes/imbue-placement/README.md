# PROTOTYPE -- where the imbue target sits on an item row (#25)

Throwaway. Not production, not imported by anything. `scripts/build_site.py` is
the real generator.

## Run it

```sh
python -m http.server 8778          # from the repo root, so ../../data/assets resolves
# then open:
#   http://127.0.0.1:8778/prototypes/imbue-placement/index.html?variant=A&build=0
```

Left/right arrow keys and the floating bar cycle the variants; the dropdown
switches build (`?build=0` Spirit Ivy, `1` Spirit Paradox, `2` Gun Ivy).

`uv run python prototypes/imbue-placement/prepare_data.py` regenerates
`data.js` from the model. `roster_sublines.json` is variant A's subline for
every imbue row in all 80 generated builds, used for the overflow count below.

## The variants

Everything except the imbue is #23's row, held constant: 51px closed,
`role="button"` + `aria-expanded`, "builds into X" in the subline, the one
ranked stat in the subline only where there is no "builds into".

- **A** -- on the row. The target leads the subline: `Imbue Stone Form ·
  builds into Greater Expansion`.
- **B** -- in the disclosure only, beside the item facts.
- **C** -- both: the ability's own icon badged on the item icon's corner (the
  way the game marks an imbued item), full phrasing in the disclosure.

## What it measured

**The ticket's premise does not hold.** It expected imbue on 1-2 rows per build
with the "builds into" collision rare. Across all 80 builds:

| | count |
|---|---|
| builds with at least one imbue row | 68 of 80 |
| imbue rows per build | 0: 12, 1: 24, 2: 23, 3: 16, 4: 5 |
| imbue rows | 138 |
| ...that also carry "builds into" | **79 (57%)** |

**Variant A overflows on every one of the 79** at 375px (shortest needs 242px;
the subline has 185-200px) and on **none of the other 59** (longest 153px).
Truncation eats the "builds into" first, so A removes #23's content from the
rows where it matters. At 1280px everything fits in every variant. Row height
is 51px in all nine variant x build combinations, no horizontal page scroll.

**Found while building it: the imbue usually ends at the upgrade.** Of the 79
absorbed imbue rows, **67** build into a composite with no `imbue` field
(Superior Cooldown 27, Greater Expansion 21, Superior Duration 19), whose bonus
applies to every ability. Only Quicksilver Reload -> Mercurial Magnum (12) keeps
its target. This is from the assets API (`imbue` field and tooltip text), not
from match data -- imbue rows record only the purchase -- so it is strong but
not observed in play. B and C state it in the disclosure.

Screenshots in `screenshots/`: A truncating Compress Cooldown to
"Imbue: usually Entangling Thorn…" with "builds into" gone; B with no imbue
signal on the closed row; C with the badge on the row and the full phrasing open.
