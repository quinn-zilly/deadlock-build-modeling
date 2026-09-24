# Ability focus: another way to name builds, and its limits

**Status:** a record of an investigation. Some of it has changed since:

- `kits.py` now reads ability descriptions, with its own tag set (burst, dot,
  cc, and so on) rather than the eleven tags here.
- Section 4 found that ability levels can't separate same-family builds.
  Later work found that the order abilities are maxed in does differ between
  archetypes (Ivy 67% against 9%, Holliday 38% against 1%), though it still
  doesn't find them (ADR 0003). Ability focus is used for naming, from imbue
  targets first and the ability maxed first second.
- Archetype counts here are from the time. Dynamo now has two archetypes.

`semantics.name_cluster` names a build after its items' families. That gives
one name per family per hero, so it can't tell apart two builds of the same
family on one hero. Three heroes had exactly that problem
**[measured, `archetype_meta.json`]**:

| Hero | k | Archetypes | Colliding family |
|---|---|---|---|
| Venator | 2 | Hybrid-Gun Venator, Gun Venator | Gun |
| Celeste | 3 | Spirit Celeste, Celeste, Hybrid-Spirit Celeste | Spirit |
| Drifter | 3 | Melee Drifter, Hybrid-Melee Drifter, Gun Drifter | Melee |

A player suggested naming them by ability focus: naming a spirit build after
the ability it is built around, like "ult Dynamo" and "stomp Dynamo". This
document tests that idea. It has one big positive finding and one clear
negative one.

**Positive:** abilities do have description text, in a field the code didn't
read at the time. All 38 playable heroes' abilities are fully described, and
tags built from that text reproduce three of the player's six hero groupings
exactly.

**Negative:** ability levels can't separate the three same-family builds. On
their own they reach AUC 0.68-0.82, but they add at most +0.007 over items,
because players max the same one or two abilities first whatever the build.

Sources are marked: **[asset]** for a field in
`data/raw/assets/v1_assets_items__c2557efa885c5123.json`, **[web: URL]** for a
linked page, **[measured]** for numbers computed from the parquet files, and
**[inferred]** where this document is reasoning rather than citing.

---

## 1. Ability text is in `description`, not `tooltip_sections`

The task assumed abilities have no description text, because
`semantics.tooltip_text()` returns nothing for all 221 signature abilities.
That result is right but the conclusion is wrong: `tooltip_text` reads
`tooltip_sections`, which only items have. Abilities keep their text in a
different field.

### Every top-level field on the 389 ability entries **[asset]**

| Field | Present | Non-empty | What it holds |
|---|---|---|---|
| `id`, `class_name`, `type` | 389 | 389 | identity |
| `name` | 389 | 388 | display name |
| `properties` | 389 | 388 | stats, with annotations (section 1.2) |
| `ability_type` | 389 | 389 | `signature` \| `ultimate` \| others |
| **`description`** | **389** | **211** | **the ability text, see below** |
| `heroes` | 389 | 285 | list of hero ids |
| `image`, `image_webp` | 371 | 371 | art |
| **`behaviours`** | **360** | **360** | 56 engine flags (section 1.3) |
| `boss_damage_scale` | 287 | 287 | float |
| `hero` | 285 | 285 | owning hero id |
| `upgrades` | 285 | 276 | the 3 AP tiers, as `property_upgrades` |
| **`tooltip_details`** | **250** | **249** | `info_sections[].loc_string`, a fallback text |
| `start_trained` | 389 | 110 | bool |
| `update_time` | 210 | 134 | int |
| `videos` | 131 | 131 | clip URLs |
| `dependent_abilities` | 31 | 24 | recast/sub-ability links |
| `weapon_info` | 388 | **0** | always empty |
| `grant_ammo_on_cast` | 1 | 1 | one entry |

No ability has a `tooltip_sections`, `damage_type`, or `targeting` field.
`weapon_info` is on 388 entries and empty on all of them.

### 1.1 How much text there is

Only 152 of the 221 signature abilities belong to a playable hero. The other
69 belong to the 19 disabled or unfinished heroes. For the 38 playable heroes
the mapping is complete: 38 heroes times 4 slots is 152, with no gaps
**[measured]**.

`description` is a dict with several sub-keys **[asset]**:

| Sub-key | Count (of 152) | Content |
|---|---|---|
| `desc` | 147 | the ability's main description |
| `t3_desc` | 139 | what the **third** AP upgrade does, in prose |
| `t2_desc` | 106 | second AP upgrade |
| `t1_desc` | 63 | first AP upgrade |
| `quip` | 103 | flavour text, not mechanical |
| `active` / `passive` | 3 / 3 | split text where an ability has both halves |

Reading `desc`, `active`, and `passive`, then falling back to
`tooltip_details.info_sections[].loc_string`, gives text for 151 of 152
signature abilities **[measured]**. The five without `desc`:

| Hero | Ability | Recovered from |
|---|---|---|
| Shiv | Killing Blow | `description.active` + `.passive` |
| Drifter | Bloodscent | `description.active` + `.passive` |
| Graves | Borrowed Decree | `info_sections` |
| Silver | Boot Kick | `info_sections` |
| **Mina** | **Rake** | **nothing: unresolved key** |

Mina's Rake is the only gap. Its `info_sections` holds the raw localization
key `#ability_vampirebat_steallife_desc`, so the asset data doesn't include
that text at all **[asset]**. It is the one ability whose behaviour can't be
read from the assets.

The text is HTML, with inline `<svg>` damage-type icons (one is 4 KB) and
`<span class="inline-attribute-label SpiritDamage">` markers. Removing the
`<svg>` blocks and then all other tags leaves clean text.
`semantics.tooltip_text` already does exactly this, just on the wrong field.

This was the most useful finding of the task. Item naming relies heavily on
tooltips (most support evidence comes from `_tooltip_families`). The same
kind of evidence for abilities was thought to be missing and is actually
complete.

### 1.2 `properties` has few useful stat names but good annotations

The 152 abilities have 978 distinct stat names, mostly one-off details
(`FallSpeedMax`, `DampingFactor`, `TossSpeed`). Only 11 names appear on more
than 20 abilities, and the most common are engine plumbing:
`AbilityUnitTargetLimit` (152 of 152), `AbilityCooldown` (143),
`ChannelMoveSpeed` (138) **[measured]**. Stat names alone are mostly noise,
which is why `semantics.hero_ability_families`, which read them, was weak at
the time. (It now reads `kits.hero_kits`, which uses the description text.)

Three annotations in `properties` are much more useful than the names:

**`css_class`**: 22 hand-picked values the game's UI uses to color each
number **[asset]**:

| css_class | Abilities | css_class | Abilities |
|---|---|---|---|
| cooldown | 144 | slow | 41 |
| charge_cooldown | 143 | healing | 29 |
| move_speed | 140 | damage | 17 |
| duration | 121 | bullet_damage | 17 |
| cast | 119 | health | 11 |
| **tech_damage** | **109** | fire_rate | 8 |
| distance | 101 | melee_damage | 3 |
| range | 59 | combat_barrier | 1 |

`tech_damage`, `bullet_damage`, and `melee_damage` are the game's own
damage-type markers, a far clearer signal than the 978 stat names.

**`provided_property_type`**: 46 `MODIFIER_VALUE_*` values marking stats the
game treats as real hero modifiers, most often
`MODIFIER_VALUE_MOVEMENT_SPEED_SLOW_PERCENT` (31) and
`MODIFIER_VALUE_MOVEMENT_SPEED_MAX` (18) **[asset]**.

**`scale_function.specific_stat_scale_type`**: which stat an ability scales
with (`ETechPower`, `ETechCooldown`), and `stat_scale`, the multiplier. This
is how the assets say "this ability scales with Spirit Power at 0.525".

### 1.3 `behaviours` is mostly input handling

56 distinct flags on 145 of 152 abilities **[asset]**. Most are about input
(`DONT_INTERRUPT_SLIDE_ON_CAST` 67, `CAN_SET_QUICK_CAST` 42) and say nothing
about playstyle. Four are useful:

