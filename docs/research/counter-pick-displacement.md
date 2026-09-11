# What a counter-pick displaces from the build

Resolves [#26](https://github.com/quinn-zilly/deadlock-build-modeling/issues/26).

**Answer: nothing in particular.** A counter-pick is paid for out of the whole
build, a couple of percentage points at a time, not by dropping one item. The
"substitute X for Y" phrasing #20 wanted is not earned, and the matchup section
ships additive.

## The question

`counters.py` measures **lift**: facing Vindicta raises Knockdown's pick rate.
Lift is additive. #20 wanted the stronger, more useful instruction —
*"substitute Knockdown for Y against Vindicta"* — which is a claim about
**displacement**, about what the player gave up. No table held one. This
measures whether such a table could exist.

## Method

Within each (hero, archetype) cell, split players by whether they faced the
enemy hero, then compare per-item prevalence between the two groups. An item
whose prevalence **falls** when the counter-pick's rises is a displacement
candidate.

- 296,332 players, 5.1M purchase rows, joined to `archetypes.parquet`.
- Prevalence is measured over players, not purchase rows, matching
  `counters.py` (no item is bought twice).
- A cell is kept when **both** sides clear 500 players, so `MIN_FACING`
  binds on the smaller group rather than only the facing one.
- **1,361 cells** qualify, spanning 200,993 (cell × item) deltas.

The confounds #26 named are both handled below: build length settles the
"bought in addition" alternative, and a placebo split settles sampling noise.

## Finding 1 — the budget is conserved, so something does leave

Facing the enemy hero changes mean build length by **+0.036 items** (median
+0.035) and mean net worth by +97 souls. Both are negligible: players facing a
counter-pick target do not simply buy one item more. Within a counter cell,
positive and negative prevalence movement nearly cancel (mean +0.55 / −0.51).

So the counter-pick *is* paid for. The question is by whom.

## Finding 2 — the payer is the entire build, not one item

Take the 93 strongest cells, those where some item rises by ≥10pp. Within them:

| | mean |
|---|---|
| the rise (the counter-pick) | +13.4pp |
| the single biggest drop | −4.9pp |
| items that dropped at all | **81.3** |
| share of all negative movement carried by the biggest drop | **8.7%** |
| share carried by the top 3 drops | **21.0%** |

The cost is spread across ~81 items. The largest single drop carries under a
tenth of it. There is no Y.

The strongest cell in the dataset reads by hand — Rem (archetype 0) vs
Vindicta, n=1,557:

```
rises   Knockdown          +27.89pp   19.6 -> 47.5
        Phantom Strike      +1.89pp    0.8 ->  2.7
drops   Rapid Recharge      -3.51pp   63.1 -> 59.5
        Tankbuster          -3.17pp   44.5 -> 41.3
        Spirit Burn         -2.81pp   16.4 -> 13.6
```

A +27.9pp rise against a −3.5pp largest drop. Nothing here supports "instead
of Rapid Recharge" — and as Finding 3 shows, −3.5pp is not even distinguishable
from noise.

## Finding 3 — `MIN_LIFT` = 0.03 is a noise floor at cell size, not a bar

This is the methodological trap, and it nearly produced a false positive.
1,031 of 1,234 counter cells contain a drop clearing `MIN_LIFT`. That looks
like displacement everywhere. It is not.

Re-splitting each cell **at random**, same group sizes, same code, gives:

| threshold | real cells w/ drop | placebo | excess |
|---|---|---|---|
| −0.02 | 1,334 | 1,253 | 81 |
| −0.03 | 1,116 | **784** | 332 |
| −0.05 | 369 | 104 | 265 |
| −0.08 | 20 | 3 | 17 |
| −0.10 | 4 | 0 | 4 |

A coin flip clears the project's `MIN_LIFT` bar in **784 of 1,361 cells**.
`MIN_LIFT` was calibrated for lift on the full table, where the baseline is
measured over all 296k players; inside a cell of ~600 per side it is roughly
the noise floor. The rise side survives this easily (93 cells at ≥0.10 vs 0
placebo; max real rise +27.9pp vs max placebo +8.7pp). The drop side does not:
the largest drop anywhere is −12.7pp against a placebo maximum of −10.0pp.

**Lift replicates. Displacement does not.**

## Finding 4 — the big drops are matchups, not substitutions

The largest drops are themselves counter-pick logic with the sign reversed:

```
Lady Geist a0 vs Haze     Spirit Resilience  -12.66pp   67.1 -> 54.5
Warden     a0 vs Haze     Spirit Resilience  -11.22pp   50.4 -> 39.2
Billy      a1 vs Graves   Slowing Hex         -9.99pp   36.5 -> 26.5
Bebop      a1 vs Graves   Slowing Hex         -9.22pp   61.8 -> 52.6
```

Spirit Resilience falls against Haze because Haze is a gun hero — buying spirit
resist into her is the *wrong* resistance. That is a negative counter-pick, a
fact about the enemy, not about a slot freed for something else. Reporting it
as "substitute X for Spirit Resilience" would assert a trade the data does not
contain. Note both drops replicate across two heroes, so they are real effects
— just not displacement.

## Finding 5 — the genre is additive too

#23 found the genre baseline for touch detail was nothing at all. The same
holds here, and the incumbents are not avoiding substitution phrasing by
oversight:

- **deadlockitembuilder.com's counter-item helper**, the closest incumbent,
  is additive: "situational items", "situational item priority", "best items
  to counter specific ability threats". No swap language.
- **Backdash's Deadlock counter-item guide** is additive even while
  acknowledging the constraint: "you will have limited slots and souls per
  game", "you will have to pick and choose which Counter Items you need to go
  for" — it names the pressure and still declines to say what to drop.
- **Mobalytics (LoL)** frames situational items as bought *into* an enemy
  condition ("bought into team comps that have assassins"), not as swaps.

So there is no incumbent substitution pattern to copy. The measurement says why:
the trade is real in aggregate but has no identifiable counterparty, so anyone
writing "instead of Y" would be picking Y arbitrarily.

## Consequence for the site

The "if you're facing…" section ships **additive**, in the shape
`counters.py` already supports and `for_build` already returns:

> **Against Vindicta** — Knockdown, 47.5% vs 19.6% (n=1,557)

Both base rates and the sample count stay, per the module's existing rule that
a reordered list is not checkable but "+27.9pp against Vindicta" is.

Two things not to do, each of which this measurement rules out:

- **Do not compute a displaced item per counter-pick.** At cell size the
  argmin of a prevalence delta is noise 2 times in 3; it would render as
  confident, specific, hand-checkable advice and be wrong.
- **Do not lower `MIN_LIFT` for cell-level work.** It is a full-table bar. Any
  future per-cell measurement needs its own placebo split to find its floor —
  the numbers above are the calibration.

What *is* honest, and free, if the section ever wants to express the tradeoff:
the build does not get longer, so a counter-pick costs a slot. That can be said
in general ("counter-picks come out of your build, not on top of it") without
naming a victim.
