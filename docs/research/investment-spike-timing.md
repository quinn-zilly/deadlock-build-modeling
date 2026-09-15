# Investment spike timing and item fungibility at 4,800

Resolves [#27](https://github.com/quinn-zilly/deadlock-build-modeling/issues/27):
*are items interchangeable as slot-type souls toward an investment spike, and
does when a build crosses 4,800 carry a claim worth making?*

**Short answer.** One of the three sub-questions yields a shippable claim, and
it is not the one the ticket expected. Strong players cross the spike earlier
**on the clock but not in the build** — a tempo fact, not a build-order fact.
The generated builds already cross where the population crosses, so there is no
defect to fix. And the fungibility hypothesis is **refuted with its sign
reversed**: the crossing purchase is *more* concentrated than a cost-matched
ordinary purchase, not less.

Net recommendation: **nothing new ships to the website**; one model-side note is
parked behind #31; the CONTEXT.md glossary gains a clarifying sentence.

## Inputs and what was taken as given

`data/processed/purchases.parquet` (5,095,598 rows, 296,332 player-matches),
joined to `data/processed/archetypes.parquet`, plus the 75 shipped builds in
`data/processed/site_builds.json`. No network calls.

Taken as settled and not re-measured:

- From #20: the **endpoint is not a decision**. Spirit median 16,000 (95% clear
  4,800), vitality 10,400 (93%), weapon 9,600 (83%).
- From `docs/game-mechanics.md`: P(next buy same slot) is 0.563 in the run-up,
  0.427 landing on 4,800, 0.275 just past it; 67.4% of players land exactly on
  4,800 in some slot type.

## Method

### Reconstructing per-slot investment (the absorption trap)

Cumulative investment per slot type is accumulated along each player's purchase
sequence, never from held items — 70.6% of "sold" rows are absorption, so a
held-item reading would undercount most pools.

The correctness trap is **cross-slot absorption**. Enumerating the component DAG
finds exactly the 4 relationships the mechanics doc names:

| Composite | Slot | Absorbs | Slot | Souls moved |
|---|---|---|---|---:|
| Spiritual Overflow | weapon | Spirit Lifesteal | vitality | 1,600 |
| Kinetic Dash | weapon | Extra Stamina | vitality | 800 |
| Arcane Surge | spirit | Extra Stamina | vitality | 800 |
| Ballistic Enchantment | weapon | Mystic Expansion | spirit | 800 |

**How it is accounted for:** when a purchase is a composite whose cross-slot
component the player already owns, the component's souls are *subtracted* from
its own pool and *added* to the composite's pool, and the component is dropped
from the owned set. This fired on **73,738 purchase rows** — rows that would
otherwise sit in the wrong pool and mis-date a crossing.

**Correctness check.** The accumulator reproduces the independently VERIFIED
continuation curve, which is the strongest available evidence it is right:

| Cumulative in slot after buy | n (this run) | P(next same slot) | published |
|---|---:|---:|---:|
| 800–1,599 | 630,171 | 0.442 | 0.440 |
| 1,600–3,199 | 813,662 | 0.491 | 0.492 |
| 3,200–4,799 | 565,925 | **0.563** | 0.563 |
| exactly 4,800 | 259,160 | **0.429** | 0.427 |
| 4,801–6,399 | 311,657 | **0.273** | 0.275 |
| ≥ 6,400 | 2,218,691 | 0.488 | 0.488 |

Residual differences are the absorption correction, which the published run did
not apply.

### Id hygiene

All item ids are handled as `int64`: **65 of the 156 ids present in the data
exceed 2^31** and wrap negative under int32. Items are resolved by id
throughout. `site_builds.json` stores item *names*, and the known **Silencer**
collision does appear in the generated builds — two catalogue entries,
`1113837674` and `3133167885`. They were disambiguated against the purchase
data: `1113837674` has 20,302 purchase rows and `3133167885` has **zero**, so
the name resolves unambiguously in practice. Both agree on slot type (weapon)
and cost (6,400), so investment arithmetic is unaffected either way.

### The placebo design (required for every per-cell claim)

`MIN_LIFT=0.03` was calibrated over all 296k players and is roughly the noise
floor inside a small cell, so it means nothing here. Every per-cell comparison
in this document establishes **its own floor**:

