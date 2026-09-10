# Game mechanics

What a session needs to know about how Deadlock works before it changes what
this project models or shows. Not a manual: every mechanic here is one that can
plausibly change a build recommendation, its **order**, or its **timing**.

## How to read this

Each number is marked:

- **VERIFIED** — confirmed against data in this repo, with the method and the
  count. Local data is `data/processed/purchases.parquet` (5,095,598 purchase
  rows, 299,983 player-matches), `data/processed/abilities.parquet` (4,454,785
  ability level-ups) and `data/processed/imbues.parquet` (452,103 imbues).
- **UNVERIFIED** — stated by <https://deadlock.wiki> and not checkable against
  what we hold. Believe it, but do not build a gate on it without measuring.

**A third source exists beyond local parquet and the assets API:** the
deadlock-api MCP server at `https://api.deadlock-api.com/v1/mcp` gives read-only
DuckDB SQL over hourly snapshots of the upstream tables, including columns the
local ingest never pulled (`objectives.*`, `mid_boss.*`, `stats.*`). It is not
subject to the 2/min, 20/hr limit of the REST SQL endpoint. Results cap at 1,024
rows and 50 KB, so aggregate in SQL rather than pulling rows. `match_player` is
hundreds of GB: always filter on `match_id`, `account_id` or `start_time`, and
sample with `match_id % N = 0`.

**Facts that live in the assets API are not restated here.** Hero rosters, item
names, costs, tiers, slot types and components are live fields, already wired
through `src/deadlock/assets.py`; copying them into markdown creates a second
source of truth that goes stale on the next patch. Where a fact is an API
field, this document names the field instead of the value.

## The shop

### Tiers and prices

Four buyable tiers, one price each. **VERIFIED** against all 5,095,598
purchase rows — every row at a tier carries exactly one cost, no exceptions:

| Tier | Cost | Purchases observed |
|-----:|-----:|-------------------:|
| 1 | 800 | 1,324,047 |
| 2 | 1,600 | 1,632,208 |
| 3 | 3,200 | 1,270,198 |
| 4 | 6,400 | 869,145 |

Read tier and cost from `Item.tier` / `Item.cost` (`assets.load_items`), never
from a table here.

**Tier 5 is never bought.** 0 of 5,095,598 purchases are tier 5 (**VERIFIED**).
The assets API lists 17 tier-5 entries with a placeholder cost of 9999; they are
a separate game mode's items. `assets.shopable_items()` still returns them, so
anything ranking candidates must not treat "shopable" as "reachable".

### Slot types

Three shop tabs: `weapon`, `vitality`, `spirit` (`Item.slot_type`). Counts by
tab and tier come from the API; do not restate them.

