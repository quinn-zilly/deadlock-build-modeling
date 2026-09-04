# Context

The vocabulary this project uses. Terms are defined as the domain uses them —
what a Deadlock player means — not as the code happens to implement them.

## Build

An ordered sequence of item purchases for one hero in one match. Roughly 17
buys, of which 11–12 survive to the end; 37% are sold along the way.

A build is a **sequence**, not an inventory. "Buy Extra Regen early, sell it
around 20 minutes" is a real piece of advice, and only the sequence view can
express it. When the final inventory is meant specifically, say **held items**.

## Build order

The sequence in which a build's items are bought. Distinct from the build
itself: two players can own the same twelve items and have played the match
very differently. Build order and purchase timing are what this project models
— item win rates and pick rates are already easy to look up.

## Archetype

A recognizably different way of playing one hero, expressed as a distinct
build. Ivy is played as a gun carry or as a spirit support; those two builds
share few items, and advice averaged across them serves neither.

An archetype belongs to a hero. There is no global "gun build" — there is Gun
Ivy and Gun Lash, and they have different items. Not every hero has more than
one: Haze, Dynamo, and Wraith have a single archetype, and that is a finding,
not a failure to split.

Archetypes are discovered by clustering, but named by what the build *does*.
The label is a claim about playstyle a player would recognize, not a summary of
the clustering.

## Slot type

Which of the three shop tabs an item is sold in: **weapon**, **vitality**, or
**spirit**. A shop category, and nothing more.

**Slot type is not playstyle.** The two correlate but diverge often enough to
break any naming rule built on slot type alone:

- **Siphon Bullets** is vitality-slotted and belongs to gun builds.
- **Melee Charge** and **Crushing Fists** are weapon-slotted and belong to
  melee builds, which are not gun builds.
- **Rescue Beam** and **Healing Tempo** are vitality-slotted and belong to
  support builds, which are not tank builds.

Because slot shares are weighted by souls, a couple of expensive off-category
items outweigh many cheap on-category ones. Lash's gun archetype reads as 40%
vitality souls purely because Siphon Bullets costs 6400.

See [[build family]] for the concept that does carry playstyle.

## Build family

What a build is actually trying to do, inferred from what its items do rather
than where they are sold. The vocabulary players use:

- **gun** (also "weapon", "carry") — bullet damage, fire rate, clip size,
  headshots. Signature: Sharpshooter, Headhunter, Crippling Headshot,
  Siphon Bullets.
- **spirit** — spirit power, cooldown reduction, ability range and duration.
  Signature: Improved Spirit, Boundless Spirit, Mystic Expansion,
  Superior Cooldown.
- **melee** — heavy melee damage and charge. Signature: Melee Charge,
  Crushing Fists.
- **support** — healing and shielding allies. Signature: Rescue Beam,
  Healing Tempo, Divine Ward.
- **tank** — health, resistances, sustain on oneself.

A hero's archetype is named for its dominant family: "Gun Lash", "Melee
Sinclair", "Support Kelvin". Two archetypes of the same hero can share a
family — Kelvin has two spirit builds taking different paths — in which case
the name needs a second distinguishing term rather than a family label alone.

## Staple

An item bought by at least 70% of a hero-and-archetype's players. A generated
build that omits one is wrong regardless of any aggregate metric, which is what
the prevalence gate asserts.

Staples are archetype-specific. Pooled across her two archetypes Ivy has one
staple; split, they have three and four. Averaging two builds hides the staples
of both.

## Discriminative item

An item one archetype buys far more than the hero's other archetypes. The
readout used to check whether a cluster is a real build: "Active Reload, 39%
here versus 1% elsewhere" is checkable by a player.

Discriminative items are the honest signal about what a cluster *is* — more so
than its centroid, which measures only where souls went.

## Prevalence

The fraction of player-matches in a population that ever bought a given item.
Computed over players, not purchase rows, since no item is ever bought twice.

## Component

An item required to build a composite item. Sharpshooter takes High-Velocity
Mag and Long Range.

A **soft** ordering prior, never a hard constraint: only 79% of players who buy
a composite ever bought its component separately, so forbidding the parent
before the component would make a fifth of real builds unreachable.

## Tempo

How fast a player spends. Measured as the median gap between purchases, and the
strongest single feature in every model built on this data so far. Souls in the
bank are strength not on the board.

## Badge

The rank control, `average_badge`, on a 0–116 scale. A property of the *match*,
not the player, and only populated for Ranked matches.
