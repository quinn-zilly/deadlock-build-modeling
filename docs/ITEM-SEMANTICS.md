# Naming builds from what items do, not which shop tab they're in

**Status:** implemented. The naming rule proposed here is
`src/deadlock/semantics.py`, and archetype clustering now uses build families
too. This document is the investigation behind it. Cluster numbers and
"current names" below are from the time it was written, when archetypes were
still clustered and named by shop tab.

At the time, `propose_name` in `src/deadlock/archetype.py` named a cluster
after the shop tab most of its souls went to: weapon became "Gun", spirit
"Spirit", and vitality "Tank". A Deadlock player reviewed the names and found
many of them wrong.

They were wrong because the shop tab doesn't say what an item does. Compared
with their own stats, 84 of the 170 scoreable shop items (49%) are in a tab
that doesn't match what they do, so naming by tab is close to a coin flip.

This document builds a set of families from the asset data, checks the
player's five corrections against it, and proposes a naming rule that gets
all five right.

Sources are marked: **[asset]** for a field in
`data/raw/assets/v1_assets_items__c2557efa885c5123.json`, **[web]** for a
linked page, and **[inferred]** where this document is reasoning rather than
citing.

---

## 1. Where an item's stats are

The task pointed at `upgrades[].property_upgrades[]`. That field is useful but
holds only part of the stats, and the missing part is what matters for the
items the player flagged.

| Field | What it holds | Coverage |
|---|---|---|
| `upgrades[].property_upgrades[]` | Only the bonuses the item's **tier-upgrade** adds | 179 distinct names over 251 upgrades |
| `properties{}` | The item's **full stat block**, base values included | 338 distinct non-zero keys over 173 shopable |

Siphon Bullets shows the difference **[asset]**:

```
property_upgrades: HealthStealPctHero 1.5, BulletResist 10
properties:        BaseAttackDamagePercent 15  (provided_property_type
                   MODIFIER_VALUE_WEAPON_DAMAGE_INCREASE, tooltip_section innate)
                   BulletResist 10, HealthStealPctHero 2.5, StealDuration 17
```

Its +15% weapon damage is only in `properties`. Reading `property_upgrades`
alone, Siphon Bullets has no weapon stat at all, and it is one of the items
the player flagged. So both fields have to be read.

Within `properties`, 66 distinct `provided_property_type` values
(`MODIFIER_VALUE_*`) mark the stats the game treats as real hero stats, and
`tooltip_section: "innate"` marks the always-on ones **[asset]**.

### Two traps

**`AbilityCooldown` is not cooldown reduction.** It is on 90 shop items,
including 48 of the 50 actives. On an active item it is that item's own
cooldown. As an upgrade bonus it is always negative, meaning the upgrade
shortens the item's own cooldown (Grit -25, Dispel Magic -25, Capacitor -32)
**[asset]**. No shop item has it as an innate stat. Real cooldown reduction is
`CooldownReduction`, on 7 items: Enchanter's Emblem, Compress Cooldown,
Superior Cooldown, Transcendent Cooldown, Witchmail, Spellslinger, and Mystic
Conduit **[asset]**. `AbilityDuration`, `AbilityCastRange`, `AbilityCastDelay`,
and `AbilityChannelTime` also describe the item itself. Counting them as
spirit makes every active item look like a spirit item; an early version put
Rescue Beam and Healing Nova in spirit this way.

