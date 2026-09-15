# Archetype review

Fitted per hero on souls-weighted build-family shares -- how a player's
souls divided across gun, spirit, melee, support, tank, sustain, control
and mobility. A hero splits only if all four criteria pass; otherwise it
stays single, which is a result and not a failure.

Imbue is **not** in the fit. It was tried in two forms and rejected under
a rule fixed before the numbers -- see
`docs/adr/0001-imbue-out-of-the-clustering.md`. It names clusters below
and tells the player what to imbue; it does not find clusters.

**31 of 38 heroes split.** Seed 0, so a refit reproduces this exactly.

Names below are proposed from what each cluster's discriminative items
do, sharpened by its ability focus where two would otherwise collide. Edit
`data/archetype_names.json` (keyed `"<hero_id>:<archetype_id>"`) to
overrule any of them.

## Heroes that split

### Shiv  (2 archetypes, n=8,600)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.586 | >= 0.15 |
| replication | 0.999 | >= 0.90 |
| separation | 0.931 | >= 0.45 |
| smallest share | 0.234 | >= 0.12 |

**Spirit Shiv** — 77% of players (n=6,589), named at 2.4x over the runner-up

_Souls by shop tab: gun 3%  spirit 26%  melee 2%  support 1%  tank 33%  sustain 26%  control 4%  mobility 5%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Extra Charge | 82% | 9% |
| Torment Pulse | 73% | 1% |
| Healbane | 89% | 18% |
| Compress Cooldown | 69% | 2% |
| Mystic Vulnerability | 66% | 1% |
| Superior Cooldown | 61% | 1% |
| Escalating Exposure | 57% | 1% |
| Healing Booster | 61% | 22% |
| Restorative Locket | 37% | 2% |
| Mystic Reverb | 32% | 0% |

**Gun Shiv** — 23% of players (n=2,011), named at 2.9x over the runner-up

_Souls by shop tab: gun 39%  spirit 12%  melee 0%  support 0%  tank 21%  sustain 21%  control 2%  mobility 5%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Swift Striker | 94% | 1% |
| Mercurial Magnum | 93% | 0% |
| Bullet Resist Shredder | 90% | 4% |
| Quicksilver Reload | 87% | 1% |
| Battle Vest | 88% | 6% |
| Rapid Rounds | 77% | 1% |
| Monster Rounds | 84% | 10% |
| Spiritual Overflow | 76% | 2% |
| Golden Goose Egg | 80% | 7% |
| Fleetfoot | 68% | 1% |

### Victor  (2 archetypes, n=8,402)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.631 | >= 0.15 |
| replication | 0.999 | >= 0.90 |
| separation | 0.906 | >= 0.45 |
| smallest share | 0.187 | >= 0.12 |

**Spirit Victor** — 81% of players (n=6,834), named at 2.3x over the runner-up

_Souls by shop tab: gun 4%  spirit 32%  melee 0%  support 1%  tank 38%  sustain 17%  control 2%  mobility 5%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Infuser | 87% | 2% |
| Escalating Exposure | 88% | 5% |
| Mystic Vulnerability | 88% | 6% |
| Torment Pulse | 82% | 3% |
| Mystic Expansion | 79% | 5% |
| Greater Expansion | 69% | 4% |
| Improved Spirit | 85% | 27% |
| Extra Spirit | 85% | 33% |
| Warp Stone | 45% | 2% |
| Superior Cooldown | 50% | 13% |

**Gun Victor** — 19% of players (n=1,568), named at 2.7x over the runner-up

_Souls by shop tab: gun 38%  spirit 16%  melee 0%  support 1%  tank 21%  sustain 16%  control 2%  mobility 6%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Mercurial Magnum | 92% | 1% |
| Quicksilver Reload | 88% | 2% |
| Titanic Magazine | 85% | 1% |
| Opening Rounds | 92% | 8% |
| High-Velocity Rounds | 91% | 7% |
| Swift Striker | 83% | 0% |
| Spiritual Overflow | 77% | 4% |
| Extended Magazine | 73% | 1% |
| Rapid Rounds | 70% | 0% |
| Spirit Shielding | 60% | 2% |

### Viscous  (2 archetypes, n=5,700)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.290 | >= 0.15 |
| replication | 0.999 | >= 0.90 |
| separation | 0.807 | >= 0.45 |
| smallest share | 0.419 | >= 0.12 |

**Spirit Viscous** — 58% of players (n=3,314), named at 1.9x over the runner-up

_Souls by shop tab: gun 10%  spirit 29%  melee 3%  support 3%  tank 23%  sustain 18%  control 7%  mobility 7%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Improved Spirit | 67% | 7% |
| Mystic Shot | 57% | 13% |
| Extra Spirit | 48% | 6% |
| Superior Cooldown | 72% | 31% |
| Express Shot | 54% | 14% |
| Boundless Spirit | 43% | 5% |
| Compress Cooldown | 64% | 30% |
| Tankbuster | 85% | 52% |
| Spirit Burn | 39% | 6% |
| Veil Walker | 37% | 7% |

**Melee Viscous** — 42% of players (n=2,386), named at 6.8x over the runner-up

_Souls by shop tab: gun 16%  spirit 24%  melee 21%  support 1%  tank 18%  sustain 8%  control 7%  mobility 4%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Melee Charge | 88% | 7% |
| Melee Lifesteal | 85% | 7% |
| Crushing Fists | 82% | 5% |
| Lifestrike | 81% | 4% |
| Rapid Recharge | 83% | 16% |
| Extra Charge | 89% | 24% |
| Ballistic Enchantment | 66% | 3% |
| Spirit Strike | 89% | 39% |
| Spirit Snatch | 91% | 48% |
| Close Quarters | 38% | 4% |

### McGinnis  (2 archetypes, n=4,600)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.597 | >= 0.15 |
| replication | 0.998 | >= 0.90 |
| separation | 0.785 | >= 0.45 |
| smallest share | 0.299 | >= 0.12 |

**Spirit McGinnis** — 70% of players (n=3,225), named at 3.5x over the runner-up

_Souls by shop tab: gun 8%  spirit 34%  melee 0%  support 3%  tank 24%  sustain 14%  control 6%  mobility 11%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Mystic Vulnerability | 85% | 7% |
| Escalating Exposure | 79% | 5% |
| Extra Charge | 88% | 15% |
| Mystic Expansion | 75% | 3% |
| Rapid Recharge | 75% | 9% |
| Mystic Slow | 71% | 6% |
| Compress Cooldown | 65% | 1% |
| Superior Cooldown | 60% | 1% |
| Greater Expansion | 57% | 1% |
| Enchanter's Emblem | 49% | 3% |

**Gun McGinnis** — 30% of players (n=1,375), named at 4.1x over the runner-up

_Souls by shop tab: gun 51%  spirit 9%  melee 0%  support 1%  tank 17%  sustain 10%  control 5%  mobility 8%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Quicksilver Reload | 82% | 5% |
| Extended Magazine | 79% | 5% |
| Mercurial Magnum | 77% | 4% |
| Swift Striker | 63% | 1% |
| Fleetfoot | 63% | 2% |
| Rapid Rounds | 57% | 1% |
| Titanic Magazine | 45% | 4% |
| Tesla Bullets | 46% | 4% |
| Bullet Lifesteal | 42% | 1% |
| Escalating Resilience | 40% | 1% |

