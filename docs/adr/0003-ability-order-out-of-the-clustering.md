# 3. Ability order recommends builds; it does not find them

Date: 2026-09-15

## Status

Accepted.

## Context

Archetypes are fitted per hero by clustering on [[build family]] shares. ADR
0001 measured two ability-derived blocks and rejected both — ability **state**
at 480s, which degrades every hero tried, and **imbue**, which splits heroes on
whether a build bought one of the nine imbueable items. It reserved a third:

> **Ability order** — how far into a player's spending each ability reached
> each level. A sequence, where state at 480s is an inventory. **Never tested
> in the clustering.**

and said so again in its Consequences, so that no session could read the imbue
decision as covering this one. This ADR is that reserved measurement.

**Ability order was the one block that could clear ADR 0001's re-opening bar.**
That bar asks for "a block whose separating items are not concentrated in the
items the block is derived from". Imbue could never clear it, because direction
is only *defined* for the buyers of nine items, so the block moves exactly
those players and mean-imputes everyone else to a per-hero constant. Ability
order has no such hole: every player spends ability points, and **296,478 of
296,478 players in the purchase table carry ability rows — 100% coverage**, with
within-hero variance for all of them.

Three forms were fitted, because the shape was an open question rather than a
preference:

- **`order`** — `abilities.point_order_features` raw. Twelve columns,
  `pt_1_l2`..`pt_4_l4`: the point at which signature slot *s* reached level
  *L*, as a fraction of that player's total ability points.
- **`order_mean`** — the same twelve columns minus the hero's own mean.
- **`order_rank`** — the same twelve columns as a within-hero percentile,
  centred on 0.

**The residual forms were the proposal, and the reason for them is real.** Raw
order is largely hero-constant: a hero front-loads the same ability for almost
everyone who plays it. Measured, **hero identity carries a mean 43% of the raw
variance** across the twelve columns (range 28% on `pt_2_l4` to 57% on
`pt_3_l2`). A per-hero fit already conditions on hero, so that 43% is
re-encoded noise, and what survives the residual is where this player diverged
from their hero's habit. The mechanism was right. The block still failed.

A rule was fixed **before** the numbers were seen, and applied as written:

> R1 No hero loses a split it had under build family shares alone.
> R2 The block gains something: at least one hero gains a split.
> R3 Separating items do not concentrate — no single item carries the
> separating role for more than 25% of split heroes, and the top three do not
> exceed twice the families control measured in the same run.

`scripts/compare_order_fits.py` fits all 38 heroes four ways in one run and
reports the item carrying each fit's weakest cluster pair. It imports the
families control's code path from `scripts/compare_imbue_fits.py` rather than
reimplementing it, so the two sheets are read against the same baseline.

## Decision

**Ability order leaves the clustering.** It keeps every job it already had —
the recommended order itself (`abilityorder.py`), archetype naming through
[[ability focus]], and the ability order rendered beside the build.

All three forms failed R1, and the residual forms failed it worst:

| | families | `order` | `order_mean` | `order_rank` |
|---|---|---|---|---|
| heroes that split | 31 | 28 | 23 | 24 |
| splits gained | — | 3 | 9 | 4 |
| splits **lost** | — | **4** | **14** | **15** |
| top separating item | Unstoppable 13% | Rapid Recharge 11% | Extra Charge 13% | Rapid Recharge 12% |
| top three items | 35% | 32% | 22% | 25% |

- **R1 fails on every form.** `order_mean` loses fourteen heroes and
  `order_rank` fifteen, against the nine that condemned the conditional imbue
  block. **Billy, Haze and Venator lose their split under all three forms.**
- **R2 passes on every form**, which is what makes this a real trade rather
  than a dead feature: `order_mean` gains nine heroes. It gains less than it
  destroys.
- **R3 passes on every form, comfortably.** This is the result worth carrying
  forward. The concentration that condemned imbue — 83% of split heroes
  separating on one of nine items, against a 7% families control — **does not
  appear here at all**. Every form sits *at or below* the families control on
  both concentration measures. The structural argument for ability order was
  correct; the block fails on its merits instead.

