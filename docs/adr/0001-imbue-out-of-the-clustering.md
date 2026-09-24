# 1. Imbue names archetypes but doesn't find them

Date: 2026-09-07

## Status

Accepted. Re-measured on 2026-09-23 and still holds. A per-hero gate was
measured on 2026-09-24 and also rejected; that run corrects the explanation
given under Decision (see the end).

## Context

Archetypes are found per hero by clustering on build family shares. Three
ability features were proposed as extra clustering inputs:

- **Ability levels** at 480s: how many points each signature ability has.
  Tested and rejected. Adding them made clustering worse at every weight: Ivy's
  separation fell 0.508, 0.421, 0.361, 0.274 as the weight went 0, 0.25, 0.5,
  1.0, and Haze, Dynamo, Bebop, and Wraith went the same way. Between Ivy's two
  clusters, the largest gap in mean level is 0.48 out of 4.
- **Ability order**: when each ability reached each level. Not tested when
  this ADR was written; ADR 0003 later tested and rejected it.
- **Imbue**: which ability each imbueable item was aimed at. This ADR.

Imbue was tried in two forms.

The **first form** used the target shares plus `has_imbue` and an imbue count.
It split heroes on whether players bought an imbueable item, not on what they
aimed it at. The 9 imbueable items (out of 173 shop items) were the separating
item for 27 of 33 split heroes. Kelvin, Warden, Vyper, and Sinclair each lost a
real split to a 6-11% niche.

The **conditional form** was the proposed fix: target shares only, with no
`has_imbue` or count, and players who imbued nothing placed at their hero's
mean instead of at zero.

This rule was written down before seeing the results and applied as written:

> Keep the conditional imbue block in the clustering only if no hero loses a
> split it had with build family shares alone, and the share of split heroes
> whose separating item is imbueable drops by at least half.

`scripts/compare_imbue_fits.py` fits all 38 heroes three ways in one run
(families alone, first form, conditional form) and reports each fit's
separating item.

## Decision

Imbue stays out of the clustering. It is used for naming archetypes and for
advice.

The conditional form failed both parts of the rule:

| | families | first form | conditional |
|---|---|---|---|
| heroes that split | 28 | 33 | 29 |
| separating item is imbueable | 2 (7%) | 27 (82%) | 24 (83%) |

- Nine heroes lost a split they had with families alone: Drifter, Grey Talon,
  Haze, Holliday, Lady Geist, Venator, Viscous, Vyper, Warden.
- The share didn't drop: 83% against the first form's 82%.

The families column is the control. With families alone, the separating item
is imbueable for only 2 of 28 split heroes, so the high share comes from the
block, not the heroes. Removing `has_imbue` didn't remove the effect. Target
shares only exist for players who bought an imbueable item, so the block
still moves exactly those players, and everyone else sits at their hero's mean,
which carries no information.

Next-item accuracy for both fits was measured in one run
(`scripts/score_archetype_fits.py`) on the same split and the same 20,000
held-out decisions from 20,000 matches:

| fit | top-1 | top-3 | cells in the sample |
|---|---|---|---|
| build families | 0.3779 | 0.5884 | 75 |
| conditional imbue | 0.3810 | 0.5856 | 76 |

The difference is within one standard error (0.0034). The block doesn't
improve accuracy, so nothing here argues against the rule. Both fits beat the
bigram baseline of 0.266 on the same split. The cell counts are for this
20,000-match sample; on the full table the two fits have 75 and 79 cells.

## Consequences

- `scripts/review_archetypes.py` clusters on build family shares alone, and
  the archetype files (`archetypes.parquet`, `archetype_meta.json`,
  `docs/ARCHETYPES.md`) were regenerated from that fit. `archetypes.parquet`
  came back byte-identical, because the shipped labels already came from the
  family fit. `archetype_meta.json` changed because it predated unique naming:
  eight names changed, such as Dynamo's clusters becoming "Kinetic Pulse
  Dynamo" and "Ult Dynamo".
- Every generated build still passes the staple gate: 75 of 75 cells, none
  failed or inconclusive. Median order agreement (tau) stayed at +0.809 over
  75 reliable cells, and overlap with real players stayed at mean J@12 0.415
  against a player-to-player ceiling of 0.335. Measured before and after with
  `scripts/generate_builds.py`.
- Imbue keeps its other jobs. `ability_focus` checks it first when naming a
  cluster, `deadlock build` says which ability to imbue for each imbueable
  item, and exported builds include the target. It is what tells Dynamo's two
  builds apart when their items can't.
- To reopen this, bring a block whose separating items aren't concentrated in
  the items the block is built from. `archetype.separating_item` reports the
  item so this can be checked.

## Evidence

- `docs/IMBUE-FIT-COMPARISON.md` and `.csv`: k and the separating item per hero
  under each fit.
- `scripts/compare_imbue_fits.py`: the experiment, with the rule.
- `scripts/score_archetype_fits.py`: both fits scored in one run. The scoring
  loop now lives in `evaluate.next_item_accuracy`, shared with
  `scripts/score_sequence.py`. It now stops exactly at the decision limit, so
  top-1 figures from before that change don't compare with later ones.

## Re-measured 2026-09-23

Issue #41 found that `imbues.parquet` held 2,589 abandon and draw players that
`purchases.parquet` didn't, and #40 proposed reopening this decision. Both
experiments were rerun, each in one run, on the fixed table.