### Abrams  (2 archetypes, n=8,096)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.391 | >= 0.15 |
| replication | 0.999 | >= 0.90 |
| separation | 0.754 | >= 0.45 |
| smallest share | 0.193 | >= 0.12 |

**Hybrid-Spirit Abrams** — 19% of players (n=1,561), named at 1.6x over the runner-up

_Souls by shop tab: gun 4%  spirit 32%  melee 7%  support 2%  tank 27%  sustain 17%  control 4%  mobility 6%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Arcane Surge | 79% | 6% |
| Superior Cooldown | 67% | 2% |
| Extra Stamina | 62% | 6% |
| Healing Booster | 84% | 28% |
| Compress Cooldown | 56% | 2% |
| Healbane | 59% | 7% |
| Mystic Expansion | 53% | 3% |
| Spirit Strike | 83% | 35% |
| Spirit Snatch | 81% | 37% |
| Extra Spirit | 45% | 2% |

**Melee Abrams** — 81% of players (n=6,535), named at 3.1x over the runner-up

_Souls by shop tab: gun 18%  spirit 11%  melee 15%  support 1%  tank 30%  sustain 11%  control 9%  mobility 6%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Close Quarters | 92% | 16% |
| Hunter's Aura | 67% | 10% |
| Melee Charge | 98% | 41% |
| Stalker | 64% | 7% |
| Bullet Resist Shredder | 60% | 3% |
| Melee Lifesteal | 66% | 17% |
| Point Blank | 54% | 7% |
| Crushing Fists | 53% | 12% |
| Phantom Strike | 56% | 20% |
| Extra Health | 34% | 5% |

### Holliday  (3 archetypes, n=4,667)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.236 | >= 0.15 |
| replication | 0.998 | >= 0.90 |
| separation | 0.749 | >= 0.45 |
| smallest share | 0.167 | >= 0.12 |

**Rush Spirit Holliday** — 41% of players (n=1,900), named at 2.8x over the runner-up

_Souls by shop tab: gun 10%  spirit 34%  melee 0%  support 0%  tank 23%  sustain 14%  control 1%  mobility 17%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Recharging Rush | 85% | 50% |
| Improved Spirit | 80% | 47% |
| Tankbuster | 75% | 45% |
| Mystic Burst | 63% | 37% |
| Superior Duration | 62% | 37% |
| Sprint Boots | 58% | 35% |
| Extra Spirit | 87% | 65% |
| Duration Extender | 46% | 24% |
| Compress Cooldown | 41% | 21% |
| Superior Cooldown | 47% | 28% |

**Burn Spirit Holliday** — 43% of players (n=1,986), named at 3.1x over the runner-up

_Souls by shop tab: gun 8%  spirit 33%  melee 0%  support 0%  tank 21%  sustain 13%  control 12%  mobility 13%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Spirit Burn | 82% | 1% |
| Tankbuster | 84% | 41% |
| Superior Duration | 70% | 33% |
| Improved Spirit | 83% | 46% |
| Boundless Spirit | 66% | 30% |
| Recharging Rush | 85% | 50% |
| Trophy Collector | 68% | 34% |
| Mystic Burst | 67% | 35% |
| Escalating Exposure | 45% | 16% |
| Superior Cooldown | 53% | 25% |

**Gun Holliday** — 17% of players (n=781), named at 6.2x over the runner-up

_Souls by shop tab: gun 43%  spirit 13%  melee 0%  support 0%  tank 13%  sustain 6%  control 5%  mobility 19%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Sharpshooter | 77% | 2% |
| Swift Striker | 73% | 1% |
| Titanic Magazine | 68% | 1% |
| Headhunter | 79% | 18% |
| Extended Magazine | 60% | 0% |
| Headshot Booster | 85% | 29% |
| Fortitude | 61% | 5% |
| Extra Health | 59% | 5% |
| Bullet Resist Shredder | 52% | 1% |
| Glass Cannon | 50% | 0% |

### Dynamo  (2 archetypes, n=8,508)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.308 | >= 0.15 |
| replication | 0.999 | >= 0.90 |
| separation | 0.675 | >= 0.45 |
| smallest share | 0.424 | >= 0.12 |

**Hybrid-Gun Dynamo** — 42% of players (n=3,607), named at 1.4x over the runner-up

_Souls by shop tab: gun 16%  spirit 29%  melee 0%  support 2%  tank 21%  sustain 19%  control 4%  mobility 9%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Enduring Speed | 52% | 16% |
| Recharging Rush | 62% | 37% |
| Mystic Reverb | 30% | 8% |
| Extra Spirit | 42% | 20% |
| Mercurial Magnum | 20% | 0% |
| Swift Striker | 19% | 1% |
| Opening Rounds | 19% | 2% |
| High-Velocity Rounds | 19% | 2% |
| Rapid Rounds | 17% | 1% |
| Surge of Power | 22% | 6% |

**Dynamo** — 58% of players (n=4,901), **unnamed** — the families are too close to call

_Souls by shop tab: gun 6%  spirit 28%  melee 0%  support 1%  tank 41%  sustain 15%  control 2%  mobility 6%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Refresher | 81% | 13% |
| Warp Stone | 68% | 19% |
| Unstoppable | 56% | 9% |
| Duration Extender | 67% | 30% |
| Superior Duration | 61% | 28% |
| Debuff Reducer | 43% | 10% |
| Arcane Surge | 46% | 18% |
| Greater Expansion | 73% | 50% |
| Trophy Collector | 59% | 37% |
| Extra Stamina | 38% | 16% |

### Paradox  (3 archetypes, n=9,340)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.273 | >= 0.15 |
| replication | 0.999 | >= 0.90 |
| separation | 0.665 | >= 0.45 |
| smallest share | 0.137 | >= 0.12 |

**Spirit Paradox** — 14% of players (n=1,278), named at 3.0x over the runner-up

_Souls by shop tab: gun 8%  spirit 32%  melee 0%  support 0%  tank 29%  sustain 13%  control 6%  mobility 12%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Duration Extender | 88% | 4% |
| Mystic Expansion | 85% | 3% |
| Echo Shard | 81% | 1% |
| Superior Duration | 82% | 6% |
| Greater Expansion | 71% | 2% |
| Extra Spirit | 57% | 1% |
| Arcane Surge | 57% | 1% |
| Spirit Lifesteal | 48% | 1% |
| Improved Spirit | 42% | 1% |
| Vortex Web | 41% | 1% |

**Burn Gun Paradox** — 49% of players (n=4,604), named at 2.9x over the runner-up

_Souls by shop tab: gun 26%  spirit 17%  melee 0%  support 0%  tank 16%  sustain 18%  control 11%  mobility 12%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Spirit Burn | 70% | 16% |
| Mystic Reverb | 78% | 30% |
| Sharpshooter | 87% | 49% |
| Express Shot | 85% | 47% |
| Tankbuster | 91% | 55% |
| Long Range | 79% | 46% |
| High-Velocity Rounds | 78% | 51% |
| Mystic Burst | 73% | 48% |
| Restorative Shot | 55% | 34% |
| Crippling Headshot | 25% | 7% |

**Sharpshooter Gun Paradox** — 37% of players (n=3,458), named at 7.1x over the runner-up

