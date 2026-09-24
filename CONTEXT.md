# Context

The words this project uses, defined the way a Deadlock player means them.
Measurements and the reasons behind decisions live in the code, the ADRs in
`docs/adr/`, and `docs/`. This file only says what each term means.

## Builds

**Build**:
The items one player buys in one match, in the order bought. About 17
purchases, of which 11 or 12 are still held at the end.
_Avoid_: loadout, inventory (when the whole sequence is meant)

**Held items**:
The items a player still owns at the end of a match. Use this, not "build",
when the final inventory is meant.

**Build order**:
The order in which a build's items are bought. Two players can end with the
same twelve items and have bought them in very different orders. Build order
and timing are what this project models.

**Staple**:
An item bought by at least 70% of one hero-and-archetype's players. A
generated build must contain every staple. Staples belong to an archetype, not
a hero: all Ivy players together have one staple, but each Ivy archetype has
three or four.

**Component**:
An item that is part of a bigger item, the **composite**. Sharpshooter's
components are High-Velocity Mag and Long Range. Players usually buy the
component first, but about a fifth don't, so buying the composite first is
allowed.

**Absorption**:
What happens to a component when its composite is bought: it leaves the
inventory and frees its slot. Most items that show as "sold" were absorbed,
not sold. Because a staple can be absorbed, staple checks look at the purchase
sequence, never at held items.
_Avoid_: selling (for absorption)

**Active item**:
An item the player triggers, as opposed to one that works on its own. A player
can hold at most four. Identify active items by item id, never by name: two
catalogue entries are both called Silencer and disagree on whether they are
active.

## Archetypes

**Archetype**:
A distinct way of building one hero that a real share of players use. Ivy is
built either as a gun carry or as a spirit support. Archetypes belong to a
hero: there is Gun Ivy and Gun Lash, but no global "gun build". Some heroes
have only one.
_Avoid_: playstyle (as a data term), cluster (outside the fitting code)

**Cell**:
One hero and one archetype, and the players in it. Builds, staples, and imbue
targets are all per cell.

**Build family**:
What an item is for, as players would put it: **gun**, **spirit**, **melee**,
**support**, or **tank**, plus **sustain** (healing yourself), **control**,
and **mobility**, which describe items but never name a build. An item can
belong to several. Archetypes are found and named from build families.
_Avoid_: slot type, category (for this)

**Slot type**:
The shop tab an item is sold in: weapon, vitality, or spirit. It often doesn't
match the build family: Siphon Bullets is in the vitality tab and is a gun
item. Slot type still matters for the game's rules, because the
investment bonus is counted per slot type.
_Avoid_: build family, playstyle (for this)

**Discriminative item**:
An item one archetype buys far more than the hero's other archetypes, such as
"Active Reload, 39% here against 1% in the others". This is how a person
checks that an archetype is a real build.

**Separation**:
How different two archetypes of a hero are: the largest gap in any item's
pick rate between them. A hero's split counts only if every pair of its
archetypes is separated enough.

**Counter-pick**:
An item bought because of who is on the enemy team, not because of how the
hero is built: Counterspell against Lash, Healbane against Victor. A
counter-pick is never an archetype. The tool shows counter-picks beside its
recommendations and never lets them change the order.

**Prevalence**:
The share of players in a group who bought an item at least once.
_Avoid_: pick rate (in code and docs; fine when talking to players)

## Abilities

**Signature ability**:
One of the four abilities each hero levels. The fourth is the **ultimate**, or
**ult**.

**Ability point**:
What a player spends to unlock or level an ability. Levels 2, 3, and 4 cost
1, 2, and 5 points.

**Ability order**:
The order in which a player spends ability points. Final levels say little,
because by match end everyone has maxed everything. The order says which
ability was maxed first and so spent most of the match at full strength.

**Ability focus**:
The one signature ability a build is centered on. It is how players tell
apart two builds of the same family: Dynamo's **ult build** against its
**stomp build** (Kinetic Pulse). Many builds have no single focus.

**Kit tag**:
What one signature ability does, in players' words: burst, dot, cc, support,
melee, gun, mobility, sustain, or summon. Read from the ability's description
text. A hero's kit says which builds make sense on them, not which one a
player is using.

**Imbue**:
Choosing one of a hero's signature abilities for an imbueable item to affect,
done at the shop when buying it. Nine shop items can be imbued in practice.
The game requires the choice, so an imbue is never missing: a player with no
imbues bought no imbueable item. Imbues come in two groups: **active** (the
item empowers or copies the ability) and **modifier** (it raises the
ability's numbers).

**Imbue target**:
The ability a cell most often imbues a given item into. It belongs to the
archetype, not the item: Dynamo's ult and stomp builds aim the same item at
different abilities. Marked **split** when under half the cell agrees and
**thin** when fewer than 30 imbues back it.

## The model

**Backoff level**:
Which table in the model's chain a recommendation came from, `L0` (hero,
archetype, last two items, and time) down to `L5` (the hero's overall pick
rates). Every recommendation prints its level and raw count, so it can be
checked by hand.

**Thin evidence**:
A recommendation backed by fewer than 30 observations. It is shown, marked
`[thin]`.

**Badge**:
The average rank of the players in a match, from 0 to 116. It is recorded for
Ranked matches only. The tens digit is the tier and the ones digit the
subrank. Use tier names in anything a player reads: Obscurus, Initiate,
Seeker, Acolyte, Sentinel, Mystic, Ritualist, Emissary, Oracle (80),
Phantom, Ascendant, Eternus. The tool weights its data toward Oracle by
default (ADR 0002).
_Avoid_: rank, MMR (for this field)

**In scope**:
A player who belongs in the per-player tables: the match outcome is known and
they bought at least one item. Every table holds the same in-scope players.

**Tempo**:
How fast a player spends, measured as the median time between purchases.

## The game

**Boon**:
A hero level, earned by gaining souls. Spending souls on items doesn't cost
boons, so items and levels don't compete for souls.

**Investment bonus**:
A stat bonus for spending souls within one slot type, given in steps. Players
visibly spend up to the 4,800-soul step and then switch slot type, the
**4.8k spike**. The model doesn't account for it yet.

**Walker**:
The second tower in a lane. Destroying an enemy Walker gives your team one
more item slot, from 9 up to 12, so the item cap is won on the map.

**Mid-Boss**:
A neutral objective that gives the claiming team a lump of souls. The team
that claims it isn't always the team that killed it.

**Intended build**:
The community build a player selected before the match (`hero_build_id`).
Only analyzed matches have it: about 14% of matches, once analysis catches up
four to six weeks later. Those matches skew about a tier higher than the rest,
so results from them don't compare with results from everyone. A published
build lists more items than a player can hold, so "followed N of M items"
isn't meaningful.
