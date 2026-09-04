# Naming builds from what items do, not which shop tab they sit in

`propose_name` in `src/deadlock/archetype.py:352` labels a cluster from the
slot type its souls went into — `share_weapon` → "Gun", `share_spirit` →
"Spirit", `share_vitality` → "Tank". A Deadlock player reviewed the output and
found the names often wrong.

They are wrong because **slot type is a shop tab, not a playstyle**. Measured
against the item's own stat block, **84 of the 170 scoreable shopable items —
49% — sit in a tab that does not match what they do**. Naming from the tab is
therefore close to a coin flip.

This document derives a semantic taxonomy from the asset JSON, checks the
player's five specific corrections against it, and proposes a naming rule that
reproduces all five.

Sources are marked throughout: **[asset]** for a field in
`data/raw/assets/v1_assets_items__c2557efa885c5123.json`, **[web]** for a cited
URL, **[inferred]** where this document is reasoning rather than citing.

---

## 1. Where "what an item does" actually lives

The task brief pointed at `upgrades[].property_upgrades[]`. That field is real
and useful, but on its own it is **half the picture**, and the missing half is
the half that matters for the flagged items.

| Field | What it holds | Coverage |
|---|---|---|
| `upgrades[].property_upgrades[]` | Only the bonuses the item's **tier-upgrade** adds | 179 distinct names over 251 upgrades |
| `properties{}` | The item's **full stat block**, base values included | 338 distinct non-zero keys over 173 shopable |

Siphon Bullets is the clean demonstration **[asset]**:

```
property_upgrades: HealthStealPctHero 1.5, BulletResist 10
properties:        BaseAttackDamagePercent 15  (provided_property_type
                   MODIFIER_VALUE_WEAPON_DAMAGE_INCREASE, tooltip_section innate)
                   BulletResist 10, HealthStealPctHero 2.5, StealDuration 17
```

Its **+15% Weapon Damage is in `properties` only**. Read `property_upgrades`
alone and Siphon Bullets has no weapon signal at all — exactly the item the
player flagged. **Any taxonomy must union both fields.**

A useful sub-signal inside `properties`: 66 distinct `provided_property_type`
values (`MODIFIER_VALUE_*`) mark the keys the engine treats as real character
stats, and `tooltip_section: "innate"` marks the always-on ones **[asset]**.

### Two traps in the raw fields

**`AbilityCooldown` is not cooldown reduction.** It appears on 90 shopable
items, 48 of the 50 actives. On an active it is *that item's own* cooldown; as
a `property_upgrades` bonus it is always negative, i.e. the tier-upgrade
shortening the item's own cooldown (Grit `-25`, Dispel Magic `-25`, Capacitor
`-32`) **[asset]**. Zero shopable items carry it as an innate stat. The real
global CDR stat is `CooldownReduction`, on just 7 items: Enchanter's Emblem,
Compress Cooldown, Superior Cooldown, Transcendent Cooldown, Witchmail,
Spellslinger, Mystic Conduit **[asset]**. `AbilityDuration`, `AbilityCastRange`,
`AbilityCastDelay` and `AbilityChannelTime` are self-referential the same way.
Counting them as a spirit signal makes every active item look like a spirit
item — this is what dragged Rescue Beam and Healing Nova to "spirit" in a first
unweighted pass.

