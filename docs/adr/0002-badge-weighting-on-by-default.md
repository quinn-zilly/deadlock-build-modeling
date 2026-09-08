# 2. Badge weighting is on by default, and it buys builds rather than accuracy

Date: 2026-09-07

## Status

Accepted.

## Context

`sequence.row_weights` has carried a badge kernel for a long time. It was
implemented, unit-tested, and passed by nobody: no caller anywhere in the CLI,
the build generator or the scoring scripts ever supplied `target_badge`. Every
recommendation the tool has ever made therefore imitated the median player,
while the whole proposition of a build tool is "this is what good players do".

The kernel is a soft Gaussian on `average_badge`, centred at 80 — roughly the
top 30% of a distribution whose median is 61 — with a halfwidth of 25. It is
not a filter, because filtering to that bracket costs about nine times the
data, and the thin hero-and-archetype cells are exactly the ones that cannot
afford the loss.

Two things had to be settled before turning it on: what it is judged by, and
whether it quietly drops the items an archetype is built around.

## Decision

Badge weighting is on by default, centred at 80, with `--badge N` for another
bracket and `--badge all` for none. Each bracket caches its own model, and a
saved model records the bracket it was fitted for, so a cache fitted for one
bracket can never be served as another.

Weights are computed inside `sequence.fit`, after `prepare` has sorted the
frame. A caller computing weights over its own row order would produce an array
of the correct length pointing at the wrong rows — misaligned silently, which
is the class of failure this project keeps finding.

The timings follow the bracket too. Three of the six backoff levels key on a
time bucket, so the clock is half the context every deep level is asked with; a
build taking its choices from strong players and its clock from everybody is
conditioned on a pace its own players do not keep. `median_timings` therefore
takes a weighted median under the same kernel -- weighted rather than filtered,
for the same reason the tables are. The effect is small and real: Dynamo's ult
build reaches its last ability point at 2,390s weighted against 2,457s
unweighted.

The bar is high-badge held-out accuracy, fixed before the numbers were run.
General-population accuracy is not the bar: weighting the tables makes it worse
on purpose, so it would report the intended change as a regression. Win rate is
not the bar either; it is an outcome downstream of every decision the build
makes.

## Consequences

**The builds change. The accuracy does not.** Weighted and unweighted models,
scored on the same held-out decisions of players at badge 80 and above, 20,000
decisions per split:

| split   | weighted top1 | unweighted top1 | weighted top3 | unweighted top3 |
|---------|---------------|-----------------|---------------|-----------------|
| match   | 0.413         | 0.413           | 0.633         | 0.638           |
| account | 0.404         | 0.404           | 0.618         | 0.628           |
| time    | 0.398         | 0.394           | 0.612         | 0.618           |

Top-1 is a wash — one split up four thousandths, two identical. Top-3 is
slightly *worse* weighted, by half a point to a point.

So the honest reading is that next-item prediction is not where the weighting
shows up. What a high-badge player buys next, given their own prefix, is mostly
what anyone buys next given that prefix; the prefix already carries the
information. Where it does show up is in the generated build, which is a
roll-forward of many decisions rather than one: Dynamo's ult build comes out at
46,400 souls weighted against 41,600 unweighted, a different late game.

That is a real change with no measured accuracy backing it, and the default is
still on, for a reason that is a judgement and is recorded here as one: the
tool exists to imitate strong play, the weighting is what makes it do so, and
the measurement says the cost of doing it is at most a fraction of a point of
top-3. A future reader who wants the population model has `--badge all` and
loses nothing measurable.

**Staples survive it.** The concern was that weighting would thin the cells
enough to drop items nearly everyone in an archetype buys. It does not: all 75
hero-and-archetype builds pass the prevalence gate under the weighted model,
which is the same bar they passed unweighted, and `scripts/generate_builds.py`
exits non-zero if that ever stops being true.

**These numbers do not travel.** They come from one run configuration — 20,000
matches, 20,000 scored decisions, the archetype fit of this commit. Comparing
them against a figure from another run is the mistake this project has already
made three times; rerun both sides in one run instead.