Slot type is a shop category **and**, separately, the pool that investment
bonuses accumulate in. See [Where "slot type is not playstyle" does not
apply](#where-slot-type-is-not-playstyle-does-not-apply).

### Item slots

A hero starts with **9** item slots and unlocks **3 more by destroying enemy
Walkers**, for 12 (UNVERIFIED as to the Walker mechanism; the caps are
VERIFIED). Any item fits any slot — the three tabs do not have separate slot
counts.

**VERIFIED** by sweeping buy/sell intervals per player over all 299,983
player-matches: 99.69% never hold more than 12 items concurrently. The 0.31%
above 12 are an artifact of a component's recorded `sold_time_s` landing at or
after its composite's `buy_time_s`, not real 13-item inventories.

84.8% of players exceed 9 concurrent items at some point, so the extra slots
are not a corner case — they are part of the normal build.

**Slots 10-12 are unlocked by destroying enemy Walkers. They are not unlocked
by time.** This is the mechanic; the table below is *not* a measurement of it.

| Items held | Median first reached |
|-----------:|---------------------:|
| 9 | 1,315s (~22 min) |
| 10 | 1,567s (~26 min) |
| 11 | 1,809s (~30 min) |
| 12 | 2,065s (~34 min) |

**Read that table carefully. It records when players first *hold* N items, not
when the Nth slot first *becomes available*.** A player holds a 10th item only
once they both have the slot and want to fill it, so these medians are an upper
bound on slot availability, mixed with buying behaviour, and they cannot be
turned back into a slot-unlock clock. A team that takes a Walker early gets the
slot early.

**Walker timing is now measured** (**VERIFIED**). It is not in our local
`data/raw/matches/` payloads, which carry `players` and no objective events, but
it *is* in the upstream `match_player` table, reachable by SQL over the
deadlock-api MCP server: `objectives.team_objective`,
`objectives.destroyed_time_s` and `objectives.team`. Walkers are `Tier2LaneN`
(`Tier1LaneN` is a Guardian, `BarrackBossLaneN` a Base Guardian, `Titan` the
Patron).

Two traps in that data. **`objectives.team` is the team that LOST the
objective**, not the one that took it — confirmed because a destroyed `Core`
never belongs to the winner (0 of 220). The slot goes to the *other* team. And
**`destroyed_time_s` of 0 or 1 is a sentinel for "never destroyed"**, 1,299 of
6,420 Walker rows; filter them out or the p10 collapses to 1 second.

Time at which a team unlocks its Nth extra slot, i.e. destroys its Nth enemy
Walker (2,038 team-matches for the first, 3-day sample, **VERIFIED**):

| Slot unlocked | p10 | median | p90 |
|---:|---:|---:|---:|
| 10th | 743s (12.4 min) | **1,080s (18.0 min)** | 1,475s (24.6 min) |
| 11th | 1,030s | **1,402s (23.4 min)** | 1,868s |
| 12th | 1,290s | **1,712s (28.5 min)** | 2,220s |

**The spread is the point, not the median.** The 10th slot opens anywhere from
12 to 25 minutes depending on how the match goes, so no fixed clock describes
it. Compare against the first-hold medians above: players first hold a 10th
item at 1,567s but the slot typically opens at 1,080s — a 487s gap. Players
take the slot well before they fill it, in every case:

| Slot | Median unlock | Median first held | Gap |
|---:|---:|---:|---:|
| 10 | 1,080s | 1,567s | +487s |
| 11 | 1,402s | 1,809s | +407s |
| 12 | 1,712s | 2,065s | +353s |

So the hold-time table overstates slot scarcity at every slot, and a gate built
on it would have been wrong in the strict direction — refusing builds the game
in fact permits.

**And running out of slots is not a wall.** The normal play is to sell a tier 1
or tier 2 item to free a slot for something more expensive. That is what most of
the tier 1 sell rate is (see [Absorption](#components-and-absorption)), so a
build that exceeds the slot count at some moment may be entirely followable.

The consequence for this project: **do not gate build generation on a
time-based slot count.** A build longer than 12 held items is not automatically
wrong, and neither is one that reaches 10 items early.

### Active items

**No more than four active items can be held at once** (UNVERIFIED on the wiki,
**VERIFIED** here). Sweeping concurrent holdings of items with
`is_active_item == true`, over 257,050 players who bought any active item:

| Max actives held at once | Players |
|-------------------------:|--------:|
| 0 | 821 |
| 1 | 84,109 |
| 2 | 85,441 |
| 3 | 54,089 |
| 4 | 32,529 |
| 5 | 61 |

99.976% never exceed 4, and the 61 at 5 are the same sold_time/buy_time overlap
artifact. **This is a hard constraint and the model does not know it.** 50 of
173 shopable items are active (`is_active_item`); `activation` distinguishes
`passive` (123), `instant_cast` (30), `press` (19), `instant_cast_toggle` (1).

> **Resolve actives by item id, never by name.** The assets catalogue has 17
> duplicate names, and for **Silencer** the two entries disagree: the shopable
> one is `passive` / `is_active_item=false`, while a non-shopable one is
> `instant_cast` / `is_active_item=true`. Matching on name silently marks
> Silencer an active item and manufactures a cap violation that is not real.
> Filter to `shopable` first, then key on `id`. This has already produced one
> false finding; `assets.shopable_items()` returns the correct rows keyed by id.

### Components and absorption

62 shopable composites take components (60 take one, 2 take two;
`component_items`, resolved by `assets.component_map`). Buying the composite
**consumes** the component and discounts the composite by the component's full
cost.

**VERIFIED** that the discount is real: summing sticker prices per player gives
a median 43,200 souls against a median final net worth of 41,212 — 69.7% of
players' summed sticker prices exceed their entire final net worth (median
ratio 1.056). That is only possible if components are credited back.

Absorption, not selling, is what most "sold" rows mean (**VERIFIED**, and this
reproduces `CONTEXT.md` exactly):

| Population | Sold rate |
|---|---:|
| Item is a component of something | 70.6% |
| Item is not | 6.4% |
| Tier 1 | 86.6% |
| Tier 2 | 40.1% |
| Tier 3 | 7.2% |
| Tier 4 | 1.1% |

A new number that separates the two mechanisms independently of tier: median
time held before sale is **414s for components against 1,426s for
non-components** (**VERIFIED**, 1.9M sold rows). Absorption happens fast;
genuine sells happen late.

**4 of 64 component relationships cross slot types** — Spiritual Overflow
(weapon) absorbs Spirit Lifesteal (vitality), Kinetic Dash (weapon) and Arcane
Surge (spirit) both absorb Extra Stamina (vitality), and Ballistic Enchantment
(weapon) absorbs Mystic Expansion (spirit). Absorbing one of these **moves
invested souls from one investment pool to another**, which matters for
threshold arithmetic below.

### Selling and refunds

Selling refunds **half** the item's cost, except inside the shop area
immediately after purchase, where the refund is full (UNVERIFIED — the data
records that a sale happened, not what was refunded). Investment bonuses are
lost when the item is sold (UNVERIFIED).

The consequence for recommendations: a genuine sell is expensive, so advice to
buy an item early and sell it later is advice to burn half its cost. About 6%
of purchases are genuine strategic sells.

## Investment bonuses — the 4,800 spike

Souls spent **within a slot type** accumulate into a per-category stat bonus,
capped at 28,800 souls per category. The bonus is not linear: there is a large
step at **4,800 souls in a category**, which players call the *4.8k spike*.

Wiki table (UNVERIFIED as to the stat values):

| Souls in category | Weapon damage | Health | Spirit power |
|---:|---:|---:|---:|
| 800 | +9% | +9% | +7 |
| 1,600 | +12% | +12% | +11 |
| 4,800 | **+46%** | **+38%** | **+38** |
| 28,800 (cap) | +115% | +66% | +100 |

**The behavioural consequence is VERIFIED, and it is strong.** Computing each
player's running per-slot-type investment after every purchase across all 5.1M
rows, then asking whether the *next* purchase comes from the same slot type:

| Cumulative in that slot after this buy | n | P(next buy is same slot) |
|---|---:|---:|
| 800–1,599 | 626,781 | 0.440 |
| 1,600–3,199 | 815,986 | 0.492 |
| 3,200–4,799 | 566,470 | **0.563** |
| exactly 4,800 | 261,546 | 0.427 |
| 4,801–6,399 | 311,612 | **0.275** |
| ≥ 6,400 | 2,216,871 | 0.488 |

Players climb toward the threshold — same-slot continuation peaks at 0.563 in
the run-up — and then leave the moment they land on it, falling to 0.275 just
past it. The effect is not a buy-index artifact; it survives conditioning on
purchase position in every band (**VERIFIED**):

| Buy index | cum=3,200 | cum=4,000 | cum=4,800 | cum=5,600 |
|---|---:|---:|---:|---:|
| 2–5 | 0.571 | 0.552 | 0.402 | 0.209 |
| 6–9 | 0.572 | 0.570 | 0.437 | 0.279 |
| 10–13 | 0.560 | 0.534 | 0.461 | 0.336 |

**67.4% of players land exactly on 4,800 in at least one slot type**
(**VERIFIED**). 4,800 is reachable as 800+1,600+... combinations and as
3,200+1,600; it is not an accident of the price ladder that people arrive there.

This is the single largest mechanic the model cannot see. It is a *sequencing*
mechanic — it says which category the next purchase comes from — which is
exactly what this project claims to model.

## Souls and the economy

Souls are **both the currency and the experience bar**. The same soul that buys
an item also counted toward the boon level that granted an ability point.
Spending does not reduce level: leveling tracks *net worth earned*, not souls
in the bank. So there is no item-versus-ability budget tradeoff — a session
reasoning about "spending souls on abilities instead of items" is reasoning
about a mechanic the game does not have.

Income (all UNVERIFIED, from the wiki, and included only because they set the
pace a build is affordable at):

- Start with 600 souls.
- Hero kill: 200 base, +50/min, capping at 2,200 at 40 minutes. First blood +125.
- Trooper: 100, +2/min. Ranged kills drop two orbs (a flying and a ground orb,
  50% each); a melee kill gives the killer the flying orb's souls directly.
- Neutrals: 41 / 68 / 181 for small / medium / large, scaling +0.44 / +0.73 /
  +1.95 per minute, split among everyone who damaged them.
- Guardian 1,250 (30% to nearby heroes, 70% team-wide); Walker 3,500 team-wide;
  Mid-Boss 3,000 team-wide.
- Comeback: teams behind by >3,000 net worth earn up to 26% more from
  troopers/objectives, and up to 126.8% more for killing richer heroes. The two
  lowest-net-worth players on a team passively gain souls after 8 minutes.
- **Unsecured souls** (neutrals, sacrifices, crates) drop on death above a
  threshold of 50 + 5/min, and convert to secured at 0.5%/sec.

Observed pace (**VERIFIED**, median final net worth over duration sextiles):
roughly **1,036 souls/min in short matches rising to 1,251/min in long ones**.
Median final net worth 41,212; median 17 purchases (p10 13, p90 22).

The comeback mechanics are why a build's *timing* is not a fixed clock: a player
who is behind reaches a given item later than the median table in
`build.MEDIAN_BUY_TIME_S` predicts, and a player who is behind and benefiting
from catch-up souls reaches it sooner than their deficit suggests.

## Ability points and levelling

**Boons.** Reaching soul thresholds raises a boon level, maximum **35**, which
raises weapon damage, melee damage, health and spirit power (per-hero values;
no universal flat table). The threshold ladder (UNVERIFIED, wiki) starts 600 /
800 / 1,100 / 1,500 / 2,000 / 2,600 / 3,200 / 3,800 and reaches 49,200 at
level 35.

**Ability unlocks.** Levels 0, 2, 4 and 7 each grant an ability *unlock*. The
first three non-ultimate abilities can be unlocked in any order; **the ultimate
unlocks only at level 7, which is 3,800 souls**.

**VERIFIED**, and visible as a sharp time gate. Over 4.45M ability level-ups,
first level in signature slot 4 versus slots 1–3:

| | p1 | p5 | p25 | median | p75 | p95 |
|---|---:|---:|---:|---:|---:|---:|
| Ultimate (slot 4) | 280s | 310s | 352s | **383s** | 413s | 457s |
| Non-ultimate | 1s | 8s | 18s | 107s | 193s | 232s |

Nobody unlocks an ultimate before ~280s, because nobody has 3,800 souls before
then. Non-ultimates start at second 1.

**Upgrade costs.** Each ability has 3 upgrade tiers costing **1, 2 and 5**
ability points — 8 points to max one ability. Points come from every boon level
that does not grant an unlock, to a **maximum of 32**.

**VERIFIED, and this confirms both numbers at once.** In the data an ability
carries levels 1–4, where level 1 is the free unlock and 2/3/4 are the three
paid tiers. Scoring level 1 = 0, 2 = 1, 3 = 2, 4 = 5 points and summing per
player: the median is 27 and the **90th, 99th and 99.9th percentiles are all
exactly 32**, with only 0.001% above. No other cost schedule produces a clean
ceiling at 32. Points can be spent in any order, including banking them for a
5-point tier.

How many abilities a player takes to level 4 — the 5-point tier — is a real
build choice (**VERIFIED**, 299,983 players): 0 abilities 486, 1 → 2,434,
2 → 38,743, 3 → 183,266, 4 → 75,051. Most players max three.

An upgrade can be refunded within 10 seconds if no ability was used in that
window (UNVERIFIED).

## Imbue

Pointing an item at one of the hero's four signature abilities, chosen **at the
shop counter when the item is bought**.

Mechanically load-bearing and often missed: **an imbue cannot be re-pointed.**
Changing the target means selling the item and buying it again — which costs
half the item's value. So an imbue is a more committing decision than a
purchase, and "buy Mystic Reverb" without a target is genuinely half an
instruction.

Restrictions:

- Echo Shard and Omnicharge Signet (`imbue_active_non_ult`) **cannot target the
  ultimate**. Choosing Echo Shard over Mystic Reverb is therefore itself a
  statement that the build is not about the ult.
- Only Mystic Expansion and Duration Extender can be imbued on *passive*
  abilities (UNVERIFIED).
- Silver imbuing a non-ultimate imbues both her human and werewolf versions
  (UNVERIFIED).

Which items are imbueable and in which group is an API field (`Item.imbue`,
values `imbue_active`, `imbue_active_non_ult`, `imbue_modifier_value`) — read
it, do not hardcode. As of the cached assets, 13 entries carry it: 9 shopable
and buyable, 2 shopable at tier 5 (never bought), 2 disabled. All are spirit-tab
except **Ballistic Enchantment, which is weapon-tab** — the one place a gun
build makes an imbue choice.

**An imbue is never missing.** **VERIFIED**: 0 of 452,103 imbue rows have a
zero target. A hero with a low imbue rate buys imbueable items rarely; it does
not have missing data.

## Shop visits

Purchases are not evenly spaced decisions. **18.7% of consecutive purchase
pairs are within 5 seconds of each other** (896,403 of 4,799,266, **VERIFIED**)
— one shop visit, several items. Median gap between purchases is 112s (p10 1s,
p90 251s).

**Roughly a fifth of those bursts are a component bought immediately before the
composite it builds into: 176,261 of 896,403, or 19.7% (VERIFIED).** Those are
not two decisions at all — they are one purchase the shop charges in two steps,
and the component is absorbed on the spot. The remaining **80.3% are genuine
multi-item visits**: only 46.2% of them even share a slot type with the previous
purchase, and 28.9% carry an identical timestamp. Half the component bursts
(49.3%) are at gap 0 exactly.

Same-visit purchases are more slot-correlated than distant ones: P(same slot
type as previous) is **0.552 within a 5s burst against 0.452 when the gap
exceeds 60s** (**VERIFIED**). A burst is one decision about a category, not
several independent decisions.

The model treats every purchase as an independent step with its own time
bucket, so a 4-item burst is scored as four sequential decisions at effectively
the same clock time.

---

# Mechanics the model currently ignores

What the model sees, from `sequence.LEVEL_KEYS`, is exactly:
`hero_id`, `archetype_id`, `prev1`, `prev2`, `n_owned`, `time_bucket`. Plus
`average_badge` as a Gaussian row weight (`sequence.py:139`, and see the memory
note that nothing passes `target_badge`). Souls appear only as an affordability
filter (`state.candidate_items`), and in build generation they are set to 10^9
(`build.py:152`) — i.e. disabled. Enemy heroes are a post-hoc annotation
(`counters.annotate`), never a model input.

Everything below is therefore invisible to it.

| # | Mechanic | Worth modeling? | Why |
|---|---|---|---|
| 1 | **Per-slot-type investment total, and the 4,800 threshold** | **Yes — highest value** | Directly a sequencing mechanic, and the effect is large and verified (P(same slot) 0.563 → 0.275 across the threshold, surviving buy-index control). The model conditions on the last two *items* but not on the running *category totals* those items imply, so it cannot represent "I am 1,600 short of the weapon spike". Cheapest version: add running per-slot investment, bucketed at the thresholds, as a conditioning key or a re-ranking prior. |
| 2 | **The 4-active-item cap** | **Yes — cheap, but no build violates it today** | A hard rule (99.976% compliance, VERIFIED) that `build.py` does not enforce: it enforces `MAX_HELD_ITEMS` but nothing counts actives. **All 75 shipped builds currently comply** — an earlier claim that Gun Venator asks for 5 actives was an analysis error (see the warning below on resolving actives by name) and is retracted. So this is a guard against a future regression, not a live bug. A filter in the candidate step, not a learned feature. |
| 3 | **Slot availability (9 → 12 via Walkers)** | **No — the slot is rarely the binding constraint** | Slots 10-12 come from destroying enemy Walkers, not from the clock. Now measured (see [Item slots](#item-slots)): the 10th slot opens at a median 1,080s but ranges 743-1,475s, and players first *hold* a 10th item at 1,567s — **487s after the slot typically opens**. The same gap holds at 11 and 12. So players are not slot-starved on average, the spread is too wide for any fixed clock, and selling a tier 1-2 item frees a slot anyway. An earlier claim that 8 builds are "unfollowable before 1,315s" inverted the hold-time table into an availability clock and is retracted. |
| 4 | **Souls as a real budget** | Yes, for the in-match shape | Generation sets souls to infinity, so the whole-build path can only ever answer "what eventually" and never "what now". The in-match path takes `--souls` but uses it as a hard filter, not as a conditioning variable — so it cannot express "wait 40 seconds and buy the tier 3 instead", which is real advice and is what `n_saved_up` in `economy.py` already shows players doing. |
| 5 | **Shop-visit bursts** | Probably — as a correction, not a feature | 18.7% of consecutive pairs are same-visit, and **19.7% of those are a component bought immediately before its composite** — one purchase billed in two steps, not two decisions. Treating either kind as independent timed decisions inflates the apparent evidence for tight bigrams. Component bursts are the cleanest thing to collapse when *training*, since the relationship is already known from `component_map()`. |
| 6 | **Ability-point state at the buy decision** | Yes — and the data is already there | `abilities.parquet` holds 4.45M level-ups and the model does not read one. Whether the ultimate is unlocked (a hard 3,800-soul gate, VERIFIED at median 383s) changes which items make sense — an ult-empowering imbue before the ult exists is a wasted purchase. `abilityorder.py` exists but is not wired into the sequence model. |
| 7 | **Imbue irreversibility** | Yes, for how it is *shown* | Not a model change so much as a presentation one: the tool should say the target is a commitment costing half the item to change. Currently a target is reported like any other statistic. |
| 8 | **Cross-slot-type absorption** | Marginal, but it is a correctness trap | The 4 cross-tab component relationships move souls between investment pools. Any implementation of #1 that computes per-slot investment from the purchase sequence will get these 4 wrong unless it accounts for absorption. Listed so whoever builds #1 does not have to rediscover it. |
| 9 | **Comeback souls / net-worth position** | No — deliberately | This is the boundary `docs/DIAGNOSIS.md` was written about. Wealth position is an *outcome* by mid-match (memory: 0.16 in phase 0, 0.60 by phase 3). Conditioning on it reintroduces the failure this project was rebuilt to avoid. Named here so a future session recognises it and stops, rather than rediscovering it as a promising feature. |
| 10 | **Genuine sells** | No | ~6% of purchases, and the model's output is a purchase sequence. Modeling a sell would mean a different output shape for a rare event. |
| 11 | **Boon level / stat scaling** | No | It is a function of net worth and time, both already proxied by `time_bucket` and `n_owned`. Adds no independent information about *choice*. |

---

# Contradictions with current assumptions

## Where "slot type is not playstyle" does not apply

`CONTEXT.md` says slot type is "a shop category, and nothing more", and lists
Siphon Bullets, Melee Charge, Rescue Beam as proof that the tabs cut across
what builds are trying to do.

**That rule is correct, and it must not be extended past where it was argued.**
It is a claim about *naming and clustering*: do not name an archetype from its
shop tabs, and do not cluster on tab shares (19 splits at 0.321) when families
work better (28 at 0.429).

It is **not** a claim that slot type is mechanically inert, and slot type is
not mechanically inert. Investment bonuses accumulate per slot type, so the tab
an item is sold in determines which stat pool its souls feed and whether the
player crosses 4,800. Two items that do the same thing in build-family terms
are *not* interchangeable if one lands on the threshold and the other does not.

Concretely, the same fact reads two ways:

> Lash's gun archetype reads as 40% vitality souls purely because Siphon
> Bullets costs 6400.

For naming, that is the trap `CONTEXT.md` warns about — do not call this a tank
build. For mechanics, that 6,400 is real: it is 6,400 souls into the vitality
pool, past the 4,800 spike, and Lash gets the health bonus whether or not the
build is "about" vitality.

**The rule to carry forward:** slot type is not playstyle, *and* slot type is
load-bearing for investment. Use build family to name and cluster; use slot
type to reason about thresholds and ordering. Neither displaces the other.

## Souls are not a budget shared with abilities

A natural assumption — that a player trades souls between items and ability
upgrades — is **false**. Ability points come from boon levels, boon levels come
from net worth *earned*, and spending does not reduce them. There is no
tradeoff to model. Any feature or explanation framed as "spent on abilities
instead of items" is describing a mechanic that does not exist.

## "Sold" mostly does not mean sold

Already correct in `CONTEXT.md` under Absorption, and restated because it
contradicts the plain reading of the field name and keeps being rediscovered.
The new independent evidence is the holding time: 414s median for components
against 1,426s for non-components.

## "Shopable" does not mean buyable

`assets.shopable_items()` returns 173 items including 17 tier-5 entries that
are bought 0 times in 5.1M purchases. Any code treating the shopable set as the
candidate set is ranking 17 items no player can reach in this mode. `build.py`
is safe by accident — tier-5 items never accumulate probability mass — but a
future component that enumerates candidates uniformly would not be.

## The purchase sequence is not a sequence of independent decisions

`sequence.py` models P(next item | prev1, prev2, bucket). 18.7% of consecutive
purchase pairs are made in the same shop visit, where "next" is a simultaneous
choice rather than a subsequent one. This does not invalidate the model, but it
means the bigram evidence at short gaps is measuring co-selection rather than
succession, and the two are different claims. **The sharpest case is the 19.7%
of bursts that are a component followed by its own composite**: there the bigram
is not even co-selection, it is a single purchase the shop charges in two
steps.

---

# Proposed CONTEXT.md additions

Proposals only — not applied. Each is a genuinely new *term* a player would use,
not a mechanic write-up; the mechanics stay in this document.

**Investment bonus** — A cumulative stat bonus earned by spending souls within
one [[slot type]], capped at 28,800 souls per type. Not linear: a large step at
4,800 souls, which players call the **4.8k spike**. It is why [[slot type]] is
mechanically load-bearing even though it does not name a playstyle — players
visibly push one tab to 4,800 and then switch away (same-slot continuation
0.563 approaching the threshold, 0.275 just past it).

**Active item** — An item with a button, bound to one of four keys. At most
four can be held at once, which makes actives a scarce resource a build spends
rather than a free choice. `is_active_item` in the assets API; 50 of 173
shopable items.

**Boon** — A hero level, earned at soul thresholds and capped at 35. Grants
stat increases, and at levels 0/2/4/7 an ability unlock, otherwise an
[[ability point]]. Souls are not consumed: boons track net worth earned, so
spending on items never costs levels.

**Ability point** — The currency for upgrading a signature ability. Each
ability has three upgrade tiers costing 1, 2 and 5 points; a player earns at
most 32 in a match, enough to max three abilities and part of a fourth.