_Souls by shop tab: gun 36%  spirit 12%  melee 0%  support 0%  tank 17%  sustain 15%  control 3%  mobility 17%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Sharpshooter | 91% | 47% |
| Long Range | 86% | 43% |
| Express Shot | 87% | 46% |
| High-Velocity Rounds | 82% | 49% |
| Tankbuster | 89% | 55% |
| Mystic Burst | 77% | 46% |
| Headhunter | 66% | 42% |
| Headshot Booster | 72% | 50% |
| Restorative Shot | 55% | 34% |
| Hollow Point | 34% | 16% |

### Bebop  (2 archetypes, n=13,228)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.406 | >= 0.15 |
| replication | 0.999 | >= 0.90 |
| separation | 0.656 | >= 0.45 |
| smallest share | 0.401 | >= 0.12 |

**Spirit Bebop** — 60% of players (n=7,930), named at 2.0x over the runner-up

_Souls by shop tab: gun 3%  spirit 23%  melee 4%  support 0%  tank 30%  sustain 22%  control 6%  mobility 11%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Improved Spirit | 70% | 12% |
| Mystic Burst | 87% | 29% |
| Tankbuster | 57% | 7% |
| Boundless Spirit | 51% | 6% |
| Extra Spirit | 60% | 16% |
| Echo Shard | 44% | 1% |
| Trophy Collector | 80% | 42% |
| Compress Cooldown | 41% | 3% |
| Mystic Reverb | 40% | 2% |
| Superior Cooldown | 42% | 4% |

**Gun Bebop** — 40% of players (n=5,298), named at 2.7x over the runner-up

_Souls by shop tab: gun 29%  spirit 9%  melee 5%  support 1%  tank 19%  sustain 15%  control 8%  mobility 14%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Headshot Booster | 72% | 6% |
| Headhunter | 70% | 5% |
| Fleetfoot | 45% | 4% |
| Tesla Bullets | 41% | 3% |
| Stalker | 41% | 6% |
| Siphon Bullets | 35% | 1% |
| Capacitor | 33% | 0% |
| Rapid Rounds | 29% | 1% |
| Slowing Hex | 60% | 33% |
| Spirit Snatch | 77% | 51% |

### Infernus  (2 archetypes, n=12,820)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.345 | >= 0.15 |
| replication | 1.000 | >= 0.90 |
| separation | 0.647 | >= 0.45 |
| smallest share | 0.285 | >= 0.12 |

**Spirit Infernus** — 28% of players (n=3,653), named at 2.4x over the runner-up

_Souls by shop tab: gun 11%  spirit 34%  melee 0%  support 1%  tank 29%  sustain 15%  control 5%  mobility 5%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Rapid Recharge | 79% | 26% |
| Extra Charge | 69% | 22% |
| Healbane | 63% | 32% |
| Suppressor | 29% | 11% |
| Radiant Regeneration | 23% | 5% |
| Extra Regen | 38% | 21% |
| Infuser | 18% | 3% |
| Mystic Regeneration | 21% | 5% |
| Healing Booster | 20% | 5% |
| Grit | 27% | 14% |

**Gun Infernus** — 72% of players (n=9,167), named at 3.6x over the runner-up

_Souls by shop tab: gun 29%  spirit 27%  melee 0%  support 1%  tank 21%  sustain 10%  control 6%  mobility 5%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Ricochet | 67% | 2% |
| Toxic Bullets | 81% | 33% |
| Rapid Rounds | 88% | 54% |
| Quicksilver Reload | 42% | 9% |
| Swift Striker | 74% | 44% |
| Titanic Magazine | 86% | 57% |
| Extended Magazine | 83% | 58% |
| Mercurial Magnum | 19% | 1% |
| Burst Fire | 22% | 4% |
| Leech | 22% | 5% |

### Graves  (3 archetypes, n=8,575)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.295 | >= 0.15 |
| replication | 0.999 | >= 0.90 |
| separation | 0.639 | >= 0.45 |
| smallest share | 0.230 | >= 0.12 |

**Spirit Graves** — 38% of players (n=3,239), named at 4.6x over the runner-up

_Souls by shop tab: gun 10%  spirit 31%  melee 0%  support 2%  tank 22%  sustain 17%  control 8%  mobility 11%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Superior Cooldown | 56% | 18% |
| Compress Cooldown | 56% | 19% |
| Arcane Surge | 72% | 43% |
| Transcendent Cooldown | 39% | 12% |
| Heroic Aura | 67% | 43% |
| Improved Spirit | 83% | 61% |
| Enchanter's Emblem | 45% | 25% |
| Mystic Reverb | 22% | 3% |
| Boundless Spirit | 59% | 40% |
| Spirit Burn | 30% | 14% |

**Graves** — 39% of players (n=3,368), **unnamed** — the families are too close to call

_Souls by shop tab: gun 8%  spirit 25%  melee 0%  support 1%  tank 38%  sustain 12%  control 6%  mobility 10%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Echo Shard | 82% | 11% |
| Superior Duration | 65% | 27% |
| Duration Extender | 59% | 24% |
| Refresher | 39% | 6% |
| Mystic Shot | 62% | 37% |
| Arcane Surge | 69% | 44% |
| Heroic Aura | 67% | 43% |
| Improved Spirit | 84% | 60% |
| Mystic Vulnerability | 50% | 30% |
| Boundless Spirit | 58% | 40% |

**Gun Graves** — 23% of players (n=1,968), named at 4.5x over the runner-up

_Souls by shop tab: gun 39%  spirit 14%  melee 0%  support 1%  tank 16%  sustain 10%  control 8%  mobility 13%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Tesla Bullets | 69% | 4% |
| Ricochet | 62% | 5% |
| Surge of Power | 46% | 5% |
| Active Reload | 36% | 1% |
| Toxic Bullets | 78% | 45% |
| Capacitor | 33% | 0% |
| Quicksilver Reload | 36% | 4% |
| Stamina Mastery | 64% | 36% |
| Bullet Lifesteal | 28% | 3% |
| Mercurial Magnum | 27% | 2% |

### Vyper  (2 archetypes, n=4,814)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.279 | >= 0.15 |
| replication | 0.998 | >= 0.90 |
| separation | 0.623 | >= 0.45 |
| smallest share | 0.360 | >= 0.12 |

**Gun Vyper** — 64% of players (n=3,079), named at 5.8x over the runner-up

_Souls by shop tab: gun 53%  spirit 11%  melee 1%  support 0%  tank 14%  sustain 8%  control 3%  mobility 10%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Tesla Bullets | 47% | 31% |
| Bullet Lifesteal | 56% | 45% |
| Ricochet | 34% | 25% |
| Capacitor | 16% | 8% |
| Improved Spirit | 45% | 38% |
| Lucky Shot | 11% | 4% |
| Point Blank | 31% | 25% |
| Intensifying Magazine | 19% | 15% |
| Glass Cannon | 8% | 4% |
| Extended Magazine | 9% | 6% |

**Tank Vyper** — 36% of players (n=1,735), named at 2.2x over the runner-up

_Souls by shop tab: gun 40%  spirit 11%  melee 1%  support 0%  tank 27%  sustain 9%  control 4%  mobility 8%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Unstoppable | 70% | 8% |
| Debuff Reducer | 56% | 12% |
| Spirit Shielding | 44% | 25% |
| Grit | 53% | 36% |
| Spiritual Overflow | 55% | 38% |
| Weakening Headshot | 36% | 20% |
| Silencer | 33% | 18% |
| Crippling Headshot | 22% | 7% |
| Spirit Lifesteal | 45% | 32% |
| Indomitable | 17% | 4% |

