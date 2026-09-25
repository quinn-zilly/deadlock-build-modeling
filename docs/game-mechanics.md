# Game mechanics

How Deadlock works, as far as it matters to this project. Everything here can
change a build recommendation, its order, or its timing.

## How to read this

Each number is marked:

- **VERIFIED**: checked against data in this repo, with the method and count.
- **UNVERIFIED**: from <https://deadlock.wiki>, and not checkable with our
  data. Probably right, but measure it before building a check on it.

> **The data changed on 2026-09-14, and every table was rebuilt on
> 2026-09-15.** Adding `include_objectives` and `include_mid_boss` to
> `ingest.BASE_PARAMS` made every cached page miss. The re-download fetched
> newest first, so it got newer matches, not the same ones. Its 125 pages are
> the only ones in `data/raw/matches/`.
>
> `scripts/refit.py` rebuilt all six tables from those pages:
> `purchases.parquet` has 5,119,990 purchases over 296,478 player-matches in
> 24,999 matches, `abilities.parquet` has 4,460,944 ability points,
> `imbues.parquet` has 467,271 imbues, `archetypes.parquet` labels 296,478
> player-matches in 80 cells, and all 80 generated builds pass the staple gate.
>
> The old data is still on disk as `data/raw/matches_prechange/` (125 pages,
> 5.3 GB, git-ignored, so only on the machine that downloaded it). Its purchase
> table had 5,095,598 rows over 299,983 player-matches, and any number in this
> repo quoting those counts was measured on it. Those numbers aren't wrong, but
> they don't compare with numbers from the current data. Restoring that
> directory and running `scripts/refit.py` rebuilds the old tables exactly.

## Data sources

Besides the local tables and the assets API, there are two more.

**The bulk metadata endpoint** that `ingest.py` uses can return more than we
ask for. `ingest.BASE_PARAMS` lists each flag we pass and why. We request
`include_player_items`, `include_player_stats`, `include_player_info` (which
includes `hero_build_id` and `pregame_hero_id`), `include_objectives`, and
`include_mid_boss`. We don't request `include_player_death_details` or
`include_player_final_stats`. Use this endpoint over SQL for anything it
covers: a field it returns is one flag away from being a column.

It allows 10 requests a minute per IP, measured 2026-09-15: ten requests
succeed and the eleventh returns a 429 saying
`{"type":"IP","quota":{"limit":10,"period":60}}`. An API key raises this to 10
requests per 10 seconds. There is also a global limit of 100 requests a
minute shared by all callers, which explains occasional 429s at any rate.

Don't switch to the per-match `/v1/matches/{match_id}/metadata` to get around
the limit. It is fast (2.6 requests a second with no 429s), but it returns one
match per request against the bulk endpoint's 200, making it about 12 times
slower per match, and 1.2 MB per match against 430 KB.

**Download size limits a pull, not request count.** 25,000 matches is about
11.6 GB at 430 KB a match, which took about 14 minutes at 13.5 MB/s on one
machine on 2026-09-15. Pacing at 9 requests a minute also takes about 14
minutes. So a bigger `MATCHES_PER_PAGE` or an API key saves almost nothing,
and a bigger page costs memory (see `ingest.MATCHES_PER_PAGE`). Requesting
fewer `include_` flags would help, since it cuts bytes. Both numbers are from
one machine on one day; measure again before relying on them.

> When testing this endpoint, pass Unix timestamps for the right year. A
> window set to 2025 by mistake returns real matches from before match
> analysis existed, so `hero_build_id` is missing from every row. This once
> led to a wrong conclusion that the endpoint doesn't return it.

**The deadlock-api MCP server** at `https://api.deadlock-api.com/v1/mcp` gives
read-only DuckDB SQL over hourly snapshots of the upstream tables, including
`objectives.*`, `mid_boss.*`, and `stats.*`. It doesn't have the REST SQL
endpoint's limit of 2 a minute and 20 an hour. Results are capped at 1,024
rows and 50 KB, so aggregate in SQL. `match_player` is hundreds of GB: always
filter on `match_id`, `account_id`, or `start_time`, and sample with
`match_id % N = 0`. Filtering on other columns times out at 300s.

> The Claude Code MCP client currently can't list this server's tools
> (`tools/list` fails schema validation on `ttlMs` / `cacheScope`). Plain
> JSON-RPC over `curl` to `execute_query` works, and produced every SQL number
> in this document.

**Facts from the assets API aren't copied here.** Heroes, item names, costs,
tiers, slot types, and components are live fields read by
`src/deadlock/assets.py`. A copy here would go stale on the next patch, so this
document names the field instead of the value.

## The shop

### Tiers and prices

Four tiers you can buy, each with one price. VERIFIED on all 5,095,598
purchases: every purchase of a tier has the same cost.

| Tier | Cost | Purchases observed |
|-----:|-----:|-------------------:|
| 1 | 800 | 1,324,047 |
| 2 | 1,600 | 1,632,208 |
| 3 | 3,200 | 1,270,198 |
| 4 | 6,400 | 869,145 |

In code, read tier and cost from `Item.tier` and `Item.cost`
(`assets.load_items`), not from this table.

