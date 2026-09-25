# 4. Upgrade effects and gun-routed abilities don't find archetypes

Date: 2026-09-25

## Status

Accepted.

## Context

Archetypes are found per hero by clustering on build family shares. ADR 0001
rejected ability levels and imbue targets as clustering inputs, and ADR 0003
rejected ability order and set the bar: a new input must not cost any hero a
split it had with families alone (R1). Issue #42 raised two more ability-side
signals, both read from the ability records in `/v1/assets/items`, which
nothing in the project read before.

- **Upgrade effects.** Each ability's `upgrades` list holds three tiers (1, 2
  and 5 points), and each tier's `property_upgrades` names what it adds. Two
  players who reach the same ability depth could have unlocked different
  effects.
- **Gun-routed abilities.** An ability can scale with spirit power and still
  work through the gun (Wraith's Full Auto, Infernus's Afterburn). If a
  hero's spirit spending goes into the weapon, the Spirit/Gun split behind
  archetype names might be describing the wrong thing.

Two facts shaped the test before anything was fitted.

1. **Upgrade effects are a function of ability order.** The effects a player
   has unlocked follow from which tiers they reached and when, and the
   tier-to-effect table is the same for every player on a hero. So any
   upgrade-effect feature is a reweighting of the point timeline that ADR
   0003 tested. It can only change the geometry KMeans sees, not add
   information. `upgrades.effect_features` makes this exact: it is a
   per-hero linear map of `abilities.point_order_features`, pooling the
   (slot, level) columns by the effect category each tier unlocks.
2. **A per-hero gun-routing flag can't change within-hero clustering.** It is
   the same for every player on the hero. The forms that can matter are per
   player: how much of a player's ability-point investment sits in gun-routed
   abilities (`upgrades.gun_exposure`).

The asset recount behind the second signal also changed the flag. The regex
in `docs/game-mechanics.md` matched defensive and enemy-debuff properties, and
its "41 spirit-scaling" count didn't reproduce (43 or 67, depending on the
definition). `upgrades.weapon_tier` uses the game's own weapon modifier
types, on-hit proc names, and only properties that are set, at base or by an
upgrade. By that rule, 26 signature abilities on 21 of the 38 playable heroes
scale with spirit and work through the gun.

Four candidates, each at weight 1.0:

- `effects`: exposure to each effect category, all three tiers.
- `effects_t5`: the same, 5-point tier only.
- `gunproc`: one column, spirit share × gun-routed exposure, given only to
  the 21 heroes with a gun-routed ability.
- `reroute`: no new column. On the same 21 heroes, the gun-routed part of the
  spirit share is counted as gun.

The rule was written in the script's docstring before the run and applied as
written: R1 no hero loses a split; R2 a hero gains a split (or, for the gated
fits, a gated hero's split changes); R3 the separating items don't
concentrate, with the same thresholds as ADR 0003. Held-out top-1 is the
separate check. A new conditioning key needs a demonstrated defect in
generated builds (#31).

## Decision

**Neither signal enters the clustering or the item model.**

`scripts/compare_upgrade_fits.py` fitted all 38 heroes six ways in one run.
The families control and the `order` reference reproduce ADR 0003's run
exactly: 31 splits, and `order` gains 3 and loses 4.

| | families | `effects` | `effects_t5` | `gunproc` | `reroute` |
|---|---|---|---|---|---|
| heroes that split | 31 | 30 | 28 | 28 | 32 |
| splits gained | - | 8 | 5 | 2 | 4 |
| splits lost | - | **5** | **14** | **9** | **2** |
| top separating item | Unstoppable 13% | Ricochet 7% | Rapid Recharge 18% | Rapid Recharge 14% | Rapid Recharge 12% |
| top three items | 35% | 20% | 43% | 36% | 34% |

- R1 fails for all four. `effects` loses Billy, Paradox, Rem, Venator and
  Vyper; three of those are splits `order` also loses. `reroute` comes closest
  and still loses Haze and Paradox.
- R2 and R3 pass for all four.

Held-out next-item accuracy, one run of `scripts/score_archetype_fits.py`
on the same split and the same 20,000 decisions:

| fit | top-1 | vs families | top-3 | cells in the sample |
|---|---|---|---|---|
| build families | 0.3732 | -- | 0.5790 | 79 |
| `effects` | 0.3744 | +0.0012 | 0.5807 | 79 |
| `effects_t5` | 0.3759 | +0.0027 | 0.5830 | 72 |
| `gunproc` | 0.3703 | -0.0029 | 0.5790 | 71 |
| `reroute` | 0.3732 | 0.0000 | 0.5796 | 80 |

The standard error is 0.0034 for every fit, and each difference from families
is under one standard error. All beat the bigram's 0.2647 on the same split.
The families figure matches ADR 0003's run (0.3732), because the sample,
split and decision limit are the same.

**Gun-routed heroes aren't a special case.** At a forced k=2, each hero with
a placebo floor from 20 label shuffles, the 21 gun-routed heroes don't differ
from the other 17. They split as often (0.81 against 0.82, p = 1.00), as far
above their floors (0.52 against 0.60, p = 0.18), and with as much of the gap
on gun and spirit (0.54 against 0.56, p = 0.73), by permutation tests of
10,000 draws. Within those heroes, spirit share goes with *less* investment
in the gun-routed ability (rank correlation negative on 20 of 21, median
-0.14, each above its shuffled floor). Rerouting spirit to gun flips no
archetype's Spirit/Gun name on any hero that keeps its split.

**There is no conditioning case.** Of 54 imbue targets in the 80 generated
builds, 3 aim at the ult, and all come after the ult's 5-point tier. Two
builds (Vyper 0 and 1) imbue Mercurial Magnum into Screwjab Dagger before the
build's own ability order unlocks it. That is a defect, but the ability-order
generator causes it: it unlocks Screwjab Dagger 13th, at about 23 minutes,
against a median 1.8 minutes for real players. An upgrade key in the item
model wouldn't fix it.

## Consequences

- `archetype.py` still clusters on build family shares alone. Nothing shipped
  changes.
- `src/deadlock/upgrades.py` stays as the one parser of `upgrades`, weapon
  properties and spirit scaling, with tests for the traps (a property
  listed at "0" isn't set, enemy debuffs carry weapon modifier types,
  `scale_function` not `scale`). Nothing in the shipped pipeline calls it. It
  is there for describing abilities on the site and for rechecking these
  numbers.
- `docs/game-mechanics.md` is corrected: the 41 doesn't reproduce, Kinetic
  Pulse and Dust Devil don't work through the gun, and 11 of the 26 gun-routed
  abilities get their gun effect only from an upgrade.
- Any future ability-side clustering input should note that it is a function
  of the point timeline, which ADR 0003 rejected. It needs a new source of
  per-player variation, not a new view of the same one.
- The Vyper ability-order defect is a follow-up for `abilityorder.py`.

## Evidence

- `docs/UPGRADE-FIT-COMPARISON.md`, `.csv` and `-ROSTER.csv`: k, separation,
  separating item, ARI and proposed names per hero and fit; the roster
  comparison; imbue levels; every imbue target in the generated builds.
- `scripts/compare_upgrade_fits.py`: the experiment, with the rule in its
  docstring.
- `scripts/score_archetype_fits.py --blocks families,effects,effects_t5,gunproc,reroute`:
  held-out accuracy.
- `docs/research/ability-upgrade-signals.md`: the write-up, with the source of
  each claim.