**The residual is load-bearing, and it points the wrong way.** The 43% figure
says hero identity really is most of the raw signal, so removing it should have
sharpened the block. Instead `order` loses 4 splits and `order_mean` loses 14.
The reading: what the residual removes is not noise. A hero's own habit is the
reference frame that makes a *within-hero* order legible, and subtracting it
leaves twelve columns of low-variance spread that the family shares then have
to compete against. The block does not find playstyle; it dilutes the one that
the family shares had already found.

Held-out next-item accuracy was compared **in the same run**
(`scripts/score_archetype_fits.py --blocks`), on the same match split and the
same capped set of decisions, because separation falls whenever k rises and a
top-1 figure recorded under one configuration says nothing about one recorded
under another. Over 20,000 matches and the same 20,000 held-out decisions:

| fit | top-1 | top-3 | cells in the sample |
|---|---|---|---|
| build families | 0.3732 | 0.5790 | 79 |
| `order` | 0.3716 | 0.5792 | 78 |
| `order_mean` | 0.3729 | 0.5801 | 71 |
| `order_rank` | 0.3757 | 0.5816 | 69 |

That is a wash — the whole spread is 0.0041 where one standard error on 20,000
decisions is 0.0034. The bigram bar measured on this same split is 0.2647, and
every fit clears it. So accuracy argues neither way, and R1 decides alone.

**One number in this table is not the number ADR 0001 records.** The families
control splits **31** heroes here, where ADR 0001 reports 28. The purchase
table was re-pulled between the two runs. 31 is the control for every figure in
this ADR, and the 28 is not comparable to it — which is the point of running
both sides in one run.

## Consequences

- `archetype.py` fits on build family shares alone, unchanged. No shipped
  artifact moves: this ADR adds no block, so `archetypes.parquet`,
  `archetype_meta.json` and the 75 generated builds are untouched. Nothing
  needs regenerating.
- **ADR 0001's reserved consequence is discharged.** Ability order was the
  outstanding untested block, and it is now measured and rejected. A future
  session proposing it should read this ADR first.
- **The re-opening bar tightens, and it is no longer the concentration test.**
  Ability order passed R3 and still failed, so "separating items are not
  concentrated in the items the block is derived from" is necessary and not
  sufficient. **A new clustering block enters on R1: it must lose no hero a
  split.** This sits alongside #31's bar for a new *conditioning* signal — a
  demonstrated defect in generated builds — and neither replaces the other.
  They govern different parts of the model.
- Ability order keeps its existing jobs untouched. It is the second half of
  every recommendation, and `abilities.point_order_features` is still what
  `scripts/sweep_ability_features.py` sweeps. Rejecting it as a *clustering*
  input says nothing about it as advice, and the Ivy figure ADR 0001 quotes
  still holds — Ivy keeps k=3 under all four fits, so order does vary across
  her archetypes. It simply does not find them.
- `abilities.residual_point_order_features` is committed rather than thrown
  away. It is the measurement's apparatus and the 43% figure comes from it, so
  a session that wants to re-check the residual claim does not have to rebuild
  it. Nothing in the shipped pipeline calls it.
- **Not decided here: whether ability order belongs on the page.** The map
  carries that as an open question, and it is a presentation decision about a
  signal the tool already recommends.

## Evidence

- `docs/ORDER-FIT-COMPARISON.md` and its `.csv` — per hero, k under each of
  the four fits and the separating item behind each.
- `scripts/compare_order_fits.py` — the experiment, rule included. Its families
  control is `scripts/compare_imbue_fits.py`'s own `hero_rows`.
- `scripts/score_archetype_fits.py --blocks families,order,order_mean,order_rank`
  — all four fits scored in one run, against the baselines from that run.
- `abilities.residual_point_order_features` — the two residual forms, and the
  source of the 43% hero-variance figure.
