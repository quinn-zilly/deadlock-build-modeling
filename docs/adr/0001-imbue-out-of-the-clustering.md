# 1. Imbue names archetypes; it does not find them

Date: 2026-09-07

## Status

Accepted.

## Context

Archetypes are fitted per hero by clustering on [[build family]] shares. Two
ability-derived feature blocks have been proposed as extra input, and they are
not the same feature:

- **Ability state** — how many points each of the four signature abilities
  holds at a fixed instant, read at 480s. Measured, and rejected: adding it
  degrades the fit monotonically, with Ivy's separation falling 0.508 → 0.421 →
  0.361 → 0.274 as the block's weight went 0 → 0.25 → 0.5 → 1.0, and the same
  direction on Haze, Dynamo, Bebop and Wraith. The reason is visible directly —
  between Ivy's two clusters the largest mean ability-level gap is 0.48 of 4.
- **Ability order** — how far into a player's spending each ability reached
  each level. A sequence, where state at 480s is an inventory. **Never tested
  in the clustering.** It separates Ivy 67% against 9%, and it earns its place
  in the recommendation and the naming, where it was measured.
- **Imbue** — which ability a build points its imbueable items at. This ADR.

Imbue was put in the clustering in two forms.

The **first form** carried the direction shares plus `has_imbue` and a depth
count. It split heroes on *whether* a build bought an imbueable item rather
than on which ability it aimed at: nine imbueable items out of 173 shopable
supplied the separating item for 27 of 33 split heroes, and Kelvin, Warden,
Vyper and Sinclair each lost a genuine split when a sharp 6–11% niche displaced
their broad playstyle split.

The **conditional form** was the proposed fix. Direction only — no ownership
flag, no depth — with a build that imbued nothing placed at its hero's mean, so
that it says nothing rather than joining every other non-imbuer at the origin.

A rule was fixed **before** the numbers were seen, and applied as written:

> Keep the conditional imbue block in the clustering only if no hero loses a
> split it had under build family shares alone, **and** the concentration of
> imbueable items among the separating items drops materially.

`scripts/compare_imbue_fits.py` fits all 38 heroes three ways in one run —
families alone, first form, conditional form — and reports the item carrying
each fit's weakest cluster pair, which is the claim behind the separation
score.

## Decision

**Imbue leaves the clustering.** It serves naming and advice only.

The conditional form failed both halves of the rule:

| | families | first form | conditional |
|---|---|---|---|
| heroes that split | 28 | 33 | 29 |
| separating item is imbueable | 2 (7%) | 27 (82%) | 24 (83%) |

- **Nine heroes lose a split** they had under build families alone: Drifter,
  Grey Talon, Haze, Holliday, Lady Geist, Venator, Viscous, Vyper, Warden.
- **The concentration did not drop.** 83% against the first form's 82%, where
  the rule asked for at most half.

The build-family column is the control that makes the concentration figure mean
anything: under families alone the separating item is imbueable for 2 of 28
split heroes. Nine items out of 173 carrying five sixths of the splits is
therefore a property of the block, not of the heroes — and the conditional form
removed the ownership *columns* without removing the effect. Direction shares
are still only defined for builds that buy those items, so the block continues
to move exactly the players who bought them, and mean-imputation moves everyone
else to a per-hero constant that carries no within-hero signal at all.

Held-out next-item accuracy was compared between the two fits **in the same
run** (`scripts/score_archetype_fits.py`), on the same match split and the same
capped set of decisions, because separation falls whenever k rises and a top-1
figure recorded under one run configuration says nothing about one recorded
under another. Over 20,000 matches and the same 20,000 held-out decisions:

| fit | top-1 | top-3 | cells in the sample |
|---|---|---|---|
| build families | 0.3779 | 0.5884 | 75 |
| conditional imbue | 0.3810 | 0.5856 | 76 |

That is a wash — ±0.003 either way on 20,000 decisions, where one standard
error is 0.0034. The block does not buy accuracy, so nothing here argues
against the rule; both fits sit well above the bigram bar of 0.266 measured on
the same split. The cell counts are the fits over that 20,000-match sample, not
over the full table where the same two fits reach 75 and 79 cells; both numbers
come from this run and neither is comparable to a figure recorded elsewhere.

## Consequences

- `scripts/review_archetypes.py` fits on build family shares alone. The
  archetype artifacts — `archetypes.parquet`, `archetype_meta.json`,
  `docs/ARCHETYPES.md` — are regenerated from that fit. `archetypes.parquet`
  comes back byte-identical to the shipped one: the labels were already the
  family fit, and only the script had drifted. `archetype_meta.json` does move,
  because it had never been regenerated since archetype names were made unique
  — Dynamo's clusters ship as "Kinetic Pulse Dynamo" and "Ult Dynamo", Lady
  Geist's as "Reverb" and "Exposure", eight names in all. That is committed
  naming code catching up on a stale artifact, not a decision taken here.
- Every generated build still passes the prevalence gate: 75 of 75 cells, 0
  failed, 0 inconclusive. Order agreement is unchanged at median tau +0.809
  over 75 of 75 reliable cells, and membership against real players is
  unchanged at mean J@12 0.415 against a player-vs-player ceiling of 0.335.
  Measured before and after the change in this work, from
  `scripts/generate_builds.py`.
- Imbue keeps every job it had outside the fit: `ability_focus` reads it first
  when naming a cluster, `deadlock build` names the ability to imbue for each
  imbueable item it recommends, and the exported build carries the target. That
  is where imbue measured strongly, and it is the one signal that names
  Dynamo's two builds when the item lifts cannot.
- Ability **order** remains untested as a clustering feature. It is a different
  feature from ability state, which was tested and rejected, and this decision
  does not stand in for a measurement of it.
- Re-opening this needs a block whose separating items are not concentrated in
  the items the block is derived from. Reporting the separating item, not only
  the separation score, is what makes that checkable —
  `archetype.separating_item`.

## Evidence

- `docs/IMBUE-FIT-COMPARISON.md` and its `.csv` — per hero, k under each fit
  and the separating item.
- `scripts/compare_imbue_fits.py` — the experiment, rule included.
- `scripts/score_archetype_fits.py` — both fits scored in one run. The
  teacher-forced loop behind it moved into `evaluate.next_item_accuracy` so
  both fits and `scripts/score_sequence.py` share one definition. Its decision
  cap now stops exactly at the cap rather than at the end of the player who
  crossed it, so top-1 figures from that script recorded before this change are
  not comparable with figures recorded after it.