### Silver  (2 archetypes, n=3,290)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.244 | >= 0.15 |
| replication | 0.996 | >= 0.90 |
| separation | 0.618 | >= 0.45 |
| smallest share | 0.365 | >= 0.12 |

**Hybrid-Melee Silver** — 64% of players (n=2,090), named at 1.7x over the runner-up

_Souls by shop tab: gun 24%  spirit 9%  melee 5%  support 0%  tank 29%  sustain 11%  control 10%  mobility 13%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Close Quarters | 65% | 38% |
| Extra Stamina | 42% | 16% |
| Point Blank | 45% | 20% |
| Stamina Mastery | 29% | 11% |
| Lifestrike | 23% | 6% |
| Phantom Strike | 21% | 9% |
| Enduring Speed | 20% | 9% |
| Bullet Lifesteal | 13% | 2% |
| Slowing Bullets | 48% | 38% |
| Extra Regen | 14% | 5% |

**Tank Silver** — 36% of players (n=1,200), named at 3.1x over the runner-up

_Souls by shop tab: gun 17%  spirit 7%  melee 3%  support 0%  tank 47%  sustain 10%  control 6%  mobility 10%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Unstoppable | 75% | 13% |
| Debuff Reducer | 70% | 23% |
| Tankbuster | 62% | 27% |
| Spirit Shielding | 55% | 26% |
| Grit | 55% | 27% |
| Veil Walker | 51% | 26% |
| Mystic Burst | 40% | 18% |
| Berserker | 73% | 52% |
| Restorative Shot | 90% | 69% |
| Cold Front | 33% | 14% |

### Mirage  (2 archetypes, n=3,136)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.321 | >= 0.15 |
| replication | 0.998 | >= 0.90 |
| separation | 0.609 | >= 0.45 |
| smallest share | 0.207 | >= 0.12 |

**Spirit Mirage** — 79% of players (n=2,487), named at 2.6x over the runner-up

_Souls by shop tab: gun 28%  spirit 25%  melee 0%  support 1%  tank 20%  sustain 14%  control 9%  mobility 3%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Escalating Exposure | 85% | 24% |
| Superior Cooldown | 69% | 39% |
| Mystic Vulnerability | 87% | 60% |
| Spiritual Overflow | 50% | 23% |
| Spirit Lifesteal | 43% | 19% |
| Compress Cooldown | 88% | 65% |
| Transcendent Cooldown | 22% | 4% |
| Boundless Spirit | 23% | 7% |
| Spirit Sap | 18% | 4% |
| Dispel Magic | 66% | 56% |

**Gun Mirage** — 21% of players (n=649), named at 6.0x over the runner-up

_Souls by shop tab: gun 43%  spirit 17%  melee 0%  support 0%  tank 13%  sustain 12%  control 11%  mobility 4%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Quicksilver Reload | 53% | 21% |
| Mercurial Magnum | 34% | 14% |
| Ricochet | 96% | 81% |
| Swift Striker | 14% | 4% |
| Rapid Rounds | 14% | 3% |
| Headshot Booster | 34% | 24% |
| Opening Rounds | 16% | 7% |
| High-Velocity Rounds | 14% | 6% |
| Recharging Rush | 29% | 22% |
| Headhunter | 27% | 20% |

### Celeste  (2 archetypes, n=6,747)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.282 | >= 0.15 |
| replication | 0.999 | >= 0.90 |
| separation | 0.595 | >= 0.45 |
| smallest share | 0.212 | >= 0.12 |

**Grit Celeste** — 79% of players (n=5,314), named by what it imbues — the families are too close to call

_Souls by shop tab: gun 7%  spirit 26%  melee 0%  support 2%  tank 36%  sustain 20%  control 2%  mobility 7%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Grit | 51% | 24% |
| Torment Pulse | 90% | 63% |
| Spirit Shielding | 53% | 28% |
| Mystic Burst | 28% | 4% |
| Tankbuster | 26% | 2% |
| Restorative Locket | 70% | 47% |
| Mystic Expansion | 80% | 58% |
| Witchmail | 62% | 42% |
| Greater Expansion | 86% | 67% |
| Superior Cooldown | 29% | 11% |

**Spellslinger Celeste** — 21% of players (n=1,433), named by what it imbues — the families are too close to call

_Souls by shop tab: gun 22%  spirit 26%  melee 0%  support 1%  tank 24%  sustain 15%  control 2%  mobility 9%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Spellslinger | 72% | 12% |
| Swift Striker | 39% | 3% |
| Kinetic Dash | 38% | 3% |
| Spiritual Overflow | 61% | 30% |
| Quicksilver Reload | 30% | 1% |
| Spirit Lifesteal | 65% | 37% |
| Opening Rounds | 86% | 60% |
| Mercurial Magnum | 25% | 0% |
| Rapid Rounds | 26% | 2% |
| Extra Stamina | 48% | 31% |

### Billy  (2 archetypes, n=7,972)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.161 | >= 0.15 |
| replication | 0.999 | >= 0.90 |
| separation | 0.594 | >= 0.45 |
| smallest share | 0.279 | >= 0.12 |

**Spirit Billy** — 28% of players (n=2,224), named at 5.9x over the runner-up

_Souls by shop tab: gun 16%  spirit 20%  melee 14%  support 1%  tank 25%  sustain 12%  control 6%  mobility 6%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Rapid Recharge | 79% | 19% |
| Extra Charge | 57% | 15% |
| Greater Expansion | 55% | 21% |
| Cultist Sacrifice | 55% | 29% |
| Mystic Expansion | 37% | 12% |
| Enchanter's Emblem | 55% | 35% |
| Slowing Hex | 39% | 30% |
| Witchmail | 12% | 4% |
| Battle Vest | 53% | 45% |
| Spirit Strike | 72% | 65% |

**Billy** — 72% of players (n=5,748), **unnamed** — the families are too close to call

_Souls by shop tab: gun 20%  spirit 9%  melee 15%  support 1%  tank 29%  sustain 12%  control 8%  mobility 7%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Point Blank | 71% | 43% |
| Close Quarters | 91% | 69% |
| Weakening Headshot | 28% | 8% |
| Melee Lifesteal | 54% | 37% |
| Dispel Magic | 30% | 16% |
| Berserker | 36% | 22% |
| Colossus | 36% | 23% |
| Extra Health | 33% | 21% |
| Crippling Headshot | 15% | 3% |
| Debuff Reducer | 17% | 6% |

### Lady Geist  (3 archetypes, n=6,002)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.323 | >= 0.15 |
| replication | 0.999 | >= 0.90 |
| separation | 0.574 | >= 0.45 |
| smallest share | 0.318 | >= 0.12 |

**Reverb Spirit Lady Geist** — 36% of players (n=2,181), named at 4.0x over the runner-up

_Souls by shop tab: gun 1%  spirit 33%  melee 0%  support 0%  tank 25%  sustain 29%  control 6%  mobility 5%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Mystic Reverb | 82% | 12% |
| Superior Cooldown | 85% | 33% |
| Compress Cooldown | 79% | 34% |
| Tankbuster | 89% | 46% |
| Greater Expansion | 68% | 28% |
| Mystic Expansion | 93% | 53% |
| Extra Spirit | 82% | 44% |
| Sprint Boots | 75% | 39% |
| Improved Spirit | 79% | 43% |
| Transcendent Cooldown | 47% | 14% |