**The per-tier implicit bonus is not in the JSON.** Community documentation
states each item grants a flat category bonus by tier — weapon damage for
weapon items, base health for vitality, spirit power for spirit **[web:
[Dignitas](https://dignitas.gg/articles/understanding-items-in-deadlock)]**.
Checking the asset: only 20 of 61 vitality items carry `BonusHealth`, 16 of 56
weapon items carry `BaseAttackDamagePercent`, and 9 of 56 spirit items carry
`TechPower` **[asset]**. So the implicit bonus is applied by the engine and
**not stored per-item**. This matters for the diagnosis: a vitality-heavy build
reads as "tanky" in a souls-by-slot centroid partly through health the shop
grants automatically, independent of what the player was buying those items
*for*. Slot share is therefore **partly self-fulfilling as an archetype
signal** **[inferred]**.

---

## 2. The stat vocabulary, grouped into families

Counts below are `property_upgrades` occurrences across all 251 upgrades, which
is what the brief asked to enumerate. The family assignment is this document's
**[inferred]** grouping; the stat names and counts are **[asset]**.

Full `property_upgrades` vocabulary: **179 distinct names**. The long tail is
mostly single-item mechanics (`BulletSplitShot`, `HealPercentPerHeadshot`,
`DeathImmunityDuration`). The head is where the families live.

### gun — 34 distinct names, 100 occurrences

| n | Stat | Example items |
|---|---|---|
| 18 | `BonusFireRate` | Active Reload, Battle Vest, Blood Tribute |
| 17 | `BaseAttackDamagePercent` | Armor Piercing Rounds, Battle Vest, Bullet Resist Shredder |
| 8 | `BonusClipSizePercent` | Active Reload, Escalating Resilience, Extended Magazine |
| 6 | `BulletArmorReduction` | Alchemical Fire, Bullet Resist Shredder, Disarming Hex |
| 6 | `BonusBulletSpeedPercent` | Armor Piercing Rounds, Express Shot, High-Velocity Rounds |
| 5 | `BulletLifestealPercent` | Active Reload, Bullet Lifesteal, Fury Trance |
| 4 | `BulletResistReduction` | Crippling Headshot, Crushing Fists, Stalker |
| 2 each | `WeaponPowerPerStack`, `RicochetDamagePercent`, `LongRangeBonusWeaponPower`, `CloseRangeBonusWeaponPower`, `HeadShotBonusDamage`, `CritDamagePercent`, `BonusAttackRangePercent`, `ActiveBonusFireRate`, `NonPlayerBonusWeaponPower` | |

### spirit — 30 distinct names, 114 occurrences

| n | Stat | Example items |
|---|---|---|
| 18 | `TechPower` | Boundless Spirit, Decay, Diviner's Kevlar |
| 13 | `TechRangeMultiplier` | Ballistic Enchantment, Cultist Sacrifice, Divine Barrier |
| 13 | `TechRadiusMultiplier` | Ballistic Enchantment, Cultist Sacrifice, Divine Barrier |
| 7 | `CooldownReduction` | Compress Cooldown, Enchanter's Emblem, Mystic Conduit |
| 7 | `BonusAbilityDurationPercent` | Arcane Surge, Diviner's Kevlar, Duration Extender |
| 6 | `TechArmorDamageReduction` | Escalating Exposure, Mystic Vulnerability, Spirit Rend |
| 6 | `AbilityLifestealPercentHero` | Leech, Mystic Reverb, Spirit Lifesteal |
| 5 | `SpiritPower` | Alchemical Fire, Arcane Surge, Counterspell |
| 3 each | `BonusSpirit`, `BonusAbilityCharges`, `BonusSpiritForChargedAbilities`, `TechPowerReduction` | Extra Charge, Infuser, Rapid Recharge |

Note `TechRadiusMultiplier` / `TechRangeMultiplier` are **weak** spirit
signals: they ride along on many actives regardless of build direction. They
are weighted 1, not 2, in §6.

### tank — 26 distinct names, 123 occurrences

| n | Stat | Example items |
|---|---|---|
| 39 | `BonusHealth` | Boundless Spirit, Bullet Lifesteal, Counterspell |
| 21 | `TechResist` | Arctic Blast, Blood Tribute, Battle Vest |
| 19 | `BulletResist` | Battle Vest, Berserker, Siphon Bullets |
| 7 | `StatusResistancePercent` | Debuff Reducer, Nullification Burst |
| 7 | `CombatBarrier` | Cloak of Opportunity, Diviner's Kevlar, Grit |
| 5 | `MeleeResistPercent` | Close Quarters, Juggernaut, Point Blank |

**This is the family that breaks naive naming.** `BonusHealth`, `BulletResist`
and `TechResist` are on 99 of 173 shopable items (57%) — they are what a
mid-game item gives you *in addition to* its actual purpose. Siphon Bullets'
+10% Bullet Resist is a rider on a gun item, not a reason to call the build
tanky. §6 corrects for this with IDF.

### melee — 5 distinct names, 10 occurrences

| n | Stat | Items |
|---|---|---|
| 3 | `MeleeDistanceScale` | Crushing Fists, Melee Charge, Runed Gauntlets |
| 3 | `BonusMeleeDamagePercent` | Crushing Fists, Lifestrike, Melee Lifesteal |
| 2 | `BonusHeavyMeleeDamage` | Crushing Fists, Melee Charge |
| 1 | `ParryCooldownReduction` | Rebuttal |
| 1 | `AmbushBonusMeleeDamage` | Shadow Weave |

Tiny and **highly specific** — only 9 shopable items carry any melee stat.
That specificity is the whole reason melee is recoverable.

### support — 13 distinct names, 17 occurrences

`HealAmpCastPercent`, `HealAmpRegenPercent` (Healing Booster, Healing Tempo);
`TotalHealthRegen` (Healing Nova, Healing Rite); `HealPercentAmount` (Rescue
Beam); `HealPerStack`/`Max`/`MinStaminaRestore` (Restorative Locket); `MinHeal`
(Celestial Blessing); `Regeneration`/`HealingPerCast` (Radiant Regeneration,
Mystic Regeneration); `HealFromHero`/`HealFromNPC` (Restorative Shot);
`HealOnActivate` (Dispel Magic); `AllyPercentage`/`HealAmount` (Mystic
Conduit). 12 items — as specific as melee.

### sustain — self-healing, distinct from support

`OutOfCombatHealthRegen` (18), `BonusHealthRegen` (4), plus one-offs
`HealthStealPctHero` (Siphon Bullets), `HealOnKill` (Healbane), `HealOnVeil`
(Veil Walker), `HealOnSuccess` (Counterspell),
`HealLifePercentOutOfCombat` (Fortitude). **Separating this from `support`
matters**: without the split, Siphon Bullets' HP-steal and Extra Regen land in
the same bucket as Healing Tempo, and Kelvin's support cluster stops being
distinguishable **[inferred]**.

### mobility — 12 names, 52 occurrences

`BonusMoveSpeed` (14), `BonusSprintSpeed` (10), `Stamina` (7),
`StaminaCooldownReduction` (6), `GroundDashReductionPercent` (6).

### control — 9 names, 34 occurrences

`HealAmpReceivePenaltyPercent` / `HealAmpRegenPenaltyPercent` (7 each — anti-heal),
`SlowPercent` (5), `FireRateSlow` (4), `StunDuration` (3),
`OutgoingDamagePenaltyPercent` (3), `SilenceDuration` (1).

---

## 3. The proposed taxonomy

Eight families. Each item scores into every family it feeds; defining stats
weigh 2, supporting stats weigh 1 **[inferred]**. Signature items below are
ranked by that score, with the fraction of the item's total score that goes to
this family shown as "purity".

| Family | Colloquial name | Items | Built around |
|---|---|---|---|
| `gun` | "Gun X" / "Weapon X" | 71 | weapon damage, fire rate, clip, bullet lifesteal |
| `spirit` | "Spirit X" | 60 | spirit power, cooldown reduction, charges, duration |
| `tank` | "Tank X" | 99 | health, bullet/spirit resist, barrier |
| `mobility` | (rarely a build name) | 59 | move/sprint speed, stamina, dash |
| `control` | (rarely a build name) | 36 | slow, stun, silence, anti-heal |
| `sustain` | (rarely a build name) | 35 | self regen, lifesteal |
| `support` | "Support X" | 12 | heal amp, ally heals, barriers on allies |
| `melee` | "Melee X" / "Punch X" | 9 | melee damage, heavy melee, melee distance |

### gun — signature items **[asset]**

| Score | Purity | Slot | Item |
|---|---|---|---|
| 8 | 57% | vitality | Vampiric Burst |
| 7 | 64% | weapon | Sharpshooter |
| 7 | 54% | vitality | Fury Trance |
| 6 | 75% | weapon | Glass Cannon |
| 6 | 75% | **spirit** | Mercurial Magnum |
| 6 | 75% | weapon | Active Reload |
| 6 | 67% | weapon | Frenzy |
| 6 | 60% | weapon | Headhunter |
| 6 | 60% | weapon | Escalating Resilience |
| 5 | 100% | weapon | Express Shot |
| 5 | 71% | weapon | Opening Rounds |
| 4 | 100% | weapon | Extended Magazine, Lucky Shot, Ricochet, Titanic Magazine |
| 3 | — | **spirit** | Quicksilver Reload, Bullet Resist Shredder |
| 2 | — | **vitality** | Siphon Bullets |

Note three of the top gun items are not in the weapon tab.

### spirit — signature items **[asset]**

| Score | Purity | Slot | Item |
|---|---|---|---|
| 12 | 100% | spirit | Omnicharge Signet |
| 10 | 67% | **weapon** | Spiritual Overflow |
| 8 | 100% | spirit | Rapid Recharge |
| 8 | 67% | **vitality** | Infuser |
| 6 | 75% | **vitality** | Healing Nova |
| 6 | 60% | spirit | Arcane Surge, Mystic Conduit |
| 5 | 71% | spirit | Mystic Reverb |
| 5 | 71% | **vitality** | Witchmail |
| 4 | 100% | spirit | Extra Charge |
| 4 | 67% | **vitality** | Spirit Lifesteal, Diviner's Kevlar |
| 4 | 67% | **weapon** | Spirit Rend |

### melee — the complete family, all 9 items **[asset]**

| Score | Purity | Slot | Tier | Item | Stats |
|---|---|---|---|---|---|
| 9 | 64% | weapon | T4 | **Crushing Fists** | MeleeDistanceScale, BonusMeleeDamagePercent, BonusHeavyMeleeDamage, HeavyMeleeMultiplier, LightMeleeAmmo |
| 6 | 75% | weapon | T2 | **Melee Charge** | MeleeDistanceScale, BonusMeleeDamagePercent, BonusHeavyMeleeDamage |
| 4 | 100% | vitality | T1 | Melee Lifesteal | BonusMeleeDamagePercent, LifestrikeHeal |
| 4 | 67% | weapon | T5 | Runed Gauntlets | MeleeDistanceScale, BonusMeleeDamagePercent |
| 4 | 50% | vitality | T1 | Rebuttal | ParryCooldownReduction, ParrySuccessHealPercentage |
| 2 | 20% | weapon | T3 | Shadow Weave | AmbushBonusMeleeDamage |
| 2 | 20% | vitality | T3 | Lifestrike | BonusMeleeDamagePercent |
| 2 | 18% | spirit | T3 | Spirit Snatch | BonusMeleeDamagePercent |
| 2 | 15% | vitality | T4 | Colossus | BonusMeleeDamagePercent |

Also melee-adjacent by tooltip but carrying no typed melee stat: **Spirit
Strike** ("When you perform a Light or Heavy Melee attack against a hero, deal
extra spirit damage") and **Close Quarters** (`CloseRangeBonusWeaponPower`,
typed as gun) **[asset]**. Community guides list both in melee builds
**[web: [Sportskeeda Abrams](https://www.sportskeeda.com/esports/deadlock-abrams-build-guide)]**.

### support — the complete family, all 12 items **[asset]**

| Score | Purity | Slot | Tier | Item |
|---|---|---|---|---|
| 4 | 67% | vitality | T2 | Restorative Locket |
| 4 | 57% | vitality | T2 | **Healing Booster** |
| 4 | 57% | vitality | T5 | Celestial Blessing |
| 4 | 40% | spirit | T5 | Mystic Conduit |
| 4 | 31% | vitality | T4 | **Healing Tempo** |
| 3 | 43% | spirit | T3 | Radiant Regeneration |
| 2 | 50% | vitality | T1 | Healing Rite |
| 2 | 50% | weapon | T1 | Restorative Shot |
| 2 | 33% | vitality | T3 | **Rescue Beam** |
| 2 | 33% | vitality | T3 | Dispel Magic |
| 2 | 25% | vitality | T3 | Healing Nova |
| 1 | 33% | spirit | T1 | Mystic Regeneration |

**Gap: barrier-on-ally items score `tank`, not `support`.** Guardian Ward
(`GuardianWardCombatBarrier` 250) and Divine Barrier (`CombatBarrier` 600) put
a shield on a teammate but their typed stats are indistinguishable from Plated
Armor's **[asset]**. The distinguishing evidence is in `tooltip_sections`, not
`properties`:

> Guardian Ward: "Provide the target with a Barrier and temporary Move Speed.
> Can be self-cast. **Cooldown is reduced by half when cast on someone else.**"
> Divine Barrier: same clause. **[asset]**

Recommendation in §6: add a support point for any item whose tooltip matches
`/self-cast|someone else|allied hero|friendly target|allies/i`. That catches
Guardian Ward, Divine Barrier, Rescue Beam, Healing Rite, Shrink Ray, Scourge,
Heroic Aura and Celestial Blessing **[asset]**.

### tank — signature items **[asset]**

Restricted to high purity, since the family is a 57% catch-all: Return Fire
(100%), Plated Armor (100%), Spellbreaker (100%), Debuff Reducer (100%),
Unstoppable (100%), Refresher (100%, spirit slot), Echo Shard (100%, spirit
slot), Torment Pulse (100%, spirit slot), Scourge (100%, spirit slot),
Indomitable (75%), Cheat Death (60%), Blood Tribute (55%, weapon slot).

---

## 4. Verifying the player's five claims

All five hold. Four are confirmed by both the asset data and community sources;
one needed a name correction.

### Siphon Bullets — CLAIM SUPPORTED

| Field | Value |
|---|---|
| `item_slot_type` | `vitality` **[asset]** |
| `item_tier` / `cost` | 4 / 6400 **[asset]** |
| `activation` | `passive`, `is_active_item: false` **[asset]** |
| `properties.BaseAttackDamagePercent` | **15**, `MODIFIER_VALUE_WEAPON_DAMAGE_INCREASE`, `tooltip_section: innate` **[asset]** |
| `properties.BulletResist` | 10, innate **[asset]** |
| `properties.HealthStealPctHero` | 2.5, `tooltip_is_important: true` **[asset]** |
| `property_upgrades` | `HealthStealPctHero 1.5`, `BulletResist 10` **[asset]** |
| Tooltip | "Your bullets temporarily steal Max HP from enemies." **[asset]** |

It is a **bullet-proc item**: the HP steal only fires on bullets hitting, at
`ProcCooldown` 1.2s, and it carries flat +15% weapon damage. Its family score
is `tank 2 / gun 2 / sustain 2` — a three-way tie under raw counting, which is
exactly why raw counting is not enough.

The wiki independently confirms the stat line and the category tension: "+15%
Weapon Damage, +10% Bullet Resist… Siphon Bullets is a Vitality item, not a
weapon or gun-build item"
**[web: [deadlock.wiki](https://deadlock.wiki/Siphon_Bullets)]**.

Decisive evidence for the player's claim is that community Lash builds are
**literally named** "Gun Lash" and contain Siphon Bullets alongside Headhunter,
Sharpshooter and Quicksilver Reload
**[web: [El classico Lash Gun](https://deadlocklabs.gg/builds/lash-el-classico-lash-gun-644537/),
[car gun lash](https://deadlocklabs.gg/builds/brutus-car-gun-lash-776317/),
[Hyper the Return of Gun Lash](https://deadlocklabs.gg/builds/lash-hyper-the-return-of-gun-lash-build-598976/)]**.

Our own Lash cluster 1 confirms it. Its highest-lift items are Sharpshooter,
Recharging Rush, Bullet Resist Shredder, Headhunter — and Siphon Bullets. Its
souls centroid is `weapon 0.30 / vitality 0.40 / spirit 0.30`, so slot-share
names it **Tank Lash**; every item in it says gun.

### Melee Charge and Crushing Fists — CLAIM SUPPORTED

Both are `weapon`-slot **[asset]**, and they form a coherent family with a
component edge between them: `Crushing Fists.component_items = ["upgrade_melee_charge"]`
**[asset]**. Stats in §3. The wiki confirms "+60% Heavy Melee Distance, +22%
Melee Damage, +12% Bullet Resist… Upgrades From: Melee Charge"
**[web: [deadlock.wiki](https://deadlock.wiki/Crushing_Fists)]**.

The rest of the family is the 9 items in §3. It is coherent and, at 5% of the
shopable pool, extremely specific.

**Sinclair cluster 2 (15%)**: its highest-lift items are Melee Charge (+0.27
lift), Crushing Fists (+0.16), Melee Lifesteal, Close Quarters. Melee Sinclair
is a real community build — the deadlock.coach guide covers a "melee bruiser"
Sinclair progressing Close Quarters → Melee Lifesteal → Melee Charge → Crushing
Fists, and there is a known Crushing-Fists-with-Rabbit-Hex interaction
**[web: [deadlock.coach Sinclair](https://deadlock.coach/en/heroes/sinclair/builds/209974),
[playdeadlock forums](https://forums.playdeadlock.com/threads/sinclairs-rabbit-hex-with-crushing-fists-procs-twice.63222/)]**.

**Abrams cluster 1 (78%)**: highest-lift items include Crushing Fists, Melee
Charge, Melee Lifesteal, Point Blank, Close Quarters. Confirmed
**[web: [Sportskeeda Abrams](https://www.sportskeeda.com/esports/deadlock-abrams-build-guide)]** —
"Crushing Fists and Point-Blank lock and delete targets in your face", wall-pin
into "Heavy Melee (juiced by Crushing Fists / Melee Charge + Spirit Strike)".
Abrams cluster 0 (22%) is spirit-led (Arcane Surge, Spirit Snatch, Witchmail,
Spirit Strike), matching the claimed spirit/melee split.

### Rescue Beam, Healing Tempo, "Divine Ward" — CLAIM SUPPORTED, one name corrected

**There is no item called "Divine Ward"** in the asset **[asset]**. The two
nearest are **Guardian Ward** (vitality T2, 1600) and **Divine Barrier**
(vitality T4, 6400, `component_items: ["upgrade_guardian_ward"]`) — the player
appears to have merged the two names. Both do what they described.

| Item | Slot | Support evidence **[asset]** |
|---|---|---|
| Rescue Beam | vitality T3 | `HealPercentAmount` 20; "Heals a target allied hero and yourself… Can be self-cast"; `component_items: [upgrade_health_stimpak]` |
| Healing Tempo | vitality T4 | `HealAmpCastPercent` 25, `HealAmpRegenPercent` 25; "Applying heal to yourself or an ally grants the target bonus fire rate and move speed"; `component_items: [upgrade_healing_booster]` |
| Guardian Ward | vitality T2 | `GuardianWardCombatBarrier` 250; "Provide the target with a Barrier… Cooldown is reduced by half when cast on someone else" |
| Divine Barrier | vitality T4 | `CombatBarrier` 600; same clause; builds from Guardian Ward |

They are a coherent family, tied together by the component graph (Healing
Booster → Healing Tempo; Guardian Ward → Divine Barrier; Health Stimpak →
Rescue Beam / Healing Nova) **[asset]**. Full membership in §3.

Community sources agree these are the Kelvin support kit: "Rescue Beam can be
used to save teammates that are further away"; "Healing Tempo is like a second
Heroic Aura for your team"; "Guardian Ward is great for mobile support"
**[web: [Mobalytics Kelvin](https://mobalytics.gg/deadlock/builds/kelvin),
[dving.net Kelvin guide](https://dving.net/guides/deadlock/kelvin-guide)]**.

Our Kelvin cluster 2 (16%) has exactly these as its highest-lift items —
Healing Tempo, Rescue Beam, Healing Booster, Healing Rite, Guardian Ward — and
clusters 0 and 1 are both spirit-led (Escalating Exposure, Boundless Spirit,
Mystic Reverb vs. Infuser, Transcendent Cooldown), matching the claimed
two-spirit-paths-plus-support structure.

### Bebop — CLAIM SUPPORTED

Cluster 0 (58%) is spirit-led (Boundless Spirit, Mystic Reverb, Improved
Spirit, Echo Shard); cluster 1 (42%) is gun-led (Headhunter +0.46 lift,
Headshot Booster, Fleetfoot, Weighted Shots) but has a vitality-heavy souls
centroid (`vitality 0.40`) and so is currently named "Tank Bebop". Community
sources describe exactly a weapon-damage Bebop and a spirit/Sticky-Bomb Bebop
**[web: [egamersworld](https://egamersworld.com/blog/deadlock-bebop-build-guide-YCTMv35pP)]**.

### On "Tank" and "Bruiser" as build names

The community uses "tank" and "bruiser" mostly as **hero-role** vocabulary
(Warden is a bruiser, Abrams tanks damage), not as build names on a par with
"gun build" / "spirit build"
**[web: [Sportskeeda Warden](https://www.sportskeeda.com/esports/deadlock-warden-build-guide),
[playdeadlock forums](https://forums.playdeadlock.com/threads/new-hero-idea-bruiser-tank.154620/)]**.
Build-site titles overwhelmingly use gun/spirit/melee/support. So "Tank X"
should be a **rare** label, reserved for clusters genuinely led by
survivability items, rather than the default landing spot it is today
**[inferred]**.

---

## 5. The misleading items — 84 of 170

Systematically: for each shopable item, compare the family its shop tab implies
(weapon→gun, vitality→tank, spirit→spirit) against its top-scoring stat family.
**84 of the 170 scoreable items disagree** — 49%. All rows **[asset]**.

Read "naive vs top" as the score the tab's family got versus the score the
winning family got.

### Vitality-slot items that are not tank builds (33)

| Tier | Item | Actually | Naive/top | Key stats |
|---|---|---|---|---|
| T4 | **Siphon Bullets** | gun / sustain | 2 vs 2 | BaseAttackDamagePercent 15, HealthStealPctHero |
| T4 | Vampiric Burst | **gun** | 4 vs 8 | BaseAttackDamagePercent, ActiveBonusFireRate, ActiveReloadPercent, BulletLifestealPercent |
| T3 | Fury Trance | **gun** | 4 vs 7 | BaseAttackDamagePercent, ActiveBonusFireRate, BulletLifestealPercent |
| T2 | Battle Vest | **gun** | 2 vs 4 | BaseAttackDamagePercent, BonusFireRate |
| T2 | Bullet Lifesteal | **gun** | 2 vs 4 | BaseAttackDamagePercent, BulletLifestealPercent |
| T4 | Leech | **gun / spirit** | 2 vs 4 | BaseAttackDamagePercent, BulletLifestealPercent |
| T4 | Infuser | **spirit** | 4 vs 8 | BonusSpirit 30, TechPower, AbilityLifestealPercentHero |
| T4 | Witchmail | **spirit** | 2 vs 5 | TechPower 14, CooldownReduction, CooldownReductionPerHit |
| T4 | Diviner's Kevlar | **spirit** | 2 vs 4 | TechPower 40, BonusAbilityDurationPercent |
| T3 | Healing Nova | **spirit** | 0 vs 6 | SpiritPower, TechPower, TechRadius/RangeMultiplier |
| T3 | Counterspell | **spirit** | 2 vs 4 | SpiritPower 20, SpiritPowerInnate |
| T2 | Enchanter's Emblem | **spirit** | 2 vs 4 | TechPower 15, CooldownReduction |
| T2 | Spirit Lifesteal | **spirit** | 2 vs 4 | TechPower, AbilityLifestealPercentHero |
| T4 | Phantom Strike | control / gun / spirit | 0 vs 2 | SlowPercent |
| T4 | Healing Tempo | **support** | 2 vs 4 | HealAmpCastPercent 25, HealAmpRegenPercent 25 |
| T5 | Celestial Blessing | **support** | 0 vs 4 | HealPercentAmount 60, MinHeal 400 |
| T2 | Healing Booster | **support** | 0 vs 4 | HealAmpCastPercent, HealAmpRegenPercent |
| T2 | Restorative Locket | **support** | 2 vs 4 | HealPerStack, Max/MinStaminaRestore |
| T1 | Healing Rite | mobility / support | 0 vs 2 | TotalHealthRegen, BonusSprintSpeed |
| T3 | Rescue Beam | mobility / spirit / support | 0 vs 2 | HealPercentAmount 20, BonusSprintSpeed |
| T1 | Melee Lifesteal | **melee** | 0 vs 4 | BonusMeleeDamagePercent, LifestrikeHeal |
| T4 | Inhibitor | **control** | 2 vs 6 | HealAmp penalties, OutgoingDamagePenaltyPercent |
| T2 | Healbane | **control** | 0 vs 4 | HealAmpReceive/RegenPenaltyPercent |
| T3 | Stamina Mastery | **mobility** | 0 vs 5 | Stamina, StaminaCooldownReduction, AirMoveIncreasePercent |
| T3 | Veil Walker | **mobility** | 2 vs 5 | BonusMoveSpeed, BonusSprintSpeed, InvisMoveSpeedMod |
| T2 | Trophy Collector | **mobility** | 0 vs 4 | BonusSprintSpeed, StackingBonusSprintSpeed |
| T2 | Guardian Ward | mobility (see §3 gap) | 2 vs 3 | GuardianWardCombatBarrier, BonusMoveSpeed |
| T1 | Extra Stamina | **mobility** | 0 vs 4 | Stamina, StaminaCooldownReduction |
| T5 | Seraphim Wings | **mobility** | 0 vs 4 | AirControl, StaminaCooldownReduction |
| T5 | Electric Slippers | **mobility** | 0 vs 3 | SlideScale, Stamina |
| T1 | Sprint Boots, T2 Enduring Speed | mobility | 0-1 vs 2 | BonusSprint/MoveSpeed |
| T3 | Lifestrike | **sustain** | 2 vs 4 | LifestealHeal, LifestealHealPercent |
| T1 | Extra Regen | **sustain** | 0 vs 3 | BonusHealthRegen, OutOfCombatHealthRegen |

### Spirit-slot items that are not spirit builds (29)

| Tier | Item | Actually | Naive/top | Key stats |
|---|---|---|---|---|
| T4 | **Mercurial Magnum** | **gun** | 2 vs 6 | BonusFireRate, BonusClipSizePercent, AmmoReloadPercent |
| T2 | **Quicksilver Reload** | **gun** | 0 vs 3 | BonusFireRate, AmmoReloadPercent |
| T2 | Bullet Resist Shredder | **gun** | 0 vs 3 | BaseAttackDamagePercent, BulletArmorReduction |
| T3 | Surge of Power | **gun** | 2 vs 4 | FireRateBonus, MoveWhileShooting/ZoomedPenaltyReduction |
| T5 | Shrink Ray | gun / mobility | 0 vs 2 | BonusFireRate |
| T4 | Scourge | **tank** | 0 vs 8 | BonusHealth, CombatBarrier, TechResist, StatusResistancePercent |
| T4 | Echo Shard, Refresher | **tank** | 0 vs 4 | BulletResist, TechResist |
| T3 | Torment Pulse | **tank** | 0 vs 4 | BonusHealth, MeleeResistPercent |
| T3 | Tankbuster, Silence Wave | **tank** | 0 vs 2 | BonusHealth |
| T1 | Mystic Regeneration | **tank** | 0 vs 2 | BonusHealth |
| T2 | Mystic Vulnerability | tank | 1 vs 2 | TechResist |
| T5 | Mystical Piano | **control** | 0 vs 5 | StunDuration, DazeDuration, DazeMoveSpeed |
| T4 | Lightning Scroll | **control** | 0 vs 6 | SlowPercent, MovementSpeedSlow, StunDuration |
| T4 | Arctic Blast | **control** | 0 vs 4 | SlowPercent, FreezeDuration |
| T4 | Spirit Burn | **control** | 2 vs 4 | HealAmp penalties |
| T3 | Decay | **control** | 2 vs 4 | HealAmp penalties |
| T4 | Cursed Relic | control | 0 vs 2 | OutgoingDamagePenaltyPercent |
| T1 | Golden Goose Egg | control / mobility | 0 vs 2 | OutgoingDamagePenaltyPercent, BonusSprintSpeed |
| T1 | Rusted Barrel | control / mobility / tank | 0 vs 2 | FireRateSlow |
| T2 | Cold Front | control / tank | 0 vs 2 | MovementSpeedSlow |
| T2 | Mystic Slow, Slowing Hex | **mobility** | 0 vs 4 | BonusSprintSpeed, GroundDashReductionPercent |
| T4 | Vortex Web | **mobility** | 2 vs 4 | BonusSprintSpeed, GroundDashReductionPercent |
| T4 | Ethereal Shift | mobility | 2 vs 3 | BonusMoveSpeed, FloatMoveSpeed |
| T3 | Disarming Hex | mobility / tank | 0 vs 2 | BonusSprintSpeed |
| T5 | Prism Blast | mobility | 0 vs 1 | FloatMoveSpeed |
| T3 | Radiant Regeneration | **support** | 0 vs 3 | HealingPerCast, Regeneration |

### Weapon-slot items that are not gun builds (22)

| Tier | Item | Actually | Naive/top | Key stats |
|---|---|---|---|---|
| T4 | **Crushing Fists** | **melee** | 1 vs 9 | MeleeDistanceScale, BonusMeleeDamagePercent, BonusHeavyMeleeDamage |
| T2 | **Melee Charge** | **melee** | 0 vs 6 | MeleeDistanceScale, BonusMeleeDamagePercent, BonusHeavyMeleeDamage |
| T5 | Runed Gauntlets | **melee** | 0 vs 4 | MeleeDistanceScale, BonusMeleeDamagePercent |
| T4 | Spiritual Overflow | **spirit** | 3 vs 10 | BonusSpirit 40, AbilityLifesteal, BonusAbilityDurationPercent |
| T3 | Spirit Rend | **spirit** | 0 vs 4 | AbilityLifestealPercentHero, MagicResistReduction, TechArmorDamageReduction |
| T2 | Spirit Shredder Bullets | **spirit** | 0 vs 3 | AbilityLifestealPercentHero, TechArmorDamageReduction |
| T3 | Cultist Sacrifice | **spirit** | 3 vs 4 | BonusAbilityCharges, TechRadius/RangeMultiplier |
| T3 | Alchemical Fire, T2 Mystic Shot | spirit | 1 vs 2 | SpiritPower |
| T5 | Haunting Shot | **control** | 0 vs 8 | HealAmp penalties, MovementSpeedSlow, OutgoingDamagePenalty |
| T3 | Toxic Bullets | **control** | 1 vs 4 | HealAmpReceive/RegenPenaltyPercent |
| T4 | Crippling Headshot | **control** | 1 vs 4 | HealAmp penalties |
| T3 | Hunter's Aura | control / mobility / tank | 1 vs 2 | FireRateSlow |
| T2 | Slowing Bullets | control / mobility | 1 vs 2 | SlowPercent |
| T3 | Blood Tribute | **tank** | 2 vs 6 | TechResist, StatusResistancePercent, InnateStatusResistancePercent |
| T4 | Silencer | **tank** | 1 vs 4 | TechResist, TechDamageReduction |
| T3 | Point Blank | **tank** | 2 vs 4 | BonusHealth, MeleeResistPercent |
| T2 | Weakening Headshot | tank | 1 vs 2 | BonusHealth |
| T3 | Weighted Shots | **mobility** | 3 vs 6 | BonusMoveSpeed, GroundDashReduction, StaminaCooldownReduction |
| T3 | Heroic Aura | **mobility** | 2 vs 4 | ActiveBonusMoveSpeed, BonusSprintSpeed |
| T3 | Shadow Weave | mobility | 2 vs 3 | BonusSprintSpeed, InvisMoveSpeedMod |
| T2 | Stalker | mobility / tank | 1 vs 2 | BonusMoveSpeed |
| T1 | Restorative Shot | gun / support | tie | HealFromHero, HealFromNPC |

**The pattern**: vitality leaks into gun (lifesteal items carry weapon damage)
and into support; spirit leaks into control (every debuff item) and mobility
(every hex/slow carries sprint speed for the caster); weapon leaks into melee
and into spirit (every "your bullets apply a spirit debuff" item). None of
these are edge cases — they include the highest-pick-rate items in the game.

---

## 6. The recommended naming rule

### Why raw stat counting is not enough

Scoring a cluster by summing item family scores gets Lash and Bebop right but
still fails three of the five corrections, because `tank` (99 items) and `gun`
(71) drown `melee` (9) and `support` (12):

| Hero | Cluster | Unweighted top family | Correct |
|---|---|---|---|
| Abrams | c1 | tank 11.7 (melee 8.2 second) | melee |
| Sinclair | c2 | tank 4.7 (melee 3.7 second) | melee |
| Kelvin | c2 | spirit 3.4 (support 2.9 third) | support |

### The fix: IDF

Weight each family by how rare it is across the shopable pool — the standard
TF-IDF correction, `idf(f) = ln(N / items_feeding_f)` with N = 173 **[inferred]**:

| Family | Items | IDF |
|---|---|---|
| melee | 9 | 2.96 |
| support | 12 | 2.67 |
| sustain | 35 | 1.60 |
| control | 36 | 1.57 |
| mobility | 59 | 1.08 |
| spirit | 60 | 1.06 |
| gun | 71 | 0.89 |
| tank | 99 | 0.56 |

A tank stat is cheap evidence; a melee stat is expensive evidence.

### The rule

```
score(cluster, family) = Σ over items i in the cluster's top_items:
                             max(0, prevalence_in_cluster(i) − prevalence_elsewhere(i))
                           × family_weight(i, family)
                           × idf(family)

name = "<Display(argmax family)> <hero name>"
```

Three deliberate choices:

1. **Lift, not prevalence.** `in_cluster − elsewhere` is already in
   `archetype_meta.json` per item **[asset: `data/processed/archetype_meta.json`]**.
   Raw prevalence would name every cluster after the hero's staples; lift names
   it after what makes the cluster *different*, which is what the label is for.
   Negative lift contributes nothing.
2. **Multi-family items count in every family they feed.** Crushing Fists is
   melee 9 *and* gun 1 *and* tank 2. Forcing a single label per item throws away
   the fact that gun and melee builds share Close Quarters.
3. **IDF at the family level, not the item level.** The thing that needs
   deflating is the family's prior breadth, not any individual item's.

### It reproduces every correction

Run against the live clusters in `data/processed/archetype_meta.json`:

| Hero | c | Share | Current name | Rule's name | Margin over 2nd |
|---|---|---|---|---|---|
| Lash | 0 | 54% | Spirit Lash | Spirit Lash | 3.2x |
| Lash | 1 | 46% | **Tank Lash** | **Gun Lash** | 3.3x |
| Sinclair | 0 | 47% | Spirit Sinclair | Spirit Sinclair | 5.4x |
| Sinclair | 1 | 38% | Spirit Sinclair | Spirit Sinclair | 4.1x |
| Sinclair | 2 | 15% | **Spirit Sinclair** | **Melee Sinclair** | 3.6x |
| Abrams | 0 | 22% | Spirit Abrams | Spirit Abrams | 2.9x |
| Abrams | 1 | 78% | **Tank Abrams** | **Melee Abrams** | 3.4x |
| Bebop | 0 | 58% | Spirit Bebop | Spirit Bebop | 3.5x |
| Bebop | 1 | 42% | **Tank Bebop** | **Gun Bebop** | 1.5x |
| Kelvin | 0 | 44% | Spirit Kelvin | Spirit Kelvin | 3.2x |
| Kelvin | 1 | 40% | Spirit Kelvin | Spirit Kelvin | 3.4x |
| Kelvin | 2 | 16% | **Spirit Kelvin** | **Support Kelvin** | 2.1x |
| Ivy | 0 | 46% | Spirit Ivy | Spirit Ivy | 2.2x |
| Ivy | 1 | 54% | Gun Ivy | Gun Ivy | 2.7x |

**14/14**, including the two the player already considered correct (Ivy).

### Across all 38 heroes

64 clusters; 17 are single-cluster heroes with no differential items and get no
name (they should keep the bare hero name, as today).

| Label | Old (slot-share) | New (IDF rule) |
|---|---|---|
| Spirit | 27 | 24 |
| Gun | 10 | 13 |
| Tank | 10 | **2** |
| Melee | 0 | **6** |
| Support | 0 | **2** |

Duplicate names within a hero drop from 9 to 4 — the rule separates clusters
the old one collapsed. The new melee labels are Abrams, Apollo, Calico,
Sinclair, Viscous, Yamato; melee Yamato and melee Calico are documented
community builds
**[web: [Deadlock Tracker melee Yamato](https://deadlocktracker.gg/builds/yamato/277099-d1vio-melee-yamato),
[Retro Calico's Melee Build](https://deadlocktracker.gg/builds/calico/253486-retro-calico-s-melee-build)]**.
Apollo, Viscous were not verified against community sources **[inferred]**.

### What this needs, concretely

One new module — call it `src/deadlock/semantics.py` — exporting:

```python
FAMILY_WEIGHTS: dict[str, tuple[str, int]]   # stat key -> (family, 1 or 2)
SELF_REF: frozenset[str]                     # AbilityCooldown, AbilityDuration, ...
ALLY_TOOLTIP_RE: re.Pattern                  # self-cast | someone else | allied ...

def item_families(item_id: int) -> dict[str, int]      # family -> score
def family_idf() -> dict[str, float]                   # ln(N / docfreq), over shopable
def name_cluster(top_items, hero_name) -> tuple[str, dict[str, float]]
```

`item_families` must read the raw asset entry, not the current `Item`
dataclass — `assets.py` keeps only 6 fields and drops `properties`,
`upgrades` and `tooltip_sections` entirely. Either widen `Item` with a
`stats: frozenset[str]` field populated at load, or add a parallel
`load_item_stats()` cache. The stat union per item is small (median well under
20 keys), so caching all 173 costs nothing.

`propose_name` at `archetype.py:352` then takes `prevalence` and `cluster`
instead of `centroid` — it already receives both — and returns the scored
family. Keep it a proposal: `data/archetype_names.json` overrides stay the
final word, and the score dict should be written into `archetype_meta.json`
next to the name so a reviewer can see *why* a cluster got its label.

### Known limits

- **Barrier-on-ally is unresolved in the typed stats.** Guardian Ward and
  Divine Barrier score `tank` without the tooltip regex. Implement the regex.
- **Multi-label clusters exist.** Abrams c1 is genuinely melee *and* gun (Melee
  Charge, Crushing Fists, Close Quarters, Point Blank, Bullet Resist Shredder).
  Where the margin over 2nd place is under ~1.3x, consider a compound name
  ("Melee/Gun Abrams") or flag for human review rather than forcing one word.
  Bebop c1 at 1.5x and Infernus c2 at 1.0x are the current marginal cases.
- **The taxonomy is a snapshot.** Deadlock is in active development; item stats
  change between patches. The family map keys on stat *names*, which are far
  more stable than balance numbers, but a renamed stat silently drops out of
  its family. Add a test asserting every key in `FAMILY_WEIGHTS` still appears
  in the asset, so a patch that renames one fails loudly.
- **This names clusters; it does not validate them.** Per `docs/DIAGNOSIS.md`,
  aggregate metrics passed while the builds were unusable. A correct *name* on
  a cluster does not make the cluster's recommended build correct.

---

## Sources

Asset data: `data/raw/assets/v1_assets_items__c2557efa885c5123.json` (251
upgrades, 389 abilities; Valve first-party data served via deadlock-api.com).
Cluster data: `data/processed/archetype_meta.json`.

Community:
- [deadlock.wiki — Siphon Bullets](https://deadlock.wiki/Siphon_Bullets)
- [deadlock.wiki — Crushing Fists](https://deadlock.wiki/Crushing_Fists)
- [Dignitas — Understanding Items in Deadlock](https://dignitas.gg/articles/understanding-items-in-deadlock)
- [Deadlock Labs — El classico Lash Gun](https://deadlocklabs.gg/builds/lash-el-classico-lash-gun-644537/)
- [Deadlock Labs — car gun lash](https://deadlocklabs.gg/builds/brutus-car-gun-lash-776317/)
- [Deadlock Labs — Hyper the Return of Gun Lash](https://deadlocklabs.gg/builds/lash-hyper-the-return-of-gun-lash-build-598976/)
- [deadlock.coach — Sinclair builds](https://deadlock.coach/en/heroes/sinclair/builds/209974)
- [playdeadlock forums — Sinclair Rabbit Hex + Crushing Fists](https://forums.playdeadlock.com/threads/sinclairs-rabbit-hex-with-crushing-fists-procs-twice.63222/)
- [Sportskeeda — Abrams build guide](https://www.sportskeeda.com/esports/deadlock-abrams-build-guide)
- [Mobalytics — Kelvin build](https://mobalytics.gg/deadlock/builds/kelvin)
- [dving.net — Kelvin guide](https://dving.net/guides/deadlock/kelvin-guide)
- [egamersworld — Bebop build guide](https://egamersworld.com/blog/deadlock-bebop-build-guide-YCTMv35pP)
- [Deadlock Tracker — d1vio melee yamato](https://deadlocktracker.gg/builds/yamato/277099-d1vio-melee-yamato)
- [Deadlock Tracker — Retro Calico's Melee Build](https://deadlocktracker.gg/builds/calico/253486-retro-calico-s-melee-build)
- [Sportskeeda — Warden build guide](https://www.sportskeeda.com/esports/deadlock-warden-build-guide)
- [playdeadlock forums — Bruiser Tank hero idea](https://forums.playdeadlock.com/threads/new-hero-idea-bruiser-tank.154620/)
