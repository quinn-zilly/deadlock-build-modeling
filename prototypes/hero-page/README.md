# PROTOTYPE -- hero page: chooser, or archetype tabs in place? (#24)

Throwaway. Not production, not imported by anything. `scripts/build_site.py` is
the real generator.

## Run it

```sh
python -m http.server 8777          # from the repo root, so ../../data/assets resolves
# then open:
#   http://127.0.0.1:8777/prototypes/hero-page/index.html?variant=A
#   http://127.0.0.1:8777/prototypes/hero-page/index.html?variant=B
```

Left/right arrow keys and the floating bar cycle the variants. `?build=<n>`
picks a build page inside variant B.

`./verify.sh` parses the page script and renders every variant against a DOM
stub. A page that parses can still throw on its first render, and on the page
the two failures look identical.

`python prepare_data.py` regenerates `data.json` from the model; `data.js` is
that JSON as a global so the page needs no fetch.

## The variants

- **A** -- one page per hero. Archetype tabs above a single rendered build,
  selection in place, no navigation. 38 URLs.
- **B** -- the hero page is a chooser: the side-by-side archetype comparison,
  linking out to one page per build. 75 URLs.

Built on Ivy, which has three archetypes: the hardest case on the roster.

**The build rendering is held constant** -- identical markup under both, checked
by `verify.sh`. The prototype is about *where selection happens*, not about the
visual, which #19 and #23 settled.

## What is deliberately not built

#24's text asks B's chooser to carry performance descriptions ("Gun Ivy fires
2.6x the bullets of Spirit Ivy per soul"). **#21 closed later and dropped build
descriptions entirely**, so that line is not built. Reviving it would rig the
comparison in B's favour using a claim the project no longer makes. The chooser
carries exactly what #21 settled: name, share, absolute win rate with n, two
labelled item columns, and the imbue target only where it differs.