> Pool the treatment and control rows of that cell. Shuffle the treat/control
> label, holding **group sizes fixed**, and recompute the identical statistic
> with the identical code. 200 draws. The **p95 of the absolute delta** is that
> cell's floor. A cell's real delta is reported as a finding only if it exceeds
> its own floor.

Because the floor is computed per cell, a small cell gets a large floor by
construction. That is the intent — it is what killed the first result in #26.

## Sub-question 1 — does spike timing separate good builds?

First crossing of 4,800 in any slot type, per player. **296,090 of 296,332
players (99.9%) cross at least once**, which alone says crossing is not
optional. 762,339 (player, slot) crossing events.

By badge band, first crossing in any slot:

| Badge | n | median buy index | median time (s) |
|---|---:|---:|---:|
| <50 | 116,648 | 5.0 | 657 |
| 50–59 | 28,688 | 5.0 | 636 |
| 60–69 | 30,739 | 5.0 | 632 |
| 70–79 | 30,641 | 5.0 | 625 |
| 80–89 | 49,234 | 5.0 | 615 |
| 90+ | 40,140 | 5.0 | **592** |

The gradient is **monotone in time and flat in buy index**. That distinction is
the whole finding. Per slot, comparing badge <60 against badge 80+, with each
delta against its own placebo floor:

| Slot | metric | lo n | hi n | lo med | hi med | delta | placebo \|d\| p95 |
|---|---|---:|---:|---:|---:|---:|---:|
| weapon | buy index | 96,044 | 65,310 | 6 | 6 | **0** | 0.0 |
| weapon | time (s) | 96,044 | 65,310 | 814 | 704 | **−110** | 4.5 |
| vitality | buy index | 135,957 | 86,543 | 9 | 8 | −1 | 0.0 |
| vitality | time (s) | 135,957 | 86,543 | 1,046 | 946 | **−100** | 3.0 |
| spirit | buy index | 135,424 | 84,324 | 7 | 7 | **0** | 0.0 |
| spirit | time (s) | 135,424 | 84,324 | 826 | 809 | −17 | 3.0 |

Win/loss splits the same way but far weaker (time deltas −9s weapon, −24s
vitality, −24s spirit; buy-index deltas all 0).

**Is the time gradient just tempo?** Largely yes. Spearman against badge:

| Slot | n | ρ(badge, cross index) | ρ(badge, cross time) | ρ(badge, early pace) |
|---|---:|---:|---:|---:|
| weapon | 203,772 | −0.079 | −0.155 | −0.096 |
| vitality | 281,086 | −0.061 | −0.168 | −0.088 |
| spirit | 277,481 | **+0.044** | −0.036 | −0.090 |

Spirit **reverses sign**: higher-badge players cross spirit *later* in the
build. Holding early pace fixed (t5 quartile), a small badge effect on index
survives in weapon (mean 8.17 → 7.49 within the fast quartile), but the median
moves by at most one buy.

**Resolution.** Timing separates strong from weak players **on the clock**
(−110s weapon, −100s vitality, against floors of 4.5s and 3.0s) and **not in
the build** (median index delta 0 in two of three slots). Stated as an
imitation-model fact: strong players cross the spike at the same *point in
their build* as everyone else, and simply get there sooner because they earn
faster. Crossing earlier is a **consequence of tempo**, an already-known
feature, not an independent build-order instruction. Nothing here is framed as
crossing earlier causing wins, and the win-rate split is too weak to tempt it.

## Sub-question 2 — do generated builds cross as efficiently?

For each of the 75 shipped builds, cumulative per-slot investment was
reconstructed along its exported purchase order (17 items, components included)
with the same absorption-aware accumulator, and its crossing index in its
**dominant slot** (most souls) compared against the population distribution for
that exact (hero, archetype, slot).

| Measure | Value |
|---|---|
| Builds analysed | 75 |
| Crossing records (all slots) | 185 |
| Builds that cross in their dominant slot | **75 of 75** |
| Builds that never cross in the dominant slot | 0 |
| Median delta (generated index − population median) | **−1.0** |
| Mean delta | −0.56 |
| Inside the population IQR | **56 of 75** |
| Earlier than population p25 | 14 |
| Later than population p75 | 5 |

Across all slots (n=185) the median delta is **+0.0** and 147 of 185 sit inside
the IQR.

Overshoot — how far past 4,800 the crossing buy lands:

| Statistic | Souls |
|---|---:|
| min | 4,800 |
| median | 5,600 |
| p90 | 7,200 |
| max | 10,400 |
| lands **exactly** on 4,800 | **61 of 185 (33.0%)** |

The generated builds land exactly on 4,800 at 33.0% of crossings. The
population figure for comparison is the VERIFIED 67.4% of *players* landing
exactly on 4,800 in *some* slot — not the same denominator, so the two are
**not compared here**; establishing a like-for-like number would need both
sides recomputed in one run and is not required to answer this sub-question.

The five latest dominant-slot crossings, the only candidates for "dawdling":

| Hero | Archetype | Slot | gen idx | pop med | pop n | delta |
|---|---|---|---:|---:|---:|---:|
| Celeste | Hybrid-Gun Celeste | weapon | 15 | 10.0 | 1,491 | **+5** |
| The Doorman | The Doorman | spirit | 10 | 7.0 | 4,431 | +3 |
| Kelvin | Spirit Kelvin | spirit | 8 | 6.0 | 3,435 | +2 |
| Vyper | Tank Vyper | weapon | 7 | 5.0 | 1,485 | +2 |
| Venator | Venator | vitality | 9 | 7.0 | 4,300 | +2 |

**Resolution.** The model already crosses the spike about where real players do,
slightly *earlier* if anything (median −1). It does not dawdle and it does not
systematically overshoot. Only **Hybrid-Gun Celeste** is a visible outlier at
+5 buys, and a single build out of 75 is not a model defect. **No fix is
warranted**, and this closes the efficiency concern rather than opening work.

## Sub-question 3 — are items interchangeable at the crossing?

**Hypothesis:** at the purchase that lands a player on or over 4,800, item
choice is drawn from a *wider* pool than usual, because the build wants souls in
that slot and any qualifying item will do.

**Test.** Within a (hero, archetype, slot type, **exact cost**) cell, compare
the crossing purchases against non-crossing purchases *in the same cell*.
Concentration is the **HHI** over item ids; lower HHI = wider pool. Cost is
matched exactly, so a wider pool cannot be an artifact of price. Cells require
n≥30 on both sides. Every cell carries its own placebo floor.

Cost+slot+cell matched — **809 cells**:

| Outcome | Cells |
|---|---:|
| Crossing pool **wider** (clears floor) | 120 |
| Crossing pool **narrower** (clears floor) | **509** |
| Inside the placebo floor, no claim | 180 |

Median ΔHHI **+0.068**, median placebo floor 0.029.

The obvious confound is that the crossing buy sits at a characteristic point in
the build. Re-running with the control **also matched on buy-index band**
(0–3 / 4–6 / 7–9 / 10–12 / 13+) — **2,177 cells**, 736,068 crossing buys against
2,638,705 controls:

| Outcome | Cells |
|---|---:|
| Crossing pool **wider** | 414 |
| Crossing pool **narrower** | **908** |
| Inside the floor, no claim | 855 |

| Cost | Cells | Median ΔHHI | Median floor | Wider | Narrower |
|---|---:|---:|---:|---:|---:|
| 800 | 288 | +0.031 | 0.083 | 40 | 115 |
| 1,600 | 721 | −0.003 | 0.049 | 219 | 243 |
| 3,200 | 811 | **+0.064** | 0.062 | 115 | **409** |
| 6,400 | 357 | +0.054 | 0.082 | 40 | 141 |

Weighted by crossing volume: **mean HHI 0.478 at the crossing against 0.367 in
the matched control.**

**The hypothesis is refuted, and its sign is reversed.** The crossing purchase
is *more* concentrated than an ordinary cost-matched purchase at the same stage
of the build — outnumbering the opposite result more than two to one, against
per-cell placebo floors. The 1,600 band is the sole near-tie (219 wider vs 243
narrower, median ΔHHI −0.003), i.e. genuinely undecided rather than supportive.

### The named trio

The ticket names Trophy Collector, Enduring Speed and Restorative Locket — all
vitality, all tier 2, all cost 1,600, so they are a fair test.

| Item | id | purchases | crossing buys | crossing rate | median buy index |
|---|---:|---:|---:|---:|---:|
| Trophy Collector | 3074274290 | 80,544 | 6,417 | **0.080** | 4.0 |
| Enduring Speed | 2447176615 | 65,851 | 15,888 | **0.241** | 8.0 |
| Restorative Locket | 2059712766 | 26,932 | 6,170 | **0.229** | 7.0 |