**Exposure Spirit Lady Geist** — 32% of players (n=1,911), named at 2.3x over the runner-up

_Souls by shop tab: gun 7%  spirit 31%  melee 0%  support 0%  tank 31%  sustain 19%  control 5%  mobility 6%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Escalating Exposure | 76% | 28% |
| Mystic Vulnerability | 82% | 37% |
| Improved Spirit | 84% | 41% |
| Extra Spirit | 83% | 44% |
| Tankbuster | 86% | 48% |
| Leech | 52% | 19% |
| Mystic Expansion | 88% | 56% |
| Boundless Spirit | 52% | 20% |
| Enduring Speed | 65% | 38% |
| Compress Cooldown | 66% | 41% |

**Gun Lady Geist** — 32% of players (n=1,910), named at 2.4x over the runner-up

_Souls by shop tab: gun 33%  spirit 14%  melee 0%  support 1%  tank 22%  sustain 19%  control 3%  mobility 7%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Kinetic Dash | 88% | 4% |
| Berserker | 96% | 13% |
| Monster Rounds | 80% | 5% |
| Bullet Resist Shredder | 64% | 1% |
| Spellslinger | 63% | 2% |
| Extra Regen | 92% | 35% |
| Extra Stamina | 62% | 11% |
| Mercurial Magnum | 47% | 1% |
| Cultist Sacrifice | 48% | 2% |
| Healing Booster | 66% | 25% |

### Paige  (2 archetypes, n=9,052)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.240 | >= 0.15 |
| replication | 0.999 | >= 0.90 |
| separation | 0.534 | >= 0.45 |
| smallest share | 0.333 | >= 0.12 |

**Spirit Paige** — 67% of players (n=6,036), named at 4.6x over the runner-up

_Souls by shop tab: gun 5%  spirit 36%  melee 0%  support 5%  tank 20%  sustain 16%  control 8%  mobility 10%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Rapid Recharge | 78% | 24% |
| Extra Charge | 89% | 49% |
| Improved Spirit | 60% | 24% |
| Superior Cooldown | 81% | 47% |
| Compress Cooldown | 71% | 39% |
| Greater Expansion | 79% | 47% |
| Transcendent Cooldown | 59% | 29% |
| Duration Extender | 47% | 18% |
| Boundless Spirit | 42% | 13% |
| Superior Duration | 55% | 26% |

**Gun Paige** — 33% of players (n=3,016), named at 2.5x over the runner-up

_Souls by shop tab: gun 14%  spirit 23%  melee 0%  support 6%  tank 15%  sustain 12%  control 13%  mobility 16%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Express Shot | 41% | 5% |
| Cursed Relic | 43% | 15% |
| Slowing Hex | 59% | 35% |
| Opening Rounds | 70% | 47% |
| High-Velocity Rounds | 89% | 68% |
| Surge of Power | 30% | 13% |
| Spirit Shielding | 19% | 6% |
| Vortex Web | 35% | 23% |
| Arcane Surge | 27% | 17% |
| Split Shot | 9% | 1% |

### Ivy  (3 archetypes, n=8,544)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.320 | >= 0.15 |
| replication | 0.999 | >= 0.90 |
| separation | 0.531 | >= 0.45 |
| smallest share | 0.314 | >= 0.12 |

**Spirit Ivy** — 34% of players (n=2,869), named at 3.3x over the runner-up

_Souls by shop tab: gun 6%  spirit 34%  melee 0%  support 2%  tank 26%  sustain 12%  control 9%  mobility 10%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Trophy Collector | 72% | 12% |
| Extra Charge | 90% | 33% |
| Superior Duration | 67% | 15% |
| Superior Cooldown | 61% | 14% |
| Rapid Recharge | 75% | 28% |
| Greater Expansion | 79% | 33% |
| Compress Cooldown | 56% | 12% |
| Echo Shard | 42% | 3% |
| Mystic Expansion | 86% | 49% |
| Duration Extender | 51% | 14% |

**Ivy** — 35% of players (n=2,988), **unnamed** — the families are too close to call

_Souls by shop tab: gun 31%  spirit 21%  melee 0%  support 4%  tank 15%  sustain 12%  control 7%  mobility 9%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Tesla Bullets | 92% | 54% |
| Titanic Magazine | 92% | 57% |
| Extended Magazine | 89% | 55% |
| Healing Booster | 57% | 28% |
| Healing Tempo | 48% | 20% |
| Healing Nova | 34% | 8% |
| Healing Rite | 38% | 16% |
| Extra Regen | 48% | 26% |
| Mystic Slow | 48% | 28% |
| Quicksilver Reload | 31% | 11% |

**Gun Ivy** — 31% of players (n=2,687), named at 4.9x over the runner-up

_Souls by shop tab: gun 52%  spirit 7%  melee 0%  support 2%  tank 13%  sustain 11%  control 7%  mobility 9%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Capacitor | 94% | 30% |
| Active Reload | 58% | 2% |
| Bullet Resist Shredder | 59% | 5% |
| Tesla Bullets | 99% | 50% |
| Titanic Magazine | 99% | 54% |
| Extended Magazine | 95% | 52% |
| Siphon Bullets | 35% | 6% |
| Swift Striker | 29% | 1% |
| Headhunter | 33% | 5% |
| Fleetfoot | 38% | 10% |

### Rem  (2 archetypes, n=8,589)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.266 | >= 0.15 |
| replication | 0.996 | >= 0.90 |
| separation | 0.525 | >= 0.45 |
| smallest share | 0.310 | >= 0.12 |

**Spirit Rem** — 69% of players (n=5,924), named at 1.8x over the runner-up

_Souls by shop tab: gun 5%  spirit 32%  melee 0%  support 7%  tank 22%  sustain 19%  control 7%  mobility 8%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Superior Cooldown | 67% | 15% |
| Mystic Expansion | 66% | 20% |
| Compress Cooldown | 56% | 11% |
| Rapid Recharge | 74% | 31% |
| Mystic Burst | 59% | 21% |
| Tankbuster | 53% | 17% |
| Greater Expansion | 51% | 17% |
| Improved Spirit | 75% | 41% |
| Transcendent Cooldown | 40% | 8% |
| Extra Spirit | 66% | 35% |

**Gun Rem** — 31% of players (n=2,665), named at 2.2x over the runner-up

_Souls by shop tab: gun 14%  spirit 17%  melee 0%  support 6%  tank 24%  sustain 14%  control 17%  mobility 9%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Cursed Relic | 66% | 25% |
| High-Velocity Rounds | 60% | 19% |
| Opening Rounds | 52% | 16% |
| Decay | 30% | 12% |
| Echo Shard | 34% | 18% |
| Sprint Boots | 63% | 48% |
| Cheat Death | 20% | 4% |
| Trophy Collector | 74% | 61% |
| Spirit Shielding | 15% | 2% |
| Scourge | 21% | 11% |

### Grey Talon  (3 archetypes, n=4,059)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.294 | >= 0.15 |
| replication | 0.998 | >= 0.90 |
| separation | 0.519 | >= 0.45 |
| smallest share | 0.144 | >= 0.12 |

**Spirit Grey Talon** — 52% of players (n=2,106), named at 4.9x over the runner-up

