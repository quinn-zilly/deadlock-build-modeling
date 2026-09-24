# 3. Ability order is recommended but doesn't find archetypes

Date: 2026-09-15

## Status

Accepted.

## Context

Archetypes are found per hero by clustering on build family shares. ADR 0001
rejected two ability features as clustering inputs: ability levels at 480s,
which made every hero tried worse, and imbue targets, which split heroes on
whether they bought an imbueable item. It left ability order untested. This
ADR tests it.

Ability order was the feature most likely to pass ADR 0001's bar for
reopening: its separating items shouldn't concentrate in the items it's built
from. Imbue failed that because target shares exist only for players who buy
one of 9 items. Every player spends ability points, though: all 296,478
players in the purchase table have ability rows.

Three forms were fitted, since the right one wasn't known:

- `order`: `abilities.point_order_features` as is. Twelve columns, `pt_1_l2`
  to `pt_4_l4`: the point at which slot s reached level L, divided by the
  player's total ability points.
- `order_mean`: the same twelve columns minus the hero's mean.
- `order_rank`: the same twelve columns as a percentile within the hero,
  minus 0.5.

The two relative forms were the proposal. Most players on a hero level
abilities in the same order: on average, which hero it is explains 43% of the
variance in each column (from 28% for `pt_2_l4` to 57% for `pt_3_l2`).
Clustering already runs one hero at a time, so that part adds nothing, and the
relative forms keep only how each player differs from their hero's usual
order.

This rule was written down before seeing the results and applied as written:

> R1 No hero loses a split it had with build family shares alone.
> R2 At least one hero gains a split.
> R3 The separating items don't concentrate: no single item separates more
> than 25% of split heroes, and the top three items' share is at most twice
> the families control from the same run.

`scripts/compare_order_fits.py` fits all 38 heroes four ways in one run and
reports each fit's separating item. It reuses the families control code from
`scripts/compare_imbue_fits.py`, so both comparisons share a baseline.

## Decision

Ability order stays out of the clustering. It is still recommended with every
build, and still used to name archetypes through ability focus.

All three forms failed R1, and the relative forms failed worst:

| | families | `order` | `order_mean` | `order_rank` |
|---|---|---|---|---|
| heroes that split | 31 | 28 | 23 | 24 |
| splits gained | - | 3 | 9 | 4 |
| splits lost | - | 4 | 14 | 15 |
| top separating item | Unstoppable 13% | Rapid Recharge 11% | Extra Charge 13% | Rapid Recharge 12% |
| top three items | 35% | 32% | 22% | 25% |

- R1 fails for every form. `order_mean` loses 14 heroes' splits and
  `order_rank` 15. Billy, Haze, and Venator lose their split under all three.
- R2 passes for every form. `order_mean` gains nine splits, but loses more.
- R3 passes easily for every form. Unlike imbue (83% against a 7% control),
  every form is at or below the families control on both measures. So ability
  order doesn't have imbue's problem. It fails for a different reason.

Removing each hero's usual order made things worse, not better: `order` lost 4
splits and `order_mean` lost 14. Our reading is that the hero's usual order
isn't noise. It is what makes a player's order meaningful, and without it the
block is twelve columns of small differences competing with the family shares.

Next-item accuracy for all four fits was measured in one run
(`scripts/score_archetype_fits.py --blocks`) on the same split and the same
20,000 held-out decisions from 20,000 matches:

| fit | top-1 | top-3 | cells in the sample |
|---|---|---|---|
| build families | 0.3732 | 0.5790 | 79 |
| `order` | 0.3716 | 0.5792 | 78 |
| `order_mean` | 0.3729 | 0.5801 | 71 |
| `order_rank` | 0.3757 | 0.5816 | 69 |

The whole spread is 0.0041, about one standard error (0.0034). All four beat
the bigram baseline of 0.2647 on the same split. Accuracy doesn't favor any
fit, so R1 decides.

The families control splits 31 heroes here and 28 in ADR 0001, because the
purchase table was re-downloaded between the two runs. Every number in this
ADR uses the 31.

## Consequences

- `archetype.py` still clusters on build family shares alone. Nothing shipped
  changes and nothing needs regenerating.
- A new clustering input must now pass R1: no hero may lose a split. Passing
  ADR 0001's concentration test isn't enough, since ability order passed it
  and still failed. This is separate from #31's bar for new conditioning
  signals in the model.
- Ability order still does everything else it did: it is half of every
  recommendation, and `scripts/sweep_ability_features.py` still uses
  `abilities.point_order_features`. Ivy keeps three archetypes under all four
  fits, so order does differ between her archetypes. It just doesn't find
  them.
- `abilities.residual_point_order_features` is kept so the 43% figure and the
  relative forms can be rechecked. Nothing in the shipped pipeline calls it.
- Not decided here: whether the website should show ability order.

## Evidence

- `docs/ORDER-FIT-COMPARISON.md` and `.csv`: k and the separating item per hero
  under each fit.
- `scripts/compare_order_fits.py`: the experiment, with the rule.
- `scripts/score_archetype_fits.py --blocks families,order,order_mean,order_rank`:
  all four fits scored in one run.
- `abilities.residual_point_order_features`: the relative forms and the source
  of the 43% figure.