| Flag | Count | Meaning |
|---|---|---|
| `_CHANNELLED` | 31 | ability is channelled |
| `_MOVEMENT` | 26 | ability moves the caster |
| `_PROJECTILE` | 34 | fires a projectile |
| `_CAN_HEAL_PLAYERS` | 4 | can heal another player |

`_CAN_HEAL_PLAYERS` says directly that an ability heals someone else, the
ally-or-self distinction `ITEM-SEMANTICS.md` needed a tooltip pattern for.

### 1.4 Checked against community sources

Where checked, the asset text matches community sources word for word:

- Dynamo's four abilities and the Singularity ultimate text match the wiki
  **[web: https://deadlock.wiki/Dynamo]**.
- Kelvin's Frost Grenade "heals allies" and Frozen Shelter "allies gain rapid
  regeneration" match **[web: https://deadlock.wiki/Kelvin]**.
- Venator's Consecrating Grenade, Gutshot, and Ira Domini match a third-party
  guide closely enough to come from the same text
  **[web: https://mobalytics.gg/deadlock/venator-guide]**.
- Celeste's four abilities match **[web: https://deadlock.wiki/Celeste]**.

No community source contradicted the assets, so the assets are the main
source below and the web is a cross-check **[inferred]**.

---

## 2. Tags for abilities

Eleven tags, read from the text and backed up by the typed fields. As in
`ITEM-SEMANTICS.md`, the text says what an ability is for, the stats say which
numbers change, and when they disagree the text wins.

A first attempt made mistakes that led to two rules **[measured]**:

1. **`css_class` alone isn't enough.** Abrams' Siphon Life has css `healing`
   but only heals Abrams. Warden's Alchemical Flask has `bullet_damage` but
   lowers the enemy's. Every tag except `spirit_burst` now needs a text match,
   and the typed field only adds weight.
2. **`spirit_burst` is the exception.** Many descriptions just say "damaging
   enemies", and `css_class: tech_damage` gives the damage type. So for this
   one tag, `tech_damage` counts on its own.

A tag scores 2 when the text and the typed field agree, and 1 on text alone.

### Coverage over the 152 signature abilities **[measured]**

| Tag | Abilities | % | Justified by |
|---|---|---|---|
| spirit_burst | 109 | 72% | css `tech_damage`; "dealing spirit damage" |
| control | 82 | 54% | css `slow`; `SlowPercent`/`StunDuration`/`SilenceDuration`; stun/silence/root/pull text |
| mobility | 64 | 42% | behaviour `_MOVEMENT`; css `move_speed`; dash/leap/teleport/fly text |
| tank | 40 | 26% | css `combat_barrier`/`bullet_armor_up`; `BulletResist`/`TechResist`; barrier/resist text |
| gun | 21 | 14% | css `bullet_damage`/`fire_rate`; `BonusFireRate`; "your bullets"/"weapon damage" gained by *you* |
| sustain | 18 | 12% | css `healing` + self-heal text ("healing for a portion", lifesteal) |
| dot | 17 | 11% | `DPS`/`TickRate`/`BurnDuration`; burn/bleed/over-time text |
| support | 17 | 11% | behaviour `_CAN_HEAL_PLAYERS`; css `healing` + explicit ally recipient |
| channel | 16 | 11% | behaviour `_CHANNELLED`; "channel"/"charge up" |
| summon | 14 | 9% | summon/deploy/turret/Ghoul/Assistant/familiar text |
| melee | 11 | 7% | css `melee_damage`; "melee damage"/"heavy melee" |

150 of 152 abilities get at least one tag. The two that don't are Shiv's
Bloodletting (delays incoming damage, which no tag covers) and Sinclair's
Audience Participation (copies an enemy ultimate, so it does whatever it
copied) **[measured]**. Both are real gaps in the tag set, not parsing
failures.

### 2.1 The player's six groupings

Each hero's score for a tag is the sum over its four abilities.

#### Support: Kelvin, Dynamo, Paige, Viscous, Rem. Holds for 4 of 5

| Hero | support score | Rank of 38 |
|---|---|---|
| Kelvin | 5 | **1** |
| Rem | 4 | **2** |
| Dynamo | 3 | **3** |
| Ivy | 3 | 4 |
| Paige | 3 | **5** |
| Bebop | 2 | 6 |
| McGinnis | 2 | 7 |
| Viscous | 1 | **10** |

Only 10 of 38 heroes have any support ability, so this tag is selective. Four
of the five named heroes rank 1, 2, 3, and 5. Viscous is the exception. Its
only support evidence is Puddle Punch's "you and your allies have increased
Air Control", a movement buff, not healing. The Cube heals a target, but the
text says "Can be used on self", so it doesn't count. By these tags Viscous
is a melee hero, not a support hero **[inferred]**. (The later `kits.py` tags,
which read The Cube's text differently, do count Viscous as support.) The
claim also leaves out Ivy, whose Kudzu Connection ("replicated healing") and
Air Drop ("grab an ally") tie Paige at 3.

#### Gun: Venator, Wraith, Haze, Vindicta. Holds for 4 of 4

| Hero | gun score | Rank |
|---|---|---|
| Venator | 6 | **1** |
| Haze | 4 | **2** |
| Silver | 4 | 3 |
| Vindicta | 3 | **4** |
| Wraith | 3 | **5** |

All four are in the top five of 38. The tag adds Silver, whose Slam Fire
("instantly reload... bonus fire rate") and Lycan Curse ("stacking fire rate")
are as gun-focused as anything of Haze's. This is the clearest of the six.

#### Melee: Calico, Viscous, Billy. Holds for 3 of 3

Only 9 of 38 heroes have a melee ability. Five tie at the top with a score of
2: Bebop, Billy, Calico, Viscous, and Yamato. Drifter, Graves, Silver, and
Venator follow at 1. All three named heroes are in the top group, plus Bebop
(Exploding Uppercut) and Yamato (Flying Slash, Crimson Slash).

#### Spirit burst: Lash, Viscous, Dynamo, Apollo. Doesn't hold

| Hero | spirit_burst | Rank |
|---|---|---|
| Infernus | 8 | 1 |
| Victor | 8 | 2 |
| Bebop, Celeste, Paige, Pocket | 6 | 3-6 |
| ... | | |
| Dynamo | 4 | **17** |
| Apollo | 3 | **25** |
| Lash | 3 | **28** |
| Viscous | 2 | **36** |

All 38 heroes have a spirit_burst ability, so the tag has an IDF of zero and
can't tell heroes apart. The four named heroes rank 17th, 25th, 28th, and
36th of 38, nearly the reverse of the claim. Dealing spirit damage is what
abilities in this game do; it isn't a playstyle **[inferred]**. If "spirit
burst" means something, it's about timing (one big hit against steady
damage), which the assets don't show. (`kits.py` later handled this by
requiring words like explosion or impact.)

#### Crowd control: Paige, Vindicta, Dynamo, Ivy, Graves. Holds weakly, 2 of 5

36 of 38 heroes have a control ability, so this tag is also nearly universal.
Top: Viscous 7, Apollo 6, Bebop 6, then Graves, Grey Talon, Infernus, Ivy,
Lady Geist, Rem, and Vyper at 5. Of the named heroes only Graves (4th) and Ivy
(7th) rank high. Paige is 15th, Dynamo 27th, Vindicta 32nd. Vindicta's Stake
does tether, but a dozen other heroes have more control.

#### Spirit damage over time: Infernus, Shiv, Holliday. Holds partly, 1 of 3

| Hero | dot | Rank |
|---|---|---|
| **Infernus** | 6 | **1** |
| Dynamo | 3 | 2 |
| Abrams, Drifter, **Holliday**, McGinnis, Mo & Krill, Paige, Pocket, Venator | 2 | 3-10 |
| **Shiv** | 1 | **14** |

Infernus scores twice anyone else: Napalm, Flame Dash, and Afterburn all
burn. Holliday is in the middle. Shiv scores only 1, which is a tagging miss,
not evidence against the claim: Serrated Knives clearly bleeds and stacks, but
its stats have no `DPS` or `TickRate` key, so only the text counts
**[measured]**. Shiv belongs in the group.

### 2.2 Tags the player didn't name

Four tags came out of the data that the player's list didn't have, and two are
more selective than any on it:

- **summon (9%, 8 heroes).** The rarest tag and so the most selective.
  Graves, McGinnis, and Sinclair score 3 each; their kits center on units that
  act on their own (Ghouls, turrets, the Spectral Assistant). Ivy, Paige, Rem,
  Vindicta, and Wraith have one summon ability each.
- **mobility (42%).** Too common to name a build, but helps tell similar
  heroes apart. Bebop, Calico, Dynamo, Kelvin, and Rem all score 6.
- **channel (11%).** The hero stands still and can be interrupted, which
  pushes item choices toward survival **[inferred]**.
- **sustain.** Separate from support for the same reason as in
  `ITEM-SEMANTICS.md`: Abrams, Lady Geist, Mo & Krill, and Yamato all heal,
  but only themselves.

Two possible tags the data doesn't support: imbue target (no field marks it)
and aura (only `_CAN_HEAL_PLAYERS` hints at it, on 4 abilities).

### 2.3 Every ability

152 rows. Bold means the text and typed field agree; plain means text only.

| Hero | Slot | Ability | What it does **[asset]** | Tags |
|---|---|---|---|---|
| Abrams | 1 | Siphon Life | Drain health from nearby enemies, dealing spirit damage over time and healing for a portion of… | **spirit_burst**, **dot**, **sustain** |
| Abrams | 2 | Shoulder Charge | Charge forward, pulling enemies you hit. Pushing a hero into a wall applies stun. If you collid… | spirit_burst, **control**, **mobility** |
| Abrams | 3 | Infernal Resilience | Gain bonus defensive attributes. Taking damage grants temporary regeneration for a portion of t… | **sustain**, tank |
| Abrams | 4 | Seismic Impact | Leap high into the air before crashing into the ground, dealing spirit damage and applying stun. | **spirit_burst**, **control**, **mobility** |
| Apollo | 1 | Disengaging Sigil | Draw a sigil sphere in front of you and then leap backwards as it explodes, damaging and slowin… | spirit_burst, **control**, **mobility** |
| Apollo | 2 | Riposte | Prepare to deflect the next incoming attack. On a successful deflection, briefly become invulne… | **sustain**, tank, **control**, **mobility** |
| Apollo | 3 | Flawless Advance | Perform a series of lunges in any direction, delivering piercing stabs ahead of you. Hold your… | spirit_burst, tank, channel |
| Apollo | 4 | Itani Lo Sahn | Charge up and perform a long range slash. Struck enemies cannot take action or heal and are stu… | spirit_burst, tank, **control**, **channel** |
| Bebop | 1 | Exploding Uppercut | Deal melee damage to nearby enemies and apply knockback. When they land, they deal spirit damag… | **spirit_burst**, **melee**, support, **control**, **mobility** |
| Bebop | 2 | Sticky Bomb | Attach a bomb that explodes after a delay, dealing spirit damage to nearby enemies. If the bomb… | **spirit_burst**, **mobility** |
| Bebop | 3 | Grapple Arm | Launch out a mechanical hand that pulls the first character it hits, reeling them in. Grapple A… | support, **control**, **mobility** |
| Bebop | 4 | Hyper Beam | Channel a powerful torrent of energy that deals spirit damage and applies slow. | **spirit_burst**, **control**, **channel** |
| Billy | 1 | Bashdown | Slam your bat into the ground, pulling enemies down and dealing melee damage. The slam creates… | **spirit_burst**, melee, control |
| Billy | 2 | Rising Ram | Charge head-first into an enemy and send them into the air along with Billy. Cooldown reduced b… | spirit_burst |
| Billy | 3 | Blasted | Passive: Melee hits restore ammo and inflict wrecked on the victim for 7.0s. Active: Bullets ar… | **gun**, melee, **mobility** |
| Billy | 4 | Chain Gang | Chain nearby enemies to you. Chained enemies cannot use movement abilities and receive a heavy… | **spirit_burst**, tank, control |
| Calico | 1 | Gloom Bombs | Throw a cluster of bombs that detonate after a delay, dealing spirit damage. Enemies hit by mul… | **spirit_burst** |
| Calico | 2 | Leaping Slash | Dash forward before slashing all enemies in a circle, dealing melee damage. If the ability hits… | **melee**, **mobility** |
| Calico | 3 | Ava | Turn to shadows and possess Ava. You gain bonus move speed that increases over time, and become… | **mobility** |
| Calico | 4 | Return to Shadows | Instantly turn to shadows, becoming untargetable, gaining bonus move speed, and dealing spirit… | **spirit_burst**, **mobility** |
| Celeste | 1 | Light Eater | Blast enemies in a cone in front of you with a flare of light. Blasted enemies take spirit dama… | spirit_burst, **sustain** |
| Celeste | 2 | Dazzling Trick | Surround yourself in a protective prism. If the barrier is destroyed, it silences nearby enemie… | spirit_burst, **tank**, control |
| Celeste | 3 | Radiant Daggers | Call down a beam of light from the sky. After a short duration, the beam will fully form, causi… | **spirit_burst** |
| Celeste | 4 | Shining Wonder | Launch a deadly orb of light that deals spirit damage and applies slow and reduces Dash Distanc… | **spirit_burst**, **control**, **mobility** |
| Drifter | 1 | Rend | Swipe at enemies in a cone ahead of you, dealing spirit damage. If the enemy is in close range,… | **spirit_burst**, melee, control |
| Drifter | 2 | Stalker's Mark | Send out a mark that bleeds the first target it hits, dealing spirit damage over time. While th… | **spirit_burst**, **dot**, tank |
| Drifter | 3 | Bloodscent | Active: Accentuate your senses, revealing a trail that leads to nearby heroes. Isolated heroes… | **gun**, **mobility** |
| Drifter | 4 | Eternal Night | Surround nearby enemy heroes in darkness, severely limiting their vision of other units. Affect… | **mobility** |
| Dynamo | 1 | Kinetic Pulse | Release an energy pulse that travels along the ground, dealing spirit damage and applying knock… | **spirit_burst**, tank, control, **mobility** |
| Dynamo | 2 | Quantum Entanglement | Briefly become untargetable while teleporting to the target location. Restores stamina upon use… | support, **mobility** |
| Dynamo | 3 | Rejuvenating Aurora | While channeling, restore health over time to you and any allies nearby. You can dash and melee… | dot, **support**, **mobility**, **channel** |
| Dynamo | 4 | Singularity | Create a singularity in your hands, dealing spirit damage over time, applying stun, and pulling… | **spirit_burst**, **dot**, control |
| Graves | 1 | Jar of Dead | Passive: Collect death when anything dies nearby and store it in your Jar of Dead. Active: Thro… | **spirit_burst**, control, summon |
| Graves | 2 | Grasping Hands | Unearth a line of grasping hands, summoning a Ghoul and leaving behind a rift. Enemies who pass… | spirit_burst, **control**, summon |
| Graves | 3 | Essence Theft | Your weapon steals weapon damage and spirit resist over time, up to a maximum amount per target. | **gun**, tank, summon |
| Graves | 4 | Borrowed Decree | Innate: Abilities can summon Ghouls that shamble toward the enemy base, dealing melee damage. T… | **spirit_burst**, melee, **control**, summon |
| Grey Talon | 1 | Charged Shot | Charge up a powerful shot that pierces through enemies. Hold Ability 1 or to hold the shot. | spirit_burst, **channel** |
| Grey Talon | 2 | Rain of Arrows | Launches you high in the air, allowing you to glide slowly. While airborne, you gain Weapon Dam… | **gun**, sustain, control, **mobility** |
| Grey Talon | 3 | Spirit Snare | Throw out a trap that begins to arm itself. Once armed, the trap will trigger when an enemy ent… | spirit_burst, tank, **control** |
| Grey Talon | 4 | Guided Owl | After 1.5s cast time, launch a spirit owl that you control and which explodes on impact, damagi… | spirit_burst, **control**, mobility |
| Haze | 1 | Sleep Dagger | Throw a dagger that damages and sleeps the target. Sleeping targets wake up shortly after being… | spirit_burst, tank, control, **mobility**, channel |
| Haze | 2 | Smoke Bomb | Fade out of sight, becoming invisible and gaining sprint speed. Attacking removes invisibility,… | sustain, **mobility** |
| Haze | 3 | Fixation | Shooting a target increases your bullet damage on that target. Gain one stack per bullet hit, t… | **gun**, control |
| Haze | 4 | Bullet Dance | Enter a flurry, firing your weapon at nearby enemies with perfect accuracy and added Bullet Dam… | **gun** |
| Holliday | 1 | Powder Keg | Throw a barrel that explodes after a delay, dealing spirit damage, setting enemies on fire and… | **spirit_burst**, **dot**, control |
| Holliday | 2 | Bounce Pad | Drop a bounce pad in the world that launches any hero. You explode on landing, dealing Damage t… | spirit_burst, support, control, **mobility** |
| Holliday | 3 | Crackshot | Headshots deal bonus Damage and applies a Fading Move Speed penalty. This effect can only occur… | **gun**, mobility |
| Holliday | 4 | Spirit Lasso | Throw out your lasso, dealing spirit damage, pulling, and applying stun. Using a Bounce Pad ext… | **spirit_burst**, control |
| Infernus | 1 | Napalm | Spew an incendiary mixture, dealing spirit damage, applying slow, and coating targets in napalm. | **spirit_burst**, **dot**, sustain, **control** |
| Infernus | 2 | Flame Dash | Dash forward, gaining slow resistance while leaving a flaming trail that deals spirit damage ov… | **spirit_burst**, **dot**, control, **mobility** |
| Infernus | 3 | Afterburn | Weapon hits build up a burning effect, dealing spirit damage over time. Abilities refresh to th… | **spirit_burst**, **dot** |
| Infernus | 4 | Concussive Combustion | Become a living bomb, dealing spirit damage and applying stun to all nearby enemies after a del… | **spirit_burst**, sustain, **control** |
| Ivy | 1 | Entangling Thorns | Summon a patch of choking thorns that damage and slows enemies in its radius. | spirit_burst, **control**, summon |
| Ivy | 2 | Kudzu Connection | Connect with a nearby ally to gain bonuses, replicated healing, and ignore the move speed penal… | **support**, **mobility** |
| Ivy | 3 | Stone Form | Turn yourself into impervious stone and smash into the ground, stunning and damaging enemies ne… | spirit_burst, **sustain**, tank, **control** |
| Ivy | 4 | Air Drop | Grab an ally and take flight with them. Drop your ally to cause an explosion, dealing spirit da… | **spirit_burst**, support, tank, control, **mobility** |
| Kelvin | 1 | Frost Grenade | Throw a grenade that explodes in a cloud of freezing ice that heals allies and applies spirit d… | spirit_burst, **support**, **mobility** |
| Kelvin | 2 | Ice Path | Kelvin creates a floating trail of ice and snow that gives movement bonuses to him and his alli… | support, tank, control, **mobility** |
| Kelvin | 3 | Arctic Beam | Shoot freezing cold energy out in front of you, damaging targets and progressively reducing the… | spirit_burst, **mobility** |
| Kelvin | 4 | Frozen Shelter | Target yourself or a Hero to freeze the air and create an impenetrable dome around them. While… | **support**, tank, **control** |
| Lady Geist | 1 | Essence Bomb | Sacrifice some of your health to launch a bomb that deals damage after a brief arm time. Self d… | spirit_burst, dot |
| Lady Geist | 2 | Life Drain | Create a tether that drains enemy health over time and heals you. Target must be in line of sig… | spirit_burst, **sustain**, **control**, **mobility** |
| Lady Geist | 3 | Malice | Sacrifice some of your health to launch blood shards that apply a stack of Malice. Each stack s… | spirit_burst, **control** |
| Lady Geist | 4 | Soul Exchange | Swaps health levels with an enemy target. There is a minimum health percentage that enemies can… | tank, control |
| Lash | 1 | Ground Strike | Stomp the ground beneath you, damaging enemies in front of you. If you perform Ground Strike wh… | spirit_burst, control |
| Lash | 2 | Grapple | Pull yourself through the air toward a target. Using Grapple also resets your limit of air jump… | control, **mobility** |
| Lash | 3 | Flog | Strike enemies in front of you with your whip, healing for a portion of the damage dealt. | spirit_burst, **sustain**, **mobility** |
| Lash | 4 | Death Slam | Focus on enemies to connect whips to them. After channeling, connected enemies are lifted and s… | spirit_burst, **control**, **channel** |
| McGinnis | 1 | Mini Turret | Deploy a turret that shoots enemies, dealing spirit damage over time. The turret expires after… | **spirit_burst**, **dot**, summon |
| McGinnis | 2 | Medicinal Specter | Deploy a spirit that provides healing to nearby allies. | **support**, tank, summon |
| McGinnis | 3 | Spectral Wall | Cast a wall that applies slow on enemies it passes through. Erupt the wall to divide the terrai… | spirit_burst, **control**, summon |
| McGinnis | 4 | Heavy Barrage | Unleashes a volley of rockets that home in on a targeted location. McGinnis is slowed and is st… | spirit_burst, **control**, **mobility** |
| Mina | 1 | Rake | *no text in asset* | spirit_burst |
| Mina | 2 | Sanguine Retreat | Briefly disperse, becoming untargetable and flying to a target location. Can be recast within a… | **mobility** |
| Mina | 3 | Love Bites | Your bullets apply additional spirit damage. Dealing damage your abilities builds up to a vicio… | gun, **spirit_burst**, control |
| Mina | 4 | Nox Nostra | Active: Unleash a cloud of bats that seek out targets, each dealing spirit damage and applying… | **spirit_burst**, control |
| Mirage | 1 | Fire Scarabs | Infest an enemy with fire scarabs, stealing life from them and causing them to deal reduced dam… | **sustain** |
| Mirage | 2 | Dust Devil | Transform yourself into a whirlwind that travels forward, damaging enemies, slowing their move… | spirit_burst, **control**, **mobility** |
| Mirage | 3 | Djinn's Mark | Active: Consume all Djinn Mark's to deal its damage now. Passive: Your shots apply a Djinn Mark… | gun, **spirit_burst**, control |
| Mirage | 4 | Traveler | Target a location on the minimap. After a brief wait, teleport to that location. Taking damage… | tank, **mobility** |
| Mo & Krill | 1 | Scorn | Deal damage to nearby enemies and heal yourself based on the damage done. Heal is stronger agai… | spirit_burst, **sustain** |
| Mo & Krill | 2 | Burrow | Burrow underground, moving faster, and gaining spirit and bullet armor. Damage from enemy heroe… | **spirit_burst**, **tank**, control, **mobility** |
| Mo & Krill | 3 | Sand Blast | Spray sand that disarms enemies in front of you and deals damage. | spirit_burst, control, **mobility** |
| Mo & Krill | 4 | Combo | Hold the target in place, stunning them and dealing damage during the channel. If they die duri… | spirit_burst, **dot**, sustain, tank, control, **channel** |
| Paige | 1 | Bookwyrm | Conjure a dragon that appears at the target location before flying forward, dealing spirit dama… | **spirit_burst**, **dot**, summon |
| Paige | 2 | Plot Armor | Grant an ally a barrier. While the barrier holds, they gain bonus weapon damage. | **gun**, support, **tank** |
| Paige | 3 | Captivating Read | Target an area with latent magic, applying slow. The magic detonates after a delay, dealing spi… | **spirit_burst**, tank, **control** |
| Paige | 4 | Rallying Charge | Release a wave of spectral knights and steeds that charge across the entire city, healing allie… | **spirit_burst**, **support**, **control** |
| Paradox | 1 | Pulse Grenade | Throw a grenade that begins pulsing when it lands. Each pulse expands the radius and applies sp… | spirit_burst, **control** |
| Paradox | 2 | Time Wall | Create a time warping wall that stops time for all enemy projectiles and bullets that touch it… | **gun**, **control** |
| Paradox | 3 | Kinetic Carbine | Charge up a powerful shot of time energy, dealing spirit damage and applying a Time-Stop to ene… | **spirit_burst**, **mobility**, channel |
| Paradox | 4 | Paradoxical Swap | Fire a projectile that swaps your position with the target enemy hero. | spirit_burst, tank |
| Pocket | 1 | Barrage | Channel to start launching projectiles that deal spirit damage and apply slow around their impa… | **spirit_burst**, **control**, **channel** |
| Pocket | 2 | Flying Cloak | Launch a sentient cloak that travels forward and damages enemies. You can press Ability 2 to te… | spirit_burst, **mobility** |
| Pocket | 3 | Enchanter's Satchel | Escape into your suitcase. When the duration ends, deal spirit damage to nearby enemies. Durati… | **spirit_burst**, **mobility** |
| Pocket | 4 | Affliction | Applies damage over time to enemies nearby. Affliction's damage is non-lethal and does not appl… | spirit_burst, **dot** |
| Rem | 1 | Pillow Toss | Throw your trusty pillow inflicting spirit damage and heavy knockback. Landing hits reduces the… | spirit_burst, **control** |
| Rem | 2 | Tag Along | Jump to an ally and nap alongside them. Both you and the ally receive a burst heal based on mis… | **support**, tank, control, **mobility** |
| Rem | 3 | Lil Helpers | Signal a Helper to lend a hand. They can collect boxes, do Sinner's Sacrifices, or be sent to s… | spirit_burst, **support**, **tank**, **mobility**, summon |
| Rem | 4 | Naptime | Cast your gaze forward, piercing walls and floors. Enemies in the gaze are slowed, have reduced… | spirit_burst, **control**, **mobility**, **channel** |
| Seven | 1 | Lightning Ball | Shoot a ball of lightning that travels in a straight line. Does damage to all targets in its ra… | spirit_burst, control, **mobility** |
| Seven | 2 | Static Charge | Apply a charge to a target enemy hero. After a short duration, the static charge stuns and dama… | spirit_burst, **control** |
| Seven | 3 | Power Surge | Power up your weapon with a shock effect, making your bullets proc shock damage on your target.… | gun, spirit_burst, tank, **mobility** |
| Seven | 4 | Storm Cloud | Channel an expanding storm cloud around you that damages all enemies within its radius. Enemies… | spirit_burst, tank, mobility, **channel** |
| Shiv | 1 | Serrated Knives | Throw a knife that bleeds an enemy. Each additional hit adds a stack and refreshes the bleed du… | spirit_burst, dot |
| Shiv | 2 | Slice and Dice | Perform a dash forward, damaging enemies along the path. Hit Enemies have their spirit resist r… | spirit_burst, tank, **mobility** |
| Shiv | 3 | Bloodletting | Take only a portion of incoming damage immediately and defer the rest to be taken over time. Ac… | — |
| Shiv | 4 | Killing Blow | Active: Leap forward, dealing spirit damage to the first enemy hero. If they are below the kill… | **spirit_burst**, **mobility** |
| Silver | 1 | Slam Fire | Instantly reload your gun. You gain bonus fire rate and deal bonus weapon damage based on the t… | **gun** |
| Silver | 2 | Boot Kick | Dash forward and kick the first enemy hit, dealing melee damage while pushing yourself off and… | **spirit_burst**, melee, **mobility** |
| Silver | 3 | Entangling Bola | Throw a bola, dealing spirit damage, applying slow and preventing movement abilities or stamina. | **spirit_burst**, **control** |
| Silver | 4 | Lycan Curse | Passive: Dealing damage generates bloodlust, increased at low health. At max bloodlust, you aut… | **gun**, **tank**, **mobility** |
| Sinclair | 1 | Vexing Bolt | Fire a bolt of magic that deals Damage, increasing as it travels. If you have an Assistant, the… | spirit_burst, summon |
| Sinclair | 2 | Spectral Assistant | Summon an Assistant at the targeted location. The Assistant attacks whenever you fire your weap… | spirit_burst, summon |
| Sinclair | 3 | Rabbit Hex | Hex a target area and transforming all enemies into a Rabbit for a limited duration. Rabbits ar… | control |
| Sinclair | 4 | Audience Participation | Copy the Ultimate of an enemy hero for a limited time. Reactivating the ability will use the Co… | — |
| The Doorman | 1 | Call Bell | Throw out a call bell that deals spirit damage on impact. After a short delay it explodes, deal… | **spirit_burst**, **control** |
| The Doorman | 2 | Doorway | Place two connected doors in the world. Players and most projectiles entering one door will exi… | tank |
| The Doorman | 3 | Luggage Cart | Send out a luggage Cart that deals spirit damage and pulls enemy heroes along its path. Can be… | **spirit_burst**, support, control |
| The Doorman | 4 | Hotel Guest | Send the target's physical body to be a guest at the Baroness Hotel. The guest is to promptly m… | spirit_burst, control |
| Venator | 1 | Consecrating Grenade | Fire a grenade that bounces before exploding, dealing weapon damage and setting enemies on fire… | **gun**, **dot** |
| Venator | 2 | Gutshot | Fire a blast with your shotgun, dealing weapon damage and pushing enemies back. Enemies near a… | **gun**, melee, **control** |
| Venator | 3 | Hex-Lined Snap Trap | Kick a trap that arms after a brief delay. The trap springs on the first enemy it touches, deal… | **spirit_burst**, control |
| Venator | 4 | Ira Domini | Load your crossbow with 3 stakes, dealing massively increased weapon damage. The final stake is… | **gun**, spirit_burst, **mobility** |
| Victor | 1 | Pain Battery | Taking any damage passively charges up your Pain Battery. Once full, activating the ability fir… | **spirit_burst**, control |
| Victor | 2 | Jumpstart | Deal spirit damage to yourself. Then, gain bonus regeneration and bonus move speed, decaying ov… | **spirit_burst**, **sustain**, **mobility** |
| Victor | 3 | Aura of Suffering | Unleash pain, dealing spirit damage over time to both enemies and yourself. The damage continue… | **spirit_burst**, **dot**, control, **mobility**, channel |
| Victor | 4 | Shocking Reanimation | Release a wave after taking lethal damage, applying a diminishing slow. After a brief channel y… | **spirit_burst**, **control**, **channel** |
| Vindicta | 1 | Stake | Throw a stake that tethers enemies to the location where the stake lands. Enemy movement is res… | spirit_burst, **control** |
| Vindicta | 2 | Flight | Leap into the air and fly. While in flight your weapon deals bonus spirit damage and your items… | gun, spirit_burst, **mobility** |
| Vindicta | 3 | Crow Familiar | Your crow familiar deals impact damage, reduces their bullet resist and applies a bleed that de… | spirit_burst, **dot**, tank, summon |
| Vindicta | 4 | Assassinate | Use your scoped rifle to fire a powerful shot over long distances. Deal only partial damage unt… | **gun**, spirit_burst |
| Viscous | 1 | Splatter | Throw a ball of goo that deals damage and leaves puddles of goo behind that apply movement slow… | spirit_burst, **control** |
| Viscous | 2 | The Cube | Encase the target in a cube of restorative goo that protects from damage, and increases health… | tank, control, **mobility** |
| Viscous | 3 | Puddle Punch | Materialize a fist in the world that punches everyone in the area, applying knockup. Punching a… | **melee**, support, **control** |
| Viscous | 4 | Goo Ball | Morph into a large goo ball that deals damage and stuns enemies on impact. The ball grants larg… | spirit_burst, **tank**, **control**, **mobility** |
| Vyper | 1 | Screwjab Dagger | Throw a dagger, dealing spirit damage and applying slow. Every subsequent dagger against the sa… | **spirit_burst**, tank, **control** |
| Vyper | 2 | Lethal Venom | Inject a target with lethal venom. After a delay the venom triggers, dealing Spirit Damage. The… | **spirit_burst**, control |
| Vyper | 3 | Slither | You have increased Slide Distance, can Slide up hills, and can turn faster while Sliding. | tank, **mobility** |
| Vyper | 4 | Petrifying Bola | Throw an explosive bola. On exploding, the bola Slows and Damages all enemies in the area. Dire… | spirit_burst, tank, **control** |
| Warden | 1 | Alchemical Flask | Throw a flask that damages and reduces the weapon damage and move speed of enemies it hits. | spirit_burst, **mobility** |
| Warden | 2 | Willpower | Gain a Barrier and bonus move speed. | **tank**, **mobility** |
| Warden | 3 | Binding Word | Curse an enemy hero. If they don't move away from their initial position within the escape time… | spirit_burst, control |
| Warden | 4 | Last Stand | After charging for 2s, release pulses that damage enemies and heal you based on the damage done… | spirit_burst, **sustain**, **tank**, channel |
| Wraith | 1 | Card Trick | Deal weapon damage to summon cards of a random suit. Each card can be thrown, dealing damage an… | gun, spirit_burst, **mobility**, summon |
| Wraith | 2 | Project Mind | Teleport to the targeted location. | tank, **mobility** |
| Wraith | 3 | Full Auto | Temporarily boosts your fire rate and deal bonus spirit damage | **gun**, spirit_burst |
| Wraith | 4 | Telekinesis | Lift an enemy hero into the air and then slam them towards the target location. | spirit_burst, **control** |
| Yamato | 1 | Power Slash | Channel to increase damage over 1.4 seconds, then release a fully-charged sword strike. Press A… | spirit_burst, control, channel |
| Yamato | 2 | Flying Slash | Throw a grappling hook to reel yourself towards an enemy, dealing Light melee damage and slowin… | melee, **control**, **mobility** |
| Yamato | 3 | Crimson Slash | Slash enemies in front of you, damaging them and slowing their fire rate. If any enemy heroes a… | spirit_burst, melee, **sustain**, **control** |
| Yamato | 4 | Shadow Transformation | Become infused with Yamato's shadow soul. After an initial invincible transformation your abili… | **sustain**, **tank**, **mobility** |

---

## 3. Grouping heroes by kit

### 3.1 How heroes are compared

Each hero is 11 numbers, one per tag, summed over its four abilities. Then:

1. **Weighted by IDF**, like `semantics.family_idf` for items, so the common
   tags don't swamp the rare ones and make every hero look alike. The weights
   **[measured]**:

   | Tag | Heroes with it | IDF | | Tag | Heroes | IDF |
   |---|---|---|---|---|---|---|
   | summon | 8 | **1.56** | | gun | 15 | 0.93 |
   | melee | 9 | **1.44** | | tank | 28 | 0.31 |
   | support | 10 | **1.34** | | mobility | 34 | 0.11 |
   | dot | 14 | 1.00 | | control | 36 | 0.05 |
   | sustain | 14 | 1.00 | | **spirit_burst** | **38** | **0.00** |
   | channel | 14 | 1.00 | | | | |

   `spirit_burst` gets weight zero because all 38 heroes have it. This is the
   number behind section 2.1's finding that the spirit burst grouping fails.

2. **Normalized to length 1, compared by cosine distance.** A hero with more
   tagged abilities shouldn't count as "bigger", only as pointing in a
   different direction **[inferred]**.

3. **Average-linkage clustering.** The cophenetic correlation is 0.754, so the
   tree is a fair summary of the distances **[measured]**.

Counts work better than yes/no tags here. Yes/no would lose that Venator has
three gun abilities and Wraith two.

### 3.2 Dendrogram **[measured]**

```
`-+ (0.835, n=38)
   |-+ (0.798, n=24)
   |  |-+ (0.715, n=10)
   |  |  |-+ (0.213, n=3)
   |  |  |  |- McGinnis
   |  |  |  `-+ (0.066, n=2)
   |  |  |     |- Graves
   |  |  |     `- Sinclair
   |  |  `-+ (0.359, n=7)
   |  |     |-+ (0.153, n=4)
   |  |     |  |- Ivy
   |  |     |  `-+ (0.101, n=3)
   |  |     |     |- Rem
   |  |     |     `-+ (0.022, n=2)
   |  |     |        |- Kelvin
   |  |     |        `- The Doorman
   |  |     `-+ (0.256, n=3)
   |  |        |- Dynamo
   |  |        `-+ (0.190, n=2)
   |  |           |- Holliday
   |  |           `- Paige
   |  `-+ (0.753, n=14)
   |     |-+ (0.323, n=4)
   |     |  |- Bebop
   |     |  `-+ (0.210, n=3)
   |     |     |- Billy
   |     |     `-+ (0.134, n=2)
   |     |        |- Calico
   |     |        `- Viscous
   |     `-+ (0.455, n=10)
   |        |-+ (0.119, n=2)
   |        |  |- Grey Talon
   |        |  `- Seven
   |        `-+ (0.335, n=8)
   |           |- Drifter
   |           `-+ (0.231, n=7)
   |              |-+ (0.144, n=5)
   |              |  |-+ (0.061, n=2)
   |              |  |  |- Haze
   |              |  |  `- Paradox
   |              |  `-+ (0.096, n=3)
   |              |     |- Mina
   |              |     `-+ (0.075, n=2)
   |              |        |- Silver
   |              |        `- Venator
   |              `-+ (0.152, n=2)
   |                 |- Vindicta
   |                 `- Wraith
   `-+ (0.813, n=14)
      |- Vyper
      `-+ (0.649, n=13)
         |-+ (0.328, n=3)
         |  |- Pocket
         |  `-+ (0.153, n=2)
         |     |- Infernus
         |     `- Shiv
         `-+ (0.337, n=10)
            |-+ (0.186, n=5)
            |  |-+ (0.080, n=2)
            |  |  |- Mo & Krill
            |  |  `- Victor
            |  `-+ (0.154, n=3)
            |     |- Warden
            |     `-+ (0.049, n=2)
            |        |- Apollo
            |        `- Lash
            `-+ (0.262, n=5)
               |- Yamato
               `-+ (0.153, n=4)
                  |-+ (0.005, n=2)
                  |  |- Abrams
                  |  `- Lady Geist
                  `-+ (0.102, n=2)
                     |- Celeste
                     `- Mirage
```

Cutting at k=6 **[measured]**:

| Cluster | n | Heroes | Defining profile (mean tag score) |
|---|---|---|---|
| **C1 summoners** | 3 | Graves, McGinnis, Sinclair | summon 3.0 |
| **C2 supports** | 7 | Dynamo, Holliday, Ivy, Kelvin, Paige, Rem, The Doorman | support 2.9, dot 1.0 |
| **C3 melee brawlers** | 4 | Bebop, Billy, Calico, Viscous | melee 2.0, mobility 4.5 |
| **C4 gun carries** | 10 | Drifter, Grey Talon, Haze, Mina, Paradox, Seven, Silver, Venator, Vindicta, Wraith | gun 2.8 |
| **C5 self-sustain fighters** | 13 | Abrams, Apollo, Celeste, Infernus, Lady Geist, Lash, Mirage, Mo & Krill, Pocket, Shiv, Victor, Warden, Yamato | sustain 2.1, tank 1.4, dot 1.2 |
| **C6** | 1 | Vyper | singleton (control 5, tank 3, no rare tags) |

The five real clusters match the item families (support, gun, melee, and a
self-healing bruiser group), plus summon, which items have no word for. The
ability tags and the item families were built separately from different data
and ended up in the same place **[inferred]**.

### 3.3 The player's groupings as distances

Mean cosine distance between heroes within each claimed group, against 0.713
for all pairs of heroes (median 0.792) **[measured]**:

| Claimed group | Mean within-group distance | Verdict |
|---|---|---|
| Calico, Viscous, Billy | **0.184** | holds, 3.9x closer than all pairs |
| Venator, Wraith, Haze, Vindicta | **0.191** | holds, 3.7x closer |
| Kelvin, Dynamo, Paige, Viscous, Rem | 0.364 | holds without Viscous |

**Melee (Calico, Viscous, Billy): holds strongly.** All three are in C3 and
are each other's nearest neighbors: Calico to Viscous 0.134, Calico to Billy
0.172, Viscous to Billy 0.247. The cluster also has Bebop.

**Gun (Venator, Wraith, Haze, Vindicta): holds.** All four are in C4, every
pair under 0.31. The closest pairs are Venator and Silver (0.075) and Haze and
Paradox (0.061), so the cluster is a little wider than the four named heroes
but includes all of them.

**Support (Kelvin, Dynamo, Paige, Viscous, Rem): holds for four, not
Viscous.** Four are in C2 and close together (Kelvin to Rem 0.096, Kelvin to
Paige 0.217, Dynamo to Paige 0.207). Viscous is 0.565-0.673 from each of them,
farther than the median of all pairs, and sits in the melee cluster. Without
Viscous the group's mean distance falls from 0.364 to 0.197. The closest
support pair of all is Kelvin and The Doorman (0.022), a hero the player
didn't name.

### 3.4 Each hero's three nearest heroes by kit **[measured]**

| Hero | 1st | 2nd | 3rd |
|---|---|---|---|
| Abrams | Lady Geist (0.005) | Celeste (0.125) | Mo & Krill (0.138) |
| Apollo | Lash (0.049) | Warden (0.143) | Victor (0.150) |
| Bebop | Viscous (0.181) | Rem (0.302) | Calico (0.338) |
| Billy | Calico (0.172) | Silver (0.189) | Viscous (0.247) |
| Calico | Viscous (0.134) | Billy (0.172) | Bebop (0.338) |
| Celeste | Mirage (0.102) | Warden (0.110) | Lady Geist (0.112) |
| Drifter | Venator (0.135) | Holliday (0.207) | Vindicta (0.210) |
| Dynamo | Rem (0.202) | Paige (0.207) | Kelvin (0.252) |
| Graves | Sinclair (0.066) | McGinnis (0.238) | Wraith (0.306) |
| Grey Talon | Paradox (0.108) | Seven (0.119) | Haze (0.142) |
| Haze | Paradox (0.061) | Mina (0.076) | Silver (0.128) |
| Holliday | Paige (0.190) | Vindicta (0.201) | Drifter (0.207) |
| Infernus | Shiv (0.153) | Abrams (0.294) | Lady Geist (0.300) |
| Ivy | Rem (0.145) | Kelvin (0.152) | The Doorman (0.161) |
| Kelvin | The Doorman (0.022) | Rem (0.096) | Ivy (0.152) |
| Lady Geist | Abrams (0.005) | Celeste (0.112) | Mo & Krill (0.132) |
| Lash | Apollo (0.049) | Victor (0.141) | Mo & Krill (0.162) |
| McGinnis | Sinclair (0.188) | Graves (0.238) | Paige (0.252) |
| Mina | Haze (0.076) | Silver (0.087) | Venator (0.105) |
| Mirage | Celeste (0.102) | Lady Geist (0.185) | Abrams (0.189) |
| Mo & Krill | Victor (0.080) | Lady Geist (0.132) | Abrams (0.138) |
| Paige | Holliday (0.190) | Dynamo (0.207) | Rem (0.208) |
| Paradox | Haze (0.061) | Grey Talon (0.108) | Mina (0.131) |
| Pocket | Victor (0.141) | Shiv (0.325) | Mo & Krill (0.325) |
| Rem | Kelvin (0.096) | The Doorman (0.106) | Ivy (0.145) |
| Seven | Grey Talon (0.119) | Paradox (0.199) | Apollo (0.227) |
| Shiv | Infernus (0.153) | Pocket (0.325) | Drifter (0.357) |
| Silver | Venator (0.075) | Mina (0.087) | Haze (0.128) |
| Sinclair | Graves (0.066) | McGinnis (0.188) | Wraith (0.519) |
| The Doorman | Kelvin (0.022) | Rem (0.106) | Ivy (0.161) |
| Venator | Silver (0.075) | Mina (0.105) | Drifter (0.135) |
| Victor | Mo & Krill (0.080) | Lash (0.141) | Pocket (0.141) |
| Vindicta | Venator (0.152) | Wraith (0.152) | Holliday (0.201) |
| Viscous | Calico (0.134) | Bebop (0.181) | Billy (0.247) |
| Vyper | Warden (0.514) | Shiv (0.660) | Viscous (0.684) |
| Warden | Celeste (0.110) | Apollo (0.143) | Mo & Krill (0.152) |
| Wraith | Mina (0.133) | Vindicta (0.152) | Haze (0.180) |
| Yamato | Celeste (0.208) | Warden (0.245) | Mirage (0.274) |

### 3.5 Does a hero's kit predict its build families?

This was what the task hoped for, and mostly it doesn't.

The six kit clusters against the family names in `archetype_meta.json` (33
named archetypes across 38 heroes; the rest are bare hero names)
**[measured]**:

| Kit cluster | Gun | Melee | Spirit | Support |
|---|---|---|---|---|
| C1 summoners | 2 | 1 | 3 | 0 |
| C2 supports | 2 | 0 | 3 | 1 |
| C3 melee | 1 | 2 | 2 | 0 |
| C4 gun | 3 | 1 | 1 | 0 |
| C5 sustain | 3 | 2 | 6 | 0 |

Chi-squared 9.4 with 12 degrees of freedom, p = 0.67, Cramer's V 0.308
**[measured]**. Not significant: in general, the kit cluster doesn't predict
the build family.

Testing each tag against each family per hero is more precise, and finds one
real effect **[measured]**:

| Tag | Family | P(family \| tag) | P(family) | Lift | Fisher p |
|---|---|---|---|---|---|
| **melee** | Melee | **0.44** | 0.18 | **2.41** | **0.041** |
| support | Support | 0.10 | 0.03 | 3.80 | 0.263 |
| gun | Gun | 0.33 | 0.29 | 1.15 | 0.450 |
| spirit_burst | Spirit | 0.42 | 0.42 | 1.00 | 1.000 |
| dot | Spirit | 0.36 | 0.42 | 0.85 | 0.829 |

Only melee is significant. A hero with a melee ability is 2.4 times as likely
to have a melee archetype: 4 of the 7 heroes with a melee archetype (Calico,
Drifter, Sinclair, Viscous) have a melee ability, against 9 of 38 heroes
overall.

Support has the biggest lift (3.8x) but only one case: Kelvin was the only
hero with a support archetype. That Kelvin also has the strongest support kit
fits the idea but doesn't prove it.

Gun fails for a useful reason. Having a gun ability and having a gun build
are different things: Bebop, Lady Geist, Lash, and Victor all have gun
archetypes and no gun abilities, because a gun build comes from items. A kit
only limits builds where the kit is what makes the build work. That is why
melee works: melee items are nearly useless without an ability that deals
melee damage **[inferred]**.

So this section shows that kit similarity is real and measurable (cophenetic
0.754, claimed groups 3.7-3.9 times closer than all pairs), and that it lands
on the same families as items. It doesn't show that a hero's kit predicts its
archetypes. With 33 named archetypes over 38 heroes, only a very large effect
could show up, and only melee's is that large.

---

## 4. Can ability data separate same-family builds?

No. This was the task's main question.

### 4.1 Setup

Two corrections to the task's framing, from `archetype_meta.json` at the time
**[measured]**:

- Drifter's repeated family is melee, not spirit: Melee Drifter and
  Hybrid-Melee Drifter, with Gun Drifter third.
- Dynamo had one archetype then, so there was nothing to separate. Abrams (two
  archetypes, hero id 6) is used instead as a positive control: two
  archetypes of different families, where any working method should show a
  difference.

Features are each slot's level plus the time each slot first reached levels
2, 3, and 4, so order is included, not just levels. Logistic regression with
5-fold stratified cross-validation, macro one-vs-rest AUC.

### 4.2 The player's concern is real

The player expected early ability order not to help, because almost everyone
maxes the same ability first. Across all 38 heroes, the share of players
taking one particular slot to level 2 before any other **[measured]**:

| Hero | Slot | Share | | Hero | Slot | Share |
|---|---|---|---|---|---|---|
| Mo & Krill | 1 | 99% | | Venator | 2 | **90%** |
| Wraith | 1 | 99% | | Graves | 1 | 89% |
| Warden | 1 | 98% | | Celeste | 1 | **73%** |
| **Drifter** | **1** | **98%** | | Ivy | 3 | 58% |
| Shiv | 1 | 97% | | Vindicta | 1 | 52% |
| Haze | 3 | 97% | | **Abrams** | **2** | **49%** |
| Infernus | 3 | 95% | | Rem | 3 | 46% |
| **Dynamo** | **1** | **94%** | | | | |

The median across heroes is 77%, and 17 of 38 heroes are above 80%. The
player's own example holds: 94% of Dynamo players take Kinetic Pulse to level
2 first, whatever the build.

The three heroes being tested are among the most uniform (Drifter 98%,
Venator 90%, Celeste 73%), while the control, Abrams, is second least uniform
at 49%. That contrast is the whole result in small.

### 4.3 Mean level per slot, by cluster **[measured]**

**Drifter** (Rend / Stalker's Mark / Bloodscent / Eternal Night):

| Cluster | 480s | 900s | final |
|---|---|---|---|
| Melee Drifter | 2.73 / 2.35 / 1.23 / 1.03 | 3.72 / 3.11 / 2.16 / 1.34 | 3.99 / 3.96 / 3.64 / 3.26 |
| Hybrid-Melee Drifter | 2.81 / 2.04 / 1.25 / 1.08 | 3.61 / 2.99 / 2.38 / 1.62 | 3.96 / 3.93 / 3.62 / 3.46 |
| Gun Drifter | 2.64 / 2.28 / 1.26 / 1.08 | 3.07 / 3.13 / 2.68 / 2.09 | 3.77 / 3.90 / 3.69 / 3.66 |
| **max spread** | **0.17 / 0.32 / 0.04 / 0.05** | 0.64 / 0.15 / 0.52 / 0.76 | 0.23 / 0.06 / 0.07 / 0.40 |

At 480s the biggest gap between any two clusters on any slot is 0.32 levels.
The two same-family clusters (Melee and Hybrid-Melee) are closer still.

**Venator** (Consecrating Grenade / Gutshot / Snap Trap / Ira Domini), the
cleanest same-family test, since both clusters are gun:

| Cluster | 480s | 900s | final |
|---|---|---|---|
| Hybrid-Gun Venator | 1.20 / 2.90 / 1.03 / 2.03 | 2.31 / 3.06 / 1.64 / 3.76 | 3.93 / 3.42 / 3.65 / 3.99 |
| Gun Venator | 1.35 / 2.86 / 1.04 / 2.10 | 2.51 / 3.06 / 1.22 / 3.76 | 3.80 / 3.75 / 3.40 / 3.99 |
| **max spread** | **0.15 / 0.04 / 0.01 / 0.06** | 0.21 / 0.00 / 0.42 / 0.00 | 0.13 / 0.33 / 0.25 / 0.00 |

At 480s the two Venator builds are within 0.15 levels on every slot. They
level abilities the same way.

**Celeste**: biggest gap 0.35 at 480s, 0.49 at 900s, 0.15 at the end.

**Abrams (control, different families)** looks very different:

| Cluster | 480s | 900s |
|---|---|---|
| Abrams | 2.43 / 1.76 / 1.52 / 1.03 | 3.50 / 3.17 / 1.84 / 1.42 |
| Melee Abrams | 1.15 / 2.95 / 1.51 / 1.02 | 1.58 / 3.91 / 2.10 / 2.50 |
| **max spread** | **1.28 / 1.19** / 0.01 / 0.02 | **1.92** / 0.73 / 0.26 / 1.07 |

1.28 levels apart at 480s, four to eight times the gap of any same-family
pair. Median time to level 2 on Siphon Life is 185s in one cluster and 1153s
in the other. When two builds really use different abilities, the level data
shows it clearly.

### 4.4 How well abilities separate the clusters (AUC) **[measured]**

| Hero | k | Abilities @480s | @900s | @final | Items @900s |
|---|---|---|---|---|---|
| Venator | 2 | 0.599 | 0.792 | 0.817 | **0.959** |
| Celeste | 3 | 0.657 | 0.679 | 0.732 | **0.757** |
| Drifter | 3 | 0.609 | 0.736 | 0.753 | **0.886** |
| **Abrams** (control) | 2 | **0.877** | **0.924** | 0.927 | 0.952 |
| Dynamo | 1 | - | - | - | single archetype |

At 480s the three same-family heroes are at 0.60-0.66, barely above chance,
while the different-family control is at 0.877. Ability levels become more
useful later, reaching 0.73-0.82 by the end. That looks promising until the
next test.

### 4.5 The deciding test: do abilities add anything to items?

The clusters were found from purchases, so a decent ability AUC could just
reflect the items: a player committed to a build buys certain items and also
levels certain abilities. What matters is whether abilities add information
the items don't have.

Same features, same folds, at 900s **[measured]**:

| Hero | Items alone | Abilities alone | Both | **Delta over items** |
|---|---|---|---|---|
| Venator | 0.959 | 0.792 | 0.957 | **-0.002** |
| Celeste | 0.757 | 0.679 | 0.764 | **+0.007** |
| Drifter | 0.886 | 0.736 | 0.889 | **+0.003** |
| Abrams | 0.952 | 0.924 | 0.952 | **+0.000** |

Ability levels add at most +0.007 AUC, and nothing for Venator. What
abilities reach on their own (0.68-0.82) is almost all already in the items.
Even for Abrams, whose builds really do level different abilities (1.28
levels apart), the gain is zero, because items were already at 0.952.

### 4.6 Conclusion

Ability levels can't separate two builds of the same family, because of how
players level, not because of the features chosen:

1. **The hero decides the early order, not the build.** 94% of Dynamos take
   Kinetic Pulse first, 98% of Drifters take Rend, and 90% of Venators take
   Gutshot. The median across heroes is 77%. There is little variation to
   use.
2. **Final levels are all the same.** By match end every cluster is at 3.3 to
   4.0 on every slot; Celeste's three clusters differ by at most 0.15 levels.
   This matches the note in `abilities.py`.
3. **Mid-match is where levels vary, and items already cover it.** 900s is
   the best time for ability features and also where item features are
   strongest.

The player was right about why. "Ult Dynamo" against "stomp Dynamo" is about
how a player spends souls and aims, not how they spend ability points. Both
builds level Kinetic Pulse first. The difference the player sees is real; it
just isn't in the ability points.

### 4.7 What might work instead

Not tested here; noted so the negative result points somewhere
**[inferred]**:

- **Other ability data.** Cast counts, damage per ability, and time to first
  cast would separate an ult-focused player from a stomp-focused one. None of
  these are in `abilities.parquet`, which has only level-ups. (Imbue targets,
  used later, turned out to separate Dynamo's builds.)
- **The items already separate them.** Venator's two clusters are 0.959
  separable by items at 900s. What's missing is a name, not a signal: the two
  builds differ in which items they buy, and the section 2 tags could name
  that if applied to the cluster's distinctive items instead of the hero's
  kit.
- **Upgrade tiers.** `description.t1/t2/t3_desc` describes each of the three
  upgrades for 145 of 152 abilities, and the level a player reaches is in
  `abilities.parquet`. Whether what the upgrades do separates same-family
  builds wasn't tested.

---

## 5. What this couldn't answer

- **Mina's Rake.** The one signature ability with no text anywhere in the
  assets: `info_sections` holds the raw key
  `#ability_vampirebat_steallife_desc` **[asset]**. Its tags come from stats
  alone and are unverified.
- **Shiv's Bloodletting and Sinclair's Audience Participation** have no tags.
  What they do (delaying damage, copying an ultimate) isn't covered by any
  tag. They aren't parsing failures.
- **Whether a kit predicts archetypes.** p = 0.67 over 33 named archetypes
  isn't evidence of no effect; there's too little data to tell. With one
  support archetype in the whole dataset, only an effect as big as melee's
  could show up.
- **Whether "spirit burst" means anything.** The damage-type markers can't
  show it, since all 38 heroes deal spirit damage. It may be a real
  difference in timing that this data doesn't capture.
- **How abilities are used.** Cast counts, per-ability damage, and cast timing
  aren't in any local table, so section 4 could only use level-ups.