_Souls by shop tab: gun 7%  spirit 37%  melee 0%  support 0%  tank 19%  sustain 21%  control 8%  mobility 9%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Boundless Spirit | 90% | 36% |
| Spirit Burn | 75% | 22% |
| Mystic Reverb | 65% | 13% |
| Enchanter's Emblem | 81% | 32% |
| Superior Cooldown | 82% | 34% |
| Tankbuster | 96% | 49% |
| Rapid Recharge | 97% | 51% |
| Extra Charge | 98% | 54% |
| Improved Spirit | 96% | 53% |
| Mystic Burst | 99% | 55% |

**Hybrid-Spirit Grey Talon** — 34% of players (n=1,367), named at 1.4x over the runner-up

_Souls by shop tab: gun 19%  spirit 30%  melee 0%  support 0%  tank 17%  sustain 13%  control 5%  mobility 15%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Rapid Recharge | 93% | 53% |
| Tankbuster | 91% | 52% |
| Extra Charge | 94% | 56% |
| Mystic Burst | 95% | 57% |
| Opening Rounds | 77% | 39% |
| Improved Spirit | 90% | 56% |
| Stamina Mastery | 75% | 50% |
| Extra Spirit | 74% | 52% |
| High-Velocity Rounds | 83% | 61% |
| Recharging Rush | 43% | 22% |

**Gun Grey Talon** — 14% of players (n=586), named at 6.1x over the runner-up

_Souls by shop tab: gun 49%  spirit 10%  melee 0%  support 0%  tank 12%  sustain 7%  control 6%  mobility 16%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Burst Fire | 73% | 3% |
| Swift Striker | 85% | 26% |
| Bullet Lifesteal | 60% | 1% |
| Rapid Rounds | 79% | 21% |
| Glass Cannon | 59% | 2% |
| Sharpshooter | 95% | 45% |
| Vampiric Burst | 41% | 0% |
| Weakening Headshot | 42% | 3% |
| Long Range | 93% | 54% |
| Lucky Shot | 33% | 1% |

### Yamato  (2 archetypes, n=5,674)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.242 | >= 0.15 |
| replication | 0.999 | >= 0.90 |
| separation | 0.519 | >= 0.45 |
| smallest share | 0.426 | >= 0.12 |

**Spirit Yamato** — 57% of players (n=3,255), named at 1.8x over the runner-up

_Souls by shop tab: gun 7%  spirit 26%  melee 7%  support 1%  tank 24%  sustain 27%  control 5%  mobility 3%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Mystic Reverb | 80% | 28% |
| Healing Booster | 67% | 34% |
| Extra Spirit | 74% | 48% |
| Improved Spirit | 90% | 64% |
| Restorative Locket | 48% | 26% |
| Extra Regen | 58% | 38% |
| Boundless Spirit | 59% | 40% |
| Superior Cooldown | 44% | 29% |
| Healbane | 81% | 69% |
| Spiritual Overflow | 25% | 14% |

**Yamato** — 43% of players (n=2,419), **unnamed** — the families are too close to call

_Souls by shop tab: gun 11%  spirit 18%  melee 8%  support 1%  tank 33%  sustain 17%  control 6%  mobility 4%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Stalker | 48% | 19% |
| Torment Pulse | 49% | 33% |
| Cold Front | 32% | 17% |
| Scourge | 15% | 2% |
| Refresher | 27% | 15% |
| Arctic Blast | 15% | 3% |
| Colossus | 12% | 1% |
| Mystic Vulnerability | 22% | 12% |
| Extra Health | 14% | 4% |
| Bullet Resist Shredder | 11% | 1% |

### Seven  (3 archetypes, n=9,436)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.260 | >= 0.15 |
| replication | 0.999 | >= 0.90 |
| separation | 0.518 | >= 0.45 |
| smallest share | 0.198 | >= 0.12 |

**Spirit Seven** — 34% of players (n=3,163), named at 6.8x over the runner-up

_Souls by shop tab: gun 8%  spirit 40%  melee 0%  support 0%  tank 27%  sustain 15%  control 5%  mobility 5%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Mystic Expansion | 57% | 22% |
| Extra Charge | 56% | 23% |
| Rapid Recharge | 51% | 21% |
| Superior Cooldown | 51% | 23% |
| Improved Spirit | 67% | 40% |
| Greater Expansion | 47% | 24% |
| Compress Cooldown | 43% | 22% |
| Boundless Spirit | 49% | 29% |
| Transcendent Cooldown | 29% | 9% |
| Duration Extender | 60% | 43% |

**Hybrid-Tank Seven** — 47% of players (n=4,409), named at 1.3x over the runner-up

_Souls by shop tab: gun 6%  spirit 30%  melee 0%  support 1%  tank 40%  sustain 12%  control 5%  mobility 6%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Unstoppable | 83% | 21% |
| Debuff Reducer | 58% | 17% |
| Refresher | 33% | 4% |
| Infuser | 45% | 23% |
| Lightning Scroll | 26% | 10% |
| Indomitable | 34% | 19% |
| Arcane Surge | 64% | 50% |
| Cultist Sacrifice | 65% | 51% |
| Reactive Barrier | 30% | 19% |
| Mystic Slow | 23% | 13% |

**Gun Seven** — 20% of players (n=1,864), named at 1.8x over the runner-up

_Souls by shop tab: gun 19%  spirit 30%  melee 0%  support 1%  tank 25%  sustain 11%  control 6%  mobility 8%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Mercurial Magnum | 55% | 3% |
| Quicksilver Reload | 46% | 5% |
| Spiritual Overflow | 60% | 37% |
| Toxic Bullets | 40% | 21% |
| Extended Magazine | 21% | 4% |
| Surge of Power | 38% | 22% |
| Bullet Resist Shredder | 21% | 6% |
| Spirit Shielding | 33% | 18% |
| Titanic Magazine | 18% | 4% |
| Spirit Shredder Bullets | 30% | 17% |

### Sinclair  (2 archetypes, n=3,957)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.243 | >= 0.15 |
| replication | 0.996 | >= 0.90 |
| separation | 0.493 | >= 0.45 |
| smallest share | 0.451 | >= 0.12 |

**Spirit Sinclair** — 55% of players (n=2,172), named at 5.7x over the runner-up

_Souls by shop tab: gun 4%  spirit 43%  melee 0%  support 0%  tank 22%  sustain 17%  control 5%  mobility 8%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Rapid Recharge | 93% | 44% |
| Extra Charge | 95% | 51% |
| Improved Spirit | 94% | 53% |
| Boundless Spirit | 78% | 40% |
| Extra Spirit | 88% | 51% |
| Enchanter's Emblem | 62% | 29% |
| Superior Cooldown | 57% | 33% |
| Magic Carpet | 28% | 8% |
| Compress Cooldown | 41% | 23% |
| Veil Walker | 66% | 47% |

**Melee Sinclair** — 45% of players (n=1,785), named at 1.7x over the runner-up

_Souls by shop tab: gun 8%  spirit 30%  melee 2%  support 1%  tank 31%  sustain 12%  control 6%  mobility 10%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Arcane Surge | 28% | 5% |
| Grit | 30% | 9% |
| Warp Stone | 26% | 5% |
| Unstoppable | 23% | 3% |
| Echo Shard | 24% | 4% |
| Mystic Slow | 33% | 13% |
| Debuff Reducer | 22% | 3% |
| Extra Stamina | 25% | 8% |
| Guardian Ward | 18% | 3% |
| High-Velocity Rounds | 53% | 40% |

