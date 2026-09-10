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