The #41 fix didn't affect these experiments: `imbue.imbue_features` already
keeps only the purchase table's players. The numbers below differ from the
2026-09-07 ones because the match data is a newer pull of 25,000 matches.
Compare them with each other, not with the tables above.

| | families | first form | conditional |
|---|---|---|---|
| heroes that split | 31 | 33 | 28 |
| separating item is imbueable | 5 (16%) | 27 (82%) | 22 (79%) |

- Eight heroes lose a split they had with families alone: Billy, Drifter,
  Haze, Holliday, Paradox, Venator, Vyper, Warden.
- The share didn't drop by half: 79% against 82%.
- The control rose from 7% to 16%, and the block still makes the separating
  item imbueable five times as often.

Next-item accuracy (`scripts/score_archetype_fits.py`, 20,000 matches, the
same 20,000 decisions for both fits):

| fit | top-1 | top-3 | cells in the sample |
|---|---|---|---|
| build families | 0.3732 | 0.5790 | 79 |
| conditional imbue | 0.3712 | 0.5808 | 80 |

Again within one standard error, and both beat the bigram's 0.2647 on the same
split.

The decision stands: the conditional form fails both parts of the rule again.
`docs/IMBUE-FIT-COMPARISON.md` and its `.csv` were regenerated from this run.

## Gated per hero, 2026-09-24

#40 argued that this ADR's explanation of the failure is wrong, so the
rejection might not cover a per-hero form. The explanation says target shares
exist only for players who bought an imbueable item. But 79.6% of players
imbue, and more than 88% on 22 of 38 heroes, so for most heroes the
mean-imputed rows are not the majority. The actual structure is direction
entropy, which varies about 20 times across heroes: Paige's players split
across slots, and Wraith's aim Quicksilver Reload at slot 1 99.8% of the
time. #40 proposed giving the block only to heroes where players disagree on
where to aim an item.

The gate and the rule were posted on #40 before the run.

- **Gate.** Direction is measured per item. Pooling items would count two
  items with fixed but different targets as a contested choice. An item is
  contested on a hero when it has at least 300 imbued purchases, is bought by
  at least 20% of the hero's players, and its aim has at least 0.8 bits of
  entropy. A hero gets the block if it has a contested item and at least half
  its players imbue. The gate is binary at weight 1.0. Heroes outside it get
  no block, and the script checks that their fit is identical to families
  alone. `imbue.gated_heroes` implements it.
- **R1.** No hero loses a split it had with families alone.
- **R2.** This replaces the concentration test, since a block given only to
  heroes where these items are contested is expected to split on them. At
  least one gated hero's split must change (k differs, or adjusted Rand index
  below 0.80). More than half the changed heroes must separate on aim rather
  than on purchase: the largest gap between clusters in how often they aim a
  contested item at its usual slot (D) must exceed the largest gap in how
  often they buy it (P).
- **R3.** Held-out top-1 in the same run may not fall more than two standard
  errors below families.

The gate picked 24 heroes, not the nine #40 named. Compress Cooldown's target
is contested on almost every hero once direction is measured per item.
`scripts/compare_imbue_fits.py` ran five fits in one run. Its families,
first-form and conditional numbers match the 2026-09-23 run exactly.

| | families | conditional | gated (24 heroes) | #40's nine heroes |
|---|---|---|---|---|
| heroes that split | 31 | 28 | 34 | 32 |
| splits lost | -- | 8 | **1** (Paradox) | 0 |
| changed gated heroes split on aim | -- | -- | 19 of 23 | 8 of 9 |

Held-out next-item accuracy (`scripts/score_archetype_fits.py`, 20,000
matches, the same 20,000 decisions for both fits, bigram 0.2647):

| fit | top-1 | top-3 | cells in the sample |
|---|---|---|---|
| build families | 0.3732 | 0.5790 | 79 |
| gated imbue | 0.3741 | 0.5829 | 85 |

**The gated block stays out.** It passes R2 and R3 and fails R1 on one hero.
Families alone give Paradox three builds separated by Spirit Burn, a
non-imbueable item with a 0.66 gap. The block merges them into two, split on
Mystic Expansion. That is the conflict #40 described, where the block fights
the item features, and it happened on a hero the gate selected. The rule was
applied as written.

What this settles about the mechanism:

- **Most of the ungated block's failure came from heroes the gate excludes.**
  Six of its eight lost splits are on heroes outside the gate. Billy and
  Drifter have low imbue rates, which is where the explanation above does
  apply. Haze, Venator, Vyper and Warden aim at a fixed slot, so the block
  added dimensions with nothing to separate. Within the gate, Holliday keeps
  its split and Paradox does not.
- **On contested heroes the block splits on aim, not purchase**, for 19 of
  the 23 heroes whose split it changed. The first form's failure, splitting
  on whether a player bought the item, is not what the gated block does.
- **But it redraws the whole split, not just the part that is about aim.**
  Adjusted Rand index against families is below 0.3 on 20 of the 23 changed
  heroes, including heroes whose k did not move (Grey Talon 0.07, Mina 0.02,
  Holliday 0.02). The block does not refine the item-based builds. It
  replaces them.

#40's nine heroes pass R1 and R2 in the same run. That fit was declared a
comparison before the run, so it doesn't decide anything here. Choosing it
after seeing that the wider gate failed would be picking the gate on the
result. Promoting it needs its own run.