### Venator  (2 archetypes, n=7,059)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.163 | >= 0.15 |
| replication | 0.998 | >= 0.90 |
| separation | 0.485 | >= 0.45 |
| smallest share | 0.359 | >= 0.12 |

**Hybrid-Spirit Venator** — 64% of players (n=4,526), named at 1.5x over the runner-up

_Souls by shop tab: gun 36%  spirit 12%  melee 2%  support 1%  tank 23%  sustain 15%  control 6%  mobility 6%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Rapid Recharge | 69% | 21% |
| Extra Charge | 60% | 19% |
| Ballistic Enchantment | 30% | 11% |
| Enduring Speed | 64% | 46% |
| Cultist Sacrifice | 37% | 19% |
| Extra Regen | 28% | 12% |
| Monster Rounds | 43% | 28% |
| Hollow Point | 39% | 24% |
| Radiant Regeneration | 16% | 1% |
| Healing Booster | 17% | 3% |

**Gun Venator** — 36% of players (n=2,533), named at 4.2x over the runner-up

_Souls by shop tab: gun 48%  spirit 4%  melee 1%  support 0%  tank 23%  sustain 11%  control 7%  mobility 5%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Intensifying Magazine | 63% | 30% |
| Vampiric Burst | 78% | 46% |
| Berserker | 57% | 27% |
| Swift Striker | 36% | 9% |
| Fleetfoot | 55% | 28% |
| Rapid Rounds | 35% | 9% |
| Bullet Lifesteal | 86% | 67% |
| Ricochet | 20% | 4% |
| Close Quarters | 77% | 61% |
| Restorative Shot | 67% | 51% |

### Warden  (2 archetypes, n=10,117)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.263 | >= 0.15 |
| replication | 1.000 | >= 0.90 |
| separation | 0.484 | >= 0.45 |
| smallest share | 0.438 | >= 0.12 |

**Hybrid-Spirit Warden** — 44% of players (n=4,431), named at 1.3x over the runner-up

_Souls by shop tab: gun 34%  spirit 18%  melee 0%  support 0%  tank 22%  sustain 15%  control 3%  mobility 8%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Boundless Spirit | 55% | 7% |
| Improved Spirit | 40% | 10% |
| Extra Spirit | 39% | 15% |
| Unstoppable | 19% | 1% |
| Spirit Resilience | 53% | 38% |
| Witchmail | 17% | 1% |
| Juggernaut | 24% | 11% |
| Debuff Reducer | 15% | 2% |
| Spiritual Overflow | 87% | 77% |
| Spirit Lifesteal | 68% | 58% |

**Gun Warden** — 56% of players (n=5,686), named at 5.7x over the runner-up

_Souls by shop tab: gun 46%  spirit 15%  melee 0%  support 0%  tank 15%  sustain 13%  control 2%  mobility 9%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Bullet Lifesteal | 19% | 10% |
| Battle Vest | 27% | 21% |
| Kinetic Dash | 11% | 6% |
| Intensifying Magazine | 9% | 4% |
| Vampiric Burst | 14% | 9% |
| Extended Magazine | 77% | 73% |
| High-Velocity Rounds | 93% | 89% |
| Spellslinger | 9% | 5% |
| Extra Regen | 47% | 43% |
| Quicksilver Reload | 98% | 94% |

### Mina  (3 archetypes, n=8,941)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.241 | >= 0.15 |
| replication | 0.999 | >= 0.90 |
| separation | 0.483 | >= 0.45 |
| smallest share | 0.167 | >= 0.12 |

**Spirit Mina** — 59% of players (n=5,243), named at 2.6x over the runner-up

_Souls by shop tab: gun 9%  spirit 26%  melee 0%  support 2%  tank 24%  sustain 16%  control 11%  mobility 12%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Spirit Burn | 95% | 47% |
| Superior Cooldown | 62% | 40% |
| Compress Cooldown | 45% | 29% |
| Transcendent Cooldown | 29% | 17% |
| Ethereal Shift | 25% | 13% |
| Spirit Sap | 43% | 31% |
| Spirit Rend | 51% | 39% |
| Spirit Shredder Bullets | 63% | 53% |
| Boundless Spirit | 91% | 81% |
| Dispel Magic | 83% | 73% |

**Hybrid-Gun Mina** — 17% of players (n=1,491), named at 1.6x over the runner-up

_Souls by shop tab: gun 22%  spirit 23%  melee 0%  support 2%  tank 20%  sustain 13%  control 8%  mobility 12%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Mercurial Magnum | 57% | 7% |
| Ricochet | 36% | 1% |
| Spiritual Overflow | 37% | 16% |
| Rapid Rounds | 39% | 21% |
| Spirit Lifesteal | 30% | 12% |
| Toxic Bullets | 25% | 8% |
| Swift Striker | 46% | 31% |
| Focus Lens | 17% | 5% |
| Titanic Magazine | 11% | 1% |
| Extended Magazine | 10% | 1% |

**Tank Mina** — 25% of players (n=2,207), named at 5.2x over the runner-up

_Souls by shop tab: gun 10%  spirit 20%  melee 0%  support 2%  tank 31%  sustain 18%  control 3%  mobility 15%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Grit | 49% | 33% |
| Reactive Barrier | 43% | 27% |
| Dispel Magic | 87% | 71% |
| Extra Health | 58% | 43% |
| Indomitable | 27% | 13% |
| Mystic Expansion | 72% | 60% |
| Spellbreaker | 15% | 4% |
| Debuff Reducer | 14% | 6% |
| Tankbuster | 97% | 93% |
| Spirit Shielding | 17% | 13% |

### Lash  (3 archetypes, n=12,795)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.307 | >= 0.15 |
| replication | 1.000 | >= 0.90 |
| separation | 0.466 | >= 0.45 |
| smallest share | 0.270 | >= 0.12 |

**Spirit Lash** — 39% of players (n=4,970), named at 5.3x over the runner-up

_Souls by shop tab: gun 11%  spirit 29%  melee 0%  support 0%  tank 24%  sustain 16%  control 8%  mobility 12%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Superior Cooldown | 78% | 27% |
| Extra Spirit | 90% | 40% |
| Improved Spirit | 84% | 38% |
| Boundless Spirit | 64% | 23% |
| Compress Cooldown | 60% | 19% |
| Spirit Burn | 60% | 21% |
| Mystic Expansion | 71% | 36% |
| Greater Expansion | 65% | 33% |
| Trophy Collector | 47% | 17% |
| Transcendent Cooldown | 34% | 8% |

**Lash** — 27% of players (n=3,460), **unnamed** — the families are too close to call

_Souls by shop tab: gun 13%  spirit 19%  melee 0%  support 0%  tank 40%  sustain 11%  control 6%  mobility 11%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Refresher | 60% | 15% |
| Unstoppable | 54% | 13% |
| Debuff Reducer | 40% | 12% |
| Extra Spirit | 74% | 48% |
| Improved Spirit | 71% | 45% |
| Greater Expansion | 59% | 36% |
| Mystic Expansion | 62% | 41% |
| Mystic Shot | 43% | 24% |
| Majestic Leap | 25% | 13% |
| Boundless Spirit | 44% | 33% |

**Gun Lash** — 34% of players (n=4,365), named at 5.0x over the runner-up

