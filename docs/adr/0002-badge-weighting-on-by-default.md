# 2. Badge weighting is on by default. It changes builds, not accuracy

Date: 2026-09-07

## Status

Accepted.

## Context

`sequence.row_weights` could weight rows toward a badge, and it had tests, but
nothing ever passed it a badge. So every recommendation the tool made followed
the average player, even though a build tool is meant to show what good
players do.

The weighting is a Gaussian on `average_badge`, centered at 80 (Oracle) with a
halfwidth of 25. When measured, 80 was the top 29.6% of players and the median
was 56. It weights rather than filters, because filtering to that bracket
would keep about a ninth of the data, and the small hero-and-archetype cells
can't afford that.

Before turning it on we needed to decide what to judge it by, and check that
it doesn't drop the items an archetype is built around.

## Decision

Badge weighting is on by default at 80. `--badge N` picks another badge and
`--badge all` turns it off. Each badge gets its own cached model, and a saved
model records its badge, so a model fitted for one badge is never served for
another.

`sequence.fit` computes the weights after `prepare` sorts the rows. Weights
computed by the caller in their own row order would be the right length but
land on the wrong rows, with no error.

Timings are weighted too. Three of the six backoff levels key on a time
bucket, so a build that takes its choices from strong players and its timings
from everyone would be predicted at the wrong pace. `median_timings` uses a
weighted median with the same weights. The effect is small: Dynamo's ult build
reaches its last ability point at 2,390s weighted, against 2,457s unweighted.

It is judged by accuracy on held-out high-badge players, a choice made before
running the numbers. Not by accuracy on all players, which weighting makes
worse on purpose. Not by win rate, which is a result of every decision in the
match.

## Consequences

The builds change and the accuracy doesn't. Weighted and unweighted models,
scored on the same held-out decisions by players at badge 80 and above, 20,000
decisions per split:

| split   | weighted top1 | unweighted top1 | weighted top3 | unweighted top3 |
|---------|---------------|-----------------|---------------|-----------------|
| match   | 0.413         | 0.413           | 0.633         | 0.638           |
| account | 0.404         | 0.404           | 0.618         | 0.628           |
| time    | 0.398         | 0.394           | 0.612         | 0.618           |

Top-1 is the same on two splits and 0.004 higher on the third. Top-3 is
slightly worse weighted, by 0.005 to 0.010.

So weighting doesn't show up in next-item prediction. Given what a player has
bought so far, a strong player's next purchase is mostly the same as anyone's.
It does show up in generated builds, which chain many predictions: Dynamo's
ult build costs 46,400 souls weighted against 41,600 unweighted, a different
late game.

That change has no accuracy gain behind it. We keep it on by default anyway,
as a judgement: the tool is meant to follow strong players, this is what makes
it do that, and it costs at most a fraction of a point of top-3. Anyone who
wants the all-players model can pass `--badge all`.

Staples survive. The worry was that weighting would thin cells enough to drop
items nearly everyone in an archetype buys. It doesn't: all 75 builds pass the
staple gate with weighting, as they did without, and
`scripts/generate_builds.py` exits non-zero if that ever changes.

These numbers come from one run: 20,000 matches, 20,000 scored decisions, and
the archetype fit of this commit. Don't compare them with numbers from another
run; rerun both sides together.