**The automatic per-tier bonus isn't in the data.** Community guides say every
item gives a flat bonus by tier: weapon damage for weapon items, health for
vitality, and spirit power for spirit **[web:
[Dignitas](https://dignitas.gg/articles/understanding-items-in-deadlock)]**.
But only 20 of 61 vitality items list `BonusHealth`, 16 of 56 weapon items
list `BaseAttackDamagePercent`, and 9 of 56 spirit items list `TechPower`
**[asset]**. So the game adds the bonus itself, and it isn't stored per item.
This means a build with many vitality items looks tanky partly from health
the shop adds automatically, whatever the items were bought for
**[inferred]**.

---

## 2. Stats grouped into families

Counts below are how often each stat appears in `property_upgrades` across all
251 upgrades. The stat names and counts are **[asset]**; which family each
belongs to is this document's grouping **[inferred]**.

There are 179 distinct stat names. Most of the rare ones are single-item
mechanics (`BulletSplitShot`, `HealPercentPerHeadshot`,
`DeathImmunityDuration`). The common ones define the families.

### gun: 34 distinct names, 100 occurrences

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

### spirit: 30 distinct names, 114 occurrences

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

`TechRadiusMultiplier` and `TechRangeMultiplier` are weak spirit evidence:
they appear on many active items of every kind. They get weight 1, not 2, in
section 6.

### tank: 26 distinct names, 123 occurrences

| n | Stat | Example items |
|---|---|---|
| 39 | `BonusHealth` | Boundless Spirit, Bullet Lifesteal, Counterspell |
| 21 | `TechResist` | Arctic Blast, Blood Tribute, Battle Vest |
| 19 | `BulletResist` | Battle Vest, Berserker, Siphon Bullets |
| 7 | `StatusResistancePercent` | Debuff Reducer, Nullification Burst |
| 7 | `CombatBarrier` | Cloak of Opportunity, Diviner's Kevlar, Grit |
| 5 | `MeleeResistPercent` | Close Quarters, Juggernaut, Point Blank |

This family is what breaks simple naming. `BonusHealth`, `BulletResist`, and
`TechResist` are on 99 of 173 shop items (57%). They are what a mid-game item
gives you on top of its main purpose. Siphon Bullets' +10% bullet resist is an
extra on a gun item, not a reason to call the build tanky. Section 6 corrects
for this with IDF.

### melee: 5 distinct names, 10 occurrences

| n | Stat | Items |
|---|---|---|
| 3 | `MeleeDistanceScale` | Crushing Fists, Melee Charge, Runed Gauntlets |
| 3 | `BonusMeleeDamagePercent` | Crushing Fists, Lifestrike, Melee Lifesteal |
| 2 | `BonusHeavyMeleeDamage` | Crushing Fists, Melee Charge |
| 1 | `ParryCooldownReduction` | Rebuttal |
| 1 | `AmbushBonusMeleeDamage` | Shadow Weave |

Only 9 shop items have any melee stat. Because it's so specific, melee is easy
to detect once rare families are weighted up.

### support: 13 distinct names, 17 occurrences

`HealAmpCastPercent`, `HealAmpRegenPercent` (Healing Booster, Healing Tempo);
`TotalHealthRegen` (Healing Nova, Healing Rite); `HealPercentAmount` (Rescue
Beam); `HealPerStack`/`Max`/`MinStaminaRestore` (Restorative Locket); `MinHeal`
(Celestial Blessing); `Regeneration`/`HealingPerCast` (Radiant Regeneration,
Mystic Regeneration); `HealFromHero`/`HealFromNPC` (Restorative Shot);
`HealOnActivate` (Dispel Magic); `AllyPercentage`/`HealAmount` (Mystic
Conduit). 12 items, about as specific as melee.

### sustain: healing yourself, separate from support

`OutOfCombatHealthRegen` (18), `BonusHealthRegen` (4), and single-item stats
`HealthStealPctHero` (Siphon Bullets), `HealOnKill` (Healbane), `HealOnVeil`
(Veil Walker), `HealOnSuccess` (Counterspell), and
`HealLifePercentOutOfCombat` (Fortitude). This has to be separate from
support. Otherwise Siphon Bullets and Extra Regen land with Healing Tempo, and
Kelvin's support cluster can't be told apart **[inferred]**.

### mobility: 12 names, 52 occurrences

`BonusMoveSpeed` (14), `BonusSprintSpeed` (10), `Stamina` (7),
`StaminaCooldownReduction` (6), `GroundDashReductionPercent` (6).

### control: 9 names, 34 occurrences

`HealAmpReceivePenaltyPercent` and `HealAmpRegenPenaltyPercent` (7 each, anti-heal),
`SlowPercent` (5), `FireRateSlow` (4), `StunDuration` (3),
`OutgoingDamagePenaltyPercent` (3), `SilenceDuration` (1).

---

## 3. The proposed families

Eight families. Each item scores in every family it has stats for: strong
stats count 2 and weak ones 1 **[inferred]**. The typical items below are
ranked by that score. "Purity" is the share of the item's total score that
goes to this family.

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

### gun: signature items **[asset]**

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
| 3 | - | **spirit** | Quicksilver Reload, Bullet Resist Shredder |
| 2 | - | **vitality** | Siphon Bullets |

Three of the top gun items aren't in the weapon tab.

### spirit: signature items **[asset]**

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

### melee: the complete family, all 9 items **[asset]**

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

Two more items are melee by their tooltip but have no melee stat: Spirit
Strike ("When you perform a Light or Heavy Melee attack against a hero, deal
extra spirit damage") and Close Quarters (`CloseRangeBonusWeaponPower`, a gun
stat) **[asset]**. Community guides put both in melee builds
**[web: [Sportskeeda Abrams](https://www.sportskeeda.com/esports/deadlock-abrams-build-guide)]**.

### support: the complete family, all 12 items **[asset]**

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

**Gap: items that shield an ally score as tank, not support.** Guardian Ward
(`GuardianWardCombatBarrier` 250) and Divine Barrier (`CombatBarrier` 600) put
a barrier on a teammate, but their stats look the same as Plated Armor's
**[asset]**. Only the tooltip shows the difference:

> Guardian Ward: "Provide the target with a Barrier and temporary Move Speed.
> Can be self-cast. Cooldown is reduced by half when cast on someone else."
> Divine Barrier: same wording. **[asset]**

Proposed fix: add a support point for any item whose tooltip matches
`/self-cast|someone else|allied hero|friendly target|allies/i`. That catches
Guardian Ward, Divine Barrier, Rescue Beam, Healing Rite, Shrink Ray, Scourge,
Heroic Aura, and Celestial Blessing **[asset]**. (The implementation uses an
ally-word pattern plus hand-set scores for Guardian Ward and Divine Barrier;
see `semantics.TOOLTIP_OVERRIDES`.)

### tank: signature items **[asset]**

High purity only, since 57% of items have some tank stat: Return Fire
(100%), Plated Armor (100%), Spellbreaker (100%), Debuff Reducer (100%),
Unstoppable (100%), Refresher (100%, spirit slot), Echo Shard (100%, spirit
slot), Torment Pulse (100%, spirit slot), Scourge (100%, spirit slot),
Indomitable (75%), Cheat Death (60%), Blood Tribute (55%, weapon slot).

---

## 4. Checking the player's five claims

All five hold. Four are confirmed by both the asset data and community
sources, and one needed an item name corrected.

### Siphon Bullets: confirmed

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

It works through bullets: the HP steal triggers only when bullets hit (at most
every 1.2s, `ProcCooldown`), and it gives a flat +15% weapon damage. Its
family scores are tank 2, gun 2, sustain 2, a three-way tie, which is why
plain counting isn't enough.

The wiki confirms the stats and the mismatch: "+15% Weapon Damage, +10% Bullet
Resist... Siphon Bullets is a Vitality item, not a weapon or gun-build item"
**[web: [deadlock.wiki](https://deadlock.wiki/Siphon_Bullets)]**.

The clearest support for the player's claim: community Lash builds are named
"Gun Lash" and include Siphon Bullets with Headhunter, Sharpshooter, and
Quicksilver Reload
**[web: [El classico Lash Gun](https://deadlocklabs.gg/builds/lash-el-classico-lash-gun-644537/),
[car gun lash](https://deadlocklabs.gg/builds/brutus-car-gun-lash-776317/),
[Hyper the Return of Gun Lash](https://deadlocklabs.gg/builds/lash-hyper-the-return-of-gun-lash-build-598976/)]**.

Our own Lash cluster 1 agrees. Its highest-lift items are Sharpshooter,
Recharging Rush, Bullet Resist Shredder, Headhunter, and Siphon Bullets. Its
souls by tab are weapon 0.30, vitality 0.40, spirit 0.30, so naming by tab
calls it "Tank Lash", though every item in it is a gun item.

### Melee Charge and Crushing Fists: confirmed

Both are in the weapon tab **[asset]**, and Melee Charge is a component of
Crushing Fists (`Crushing Fists.component_items = ["upgrade_melee_charge"]`)
**[asset]**. Stats are in section 3. The wiki confirms "+60% Heavy Melee
Distance, +22% Melee Damage, +12% Bullet Resist... Upgrades From: Melee
Charge" **[web: [deadlock.wiki](https://deadlock.wiki/Crushing_Fists)]**.

The rest of the family is the 9 items in section 3, about 5% of the shop.

**Sinclair cluster 2 (15%)**: highest-lift items Melee Charge (+0.27),
Crushing Fists (+0.16), Melee Lifesteal, and Close Quarters. Melee Sinclair is
a real community build. The deadlock.coach guide describes a "melee bruiser"
Sinclair going Close Quarters, Melee Lifesteal, Melee Charge, then Crushing
Fists, and there is a known interaction between Crushing Fists and Rabbit Hex
**[web: [deadlock.coach Sinclair](https://deadlock.coach/en/heroes/sinclair/builds/209974),
[playdeadlock forums](https://forums.playdeadlock.com/threads/sinclairs-rabbit-hex-with-crushing-fists-procs-twice.63222/)]**.

**Abrams cluster 1 (78%)**: highest-lift items include Crushing Fists, Melee
Charge, Melee Lifesteal, Point Blank, and Close Quarters. A community guide
agrees: "Crushing Fists and Point-Blank lock and delete targets in your face",
and pinning enemies to a wall into "Heavy Melee (juiced by Crushing Fists /
Melee Charge + Spirit Strike)"
**[web: [Sportskeeda Abrams](https://www.sportskeeda.com/esports/deadlock-abrams-build-guide)]**.
Abrams cluster 0 (22%) is led by spirit items (Arcane Surge, Spirit Snatch,
Witchmail, Spirit Strike), matching the claimed spirit and melee split.

### Rescue Beam, Healing Tempo, and "Divine Ward": confirmed, one name corrected

There is no item called "Divine Ward" **[asset]**. The closest are Guardian
Ward (vitality, tier 2, 1600) and Divine Barrier (vitality, tier 4, 6400,
built from Guardian Ward). The player seems to have merged the two names. Both
do what they described.

| Item | Slot | Support evidence **[asset]** |
|---|---|---|
| Rescue Beam | vitality T3 | `HealPercentAmount` 20; "Heals a target allied hero and yourself… Can be self-cast"; `component_items: [upgrade_health_stimpak]` |
| Healing Tempo | vitality T4 | `HealAmpCastPercent` 25, `HealAmpRegenPercent` 25; "Applying heal to yourself or an ally grants the target bonus fire rate and move speed"; `component_items: [upgrade_healing_booster]` |
| Guardian Ward | vitality T2 | `GuardianWardCombatBarrier` 250; "Provide the target with a Barrier… Cooldown is reduced by half when cast on someone else" |
| Divine Barrier | vitality T4 | `CombatBarrier` 600; same clause; builds from Guardian Ward |

They form one family, linked by components: Healing Booster builds into
Healing Tempo, Guardian Ward into Divine Barrier, and Health Stimpak into
Rescue Beam and Healing Nova **[asset]**. The full list is in section 3.

Community sources describe these as Kelvin's support items: "Rescue Beam can be
used to save teammates that are further away"; "Healing Tempo is like a second
Heroic Aura for your team"; "Guardian Ward is great for mobile support"
**[web: [Mobalytics Kelvin](https://mobalytics.gg/deadlock/builds/kelvin),
[dving.net Kelvin guide](https://dving.net/guides/deadlock/kelvin-guide)]**.

Our Kelvin cluster 2 (16%) has exactly these as its highest-lift items:
Healing Tempo, Rescue Beam, Healing Booster, Healing Rite, and Guardian Ward.
Clusters 0 and 1 are both led by spirit items (Escalating Exposure, Boundless
Spirit, Mystic Reverb against Infuser, Transcendent Cooldown), matching the
claim of two spirit builds plus a support build.

### Bebop: confirmed

Cluster 0 (58%) is led by spirit items (Boundless Spirit, Mystic Reverb,
Improved Spirit, Echo Shard). Cluster 1 (42%) is led by gun items (Headhunter
+0.46 lift, Headshot Booster, Fleetfoot, Weighted Shots) but has 40% of its
souls in vitality, so naming by tab called it "Tank Bebop". Community sources
describe a weapon-damage Bebop and a spirit Bebop built around Sticky Bomb
**[web: [egamersworld](https://egamersworld.com/blog/deadlock-bebop-build-guide-YCTMv35pP)]**.

### "Tank" and "bruiser" as build names

Players mostly use "tank" and "bruiser" for hero roles (Warden is a bruiser,
Abrams soaks damage), not as build names like "gun build" or "spirit build"
**[web: [Sportskeeda Warden](https://www.sportskeeda.com/esports/deadlock-warden-build-guide),
[playdeadlock forums](https://forums.playdeadlock.com/threads/new-hero-idea-bruiser-tank.154620/)]**.
Build sites almost always use gun, spirit, melee, or support. So "Tank X"
should be rare, used only for clusters really led by survivability items, not
the default it was under tab naming **[inferred]**.

---

## 5. The 84 of 170 items in the wrong tab

For each shop item, compare the family its tab suggests (weapon to gun,
vitality to tank, spirit to spirit) with its highest-scoring family. 84 of the
170 scoreable items disagree (49%). All rows are **[asset]**.

"Naive/top" is the score of the tab's family against the score of the winning
family.

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
| T2 | Guardian Ward | mobility (see section 3 gap) | 2 vs 3 | GuardianWardCombatBarrier, BonusMoveSpeed |
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

The pattern: vitality items spill into gun (lifesteal items give weapon
damage) and support. Spirit items spill into control (every debuff) and
mobility (every hex or slow also gives the caster sprint speed). Weapon items
spill into melee and spirit (every "your bullets apply a spirit debuff" item).
These aren't edge cases; they include the most-bought items in the game.

---

## 6. The proposed naming rule

### Why plain counting isn't enough

Adding up item family scores per cluster gets Lash and Bebop right but still
fails three of the five corrections, because tank (99 items) and gun (71)
outweigh melee (9) and support (12):

| Hero | Cluster | Unweighted top family | Correct |
|---|---|---|---|
| Abrams | c1 | tank 11.7 (melee 8.2 second) | melee |
| Sinclair | c2 | tank 4.7 (melee 3.7 second) | melee |
| Kelvin | c2 | spirit 3.4 (support 2.9 third) | support |

### The fix: IDF

Weight each family by how rare it is among shop items, the usual TF-IDF
correction: `idf(f) = ln(N / items in family f)`, with N = 173 **[inferred]**:

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

A tank stat is weak evidence; a melee stat is strong evidence.

### The rule

```
score(cluster, family) = Σ over items i in the cluster's top_items:
                             max(0, prevalence_in_cluster(i) − prevalence_elsewhere(i))
                           × family_weight(i, family)
                           × idf(family)

name = "<Display(argmax family)> <hero name>"
```

Three choices:

1. **Lift, not prevalence.** `in_cluster - elsewhere` is already stored per
   item in `data/processed/archetype_meta.json`. Prevalence would name every
   cluster after the hero's staples; lift names it after what sets it apart.
   Negative lift counts as zero.
2. **Items count in every family they belong to.** Crushing Fists is melee 9,
   gun 1, and tank 2. One label per item would hide that gun and melee builds
   share Close Quarters.
3. **IDF per family, not per item.** What needs correcting is how common each
   family is.

### It gets every correction right

On the clusters in `data/processed/archetype_meta.json` at the time:

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

14 of 14, including the two Ivy names the player already considered right.

### Across all 38 heroes

64 clusters. 17 heroes had a single cluster, so there is nothing to compare
against and they keep the bare hero name.

| Label | Old (slot-share) | New (IDF rule) |
|---|---|---|
| Spirit | 27 | 24 |
| Gun | 10 | 13 |
| Tank | 10 | **2** |
| Melee | 0 | **6** |
| Support | 0 | **2** |

Duplicate names within a hero drop from 9 to 4. The new melee names are for
Abrams, Apollo, Calico, Sinclair, Viscous, and Yamato. Melee Yamato and melee
Calico are known community builds
**[web: [Deadlock Tracker melee Yamato](https://deadlocktracker.gg/builds/yamato/277099-d1vio-melee-yamato),
[Retro Calico's Melee Build](https://deadlocktracker.gg/builds/calico/253486-retro-calico-s-melee-build)]**.
Apollo and Viscous weren't checked against community sources **[inferred]**.

### How it was built

The rule is `src/deadlock/semantics.py`: `FAMILY_WEIGHTS` (stat to family and
weight), `SELF_REFERENTIAL` (stats about the item itself), the tooltip
patterns, `item_families`, `family_idf`, and `name_cluster`. It reads the raw
asset entries, because `assets.Item` doesn't keep stats or tooltips.
`archetype.propose_name` calls it with the cluster's pick rates, and names in
`data/archetype_names.json` still override it.

### Limits

- **Clusters can fit two families.** Abrams cluster 1 is both melee and gun
  (Melee Charge, Crushing Fists, Close Quarters, Point Blank, Bullet Resist
  Shredder). When the top family wins by less than about 1.3x, don't force one
  word. (Implemented: under `MIN_NAMING_MARGIN` the cluster keeps the hero
  name, and under `HYBRID_MARGIN` it gets a "Hybrid-" prefix.)
- **Stats change between patches.** The rule keys on stat names, which change
  far less than numbers, but a renamed stat would silently drop out of its
  family. A test that every `FAMILY_WEIGHTS` key still exists in the assets
  would catch that. There isn't one yet.
- **A good name doesn't make a good build.** `docs/DIAGNOSIS.md` records
  aggregate checks passing while the builds were unusable. A correct name
  says nothing about whether the cluster's generated build is right.

---

## Sources

Asset data: `data/raw/assets/v1_assets_items__c2557efa885c5123.json` (251
upgrades, 389 abilities; Valve first-party data served via deadlock-api.com).
Cluster data: `data/processed/archetype_meta.json`.

Community:
- [deadlock.wiki: Siphon Bullets](https://deadlock.wiki/Siphon_Bullets)
- [deadlock.wiki: Crushing Fists](https://deadlock.wiki/Crushing_Fists)
- [Dignitas: Understanding Items in Deadlock](https://dignitas.gg/articles/understanding-items-in-deadlock)
- [Deadlock Labs: El classico Lash Gun](https://deadlocklabs.gg/builds/lash-el-classico-lash-gun-644537/)
- [Deadlock Labs: car gun lash](https://deadlocklabs.gg/builds/brutus-car-gun-lash-776317/)
- [Deadlock Labs: Hyper the Return of Gun Lash](https://deadlocklabs.gg/builds/lash-hyper-the-return-of-gun-lash-build-598976/)
- [deadlock.coach: Sinclair builds](https://deadlock.coach/en/heroes/sinclair/builds/209974)
- [playdeadlock forums: Sinclair Rabbit Hex + Crushing Fists](https://forums.playdeadlock.com/threads/sinclairs-rabbit-hex-with-crushing-fists-procs-twice.63222/)
- [Sportskeeda: Abrams build guide](https://www.sportskeeda.com/esports/deadlock-abrams-build-guide)
- [Mobalytics: Kelvin build](https://mobalytics.gg/deadlock/builds/kelvin)
- [dving.net: Kelvin guide](https://dving.net/guides/deadlock/kelvin-guide)
- [egamersworld: Bebop build guide](https://egamersworld.com/blog/deadlock-bebop-build-guide-YCTMv35pP)
- [Deadlock Tracker: d1vio melee yamato](https://deadlocktracker.gg/builds/yamato/277099-d1vio-melee-yamato)
- [Deadlock Tracker: Retro Calico's Melee Build](https://deadlocktracker.gg/builds/calico/253486-retro-calico-s-melee-build)
- [Sportskeeda: Warden build guide](https://www.sportskeeda.com/esports/deadlock-warden-build-guide)
- [playdeadlock forums: Bruiser Tank hero idea](https://forums.playdeadlock.com/threads/new-hero-idea-bruiser-tank.154620/)
