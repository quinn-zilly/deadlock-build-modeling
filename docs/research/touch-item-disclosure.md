# How item detail reaches a player who cannot hover

Research for issue #23 (part of the #15 map), to unblock #20. Establishes what
progressive-disclosure pattern the item row should use on touch, what it costs
in vertical space, and what its keyboard path is.

Every layout number below was **measured in a browser at a 375px viewport** —
either on the live site named, or against a page built from the project's own
Ivy build data. Nothing here is quoted from a design blog. The accessibility
requirements are quoted from w3.org, not from a summary of it.

The ticket's question 2 — whether the tooltip can be shortened to one line — is
being measured separately and is not answered here.

**Bottom line.** Use a **native `<details>`/`<summary>` disclosure, one per item
row, with `role="button"` and `aria-expanded` set on the summary**. It is the
only candidate that costs **zero vertical space while closed** (measured: 51px,
identical to the bare row), needs **no JavaScript**, and arrives with the APG
disclosure keyboard contract already implemented by the browser (Tab to reach,
Enter *and* Space to toggle — both verified by real key press, not synthetic
events). The current hover tooltip is kept for pointer users but must gain a
focus trigger and a dismiss key to stop failing WCAG 1.4.13.

Three findings that change the spec rather than confirm it:

1. **The genre's real baseline is "no detail at all on touch."** On u.gg,
   mobalytics and op.gg at 375px, tapping an item icon does literally nothing —
   measured, not inferred. Matching the genre is not the bar; it is the floor
   being cleared.
2. **`<details>` alone does not expose a button.** With `list-style:none` and a
   grid `<div>` inside `<summary>`, the accessibility tree reports **`group` /
   `generic`**, so the expanded state is never announced. Two attributes fix it.
3. **The always-visible one-line summary is not free, and is the more expensive
   option.** It costs **+15px on every row, always** (66px vs 51px) — for 17
   items that is 255px of permanent page, versus 0px for a closed disclosure.

## 1. What the tools players already use actually do

Measured live, viewport 375×812, by reading each item element's box and
interactive ancestor and then dispatching a real tap.

