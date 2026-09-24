# What does a counter-pick replace in the build?

Answers [#26](https://github.com/quinn-zilly/deadlock-build-modeling/issues/26).

**Short answer: no particular item.** Players pay for a counter-pick by buying
slightly less of many items, not by dropping one. So the site can't say
"buy X instead of Y", and the matchup section lists counter-picks as additions.

## The question

`counters.py` measures lift: facing Vindicta raises Knockdown's pick rate.
Issue #20 wanted the site to say "buy Knockdown instead of Y against
Vindicta", which needs to know what the player gave up. Nothing measured that.
This checks whether it can be measured.

## Method

Within each hero-and-archetype cell, split players by whether they faced a
given enemy hero, and compare each item's prevalence between the two groups.
An item whose prevalence falls when the counter-pick's rises could be what it
replaced.

- 296,332 players and 5.1M purchases, joined to `archetypes.parquet`.
- Prevalence is per player, as in `counters.py`.
- A cell is kept only if both groups have at least 500 players, so
  `MIN_FACING` applies to the smaller group.
- 1,361 (cell, enemy hero) pairs qualify, giving 200,993 item differences.

Issue #26 raised two alternative explanations. Build length tests "players
just buy one more item", and a random re-split tests "it's noise".

## Finding 1: the counter-pick replaces something

Facing the enemy hero changes build length by +0.036 items on average (median
+0.035) and net worth by +97 souls. Both are negligible, so players don't just
buy one more item. Within a cell, the rises and drops in prevalence nearly
cancel (mean +0.55 against -0.51).

So something is given up. The question is what.

## Finding 2: the whole build pays, not one item

Take the 93 strongest cells, where some item rises by at least 10 points:

| | mean |
|---|---|
| the rise (the counter-pick) | +13.4 points |
| the single biggest drop | -4.9 points |
| items that dropped at all | 81.3 |
| share of the total drop from the biggest drop | 8.7% |
| share from the top 3 drops | 21.0% |

The cost is spread over about 81 items, and the biggest single drop is under a
tenth of it. There is no one item being replaced.

The strongest cell in the data, Rem (archetype 0) against Vindicta, n=1,557:

```
rises   Knockdown          +27.89pp   19.6 -> 47.5
        Phantom Strike      +1.89pp    0.8 ->  2.7
drops   Rapid Recharge      -3.51pp   63.1 -> 59.5
        Tankbuster          -3.17pp   44.5 -> 41.3
        Spirit Burn         -2.81pp   16.4 -> 13.6
```

A 27.9-point rise against a 3.5-point biggest drop. That doesn't support
"instead of Rapid Recharge", and Finding 3 shows a 3.5-point drop is within
noise anyway.

## Finding 3: at cell size, MIN_LIFT (3 points) is noise

This nearly produced a false result. 1,031 of 1,234 counter cells have some
item dropping by more than `MIN_LIFT`, which looks like replacement
everywhere. It isn't.

Splitting each cell at random, with the same group sizes and the same code:

| threshold | real cells with a drop | random split | difference |
|---|---|---|---|
| -0.02 | 1,334 | 1,253 | 81 |
| -0.03 | 1,116 | 784 | 332 |
| -0.05 | 369 | 104 | 265 |
| -0.08 | 20 | 3 | 17 |
| -0.10 | 4 | 0 | 4 |

A random split passes `MIN_LIFT` in 784 of 1,361 cells. `MIN_LIFT` was set for
lift over all 296k players. Within a cell of about 600 players per side it is
roughly the noise level. Rises still stand out clearly: 93 cells rise by 10
points or more against none at random, and the biggest real rise is 27.9
points against 8.7 at random. Drops don't: the biggest real drop is 12.7
points against 10.0 at random.

Lift holds up. Replacement doesn't.

## Finding 4: the biggest drops are reverse counter-picks

The largest drops are items players avoid against a hero:

```
Lady Geist a0 vs Haze     Spirit Resilience  -12.66pp   67.1 -> 54.5
Warden     a0 vs Haze     Spirit Resilience  -11.22pp   50.4 -> 39.2
Billy      a1 vs Graves   Slowing Hex         -9.99pp   36.5 -> 26.5
Bebop      a1 vs Graves   Slowing Hex         -9.22pp   61.8 -> 52.6
```

Spirit Resilience drops against Haze because Haze deals gun damage, so spirit
resistance is the wrong defense. That is a fact about the enemy, not a slot
freed for the counter-pick. Both drops repeat across two heroes, so they are
real, just not replacement.

## Finding 5: other build sites don't do this either

- deadlockitembuilder.com's counter-item helper lists "situational items" and
  "best items to counter specific ability threats", with no swap advice.
- Backdash's Deadlock counter-item guide notes "you will have limited slots
  and souls per game" and "you will have to pick and choose which Counter
  Items you need", but never says what to drop.
- Mobalytics (League of Legends) describes situational items as bought "into
  team comps that have assassins", not as swaps.

This measurement explains why. The trade-off is real overall but has no
single item on the other side, so any "instead of Y" would pick Y arbitrarily.

## What this means for the site

The "if you're facing..." section lists counter-picks as additions, in the
shape `counters.for_build` already returns:

> **Against Vindicta**: Knockdown, 47.5% vs 19.6% (n=1,557)

Both rates and the sample size are shown, so a player can check the claim.

Two things to avoid, both ruled out above:

- Don't compute a replaced item per counter-pick. At cell size the biggest
  drop is noise about two times in three, and it would look like specific,
  checkable advice.
- Don't use `MIN_LIFT` for per-cell work. It is set for the full table. Any
  per-cell measurement needs its own random-split check to find its noise
  level; the table above is that check for this one.

If the section ever needs to mention the trade-off, it can say it in general:
builds don't get longer, so a counter-pick takes the place of something else.