Baseline crossing rate over all purchases: 0.150 (n=5,095,598).

They **are** substitutes — co-occurrence within a player runs far below
independence:

| Pair | Observed together | Expected if independent | Ratio |
|---|---:|---:|---:|
| Trophy Collector & Enduring Speed | 10,132 | 17,899 | **0.57** |
| Trophy Collector & Restorative Locket | 2,126 | 7,320 | **0.29** |
| Enduring Speed & Restorative Locket | 799 | 5,985 | **0.13** |

But they are **not interchangeable at the crossing**. Trophy Collector crosses
at 8.0% — *half* the baseline — while the other two cross at ~24%, and it is
bought four buys earlier. If the three were fungible slot-type souls chosen on
game state, their crossing rates would converge. They diverge threefold.

**Resolution.** Substitution among these items is real and is a build-family
fact, not an investment-threshold fact. The spike changes *which slot type* the
next purchase comes from — that is the VERIFIED 0.563 → 0.275 continuation
result — and **not which item within the slot**. Item identity at the crossing
is, if anything, more determined than usual.

## Recommended CONTEXT.md wording

`CONTEXT.md` already carries a "Where the rule stops" paragraph under **Slot
type** and an **Investment bonus** entry, so the tension is largely handled. Two
edits close it, and both are additive. *(Proposed only — CONTEXT.md is not
edited by this ticket.)*

**1. Append to the "Where the rule stops" paragraph under *Slot type*:**

> The two rules answer different questions. *What is this build trying to do?*
> is answered by build family, and slot type must not be used for it. *What
> should be bought next?* is a sequencing question, and there slot type is the
> load-bearing term, because the [[investment bonus]] accrues per slot type and
> nothing else. A session that reads "slot type is not playstyle" as "ignore
> slot type" has conflated the two.

**2. Append to *Investment bonus*:**

> The spike governs **which slot type** the next purchase comes from, not which
> item within it. Measured over 2,177 cost- and buy-index-matched cells, item
> choice at the crossing purchase is *more* concentrated than at an ordinary
> purchase (mean HHI 0.478 against 0.367), so there is no interchangeable pool
> of "slot-type souls" to recommend from. Crossing **timing** likewise carries
> no separate instruction: strong players reach the spike ~100s sooner but at
> the same buy index, which is [[tempo]], not build order. See
> `docs/research/investment-spike-timing.md`.

## Ship / defer / drop

| Finding | Verdict | Reasoning |
|---|---|---|
| Strong players cross ~100s earlier, same buy index | **Drop from the website** | Restates [[tempo]], already the strongest known feature. A per-build page cannot act on a clock delta the player does not control, and the buy-index delta — the thing a build page could express — is 0. |
| Generated builds cross at population median (−1, 56/75 in IQR) | **Drop (clean negative)** | No defect. Worth recording so a future session does not re-open it; nothing to ship. |
| Items are **not** interchangeable at the crossing | **Drop (clean negative, reversed sign)** | Refutes the premise. Its value is preventing a "buy any vitality item here" feature that the data contradicts. |
| Crossing time as an in-match signal | **Out of scope, note for the in-match recommender** | Running per-slot investment is knowable live and the 0.563 → 0.275 continuation is strong. That is the in-match map, not map #15. |
| Conditioning the sequence model on running per-slot investment | **Defer, blocked on #31** | The continuation asymmetry is real and the model cannot see it. But whether the sequence model accepts new conditioning **at all** is open ticket #31; this is a candidate input to that decision, not an independent change. Flagging the dependency rather than assuming it. |
| CONTEXT.md wording | **Ship** (as a doc edit, not by this ticket) | Two additive paragraphs above. |

Consistent with #20's conclusion about the endpoint, the **timing** of the spike
also yields nothing for the website. The spike remains a real and large
*mechanic*; what this ticket establishes is that it is not a real *recommendation*.

## Reproduction

Scripts were throwaway (scratchpad, not committed). The pipeline: build an
absorption-aware cumulative investment table from `purchases.parquet` (verify it
against the published continuation curve before trusting it), join
`archetypes.parquet`, then three measurements — crossing index/time by badge and
outcome with placebo floors; generated-build crossings from `site_builds.json`
against per-(hero, archetype, slot) population distributions; and per-cell HHI
at crossing versus cost- and buy-index-matched controls, each cell against its
own 200-draw shuffled-label floor.
