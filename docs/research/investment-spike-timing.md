# The 4,800-soul investment spike: timing and interchangeable items

Answers [#27](https://github.com/quinn-zilly/deadlock-build-modeling/issues/27):
are items interchangeable as souls toward an investment spike, and does the
time a build crosses 4,800 tell us anything worth showing?

**Short answer.** One of the three questions produced a real finding, and not
the one the issue expected. Strong players cross the spike earlier in the
match, but at the same point in their build. That is tempo, not build order.
Generated builds already cross where real players do, so there is nothing to
fix. And items are not interchangeable at the crossing: the crossing purchase
is more predictable than a normal purchase of the same cost, the opposite of
the hypothesis.

So nothing new goes on the website. One model idea waits on #31.

## Data and assumptions

`data/processed/purchases.parquet` (5,095,598 rows, 296,332 player-matches),
joined to `data/processed/archetypes.parquet`, plus the 75 shipped builds in
`data/processed/site_builds.json`. No network calls.

Taken from earlier work without re-measuring:

- From #20: where a build ends up isn't a decision. Median final spend is
  16,000 souls in spirit (95% pass 4,800), 10,400 in vitality (93%), and
  9,600 in weapon (83%).
- From `docs/game-mechanics.md`: the chance the next purchase is the same slot
  type is 0.563 just below 4,800, 0.427 landing exactly on it, and 0.275 just
  past it. 67.4% of players land exactly on 4,800 in some slot type.

## Method

### Counting souls per slot type

Souls per slot type are added up along each player's purchase sequence, never
from held items, because 70.6% of "sold" rows are absorbed components.

The catch is absorption across slot types. The component list has exactly the
four cases the game-mechanics doc names:

| Composite | Slot | Absorbs | Slot | Souls moved |
|---|---|---|---|---:|
| Spiritual Overflow | weapon | Spirit Lifesteal | vitality | 1,600 |
| Kinetic Dash | weapon | Extra Stamina | vitality | 800 |
| Arcane Surge | spirit | Extra Stamina | vitality | 800 |
| Ballistic Enchantment | weapon | Mystic Expansion | spirit | 800 |

When a player buys one of these composites while holding the component, the
component's souls move from its slot type to the composite's. This happened on
73,738 purchases, which would otherwise have landed in the wrong slot type and
given the wrong crossing time.

The counts reproduce the published continuation curve, which is good evidence
they are right:

| Souls in slot type after the purchase | n (this run) | P(next same slot type) | published |
|---|---:|---:|---:|
| 800-1,599 | 630,171 | 0.442 | 0.440 |
| 1,600-3,199 | 813,662 | 0.491 | 0.492 |
| 3,200-4,799 | 565,925 | 0.563 | 0.563 |
| exactly 4,800 | 259,160 | 0.429 | 0.427 |
| 4,801-6,399 | 311,657 | 0.273 | 0.275 |
| 6,400 or more | 2,218,691 | 0.488 | 0.488 |

The small differences come from the absorption correction, which the
published run didn't make.

### Item ids

All item ids are int64: 65 of the 156 ids in the data are larger than 2^31
and would wrap negative as int32. Items are matched by id everywhere.
`site_builds.json` stores item names, and it includes Silencer, which is the
name of two catalogue entries, `1113837674` and `3133167885`. The purchase
data settles it: `1113837674` has 20,302 purchases and `3133167885` has none.
Both are weapon items costing 6,400, so the soul counts are the same either
way.

### Random-split check for every per-cell result

`MIN_LIFT` (0.03) was set over all 296k players and is about the noise level
inside a small cell, so it can't be used here. Each per-cell comparison sets
its own noise level:

> Pool the cell's two groups. Shuffle which rows are in which group, keeping
> the group sizes, and recompute the same statistic with the same code, 200
> times. The 95th percentile of the absolute difference is that cell's noise
> level. A cell's real difference counts only if it is above that level.

Small cells get high noise levels, which is intended. This check is what
overturned the first result in #26.

## Question 1: does spike timing separate strong players?

For each player, find the first time they reach 4,800 in any slot type.
296,090 of 296,332 players (99.9%) do, so crossing isn't a choice. There are
762,339 (player, slot type) crossings.

First crossing in any slot type, by badge:

| Badge | n | median purchase number | median time (s) |
|---|---:|---:|---:|
| under 50 | 116,648 | 5.0 | 657 |
| 50-59 | 28,688 | 5.0 | 636 |
| 60-69 | 30,739 | 5.0 | 632 |
| 70-79 | 30,641 | 5.0 | 625 |
| 80-89 | 49,234 | 5.0 | 615 |
| 90+ | 40,140 | 5.0 | 592 |

Higher badges cross earlier in time but at the same purchase number. That is
the whole finding. Per slot type, badge under 60 against 80 and above, each
difference against its own noise level:

| Slot | measure | low n | high n | low median | high median | difference | noise level |
|---|---|---:|---:|---:|---:|---:|---:|
| weapon | purchase number | 96,044 | 65,310 | 6 | 6 | 0 | 0.0 |
| weapon | time (s) | 96,044 | 65,310 | 814 | 704 | -110 | 4.5 |
| vitality | purchase number | 135,957 | 86,543 | 9 | 8 | -1 | 0.0 |
| vitality | time (s) | 135,957 | 86,543 | 1,046 | 946 | -100 | 3.0 |
| spirit | purchase number | 135,424 | 84,324 | 7 | 7 | 0 | 0.0 |
| spirit | time (s) | 135,424 | 84,324 | 826 | 809 | -17 | 3.0 |

Winners against losers show the same pattern, much weaker: time differences of
-9s (weapon), -24s (vitality), and -24s (spirit), and purchase-number
differences of 0.

Is the time difference just tempo? Mostly. Spearman correlation with badge:

| Slot | n | with crossing purchase number | with crossing time | with early pace |
|---|---:|---:|---:|---:|
| weapon | 203,772 | -0.079 | -0.155 | -0.096 |
| vitality | 281,086 | -0.061 | -0.168 | -0.088 |
| spirit | 277,481 | +0.044 | -0.036 | -0.090 |

For spirit the sign flips: higher-badge players reach 4,800 spirit later in
their build. Holding early pace fixed (quartile of time to the fifth
purchase), a small badge effect on purchase number remains in weapon (mean
8.17 to 7.49 in the fastest quartile), but the median moves by one purchase at
most.

**Answer.** Strong players cross the spike about 100 seconds earlier in weapon
and vitality (noise levels 4.5s and 3.0s), at the same point in their build.
They get there sooner because they earn faster. That is tempo, which is already
known, not a separate build-order instruction.

## Question 2: do generated builds cross at the right point?

For each of the 75 shipped builds, souls per slot type were counted along its
exported purchase order (17 items, components included) the same way. The
crossing point in the build's main slot type (most souls) was compared with
real players of the same hero, archetype, and slot type.

| Measure | Value |
|---|---|
| Builds | 75 |
| Crossings in any slot type | 185 |
| Builds that cross in their main slot type | 75 of 75 |
| Builds that never cross in their main slot type | 0 |
| Median difference (generated minus players' median purchase number) | -1.0 |
| Mean difference | -0.56 |
| Within players' middle 50% | 56 of 75 |
| Earlier than players' 25th percentile | 14 |
| Later than players' 75th percentile | 5 |

Across all slot types (185 crossings), the median difference is 0 and 147 of
185 are within players' middle 50%.

How far past 4,800 the crossing purchase lands:

| Statistic | Souls |
|---|---:|
| min | 4,800 |
| median | 5,600 |
| 90th percentile | 7,200 |
| max | 10,400 |
| exactly 4,800 | 61 of 185 (33.0%) |

The 67.4% figure for players counts players who land exactly on 4,800 in any
slot type, a different measure, so it isn't compared with the 33.0% here.

The five latest crossings in a build's main slot type:

| Hero | Archetype | Slot | generated | players' median | players | difference |
|---|---|---|---:|---:|---:|---:|
| Celeste | Hybrid-Gun Celeste | weapon | 15 | 10.0 | 1,491 | +5 |
| The Doorman | The Doorman | spirit | 10 | 7.0 | 4,431 | +3 |
| Kelvin | Spirit Kelvin | spirit | 8 | 6.0 | 3,435 | +2 |
| Vyper | Tank Vyper | weapon | 7 | 5.0 | 1,485 | +2 |
| Venator | Venator | vitality | 9 | 7.0 | 4,300 | +2 |

**Answer.** Generated builds cross about where players do, one purchase early
if anything, and don't overshoot. Only Hybrid-Gun Celeste stands out, at five
purchases late, and one build in 75 isn't a model problem. Nothing to fix.

## Question 3: are items interchangeable at the crossing?

**Hypothesis:** the purchase that reaches 4,800 comes from a wider range of
items than usual, because the build just needs souls in that slot type and any
item will do.

**Test.** Within each (hero, archetype, slot type, exact cost) cell, compare
crossing purchases with other purchases in the same cell. Concentration is
measured with the Herfindahl index (HHI) over item ids; lower means a wider
range. Matching on exact cost rules out price as the explanation. Both groups
need at least 30 purchases, and each cell has its own noise level.

Matched on cost, slot type, and cell (809 cells):

| Result | Cells |
|---|---:|
| Crossing purchases wider (above noise) | 120 |
| Crossing purchases narrower (above noise) | 509 |
| Within noise | 180 |

Median HHI difference +0.068, median noise level 0.029.

The crossing purchase happens at a typical point in the build, which could
explain this. So the comparison was also matched on purchase-number band (0-3,
4-6, 7-9, 10-12, 13+): 2,177 cells, 736,068 crossing purchases against
2,638,705 others.

| Result | Cells |
|---|---:|
| Crossing purchases wider | 414 |
| Crossing purchases narrower | 908 |
| Within noise | 855 |

| Cost | Cells | Median HHI difference | Median noise level | Wider | Narrower |
|---|---:|---:|---:|---:|---:|
| 800 | 288 | +0.031 | 0.083 | 40 | 115 |
| 1,600 | 721 | -0.003 | 0.049 | 219 | 243 |
| 3,200 | 811 | +0.064 | 0.062 | 115 | 409 |
| 6,400 | 357 | +0.054 | 0.082 | 40 | 141 |

Weighted by number of crossings, mean HHI is 0.478 at the crossing against
0.367 for matched other purchases.

**The hypothesis is wrong in the other direction.** The crossing purchase is
more predictable than a normal purchase of the same cost at the same stage,
by more than two to one. Only the 1,600-soul band is close to even (219 wider,
243 narrower).

### The three items the issue named

Trophy Collector, Enduring Speed, and Restorative Locket are all vitality, tier
2, and 1,600 souls, so they are a fair test.

| Item | id | purchases | crossing purchases | crossing rate | median purchase number |
|---|---:|---:|---:|---:|---:|
| Trophy Collector | 3074274290 | 80,544 | 6,417 | 0.080 | 4.0 |
| Enduring Speed | 2447176615 | 65,851 | 15,888 | 0.241 | 8.0 |
| Restorative Locket | 2059712766 | 26,932 | 6,170 | 0.229 | 7.0 |

Across all purchases, the crossing rate is 0.150 (n=5,095,598).

Players do treat them as substitutes: a player rarely buys two of them.

| Pair | Bought together | Expected if unrelated | Ratio |
|---|---:|---:|---:|
| Trophy Collector and Enduring Speed | 10,132 | 17,899 | 0.57 |
| Trophy Collector and Restorative Locket | 2,126 | 7,320 | 0.29 |
| Enduring Speed and Restorative Locket | 799 | 5,985 | 0.13 |

But they aren't interchangeable at the crossing. Trophy Collector crosses 8.0%
of the time, half the overall rate, and is bought four purchases earlier. The
other two cross about 24% of the time. If they were interchangeable souls,
their crossing rates would be similar. They differ threefold.

**Answer.** These items are substitutes because they serve the same purpose,
not because of the spike. The spike changes which slot type the next purchase
comes from (0.563 before, 0.275 after), not which item within it.

## Glossary follow-up

`CONTEXT.md` now separates the two questions: build family says what a build
is for, and slot type matters for the game's rules, including the investment
bonus. The other findings here (the spike affects slot type, not item choice;
crossing time is tempo) stay in this document.

## Ship, defer, or drop

| Finding | Verdict | Why |
|---|---|---|
| Strong players cross about 100s earlier, at the same purchase number | Drop | It's tempo. A build page can't act on a time difference the player doesn't control, and the purchase-number difference, which a build could show, is 0. |
| Generated builds cross at players' median (-1, 56 of 75 in the middle 50%) | Drop | No problem to fix. Recorded so it doesn't get reopened. |
| Items aren't interchangeable at the crossing | Drop | Rules out a "buy any vitality item here" feature. |
| Crossing time as a live signal during a match | Out of scope | Souls per slot type are known during a match, and the 0.563 to 0.275 drop is strong. That belongs with the in-match recommender. |
| Conditioning the model on souls per slot type | Defer, waiting on #31 | The effect is real and the model can't see it, but #31 decides whether the model takes new inputs at all. |

As #20 found for the final spend, the spike's timing gives the website
nothing to show. The spike is a real and large game mechanic, but not a
recommendation.

## Reproducing this

The scripts were throwaway and aren't committed. Steps: build the
absorption-aware soul counts per slot type from `purchases.parquet` and check
them against the published continuation curve; join `archetypes.parquet`; then
run the three measurements: crossing number and time by badge and outcome
with noise levels; generated-build crossings from `site_builds.json` against
each (hero, archetype, slot type) group of players; and per-cell HHI at the
crossing against cost- and purchase-number-matched purchases, each cell
against its own 200-shuffle noise level.