_Souls by shop tab: gun 38%  spirit 7%  melee 0%  support 0%  tank 25%  sustain 11%  control 4%  mobility 14%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Bullet Resist Shredder | 91% | 11% |
| Siphon Bullets | 87% | 11% |
| Recharging Rush | 96% | 26% |
| Sharpshooter | 56% | 2% |
| Crippling Headshot | 37% | 6% |
| Weakening Headshot | 35% | 5% |
| High-Velocity Rounds | 29% | 1% |
| Headhunter | 99% | 71% |
| Mercurial Magnum | 34% | 6% |
| Long Range | 27% | 1% |

### Haze  (3 archetypes, n=13,486)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.226 | >= 0.15 |
| replication | 0.999 | >= 0.90 |
| separation | 0.460 | >= 0.45 |
| smallest share | 0.233 | >= 0.12 |

**Spirit Haze** — 23% of players (n=3,144), named at 2.2x over the runner-up

_Souls by shop tab: gun 41%  spirit 16%  melee 0%  support 0%  tank 12%  sustain 10%  control 4%  mobility 16%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Spiritual Overflow | 68% | 14% |
| Veil Walker | 61% | 11% |
| Spirit Lifesteal | 58% | 11% |
| Extra Charge | 49% | 8% |
| Sprint Boots | 68% | 29% |
| Quicksilver Reload | 62% | 26% |
| Mercurial Magnum | 56% | 22% |
| Enchanter's Emblem | 28% | 5% |
| Tesla Bullets | 45% | 31% |
| Surge of Power | 86% | 73% |

**Haze** — 39% of players (n=5,218), **unnamed** — the families are too close to call

_Souls by shop tab: gun 40%  spirit 5%  melee 0%  support 0%  tank 25%  sustain 9%  control 9%  mobility 12%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Unstoppable | 54% | 7% |
| Debuff Reducer | 37% | 7% |
| Silencer | 55% | 28% |
| Active Reload | 72% | 48% |
| Extra Health | 45% | 24% |
| Ricochet | 77% | 57% |
| Inhibitor | 28% | 10% |
| Spirit Resilience | 38% | 19% |
| Siphon Bullets | 34% | 19% |
| Golden Goose Egg | 42% | 29% |

**Gun Haze** — 38% of players (n=5,124), named at 7.2x over the runner-up

_Souls by shop tab: gun 55%  spirit 5%  melee 0%  support 0%  tank 13%  sustain 7%  control 6%  mobility 13%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Bullet Lifesteal | 67% | 36% |
| Ricochet | 82% | 55% |
| Active Reload | 68% | 51% |
| Titanic Magazine | 31% | 15% |
| Extended Magazine | 35% | 22% |
| Lucky Shot | 18% | 5% |
| Vampiric Burst | 28% | 16% |
| Fury Trance | 25% | 14% |
| Tesla Bullets | 43% | 32% |
| Capacitor | 38% | 27% |

### Drifter  (3 archetypes, n=11,599)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.255 | >= 0.15 |
| replication | 0.999 | >= 0.90 |
| separation | 0.459 | >= 0.45 |
| smallest share | 0.289 | >= 0.12 |

**Stalker's Mark Melee Drifter** — 40% of players (n=4,639), named at 2.2x over the runner-up

_Souls by shop tab: gun 9%  spirit 18%  melee 9%  support 0%  tank 31%  sustain 10%  control 14%  mobility 9%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Tankbuster | 93% | 36% |
| Spirit Snatch | 98% | 45% |
| Superior Duration | 62% | 10% |
| Spirit Strike | 96% | 45% |
| Veil Walker | 84% | 34% |
| Spirit Burn | 50% | 4% |
| Mystic Burst | 87% | 47% |
| Cold Front | 43% | 4% |
| Melee Lifesteal | 89% | 51% |
| Duration Extender | 36% | 5% |

**Rend Melee Drifter** — 31% of players (n=3,605), named at 1.9x over the runner-up

_Souls by shop tab: gun 25%  spirit 10%  melee 7%  support 0%  tank 25%  sustain 10%  control 9%  mobility 13%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Spirit Snatch | 72% | 58% |
| Melee Lifesteal | 72% | 59% |
| Kinetic Dash | 51% | 38% |
| Weakening Headshot | 20% | 7% |
| Silencer | 28% | 17% |
| Extra Stamina | 39% | 29% |
| Opening Rounds | 19% | 9% |
| Spiritual Overflow | 19% | 10% |
| Spirit Strike | 68% | 59% |
| Crippling Headshot | 17% | 9% |

**Gun Drifter** — 29% of players (n=3,355), named at 4.0x over the runner-up

_Souls by shop tab: gun 42%  spirit 4%  melee 2%  support 0%  tank 20%  sustain 9%  control 9%  mobility 14%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Burst Fire | 76% | 26% |
| Close Quarters | 70% | 25% |
| Rapid Rounds | 62% | 19% |
| Lucky Shot | 46% | 4% |
| Kinetic Dash | 70% | 28% |
| Point Blank | 64% | 23% |
| Fortitude | 51% | 16% |
| Vampiric Burst | 41% | 7% |
| Extra Stamina | 53% | 22% |
| Bullet Lifesteal | 42% | 12% |

### Kelvin  (2 archetypes, n=5,357)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.269 | >= 0.15 |
| replication | 0.999 | >= 0.90 |
| separation | 0.455 | >= 0.45 |
| smallest share | 0.304 | >= 0.12 |

**Spirit Kelvin** — 70% of players (n=3,729), named at 3.0x over the runner-up

_Souls by shop tab: gun 2%  spirit 40%  melee 0%  support 1%  tank 27%  sustain 19%  control 6%  mobility 6%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Escalating Exposure | 79% | 33% |
| Mystic Vulnerability | 77% | 37% |
| Superior Duration | 48% | 20% |
| Mystic Expansion | 74% | 46% |
| Duration Extender | 40% | 12% |
| Superior Cooldown | 70% | 42% |
| Boundless Spirit | 72% | 45% |
| Greater Expansion | 62% | 37% |
| Torment Pulse | 34% | 10% |
| Spirit Lifesteal | 38% | 16% |

**Support Kelvin** — 30% of players (n=1,628), named at 2.0x over the runner-up

_Souls by shop tab: gun 9%  spirit 29%  melee 0%  support 5%  tank 19%  sustain 21%  control 8%  mobility 10%. Shown for reference only — the name comes from what the items below do, not from the tab they are sold in._

| item | in this build | in the others |
|---|---|---|
| Healing Tempo | 39% | 11% |
| Rescue Beam | 36% | 10% |
| Opening Rounds | 36% | 12% |
| High-Velocity Rounds | 38% | 15% |
| Healing Rite | 33% | 11% |
| Healing Booster | 83% | 64% |
| Slowing Hex | 23% | 8% |
| Guardian Ward | 17% | 3% |
| Cursed Relic | 16% | 2% |
| Quicksilver Reload | 13% | 0% |

## Heroes that did not split

| hero | n | why |
|---|---|---|
| Apollo | 5,074 | single archetype: best split fails smallest share |
| Calico | 7,936 | single archetype: best split fails smallest share |
| Mo & Krill | 9,856 | single archetype: best split k=3 fails separation (all clusters merged) |
| Pocket | 6,510 | single archetype: best split fails smallest share |
| The Doorman | 4,366 | single archetype: best split fails smallest share |
| Vindicta | 8,460 | single archetype: best split fails smallest share |
| Wraith | 11,114 | single archetype: best split k=3 fails separation (all clusters merged) |