**Nobody buys tier 5.** 0 of 5,095,598 purchases were tier 5 (VERIFIED). The
assets list 17 tier-5 entries with a placeholder cost of 9999; they belong to
another game mode. `assets.shopable_items()` still returns them, so "shopable"
doesn't mean "can be bought in this mode".

### Slot types

Three shop tabs: weapon, vitality, spirit (`Item.slot_type`). Counts per tab
and tier come from the API.

The tab is a shop category and also decides which investment bonus an item's
souls count toward. See [Where "slot type is not playstyle" stops
applying](#where-slot-type-is-not-playstyle-stops-applying).

### Item slots

A hero starts with 9 item slots and gets 3 more by destroying enemy Walkers,
for 12 (the Walker part is UNVERIFIED; the counts are VERIFIED). Any item goes
in any slot; the tabs don't have separate slots.

VERIFIED by tracking what each of 299,983 players held over time: 99.69% never
hold more than 12 items at once. The 0.31% above 12 are a recording quirk,
where a component's `sold_time_s` lands at or after its composite's
`buy_time_s`, not real 13-item inventories.

84.8% of players hold more than 9 items at some point, so the extra slots are
a normal part of a build.

**Slots 10-12 come from destroying Walkers, not from time passing.** The table
below doesn't measure that:

| Items held | Median time first reached |
|-----------:|--------------------------:|
| 9 | 1,315s (~22 min) |
| 10 | 1,567s (~26 min) |
| 11 | 1,809s (~30 min) |
| 12 | 2,065s (~34 min) |

It shows when players first hold N items, not when the Nth slot opens. A
player holds a 10th item only after they have the slot and choose to fill it,
so these times are later than the slot opening and can't be turned into a
slot clock. A team that takes a Walker early gets the slot early.

**Walker times are in the purchase table** (VERIFIED). `ingest.py` requests
objectives, and `dataset.match_to_rows` adds the times to each player's rows
as `slot10_unlock_s`, `slot11_unlock_s`, and `slot12_unlock_s`. The same data
is in SQL on the MCP server (`objectives.team_objective`,
`objectives.destroyed_time_s`, `objectives.team`). Walkers are `Tier2LaneN`.
`Tier1LaneN` is a Guardian, `BarrackBossLaneN` a Base Guardian, and `Titan`
the Patron; there are also `Core` and `TitanShieldGeneratorN`.

The raw objectives data has two traps, both handled in
`dataset.team_match_state` and tested in `tests/test_dataset.py`. Handle them
again if you read the raw data yourself:

- `objectives.team` is the team that lost the objective, not the one that
  took it. A destroyed `Core` never belongs to the winning team (0 of 220, and
  0 of 50 rechecked on the bulk endpoint). The slot goes to the other team.
- `destroyed_time_s` of 0 or 1 means "never destroyed" (1,299 of 6,420 Walker
  rows). Those become null; read as times, they would drag the 10th percentile
  down to 1 second.

**Mid-Boss kills** come with `include_mid_boss` and are stored as
`midboss_kill_s`, the first Mid-Boss the player's team claimed. Mid-Boss is
neutral, so nothing is flipped. `team_killed` and `team_claimed` differ in 11
of 81 sampled kills, and the souls go to `team_claimed`.

When a team gets its Nth extra slot, meaning it destroys its Nth enemy Walker
(2,038 team-matches for the first, a 3-day SQL sample, VERIFIED):

| Slot | 10th percentile | median | 90th percentile |
|---:|---:|---:|---:|
| 10th | 743s (12.4 min) | **1,080s (18.0 min)** | 1,475s (24.6 min) |
| 11th | 1,030s | **1,402s (23.4 min)** | 1,868s |
| 12th | 1,290s | **1,712s (28.5 min)** | 2,220s |

The same measure on the current `purchases.parquet` (296,478 player-matches,
VERIFIED) agrees closely. It is a different sample, so it confirms the table
above rather than refining it:

| Slot | Median | Player-matches with a time |
|---:|---:|---:|
| 10th | 1,117s | 96.8% |
| 11th | 1,400s | 86.6% |
| 12th | 1,669s | 70.7% |

Almost every team takes at least one Walker (96.8%), but only 70.7% take a
third, so a 12th slot isn't guaranteed. `midboss_kill_s` is present for
66.9%, with a median of 1,584s.

**The spread matters more than the median.** The 10th slot opens anywhere from
12 to 25 minutes in, so no fixed time describes it. Players first hold a 10th
item at 1,567s, while the slot usually opens at 1,080s, 487s earlier. Players
get each slot well before they fill it:

| Slot | Median opens | Median first held | Gap |
|---:|---:|---:|---:|
| 10 | 1,080s | 1,567s | +487s |
| 11 | 1,402s | 1,809s | +407s |
| 12 | 1,712s | 2,065s | +353s |

So the held-items table overstates how short slots are. A check built on it
would reject builds the game allows.

**Running out of slots isn't a hard stop.** Players normally sell a tier 1 or
2 item to make room for something better. That is most of the tier 1 sell rate
(see [Components and absorption](#components-and-absorption)), so a build that
goes over the slot count for a while can still be followed.

So: **don't limit build generation by a time-based slot count.** A build with
more than 12 items over the match isn't automatically wrong, and neither is one
that reaches 10 items early.

### Active items

**A player can hold at most four active items** (UNVERIFIED on the wiki,
VERIFIED here). Tracking how many items with `is_active_item == true` each of
257,050 players (who bought any active item) held at once:

| Most actives held at once | Players |
|-------------------------:|--------:|
| 0 | 821 |
| 1 | 84,109 |
| 2 | 85,441 |
| 3 | 54,089 |
| 4 | 32,529 |
| 5 | 61 |

99.976% never go over 4, and the 61 at 5 are the same sold/bought overlap
quirk. This is a hard rule, and build generation doesn't enforce it. 50 of
173 shop items are active (`is_active_item`). `activation` is `passive`
(123), `instant_cast` (30), `press` (19), or `instant_cast_toggle` (1).

> **Look up active items by id, never by name.** The catalogue has 17 names
> used twice, and the two Silencer entries disagree: the shop one is
> `passive` with `is_active_item=false`, and a non-shop one is `instant_cast`
> with `is_active_item=true`. Matching by name marks Silencer as active and
> invents a rule violation. Filter to shop items first, then use the id.
> This has already caused one wrong finding. `assets.shopable_items()` returns
> the right entries, keyed by id.

### Components and absorption

62 shop composites have components (60 have one, 2 have two;
`component_items`, resolved by `assets.component_map`). Buying the composite
uses up the component, and the composite's price is reduced by the
component's full cost.

VERIFIED that the discount is real: adding up list prices per player gives a
median of 43,200 souls, against a median final net worth of 41,212. 69.7% of
players' list-price totals are more than their whole final net worth (median
ratio 1.056), which is only possible if components are credited back.

Most "sold" rows are absorption, not selling (VERIFIED):

| Items | Sold rate |
|---|---:|
| Component of something | 70.6% |
| Not a component | 6.4% |
| Tier 1 | 86.6% |
| Tier 2 | 40.1% |
| Tier 3 | 7.2% |
| Tier 4 | 1.1% |

Holding time separates the two independently of tier: the median time held
before "selling" is 414s for components and 1,426s for other items (VERIFIED,
1.9M sold rows). Absorption happens quickly; real sells happen late.

4 of the 64 component links cross slot types. Spiritual Overflow (weapon)
absorbs Spirit Lifesteal (vitality); Kinetic Dash (weapon) and Arcane Surge
(spirit) both absorb Extra Stamina (vitality); and Ballistic Enchantment
(weapon) absorbs Mystic Expansion (spirit). These move souls from one
investment bonus to another, which matters for the 4,800 threshold below.

### Selling

Selling refunds half the item's cost, or the full cost if sold in the shop
right after buying (UNVERIFIED: the data records that a sale happened, not
the refund). Investment bonuses are lost when the item is sold (UNVERIFIED).

So a real sell is expensive: advice to buy an item early and sell it later
means losing half its cost. About 6% of purchases are real sells.

## Investment bonuses: the 4,800 spike

Souls spent within one slot type build up a stat bonus for that type, up to
28,800 souls. The bonus jumps at 4,800 souls in a type, which players call the
4.8k spike.

Wiki values (UNVERIFIED):

| Souls in slot type | Weapon damage | Health | Spirit power |
|---:|---:|---:|---:|
| 800 | +9% | +9% | +7 |
| 1,600 | +12% | +12% | +11 |
| 4,800 | **+46%** | **+38%** | **+38** |
| 28,800 (cap) | +115% | +66% | +100 |

**Players clearly play around it** (VERIFIED). Adding up each player's souls
per slot type after every purchase, across all 5.1M purchases, and checking
whether the next purchase is the same slot type:

| Souls in that slot type after this purchase | n | P(next purchase same slot type) |
|---|---:|---:|
| 800-1,599 | 626,781 | 0.440 |
| 1,600-3,199 | 815,986 | 0.492 |
| 3,200-4,799 | 566,470 | **0.563** |
| exactly 4,800 | 261,546 | 0.427 |
| 4,801-6,399 | 311,612 | **0.275** |
| 6,400 or more | 2,216,871 | 0.488 |

Players keep buying the same slot type as they approach 4,800 (0.563) and
switch once they reach it (0.275 just past). This isn't because of purchase
position; it holds within every position band (VERIFIED):

| Purchase number | at 3,200 | at 4,000 | at 4,800 | at 5,600 |
|---|---:|---:|---:|---:|
| 2-5 | 0.571 | 0.552 | 0.402 | 0.209 |
| 6-9 | 0.572 | 0.570 | 0.437 | 0.279 |
| 10-13 | 0.560 | 0.534 | 0.461 | 0.336 |

67.4% of players land exactly on 4,800 in at least one slot type (VERIFIED).
4,800 can be reached from many combinations of 800 and 1,600, or as 3,200 plus
1,600; players aim for it.

This is the biggest mechanic the model can't see. It decides which slot type
the next purchase comes from, which is exactly the kind of order this project
models.

## Souls

Souls are both money and experience. A soul that buys an item also counts
toward the boon level that gives ability points. Spending doesn't lower your
level, because level follows souls earned, not souls held. So items and
abilities don't compete for souls, and "spending souls on abilities instead of
items" isn't possible in this game.

Income (all UNVERIFIED, from the wiki; included because it sets how fast
builds become affordable):

- Start with 600 souls.
- Hero kill: 200, plus 50 per minute, up to 2,200 at 40 minutes. First blood
  +125.
- Trooper: 100, plus 2 per minute. Ranged kills drop two orbs (one flying, one
  on the ground, 50% each); a melee kill gives the killer the flying orb's
  souls directly.
- Neutrals: 41, 68, or 181 for small, medium, or large, plus 0.44, 0.73, or
  1.95 per minute, split among everyone who damaged them.
- Guardian 1,250 (30% to nearby heroes, 70% to the team); Walker 3,500 to the
  team; Mid-Boss 3,000 to the team.
- Catch-up: a team behind by more than 3,000 net worth earns up to 26% more
  from troopers and objectives, and up to 126.8% more for killing richer
  heroes. The two poorest players on a team slowly gain souls after 8
  minutes.
- Unsecured souls (from neutrals, sacrifices, and crates) are dropped on death
  above 50 plus 5 per minute, and become secured at 0.5% a second.

Observed pace (VERIFIED, median final net worth by match length, in six
groups): about 1,036 souls a minute in short matches, rising to 1,251 in long
ones. Median final net worth 41,212; median 17 purchases (10th percentile 13,
90th 22).

Because of catch-up souls, a build's timing isn't a fixed clock. A player who
is behind reaches an item later than `build.MEDIAN_BUY_TIME_S` suggests, but
sooner than their deficit alone would suggest.

## Ability points and levels

**Boons.** Reaching soul thresholds raises your boon level, up to 35, which
raises weapon damage, melee damage, health, and spirit power (values differ
per hero). The thresholds start 600, 800, 1,100, 1,500, 2,000, 2,600, 3,200,
3,800 and reach 49,200 at level 35.

VERIFIED against the `stats.level` and `stats.net_worth` series in
`match_player`: the lowest net worth seen at each level matches the wiki
closely: 1,109 at level 3 (wiki 1,100), 1,501 at 4 (1,500), 2,000 at 5
(2,000), 2,602 at 6 (2,600), 3,069 at 7 (3,200), and 3,751 at 8 (3,800). The
stats are sampled, so the lowest value seen is at or above the true
threshold.

**Unlocking abilities.** Levels 0, 2, 4, and 7 each unlock an ability. The
first three abilities can be unlocked in any order. The ultimate unlocks only
at level 7, which is 3,800 souls.

VERIFIED, and it shows as a sharp cutoff. Over 4.45M ability points, the time
of the first point in slot 4 against slots 1-3:

| | 1st pct | 5th | 25th | median | 75th | 95th |
|---|---:|---:|---:|---:|---:|---:|
| Ultimate (slot 4) | 280s | 310s | 352s | **383s** | 413s | 457s |
| Other abilities | 1s | 8s | 18s | 107s | 193s | 232s |

Nobody unlocks an ultimate before about 280s, because nobody has 3,800 souls
before then. Other abilities start at 1 second.

**Upgrade costs.** Each ability has 3 upgrades costing 1, 2, and 5 ability
points, 8 points to max one ability. Every boon level that doesn't unlock an
ability gives a point, up to 32 in total.

VERIFIED, confirming both numbers. In the data an ability has levels 1 to 4:
level 1 is the free unlock and 2, 3, 4 are the paid upgrades. Scoring levels
1, 2, 3, 4 as 0, 1, 2, 5 points and adding up per player, the median is 27 and
the 90th, 99th, and 99.9th percentiles are all exactly 32, with only 0.001%
above. No other cost schedule gives a clean ceiling at 32. Points can be spent
in any order, including saving them for a 5-point upgrade.

How many abilities a player takes to level 4 is a real choice (VERIFIED,
299,983 players): none 486, one 2,434, two 38,743, three 183,266, four 75,051.
Most players max three.

An upgrade can be refunded within 10 seconds if no ability was used in that
time (UNVERIFIED).

### What each upgrade does: the `upgrades` field

The costs above say what an upgrade costs. What it gives is in `upgrades` on
the ability's asset record, which `src/deadlock/upgrades.py` parses (#42). It is
listed per upgrade, so "this effect only exists from the second upgrade" can
be looked up.

VERIFIED against `data/raw/assets/v1_assets_items__*.json`: of 285 hero
ability records (`type == "ability"` with a `hero`), 220 have `upgrades`, each
with exactly 3 entries, across all 56 heroes. Entry 0 is the 1-point upgrade,
entry 1 the 2-point, and entry 2 the 5-point. Each has a `property_upgrades`
list of `{name, bonus}`, with 387 distinct names across all of them.

Examples of effects that only exist after an upgrade and aren't stated
anywhere else:

| Hero and ability | Upgrade | Gives |
|---|---|---|
| Dynamo, Kinetic Pulse | 2nd | `BulletResistReduction: -15`, `SlowPercent: 30`, `SlowDuration: 4` |
| Wraith, Full Auto | 3rd | `MagicDamagePerBullet: 0.045`, `UnlimitedAmmo: 1` |
| Lash, Flog | 2nd | `AbilityCooldown: -16`, `FireRateSlow: 30` |

So "Kinetic Pulse shreds bullet resist" is only true from the second upgrade.
Anything the site or model says about an ability's effect depends on its
upgrade level, and that level is in the data, so state it.

### Ability scaling is under `scale_function`, not `scale`

Each property's scaling is at `properties[<prop>].scale_function`, with
`specific_stat_scale_type` (such as `ETechPower` or `EWeaponPower`) and a
numeric `stat_scale`. `properties[<prop>].scale` is always empty, which gives
a clean but wrong zero. That mistake was made once in #21 and reported as "no
scaling data exists" before it was caught.

VERIFIED: 177 of 285 hero abilities have a numeric `stat_scale`, across 52 of
56 heroes. For example, Lash's Ground Strike is `ETechPower 0.7905`, Death Slam
`0.97`, and Flog `0.85`. Paradox's Kinetic Carbine is `EWeaponPower 125.0` on
`MaxBonusBulletDamage`, while Pulse Grenade and Paradoxical Swap scale with
`ETechPower`.

Base weapon stats are reachable the same way: `hero.items.weapon_primary` is a
`class_name` whose record has `weapon_info`, with `bullet_damage`,
`cycle_time` (fire rate), `bullet_speed`, `reload_speed`, and the
`damage_falloff_*` ranges. 86 records have `weapon_info`.

### Scaling type doesn't say which items an ability wants

An ability can scale with spirit and still want gun items, because it works
through the weapon. Wraith's Full Auto scales with `ETechPower` but gives
`BonusFireRate` and `MagicDamagePerBullet`, and Infernus's Afterburn builds up
per bullet hit. Concluding "scales with spirit, so buy spirit items" from the
scaling type gets these heroes wrong.

The property names identify them. `behaviours` has no flag for "works through
the weapon" on any of the 285 abilities. `TechPower` and `WeaponPower` don't
help either: they are placeholders (`value: "0"`) on every ability checked.

A name regex overcounts. Matching property and upgrade names against
`bullet|firerate|ammo|magazine|reload|weapondamage|crit|recoil|perbullet|buffbaseweapon`
(case-insensitive, ignoring the two placeholders) finds 92 of 285 abilities
across 45 of 56 heroes (VERIFIED, #42). But it also matches defensive and
enemy-debuff properties: `BulletResist` (15 abilities), `FireRateSlow` (20),
resist shred, bullet evasion and bullet shields. An earlier version of this
section said 41 of the 92 also scale with `ETechPower`. That count doesn't
reproduce: 43 have a property whose `specific_stat_scale_type` is
`ETechPower`, and 67 scale with spirit if the `scale_function_tech_damage`
class is counted too.

**A listed property isn't necessarily set.** Many weapon properties are listed
at `value: "0"` and only get a value from an upgrade tier, and some are never
set at all. This is the same trap `semantics.py` records for items. Kinetic
Pulse lists `BonusFireRate`, `BulletResistReduction` and
`IncomingBulletDamagePercentFromCaster`, all at `"0"`. Its only weapon-related
upgrade is `BulletResistReduction: -15` at the 2nd upgrade, which shreds the
enemy and doesn't work through Dynamo's gun. Mirage's Dust Devil lists only
`TargetBulletEvasionChance: "0"`, which is defensive, and its upgrades add
`WhirlwindEvasionChance`. **Neither ability works through the gun.** Both
appeared as examples in an earlier version of this table.

The rule `upgrades.py` uses (VERIFIED, #42): a property works through the gun
when the game tags it with a weapon modifier type (`provided_property_type`
`MODIFIER_VALUE_FIRE_RATE`, `..._WEAPON_DAMAGE_INCREASE`, `..._AMMO_CLIP_SIZE`,
`..._BULLET_LIFESTEAL`, and a few more) or its name marks an on-hit proc
(`PerBullet`, `CritBuildup`, `PerShot`, `Headshot`...). Names containing Slow,
Debuff or Summon are excluded, since those act on the enemy's or a summon's
gun. The property must also be set, either nonzero at base or given a bonus
by an upgrade. By that rule, 38 of 285 abilities on 32 heroes work through the
gun, 28 of them spirit-scaling. Among the signature abilities of the 38
playable heroes, **26 abilities on 21 heroes** scale with spirit and work
through the gun.

| Hero | Ability | Gun effect | From |
|---|---|---|---|
| Wraith | Full Auto | `BonusFireRate: 20`, `MagicDamagePerBullet: 2`; `UnlimitedAmmo` added | base; 5-point |
| Infernus | Afterburn | `BuildUpBulletPercentPerHit`, `CritBuildup`, `RefillDurationCrit` | base |
| Mina | Love Bites | `MagicDamagePerBullet`, `BuildUpPerShot` | base |
| Holliday | Crackshot | `AbilityCooldownPerHeadshot` | 5-point upgrade |

When the gun effect arrives, for the 26: 15 at base, 5 at the 1-point upgrade,
1 at the 2-point, and 5 at the 5-point. So for 11 of them, knowing whether the
ability works through the gun requires reading `upgrades`. Nine signature
abilities list a weapon property that nothing ever sets (Kinetic Pulse,
Quantum Entanglement, Sticky Bomb, Boot Kick, Stalker's Mark, Eternal Night,
Seismic Impact, Concussive Combustion, Medicinal Specter).

## Imbue

Choosing one of the hero's four signature abilities for an item to affect,
done at the shop when buying the item.

**An imbue can't be changed.** To change the target you sell the item and buy
it again, losing half its cost. So an imbue is a bigger commitment than a
purchase, and "buy Mystic Reverb" without a target is only half the advice.

Restrictions:

- Echo Shard and Omnicharge Signet (`imbue_active_non_ult`) can't target the
  ultimate. Choosing Echo Shard over Mystic Reverb says the build isn't about
  the ult.
- Only Mystic Expansion and Duration Extender can imbue passive abilities
  (UNVERIFIED).
- When Silver imbues a non-ultimate ability, both the human and werewolf
  versions are imbued (UNVERIFIED).

Which items can be imbued, and in which group, is an API field (`Item.imbue`:
`imbue_active`, `imbue_active_non_ult`, or `imbue_modifier_value`). Read it
rather than hard-coding a list. In the cached assets, 13 entries have it: 9 in
the shop and bought, 2 in the shop at tier 5 (never bought), and 2 disabled.
All are spirit items except Ballistic Enchantment, a weapon item, which is the
only imbue choice a gun build makes.

**An imbue is never missing.** VERIFIED: 0 of 462,517 imbue rows have a zero
target. A hero with a low imbue rate just rarely buys imbueable items.

## Shop visits

Purchases aren't evenly spaced. 18.7% of consecutive purchases are within 5
seconds of each other (896,403 of 4,799,266, VERIFIED): one shop visit,
several items. The median gap between purchases is 112s (10th percentile 1s,
90th 251s).

About a fifth of those bursts are a component bought right before its
composite: 176,261 of 896,403, or 19.7% (VERIFIED). That is one purchase the
shop charges in two steps, and the component is absorbed right away. The other
80.3% are real multi-item visits: only 46.2% of them share a slot type with
the previous purchase, and 28.9% have the same timestamp. Half the component
bursts (49.3%) are 0 seconds apart.

Purchases in the same visit share slot types more often: the chance of the
same slot type as the previous purchase is 0.552 within 5 seconds, against
0.452 when more than 60 seconds apart (VERIFIED). A burst is closer to one
decision about a slot type than several separate ones.

The model treats every purchase as a separate step with its own time bucket,
so a 4-item burst counts as four decisions at about the same time.

---

# Mechanics the model doesn't use

The model's inputs (`sequence.LEVEL_KEYS`) are `hero_id`, `archetype_id`,
`prev1`, `prev2`, `n_owned`, and `time_bucket`, plus `average_badge` as a row
weight (on by default since ADR 0002). Souls are only used to filter out
items the player can't afford (`state.candidate_items`), and build generation
sets them to 10^9, which turns that off. Enemy heroes are shown next to
recommendations (`counters.annotate`) but aren't a model input.

So the model can't see anything below.

| # | Mechanic | Worth modeling? | Why |
|---|---|---|---|
| 1 | **Souls per slot type, and the 4,800 threshold** | Yes, the most valuable | It decides the order of purchases, and the effect is large and verified (same-slot-type chance 0.563 falling to 0.275 across the threshold, holding within purchase position). The model knows the last two items but not the running total per slot type, so it can't represent "1,600 short of the weapon spike". Simplest version: add the running total per slot type, bucketed at the thresholds, as a key or a re-ranking adjustment. |
| 2 | **The 4-active-item limit** | Yes, cheap, though no build breaks it today | A hard rule (99.976% of players, VERIFIED) that `build.py` doesn't check: it checks `MAX_HELD_ITEMS` but doesn't count actives. All 75 shipped builds follow it. An earlier claim that Gun Venator needed 5 actives came from matching actives by name (see above) and was withdrawn. So this guards against a future regression, not a current bug. A filter on candidates, not a learned feature. |
| 3 | **Slots going from 9 to 12 via Walkers** | No, slots are rarely the limit | Slots 10-12 come from Walkers, not time. The 10th slot opens at a median 1,080s (range 743-1,475s), and players first hold a 10th item at 1,567s, 487s later; 11 and 12 look the same (see [Item slots](#item-slots)). Players usually aren't short of slots, the range is too wide for any fixed time, and selling a tier 1 or 2 item frees a slot anyway. An earlier claim that 8 builds couldn't be followed before 1,315s misread the held-items table as a slot clock and was withdrawn. |
| 4 | **Souls as a real budget** | Yes, for advice during a match | Build generation treats souls as unlimited, so it can only say what to buy eventually, never what to buy now. The in-match `next` command takes `--souls` but only as a filter, so it can't say "wait 40 seconds and buy the tier 3 instead". That is real advice, and `economy.py`'s `n_saved_up` shows players doing it. |
| 5 | **Shop-visit bursts** | Probably, as a correction | 18.7% of consecutive purchases are in the same visit, and 19.7% of those are a component right before its composite, one purchase in two steps. Counting these as separate timed decisions makes some bigrams look better supported than they are. Component bursts are the easiest to merge in training, since `component_map()` already knows the pairs. |
| 6 | **Ability points at the time of purchase** | Yes, and the data exists | `abilities.parquet` has 4.45M ability points, and the item model reads none of them. Whether the ultimate is unlocked (a hard 3,800-soul cutoff, VERIFIED at a median 383s) changes which items make sense: an imbue on the ultimate before it exists is wasted. `abilityorder.py` recommends ability order separately but isn't an input to the item model. And the upgrade level decides which effects exist: 220 abilities have 3 listed upgrades, so an effect like Kinetic Pulse's `BulletResistReduction` at the 2nd upgrade is part of the player's state when buying. |
| 6b | **What upgrades give, as an input to clustering or the model** | No (ADR 0004) | What a player's upgrades unlock is fixed by their ability order, so any upgrade-effect feature reweights the order ADR 0003 rejected. Measured in #42: effect-category exposure lost 5 of 31 splits, and the 5-point tier alone lost 14. No generated build has an upgrade-timing defect an item-model key would fix. `upgrades.py` parses the field for describing abilities. |
| 6c | **Abilities that work through the gun** | No (ADR 0004) | 26 signature abilities on 21 of 38 heroes scale with spirit and work through the gun (strict rule, see above). Measured in #42: these heroes split as often and as clearly as the rest, along the same gun/spirit axis; their spirit buyers invest *less* in the gun-routed ability; and counting that spirit as gun renames no Spirit/Gun archetype. Both per-player forms tried lost splits. |
| 7 | **Imbues can't be changed** | Yes, in how it's shown | A display change, not a model change: say that changing the target costs half the item. Right now a target is shown like any other statistic. |
| 8 | **Absorption across slot types** | Minor, but easy to get wrong | The 4 cross-tab component links move souls between slot types. Anyone implementing #1 from the purchase sequence will get these wrong unless they account for absorption. |
| 9 | **Catch-up souls and net-worth position** | No, on purpose | This is the line `docs/DIAGNOSIS.md` is about. By mid-match, being ahead is mostly a result of winning: its correlation with winning is 0.16 in the first phase and 0.60 by the fourth. Using it as an input brings back the failure this project was rebuilt to avoid. Listed so nobody rediscovers it as a promising feature. |
| 10 | **Real sells** | No | About 6% of purchases, and the model outputs a purchase sequence. Modeling sells would need a different output for a rare event. |
| 11 | **Boon level and stat scaling** | No | It follows from net worth and time, which `time_bucket` and `n_owned` already stand in for. It says nothing extra about choices. |

---

# Where the current assumptions break

## Where "slot type is not playstyle" stops applying

The rule that the shop tab isn't the playstyle (Siphon Bullets, Melee Charge,
and Rescue Beam are all in "wrong" tabs) is right for naming and clustering:
don't name an archetype from its tabs, and don't cluster on tab shares (19
splits at 0.321) when build families work better (28 at 0.429).

But the tab still matters to the game. Investment bonuses count per slot type,
so an item's tab decides which bonus its souls go toward and whether the
player reaches 4,800. Two items that do the same job aren't interchangeable if
one reaches the threshold and the other doesn't.

The same fact reads two ways. Lash's gun archetype has 40% of its souls in
vitality, just because Siphon Bullets costs 6,400. For naming, that's the trap:
don't call it a tank build. For the game's rules, those 6,400 souls really do go
into vitality, past the 4,800 spike, and Lash gets the health bonus whatever
the build is about.

So: use build family to name and cluster, and use slot type to reason about
thresholds and purchase order.

## Items and abilities don't share a budget

It's natural to assume players trade souls between items and ability upgrades.
They don't. Ability points come from boon levels, boon levels come from souls
earned, and spending doesn't reduce them. There is nothing to trade off.

## "Sold" mostly doesn't mean sold

`CONTEXT.md` already covers this under Absorption. It's repeated here because
the field name suggests otherwise and it keeps being rediscovered. The holding
times are further evidence: 414s median for components against 1,426s for
other items.

## "Shopable" doesn't mean you can buy it

`assets.shopable_items()` returns 173 items, including 17 tier-5 entries bought
0 times in 5.1M purchases. Code that treats the shopable set as the candidate
set includes 17 items nobody can buy in this mode. `build.py` is safe only
because tier-5 items never get any probability; code that listed candidates
evenly wouldn't be.

## The intended build is recorded for a small minority

`hero_build_id` is the community build a player selected when the match
started, and `pregame_hero_id` is the hero they locked in before the swap
window. Both come from match analysis.

Both are returned under `include_player_info`, which `ingest.py` already
passes, and both are columns on the purchase table, added per player by
`dataset.match_to_rows`. Null means "unknown", never "no build selected"; the
API's 0 becomes null for the same reason. Pages cached before these columns
were added have neither field, so they become null.

These are shared community build ids, not per-player copies (VERIFIED): the
most-used ids appear across many accounts, such as build 256053 on hero 1,
used by 64 players on 64 different accounts. `/v1/builds/{hero_id}/{build_id}`
returns the full build: items, ability order, categories, per-item notes,
`sell_priority`, and `imbue_target_ability_id`.

**So planned against actual can be compared.** For example, a hero 17 player
on "salty's spirit talon" (build 126856) bought 18 shop items, 13 from the
build and 5 not (Burst Fire, Enchanter's Emblem, Grit, Rapid Rounds, Swift
Striker).

Two cautions before building on this.

**Coverage is per match, not per player** (VERIFIED, 6-week sample). A match
is either analyzed or not, nearly all-or-nothing:

| Build ids in the match | Matches | Share |
|---|---:|---:|
| 0 (not analyzed) | 4,263 | 89.8% |
| 1-3 | 12 | 0.3% |
| 4-7 | 227 | 4.8% |
| **8-12** | **243** | **5.1%** |

So the per-player rate, which falls from about 19% in late June to under 1%
in the latest week as analysis falls behind, is the wrong measure. Over that
six-week sample, 10.2% of 4,745 matches were analyzed, and an analyzed match
usually has 8 to 12 of its 12 players.

**That 10.2% depends on the time window** (VERIFIED). A 100-match sample from
the newest window on 2026-09-14 had a build id in 1 match. Don't combine the
two numbers.

**In the window this project uses, coverage is 0.21%, too low to model on**
(VERIFIED, the full 24,999-match training set as rebuilt on 2026-09-14).
`hero_build_id` is present for 623 of 296,478 player-matches, in 87 of 24,999
matches, across 371 builds and all 38 heroes. That's about 16 rows per hero
and 1.7 per build before splitting by archetype. `pregame_hero_id` is present
more often, 1,029 player-matches (0.35%), and 128 of those players switched
hero after locking in. The two fields have different coverage.

**Split by archetype, no cell has enough** (VERIFIED, same data, against the
80 cells of the 2026-09-15 fit). All 623 rows have an archetype and they reach
78 of 80 cells, but the median cell has 6.5 rows, the largest has 26, and none
reaches 30. `evaluate.prevalence_gate` treats a cell under 300 as
inconclusive. Only a wider time window would help.

The cause is the download window. `scripts/pull_data.py` starts at the current
patch (2026-08-22) and `ingest.pull_matches` fetches newest first, so the
training data is the last few days, which analysis hasn't reached yet.
Anything that needs the intended build must download its own older window with
`max_match_id`, and count rows per cell before modeling. The six-week sample
that gave 10.2% went back far enough; the training window doesn't.

There is enough volume in older data. A 1-in-397 sample of six weeks had
3,727 player-rows across 482 matches, all 38 heroes, and 1,001 builds, so the
full data would have around a million player-rows. The recent gap is an
analysis backlog, so usable data runs a few weeks behind the present.

**On settled data, coverage is all-or-nothing and levels off near 14%**
(VERIFIED, upstream `match_player` via the MCP SQL server, 2026-09-15). In one
July week, 282,798 matches had no build id, 47,042 had all 12, and about 290
were in between (caught mid-analysis). Monthly player-row rates: March 2026
7.97%, May 14.72%, June 13.15%, July 14.64%, August 6.98%, September 1.62%.
The field doesn't exist before March 2026 (0 of 32M rows in January and
February). Daily: Aug 1 14.1%, Sep 1 3.2%, Sep 11 1.4%, Sep 15 0.12%. The
backlog is four to six weeks, and a window is settled once its rate reaches
about 14%, so check that before downloading. The column stores 0 for "none",
so filter `hero_build_id != 0`; a null check alone overcounts. For the current
patch (from 2026-08-22), almost everything is still unsettled, so any window
large enough to use is mostly the previous patch.

**Analyzed matches are about a tier higher** (VERIFIED, same July week).
Median `average_badge` is 72 for analyzed matches and 63 for the rest, and the
unanalyzed matches have 40,750 null badges against 96. Anything measured on
intended builds comes from a different set of players than the shipped builds,
and doesn't compare with them.

**Count the right thing.** A published build is a menu, not a shopping list:
the example above lists 38 shop items, some in categories named `Optional`,
against 12 slots. "Followed 13 of 38" means nothing. Measure the share of the
player's purchases that came from the build, and which items they chose when
they left it. The API also notes that `hero_build_id` is the build selected at
match start and doesn't show changes during the match, so a "deviation" may be
a switch to another build.

## Purchases aren't all separate decisions

`sequence.py` models P(next item | previous two items, time bucket). 18.7% of
consecutive purchases happen in the same shop visit, where the "next" item was
chosen at the same time, not afterwards. The model still works, but at short
gaps the bigram counts measure items chosen together, not one following
another. For the 19.7% of bursts that are a component followed by its own
composite, it isn't even two choices: it's one purchase the shop charges in
two steps.
