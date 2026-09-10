# Visual direction prototype

Throwaway. Answers [#19](https://github.com/quinn-zilly/deadlock-build-modeling/issues/19):
what should the build site look like?

    python -m http.server 8899 --directory prototypes
    # then open http://127.0.0.1:8899/visual-direction.html

Three structurally different takes on one hero page, switchable with `?variant=A|B|C`,
the bar at the bottom, or the arrow keys. Real Gun Ivy data at badge 80, lifted from
`data/site/builds.html` into `ivy-gun.json` and inlined by hand.

- **A — Shop ticket.** One narrow column, phase bands as ruled breaks.
- **B — Phase columns.** Laning / mid / late side by side, scanned across.
- **C — The spine.** Items left, ability points right, one shared centre line.

`shots/` holds desktop and 375px captures of each.

Not production code: no build step, no tests, data inlined. The winning direction
gets rewritten properly against `refit.py` output rather than promoted from here.

## Chosen: variant B, with the ticket's six changes

`variant-b.html` is the template, `variant-b.built.html` the rendered page
(data inlined, opens from a file path). Rebuild after editing the template:

    .venv/Scripts/python.exe -c "import pathlib; t=pathlib.Path('prototypes/variant-b.html').read_text(encoding='utf-8'); d=pathlib.Path('prototypes/ivy-gun-rich.json').read_text(encoding='utf-8'); pathlib.Path('prototypes/variant-b.built.html').write_text(t.replace('__DATA__',d),encoding='utf-8')"

Item icons, hero portrait, hover tooltips, "builds into X", bare percentages
with a footnote, and the ability-point order laid out as the in-game build
browser lays it out. See `docs/research/item-icons-and-tooltips.md`.
