# AP upgrade effects and gun-routed abilities as model inputs

Answers [#42](https://github.com/quinn-zilly/deadlock-build-modeling/issues/42):
do ability upgrade effects, or abilities that work through the gun, belong in
the archetype clustering or as a conditioning key in the item model?

**Short answer.** Both are rejected as clustering inputs with their numbers,
and neither enters the model as a conditioning key. Every candidate fails R1,
the bar ADR 0003 set: `effects` loses 5 heroes' splits, `effects_t5` loses 14,
`gunproc` 9 and `reroute` 2. The gun-routed heroes don't separate differently
from the rest of the roster, and rerouting their spirit share to gun changes
no archetype's Spirit/Gun name. The generated builds have exactly one timing
defect of the kind the ticket named. It is on Vyper, and it comes from the
ability-order generator, so an upgrade key in the item model wouldn't fix
it. The asset recount also corrects `docs/game-mechanics.md`: the documented
"41" doesn't reproduce, and two of its four example abilities don't work
through the gun.

Decision: ADR 0004. Numbers: `docs/UPGRADE-FIT-COMPARISON.md` and its two
CSVs. All fit, roster and imbue numbers come from one run of
`scripts/compare_upgrade_fits.py`. Held-out accuracy comes from one run of
`scripts/score_archetype_fits.py`.

## Sources

- Asset records: `data/raw/assets/v1_assets_items__c2557efa885c5123.json`, the
  cached `/v1/assets/items` payload (fetched 2026-09-03). Abilities are the
  entries with `type == "ability"` and a `hero`. Fields read:
  `upgrades[i].property_upgrades[].{name, bonus}`, `properties.<name>.value`,
  `properties.<name>.provided_property_type`, and
  `properties.<name>.scale_function.{class_name, specific_stat_scale_type, stat_scale}`.
  `properties.<name>.scale` is empty on every property of all 285 abilities
  (0 non-empty), which confirms #21's warning.
- Player data: `data/processed/abilities.parquet` (4,412,712 ability points),
  `purchases.parquet` (5,119,990 purchases, 296,478 players), `imbues.parquet`,
  and `archetypes.parquet`. Generated builds: the 80 files in `data/builds/`
  from the last refit.
- Code: `src/deadlock/upgrades.py` (new) parses the assets.
  `scripts/compare_upgrade_fits.py` (new) runs every comparison below, and
  `scripts/score_archetype_fits.py` (extended) scores held-out accuracy.
  `tests/test_upgrades.py` covers the parsing traps.

## The asset recount

Recomputed from the raw payload, without reusing the old numbers
(`upgrades.ability_table`, `upgrades.py:215`; printed by
`compare_upgrade_fits.asset_summary`).

| Claim in `docs/game-mechanics.md` | Recount | Status |
|---|---|---|
| 285 hero ability records, 56 heroes | 285, 56 | holds |
| 220 have `upgrades`, all with 3 tiers | 220, all 3 | holds |
| 387 distinct upgrade property names | 387 | holds |
| 177 abilities with a numeric `stat_scale`, 52 heroes | 177, 52 | holds |
| 92 of 285 match the weapon regex, 45 heroes | 92, 45 | holds |
| 41 of those 92 scale with `ETechPower` | 43 by `specific_stat_scale_type == ETechPower`; 67 counting `scale_function_tech_damage` too | **doesn't reproduce** |
| Mirage's Dust Devil works through the gun | Only `TargetBulletEvasionChance: "0"`, which is defensive and never set | **wrong** |
| Dynamo's Kinetic Pulse works through the gun | `BonusFireRate` and `BulletResistReduction` listed at `"0"`. The only weapon-related upgrade is `BulletResistReduction: -15`, an enemy shred | **wrong** |
| No ability gets its weapon property only from `upgrades` | All are *listed* in `properties`, but 11 of the 26 gun-routed signature abilities get their gun effect only from an upgrade tier | **misleading** |

The regex matches defensive and enemy-debuff properties as well as weapon
ones: `FireRateSlow` on 20 abilities, `BulletResist` on 15, plus resist shred,
bullet evasion and bullet shields. So I replaced it with a rule written
before any fit ran (`upgrades.is_weapon_property`, `upgrades.py:130`;
`weapon_tier`, `:159`). A property works through the caster's gun when:

- the game tags it with a weapon modifier type in `provided_property_type`
  (`MODIFIER_VALUE_FIRE_RATE`, `..._WEAPON_DAMAGE_INCREASE`,
  `..._FLAT_BULLET_DAMAGE_POST_SCALE`, `..._AMMO_CLIP_SIZE`,
  `..._BULLET_LIFESTEAL`, and others; `WEAPON_MODIFIER_TYPES`, `:57`), or its
  name marks an on-hit proc (`PerBullet`, `CritBuildup`, `PerShot`,
  `Headshot`...; `WEAPON_NAME_RE`, `:75`),
- its name has no Slow, Debuff or Summon. That excludes Warden's
  `WeaponPowerDebuff: -25` and Doorman's `DebuffAccuracy: -40`, which carry
  weapon modifier types but act on the enemy, and Graves's `SummonFireRate`,
  and
- it is **set**: nonzero at base, or given a nonzero `bonus` by an upgrade
  tier (`is_set`, `:146`). This is the same "listed isn't set" trap
  `semantics.py` documents for items.

An ability is spirit-scaling when any property's `scale_function` names
`ETechPower` or is the `scale_function_tech_damage` class. The class matters:
Wraith's Full Auto's `MagicDamagePerBullet` has it with no stat type (`:178`).

Result: 38 of 285 abilities on 32 heroes work through the gun, 28 of them
spirit-scaling. Among the 152 signature abilities of the 38 playable heroes,
**26 abilities on 21 heroes are gun-routed** (spirit-scaling and working
through the gun). The gun effect arrives at base for 15, at the 1-point
upgrade for 5, the 2-point for 1, and the 5-point for 5 (Full Auto's
`UnlimitedAmmo`, Crackshot's `AbilityCooldownPerHeadshot`). Nine signature
abilities list a weapon property that nothing ever sets, including Kinetic
Pulse and Quantum Entanglement.

`docs/game-mechanics.md` is corrected to match.

## Signal 1: upgrade effects

### What representation is possible

A player's unlocked upgrade effects are fixed by which tiers they reached and
when, and the tier-to-effect table is the same for every player on a hero. So
**every per-player upgrade-effect feature is a function of the ability-point
timeline**, which ADR 0003 already tested as ability order. No representation
can hold information order lacks. The only way it can differ is geometry, and
KMeans is geometry-sensitive, so the test still means something.

I built two forms (`upgrades.effect_features`, `upgrades.py:305`):

- `effects`: each upgrade property name maps to one of ten categories by
  first match (weapon, shred, control, sustain, mobility, cooldown, duration,
  area, damage, other; `CATEGORY_PATTERNS`, `:89`). For category c, a player's
  value is the mean, over the hero's tiers that unlock c, of how much of their
  point sequence the tier was held for (`1 - pt_s_lL`). This pools slots by
  what they unlock, so two players who took a shred tier early through
  different abilities look alike. `tests/test_upgrades.py::TestEffectFeatures`
  checks that it is exactly a linear map of `point_order_features`.
- `effects_t5`: the same, from the 5-point tier only, because the ticket
  locates the divergence there.

Both are weighted 1.0 with `archetype.scale_block`, as in ADRs 0001 and 0003.

### Clustering result (one run, all 38 heroes)

| | families | `order` (reference) | `effects` | `effects_t5` |
|---|---|---|---|---|
| heroes that split | 31 | 28 | 30 | 28 |
| splits gained | -- | 3 | 8 | 5 |
| splits lost | -- | 4 | **5** | **14** |
| top separating item | Unstoppable 13% | Rapid Recharge 11% | Ricochet 7% | Rapid Recharge 18% |
| top three items | 35% | 32% | 20% | 43% |
| heroes whose split changed (k or ARI < 0.80) | -- | 10 | 20 | 30 |

Source: `docs/UPGRADE-FIT-COMPARISON.md`, "Verdict".

- The families and `order` columns reproduce ADR 0003's run exactly: 31
  splits, and `order` gains Abrams, Mirage and Wraith and loses Billy, Haze,
  Rem and Venator. So this run's data matches the one ADR 0003 decided on.
- `effects` loses Billy, Paradox, Rem, Venator and Vyper. Three of those
  (Billy, Rem, Venator) are ones `order` also loses, as expected of a
  projection of order. It gains eight, but R1 decides.
- `effects_t5` loses 14, including Lash, Lady Geist, Holliday and Grey Talon,
  whose family splits are among the most separated on the roster. Looking
  only at the 5-point tier removes most of the variation and replaces it with
  noise.
- R3 passes for both. Like order, and unlike imbue, the separating items
  don't concentrate.

**Rejected as a clustering block** by R1, as written.

### Imbue interaction

For every imbue, the target ability's level when the item was bought
(`compare_upgrade_fits.level_at`, `:379`, an as-of join of the imbue to the
target slot's ability points):

| target | group | not unlocked | unlocked, no upgrade | level 2-3 | 5-point tier | total |
|---|---|---|---|---|---|---|
| slots 1-3 | active | 283 (0.1%) | 10,524 (4.7%) | 80,300 (36.2%) | 130,865 (59.0%) | 221,972 |
| slots 1-3 | modifier | 366 (0.2%) | 6,838 (4.1%) | 78,215 (46.4%) | 83,267 (49.4%) | 168,686 |
| ult | active | 17 (0.6%) | 26 (0.9%) | 999 (34.7%) | 1,841 (63.9%) | 2,883 |
| ult | modifier | 852 (1.2%) | 7,037 (10.2%) | 32,700 (47.4%) | 28,387 (41.2%) | 68,976 |

#29's waste, an imbue into an ability that isn't unlocked yet, is rare: 0.1%
to 1.2%. The ticket's variant, an ult imbue bought before the ult's first
upgrade, is real but a minority: 11.4% of ult modifier imbues (7,889 of
68,976) and 1.5% of ult active imbues. That is two to three times the rate
for slots 1-3 (4-5%), which fits the ult unlocking late (a median 383s,
`docs/game-mechanics.md`). Most players have taken at least one ult upgrade
before they imbue into it.

### Conditioning: is there a defect in generated builds?

#31's bar is a defect in generated builds. The rule, written before the
check: a build's imbue is a defect if the build buys the item before its own
ability order unlocks the target, or, for an ult target, before the ult's
first upgrade, **and** fewer than half of that cell's players who imbue that
item into that slot do the same. Minutes come from the builds' own `~Nmin`
annotations, so both sides round the same way (`build_defects`, `:416`).

- 54 imbue targets across 46 of the 80 builds.
- Ult targets: 3 (Graves 0, Holliday 0, Holliday 1), all bought after the
  ult's 5-point tier. None before its first upgrade. **So the ticket's
  interaction produces no defect.**
- Bought before the build's own order unlocks the target: 2, Vyper 0 and
  Vyper 1, Mercurial Magnum into Screwjab Dagger. Only 1.1% and 1.9% of those
  cells' players do this, so by the rule these are defects.

The Vyper defect isn't in the item model. The target is right: the cells'
players aim Mercurial Magnum at slot 1 (2,683 and 1,563 imbues), and 98-99%
of them have already unlocked it when they buy. The ability order is what's
wrong. Vyper players unlock Screwjab Dagger at a
median 1.8 minutes (archetype 0, n = 3,016) and 1.7 (archetype 1, n = 1,689).
The generated order unlocks it with the 13th point, at about 23 minutes,
after maxing the other three abilities (`currency_changes` in
`data/builds/Vyper_0.json`, `Vyper_1.json`). Across all 324 unlock steps in
the 80 builds, these two are the only ones more than 5 minutes later than the
cell's median unlock. The greedy walk in `abilityorder.generate_order` never
takes a first point in Screwjab Dagger while an upgrade elsewhere scores
higher at each step.

An upgrade-effect key in the item model wouldn't fix this, so the defect
doesn't justify one. **Upgrade effects are not a conditioning key.** The
Vyper order is a follow-up for `abilityorder.py`.

A limit: `data/builds` exports held items only, so an imbueable item that is
bought and later absorbed or sold isn't checked. Imbueable items are tier 3
and 4 spirit items and are rarely components.

## Signal 2: gun-routed abilities

### A per-hero flag is moot; the per-player forms

A flag that is constant within a hero is the same value for every player
KMeans clusters on that hero, so it can't change any within-hero clustering.
The forms that could matter are per player
(`upgrades.gun_exposure`, `upgrades.py:345`). `w` is the cost-weighted share
of the player's upgrade tiers, held over their point sequence, that sit in
gun-routed abilities. It is 0 on the 17 heroes with no gun-routed ability.
Two fits use it, both gated to the 21 heroes that have one. Every other
hero's fit is checked to be identical to families (`fit_rows`, `:132`).

- `gunproc`: one extra column, spirit share × `w`.
- `reroute`: no new column. Family shares with the gun-routed part of spirit
  moved to gun (`gun + spirit·w`, `spirit·(1-w)`). This directly tests the
  ticket's worry that "Spirit Wraith" may really be spending on the gun.

### Clustering result

| | families | `gunproc` | `reroute` |
|---|---|---|---|
| heroes that split | 31 | 28 | 32 |
| splits gained | -- | Pocket, Wraith | Abrams, Mirage, Paige, Pocket |
| splits lost | -- | **9**: Celeste, Drifter, Haze, Holliday, Mina, Mirage, Paige, Paradox, Sinclair | **2**: Haze, Paradox |
| gated heroes whose split changed | -- | 19 of 21 | 14 of 21 |
| heroes whose proposed names changed | -- | 15 | 10 |
| top separating item / top three | Unstoppable 13% / 35% | Rapid Recharge 14% / 36% | Rapid Recharge 12% / 34% |

Both fail R1. **Rejected as clustering inputs.**

### Names

Naming (`archetype.propose_name`) reads item lifts, not the clustering
features, so a name can change only if membership changes. Under `reroute`,
**no archetype's Spirit/Gun label flips** on any hero that keeps its split:
Bebop and Victor keep their clusters (ARI at least 0.80). Infernus and
Vyper keep both names although about a third of assignments move (ARI 0.64
and 0.76). The ten name changes all come with a changed k or a
reshuffle that isn't about gun versus spirit: Billy's Spirit build becomes
Melee, Ivy's unnamed middle build becomes Support, Paige gains a Support
build. Wraith stays single-archetype under `reroute`. `gunproc` does split
Wraith into "Gun Wraith / Spirit Wraith", but only in a fit that loses nine
other heroes.

### Does the roster separate differently?

Every hero was fitted at a forced k=2 on families, so separations compare at
equal k. Each has a placebo floor, the largest separation over 20 shuffles of
the same labels (`roster_rows`, `:324`). Every hero's separation clears its
floor, and the highest floor is The Doorman's 0.18. Gun-routed heroes against
the other 17, permutation test on hero labels, 10,000 draws, two-sided:

| measure | gun-routed (21) | others (17) | p |
|---|---|---|---|
| share that split under families | 0.810 | 0.824 | 1.000 |
| forced k=2 separation above its floor | 0.517 | 0.602 | 0.177 |
| share of the k=2 centroid gap on gun + spirit | 0.540 | 0.559 | 0.728 |
| shop-tab vs family distance | 0.269 | 0.323 | 0.064 |

No difference at p < 0.05. Gun-routed heroes split as often, as cleanly and
along the same gun/spirit axis as everyone else.

Within gun-routed heroes, **spirit share goes with less investment in the
gun-routed ability, not more**. The rank correlation between spirit share and
`w` is negative and clears its shuffled floor on 20 of 21 heroes (median
-0.14, Ivy -0.68, Bebop -0.57, Holliday -0.45). Spirit buyers level their
other abilities first. That is the opposite of "spirit investment routes
through the gun", and it is why rerouting leaves the names alone.

### Is it the slot-type boundary?

No. The slot-type boundary in #15's Notes is about *items*: an item's shop
tab isn't what it does, and tabs still matter for investment thresholds. The
gun-routed question is about *abilities*: a scaling type isn't what the
ability wants. Measured, gun-routed heroes don't show more tab-versus-family
disagreement. If anything they show a little less (0.269 against 0.323,
p = 0.064, under the bar). The two phenomena don't overlap on the roster.

## Held-out accuracy

`scripts/score_archetype_fits.py --blocks families,effects,effects_t5,gunproc,reroute`,
20,000 matches, the same 20,000 held-out decisions for every fit:

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

This is a separate check. None of the four passed R1, so accuracy can't
bring any of them in.

## Verdicts

| signal | clustering block | conditioning key | key numbers |
|---|---|---|---|
| Upgrade effects (`effects`) | rejected, R1 | no, no defect it fixes | loses 5 splits, gains 8 |
| Upgrade effects, 5-point tier (`effects_t5`) | rejected, R1 | no | loses 14, gains 5 |
| Gun-routed, extra column (`gunproc`) | rejected, R1 | no | loses 9, gains 2 |
| Gun-routed, rerouted families (`reroute`) | rejected, R1 | no | loses 2 (Haze, Paradox), gains 4 |

Where the signals still belong: in what the site says about an ability (the
upgrade that grants an effect, from `weapon_tier` and `upgrades`), and in
naming, as a caveat on heroes like Wraith. Neither belongs in the fit.

## Follow-ups this surfaced

1. **Vyper's generated ability order unlocks Screwjab Dagger 21 minutes
   late.** It is the only such case in the 80 builds, and it makes the
   exported build imbue Mercurial Magnum into an ability the build's own
   order hasn't unlocked. The fix is in `abilityorder.generate_order`, for
   example forcing unlocks the way `build.py` forces staples.
2. **Wraith splits under `gunproc`** into Gun and Spirit builds. A gate of
   Wraith alone would be picking the gate on the result, as ADR 0001's
   addendum warns. If the Wraith split is worth pursuing, it belongs with
   #57 (refine inside archetypes) and #28/#38 (single-archetype heroes), with
   its own rule set before the run.
3. **The code has no `ult` build family**, though `CONTEXT.md` defines one
   since #61. `semantics.FAMILIES` stops at mobility. The tab-versus-family
   measure here pairs the spirit tab with spirit only.
4. For the site (presentation question): when an ability's effect arrives
   with an upgrade (Full Auto's unlimited ammo at the 5-point tier), say so.
   `upgrades.weapon_tier` makes that a lookup.