| Site | Item icon at 375px | Interactive ancestor | What a tap does | Touch detail path |
|---|---|---|---|---|
| [u.gg](https://u.gg/lol/champions/jinx/build) | **20×20** | `<a>`, 42px row | navigates | separate page |
| [mobalytics](https://mobalytics.gg/lol/champions/jinx/build) | 36×36 | **none** | **nothing** | **none** |
| [op.gg](https://op.gg/lol/champions/jinx/build) | 32×32 | **none** | **nothing** | **none** |
| [deadlocktracker](https://deadlocktracker.gg/items) | 30×30 | `<a href="/items/…">` | navigates | separate page |
| [statlocker](https://statlocker.gg/items/items-library) | name label, 78px box | none | **nothing** | none (names always visible) |
| [deadlocklabs](https://deadlocklabs.gg/items/shop/) | card | card is a link | navigates | separate page |
| poe.ninja | — | 3 `aria-expanded` nodes | — | filter controls only, not item detail |

Two things fall out of that table.

**Nobody in this genre uses a bottom sheet, a long-press, or an expandable row
for item detail.** The three LoL sites — the most-trafficked build tools in
existence — give a touch user nothing. On mobalytics I dispatched
`pointerdown`/`pointerup`/`click` on Runaan's Hurricane and the page text
changed by **0 characters**, with no `[role="dialog"]` appearing. op.gg gave the
same result. This is worth stating because it means the ticket's premise is
right and there is no incumbent pattern to copy: the choice is open.

**Where a touch path exists at all, it is a link to a separate item page.**
Three of the Deadlock-adjacent sites converge on it independently. That pattern
costs zero vertical space, but it costs the whole page — the reader loses their
place in a build they are reading *in order*, which is the one thing this
project's page exists to preserve. It is the right pattern for an item
*catalogue* and the wrong one for a build *sequence*.

Note also that u.gg's 20×20 icon is **below the 24×24 CSS px floor** of WCAG
2.5.8 (Level AA), and op.gg's and mobalytics' icons are not targets at all.

## 2. What the game itself does

The site is read beside the game, so the game's vocabulary is the constraint.
Sourced from Valve's own May 2025 Shop Rework notes (via the
[unDeadlock mirror](https://undeadlock.com/en-US/patch/08-05-2025/shop-rework-update);
the [SteamDB copy](https://steamdb.info/patchnotes/18393584/) returns 403 to
this fetcher).

Valve's own lines, verbatim:

- "The Build Browser has been reworked into its own **fullscreen UI**."
- "**Hovering** an item in the damage report now displays its **tooltip**."
- "Items display Spirit Scaling when **Alt is pressed**."
- "Added **corner cap** on items to replace old tier indicators."
- "HUD items are now ordered cheapest-to-most-expensive from left to right."
- "You can now specify a suggested **imbue target** for items in a build."

What this settles, and what it does not:

- **The game's own item detail is hover-triggered and progressive.** Base
  tooltip on hover; *more* detail behind a held modifier key (Alt for Spirit
  Scaling, Tab for "extra info" per the
  [player forum](https://forums.playdeadlock.com/threads/hovering-over-items-does-not-show-boosts-for-abilities-or-other-items.98832/)).
  So a two-level disclosure — a short always-visible line, fuller detail on
  demand — **is** the game's vocabulary, not a third one invented here.
- **The build browser is fullscreen, and the shop is a grid.** Both are
  pointer-driven; Deadlock has no touch client, so the game solves the *hover*
  problem and never had to solve the *touch* problem. It cannot supply the
  answer to this ticket, only the vocabulary.
- **Caveat — I could not verify the shop's panel geometry.** Whether the item
  description sits in a fixed panel beside the grid or as a floating popover
  over it is not stated in any text source I could reach. The
  [deadlock.wiki Items page](https://deadlock.wiki/Items) documents mechanics,
  not UI, and confirms nothing about layout; the first-look articles describe
  functional changes only. Determining it needs a screenshot or the client.
  **I am not asserting a layout I did not see.** This matters less than it
  might: the recommendation below does not depend on it.

The vocabulary the site should carry forward is therefore **tier, souls, corner
cap, imbue, build browser** — and detail-on-demand as a *second* level, with
something always visible at the first.

## 3. Accessibility floor

Quoted from w3.org, normative text.

**SC 1.4.13 Content on Hover or Focus (Level AA)** requires all three of:

- **Dismissible** — "A mechanism is available to dismiss the additional content
  without moving pointer hover or keyboard focus, unless the additional content
  communicates an input error or does not obscure or replace other content".
- **Hoverable** — "If pointer hover can trigger the additional content, then the
  pointer can be moved over the additional content without the additional
  content disappearing".
- **Persistent** — "The additional content remains visible until the hover or
  focus trigger is removed, the user dismisses it, or its information is no
  longer valid".

The Understanding document also states that content triggerable by pointer hover
"should also be able to be triggered by keyboard focus."

**SC 2.1.1 Keyboard (Level A)**: "All functionality of the content is operable
through a keyboard interface…". **SC 2.5.8 Target Size (Minimum) (Level AA)**:
"The size of the target for pointer inputs is at least **24 by 24 CSS pixels**",
subject to a spacing exception for undersized targets.

### The tooltip shipped in #19 fails all three parts of 1.4.13

Read off `prototypes/variant-b.built.html` directly:

| requirement | current tooltip | why |
|---|---|---|
| triggered by focus | **no** | binds `mouseover`/`mousemove`/`mouseout` only |
| Dismissible | **no** | no Escape handler, and it *does* obscure other content |
| Hoverable | **no** | `#tip{pointer-events:none}` — the pointer cannot enter it |
| Persistent | partial | survives while hovering the row, but nothing else |
| keyboard reachable (2.1.1) | **no** | the row is a `<div>`, no `tabindex`, no focusable child |

This is not a touch-only defect. A sighted keyboard user on a desktop has
exactly the same access to item detail as a phone user does: none.

### Keyboard path per candidate pattern, and APG names

| pattern | APG pattern | keyboard path | JS needed |
|---|---|---|---|
| `<details>`/`<summary>` | **Disclosure (Show/Hide)** | Tab to summary; **Enter or Space** toggles | **none** |
| modal sheet | **Dialog (Modal)** | Tab to trigger, Enter; focus must move in, trap, Escape closes, focus restored | substantial |
| tooltip on focus | **Tooltip** | Tab to trigger; Escape dismisses | some |
| link to item page | — | Tab, Enter; **Back** to return | none |

The APG's [Disclosure pattern](https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/)
specifies "Enter: activates the disclosure control and toggles the visibility of
the disclosure content", the same for Space, `role button`, and `aria-expanded`
true/false, with `aria-controls` optional.

**The APG Tooltip pattern carries a standing warning**: "NOTE: This design
pattern is work in progress; it does not yet have task force consensus."
Building the primary path on a pattern the working group has not agreed on is a
bad trade when a settled one exists. Keep the tooltip as a pointer
*enhancement*; do not make it the mechanism.

## 4. Measured cost in vertical space

Built a page at 375px using the project's real Ivy row markup and real item
content, and measured `getBoundingClientRect().height`.

First, what the content actually is — measured over the 17 items in
`prototypes/ivy-gun-rich.json`:

| | value |
|---|---|
| items with no prose at all | **7 of 17** |
| prose length, median | **57 chars** |
| prose length, mean / max | 60 / **201** (Mercurial Magnum) |
| labelled stat lines, median / max | **4** / 5 |

So the worst case is one long item, not a page of them, and 7 of 17 rows open to
stats alone.

| pattern | height at 375px | delta vs bare row |
|---|---|---|
| bare item row (baseline) | **51px** | — |
| `<details>` **closed** | **51px** | **0** |
| `<details>` open, stat-only item (Extra Charge) | 93px | +42 |
| `<details>` open, worst item (Mercurial Magnum, 201 chars + 5 stats) | 233px | +182 |
| always-visible one-line stat summary | **66px** | **+15, permanently** |

The decisive comparison is the last two rows against the second. A closed
disclosure is **free**: it is byte-for-byte the same height as the row with no
disclosure at all. The always-visible summary line taxes **every** row forever —
+255px across a 17-item build, roughly a third of an 812px screen — to deliver
a truncated line that, for the 7 stat-only items, is the entire content anyway.

The `<summary>` is a **51px tap target**, over the 24px AA floor of 2.5.8 and
over the 44px commonly used as a comfort target. No extra padding is needed to
make it tappable; the row is already the target.

Opening is also strictly better than the tooltip on the specific failure the
ticket names: an expanded panel **pushes the page down** rather than covering
the row it describes. The obscuring problem disappears rather than being
mitigated.

## 5. The defect in the obvious implementation

Verified in the accessibility tree, not assumed. With the row styled as the
prototype styles it — `summary{list-style:none}` wrapping a grid `<div>` — the
snapshot reports:

```
- group:
  - generic "Mercurial Magnum 6200 souls 69%" [cursor=pointer]
```

**`generic`, not `button`**, and no expanded state. The native mapping is lost
once the summary is restyled, which is exactly what this design does. Screen
reader support for the native `<details>` mapping is
[known to vary by browser and AT](https://a11ysupport.io/tech/aria/aria-expanded_attribute),
with notably weaker support on iOS — the reading surface this project cares
about most.

Adding `role="button"` and `aria-expanded` to the `<summary>` repairs it.
Re-snapshotted after setting both:

```
- group:
  - button "Mercurial Magnum 6200 souls 69%" [cursor=pointer]
```

Enter and Space still toggle natively after the role is applied — verified by
real key press. So the fix costs two attributes and **no** JavaScript for the
toggle itself. Keeping `aria-expanded` truthful does need a few lines listening
for `toggle`; if #20 wants a strictly zero-JS page, the honest trade is to state
that `aria-expanded` will be stale after the first interaction, and prefer the
few lines.

## 6. Recommendation

**One `<details>` disclosure per item row.**

- **Closed state.** The row exactly as #19 draws it — icon, name, souls, builds
  into, prevalence percentage. **51px, zero cost over the current row.** No
  always-visible stat line: it costs +15px on every row to duplicate what the
  open panel says better.
- **Open state.** Prose where it exists, then labelled stats — the order the API
  supplies and the order deadlocktracker's item page uses. **+42px** for a
  stat-only item, **+182px** worst case. Content pushes down; it never covers.
- **Touch path.** Tap anywhere on the row. The target is the full 51px row,
  above both the 24px AA floor and 44px comfort. Tap again to close.
- **Keyboard path.** Tab reaches the summary with no `tabindex` needed (verified:
  `document.activeElement` becomes the `<summary>`). **Enter or Space** toggles,
  both natively (verified by real key press). This is the APG **Disclosure
  (Show/Hide)** pattern, implemented by the browser.
- **Required markup.** `<summary role="button" aria-expanded="false">`, kept in
  sync on `toggle`. Without `role="button"` the accessibility tree exposes
  `generic` and the state is never announced.
- **Pointer users keep the tooltip**, but it must be repaired to satisfy 1.4.13:
  add a `focus`/`focusin` trigger, drop `pointer-events:none` so it is
  Hoverable, and add Escape to dismiss. If that repair is not worth the code,
  **delete the tooltip** — the disclosure serves pointer users too, and a
  non-conforming tooltip is worse than none.

Two things #20 should decide that this research does not settle: whether more
than one row may be open at once (nothing here argues either way — allowing it
is the zero-JS default), and the exact truncation of the 201-char worst case, if
any, which is the shortening question being measured separately.

## Sources

- W3C, [Understanding SC 1.4.13 Content on Hover or Focus](https://www.w3.org/WAI/WCAG22/Understanding/content-on-hover-or-focus.html)
- W3C, [Understanding SC 2.1.1 Keyboard](https://www.w3.org/WAI/WCAG22/Understanding/keyboard.html)
- W3C, [Understanding SC 2.5.8 Target Size (Minimum)](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html)
- W3C, [ARIA APG — Disclosure (Show/Hide) Pattern](https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/)
- W3C, [ARIA APG — Tooltip Pattern](https://www.w3.org/WAI/ARIA/apg/patterns/tooltip/) (work in progress, no consensus)
- WHATWG, [HTML Standard — interactive elements](https://html.spec.whatwg.org/multipage/interactive-elements.html)
- Accessibility Support, [aria-expanded](https://a11ysupport.io/tech/aria/aria-expanded_attribute)
- Valve Shop Rework notes, 8 May 2025, [unDeadlock mirror](https://undeadlock.com/en-US/patch/08-05-2025/shop-rework-update)
- Live measurement at 375px: u.gg, mobalytics.gg, op.gg, deadlocktracker.gg, statlocker.gg, deadlocklabs.gg, poe.ninja
- `prototypes/variant-b.built.html` and `prototypes/ivy-gun-rich.json` in this repo
