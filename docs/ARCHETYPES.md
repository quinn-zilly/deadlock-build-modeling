# Archetype review

Fitted per hero on souls-weighted item slot-type shares. A hero splits
only if all four criteria pass; otherwise it stays single, which is a
result and not a failure.

**21 of 38 heroes split.** Seed 0, so a refit reproduces this exactly.

Names below are proposed from each cluster's dominant slot type. Edit
`data/archetype_names.json` (keyed `"<hero_id>:<archetype_id>"`) to
overrule any of them.

## Heroes that split

### Lady Geist  (2 archetypes, n=5,950)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.672 | >= 0.35 |
| replication | 0.999 | >= 0.90 |
| separation | 0.849 | >= 0.45 |
| smallest share | 0.345 | >= 0.15 |

**Spirit Lady Geist** — 66% of players (n=3,899) — weapon 3%  vitality 25%  spirit 72%

| item | in this build | in the others |
|---|---|---|
| Extra Spirit | 85% | 6% |
| Tankbuster | 89% | 11% |
| Improved Spirit | 81% | 5% |
| Superior Cooldown | 76% | 6% |
| Compress Cooldown | 71% | 4% |
| Mystic Vulnerability | 71% | 6% |
| Mystic Expansion | 90% | 26% |
| Greater Expansion | 65% | 3% |
| Sprint Boots | 71% | 11% |
| Escalating Exposure | 63% | 4% |

**Gun Lady Geist** — 34% of players (n=2,051) — weapon 40%  vitality 38%  spirit 22%

| item | in this build | in the others |
|---|---|---|
| Berserker | 94% | 9% |
| Kinetic Dash | 87% | 3% |
| Spellslinger | 82% | 1% |
| Monster Rounds | 76% | 4% |
| Bullet Resist Shredder | 59% | 1% |
| Healing Booster | 80% | 23% |
| Extra Regen | 92% | 36% |
| Extra Stamina | 63% | 10% |
| Cultist Sacrifice | 42% | 2% |
| Recharging Rush | 28% | 2% |

### McGinnis  (2 archetypes, n=4,656)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.596 | >= 0.35 |
| replication | 0.998 | >= 0.90 |
| separation | 0.771 | >= 0.45 |
| smallest share | 0.318 | >= 0.15 |

**Spirit McGinnis** — 68% of players (n=3,177) — weapon 10%  vitality 22%  spirit 67%

| item | in this build | in the others |
|---|---|---|
| Escalating Exposure | 84% | 6% |
| Mystic Vulnerability | 88% | 12% |
| Mystic Expansion | 81% | 9% |
| Extra Charge | 88% | 23% |
| Rapid Recharge | 77% | 16% |
| Mystic Slow | 68% | 9% |
| Compress Cooldown | 64% | 6% |
| Greater Expansion | 60% | 3% |
| Superior Cooldown | 60% | 4% |
| Improved Spirit | 55% | 7% |

**Gun McGinnis** — 32% of players (n=1,479) — weapon 44%  vitality 35%  spirit 21%

| item | in this build | in the others |
|---|---|---|
| Extended Magazine | 68% | 5% |
| Quicksilver Reload | 67% | 4% |
| Mercurial Magnum | 60% | 3% |
| Bullet Lifesteal | 53% | 1% |
| Fleetfoot | 53% | 2% |
| Rapid Rounds | 50% | 1% |
| Swift Striker | 49% | 1% |
| Titanic Magazine | 47% | 4% |
| Tesla Bullets | 42% | 5% |
| Vampiric Burst | 32% | 0% |

### Lash  (2 archetypes, n=12,951)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.554 | >= 0.35 |
| replication | 1.000 | >= 0.90 |
| separation | 0.762 | >= 0.45 |
| smallest share | 0.456 | >= 0.15 |

**Spirit Lash** — 54% of players (n=7,048) — weapon 10%  vitality 23%  spirit 66%

| item | in this build | in the others |
|---|---|---|
| Improved Spirit | 87% | 12% |
| Extra Spirit | 86% | 12% |
| Boundless Spirit | 63% | 3% |
| Superior Cooldown | 68% | 12% |
| Greater Expansion | 67% | 12% |
| Mystic Expansion | 69% | 14% |
| Spirit Burn | 56% | 4% |
| Compress Cooldown | 52% | 10% |
| Mystic Shot | 43% | 7% |
| Trophy Collector | 42% | 9% |

**Tank Lash** — 46% of players (n=5,903) — weapon 30%  vitality 40%  spirit 30%

| item | in this build | in the others |
|---|---|---|
| Bullet Resist Shredder | 83% | 6% |
| Siphon Bullets | 80% | 6% |
| Recharging Rush | 89% | 23% |
| Sharpshooter | 48% | 2% |
| Crippling Headshot | 40% | 4% |
| Weakening Headshot | 37% | 4% |
| Restorative Locket | 44% | 13% |
| Headhunter | 98% | 68% |
| High-Velocity Rounds | 26% | 1% |
| Long Range | 25% | 1% |

### Sinclair  (3 archetypes, n=3,690)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.404 | >= 0.35 |
| replication | 0.996 | >= 0.90 |
| separation | 0.725 | >= 0.45 |
| smallest share | 0.151 | >= 0.15 |

**Spirit Sinclair** — 47% of players (n=1,716) — weapon 3%  vitality 16%  spirit 80%

| item | in this build | in the others |
|---|---|---|
| Boundless Spirit | 87% | 39% |
| Rapid Recharge | 96% | 54% |
| Extra Charge | 97% | 59% |
| Improved Spirit | 96% | 59% |
| Extra Spirit | 89% | 54% |
| Spirit Burn | 38% | 8% |
| Tankbuster | 33% | 7% |
| Enchanter's Emblem | 64% | 39% |
| Superior Cooldown | 57% | 34% |
| Mystic Burst | 31% | 10% |

**Spirit Sinclair** — 38% of players (n=1,415) — weapon 8%  vitality 29%  spirit 63%

| item | in this build | in the others |
|---|---|---|
| Improved Spirit | 83% | 65% |
| Extra Charge | 83% | 66% |
| Rapid Recharge | 79% | 62% |
| Extra Spirit | 76% | 61% |
| Enchanter's Emblem | 56% | 43% |
| Boundless Spirit | 64% | 51% |
| Greater Expansion | 85% | 74% |
| Superior Cooldown | 48% | 38% |
| Transcendent Cooldown | 22% | 15% |
| Trophy Collector | 45% | 37% |

**Spirit Sinclair** — 15% of players (n=559) — weapon 21%  vitality 39%  spirit 40%

| item | in this build | in the others |
|---|---|---|
| Melee Charge | 29% | 2% |
| Grit | 35% | 11% |
| High-Velocity Rounds | 60% | 37% |
| Opening Rounds | 60% | 38% |
| Cultist Sacrifice | 30% | 8% |
| Arcane Surge | 29% | 9% |
| Close Quarters | 18% | 1% |
| Point Blank | 17% | 1% |
| Crushing Fists | 17% | 1% |
| Warp Stone | 23% | 7% |

### Holliday  (2 archetypes, n=4,839)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.624 | >= 0.35 |
| replication | 0.998 | >= 0.90 |
| separation | 0.716 | >= 0.45 |
| smallest share | 0.176 | >= 0.15 |

**Spirit Holliday** — 82% of players (n=3,986) — weapon 10%  vitality 25%  spirit 65%

| item | in this build | in the others |
|---|---|---|
| Tankbuster | 79% | 8% |
| Improved Spirit | 82% | 18% |
| Mystic Burst | 69% | 10% |
| Recharging Rush | 85% | 27% |
| Superior Duration | 66% | 12% |
| Boundless Spirit | 62% | 12% |
| Superior Cooldown | 50% | 4% |
| Trophy Collector | 62% | 17% |
| Extra Spirit | 91% | 49% |
| Spirit Burn | 44% | 3% |

**Gun Holliday** — 18% of players (n=853) — weapon 47%  vitality 26%  spirit 27%

| item | in this build | in the others |
|---|---|---|
| Headhunter | 75% | 13% |
| Sharpshooter | 62% | 1% |
| Swift Striker | 61% | 1% |
| Titanic Magazine | 57% | 0% |
| Headshot Booster | 79% | 24% |
| Extended Magazine | 53% | 0% |
| Fortitude | 51% | 4% |
| Extra Health | 52% | 5% |
| Bullet Resist Shredder | 47% | 1% |
| Glass Cannon | 46% | 0% |

### Venator  (2 archetypes, n=7,241)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.473 | >= 0.35 |
| replication | 0.999 | >= 0.90 |
| separation | 0.705 | >= 0.45 |
| smallest share | 0.210 | >= 0.15 |

**Tank Venator** — 21% of players (n=1,518) — weapon 31%  vitality 40%  spirit 29%

| item | in this build | in the others |
|---|---|---|
| Quicksilver Reload | 72% | 2% |
| Radiant Regeneration | 69% | 0% |
| Tesla Bullets | 69% | 1% |
| Mystic Regeneration | 68% | 0% |
| Healing Booster | 70% | 2% |
| Extra Regen | 77% | 11% |
| Healing Tempo | 64% | 2% |
| Mercurial Magnum | 60% | 1% |
| Titanic Magazine | 71% | 13% |
| Extended Magazine | 72% | 18% |

**Gun Venator** — 79% of players (n=5,723) — weapon 53%  vitality 43%  spirit 5%

| item | in this build | in the others |
|---|---|---|
| Restorative Shot | 73% | 15% |
| Vampiric Burst | 70% | 12% |
| Bullet Lifesteal | 87% | 29% |
| Weakening Headshot | 73% | 17% |
| Close Quarters | 73% | 21% |
| Fleetfoot | 42% | 7% |
| Hollow Point | 42% | 8% |
| Weighted Shots | 38% | 6% |
| Berserker | 37% | 5% |
| Silencer | 35% | 3% |

### Abrams  (2 archetypes, n=9,082)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.538 | >= 0.35 |
| replication | 0.999 | >= 0.90 |
| separation | 0.695 | >= 0.45 |
| smallest share | 0.221 | >= 0.15 |

**Spirit Abrams** — 22% of players (n=2,008) — weapon 8%  vitality 37%  spirit 54%

| item | in this build | in the others |
|---|---|---|
| Arcane Surge | 74% | 5% |
| Spirit Strike | 85% | 24% |
| Spirit Snatch | 85% | 29% |
| Superior Cooldown | 54% | 2% |
| Extra Stamina | 57% | 5% |
| Healing Booster | 75% | 27% |
| Compress Cooldown | 48% | 2% |
| Mystic Expansion | 46% | 2% |
| Healbane | 51% | 7% |
| Duration Extender | 78% | 37% |

**Tank Abrams** — 78% of players (n=7,074) — weapon 35%  vitality 47%  spirit 17%

| item | in this build | in the others |
|---|---|---|
| Close Quarters | 93% | 23% |
| Stalker | 76% | 12% |
| Hunter's Aura | 78% | 14% |
| Bullet Resist Shredder | 72% | 9% |
| Melee Charge | 98% | 46% |
| Melee Lifesteal | 64% | 22% |
| Point Blank | 51% | 11% |
| Crushing Fists | 51% | 13% |
| Phantom Strike | 58% | 20% |
| Spirit Resilience | 56% | 27% |

### Viscous  (2 archetypes, n=6,152)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.440 | >= 0.35 |
| replication | 0.999 | >= 0.90 |
| separation | 0.652 | >= 0.45 |
| smallest share | 0.412 | >= 0.15 |

**Spirit Viscous** — 59% of players (n=3,615) — weapon 11%  vitality 23%  spirit 66%

| item | in this build | in the others |
|---|---|---|
| Improved Spirit | 59% | 9% |
| Superior Cooldown | 75% | 32% |
| Tankbuster | 84% | 45% |
| Boundless Spirit | 42% | 3% |
| Spirit Burn | 39% | 3% |
| Extra Spirit | 43% | 7% |
| Transcendent Cooldown | 50% | 14% |
| Compress Cooldown | 67% | 33% |
| Mystic Shot | 50% | 17% |
| Mystic Burst | 88% | 56% |

**Spirit Viscous** — 41% of players (n=2,537) — weapon 33%  vitality 31%  spirit 36%

| item | in this build | in the others |
|---|---|---|
| Melee Charge | 83% | 17% |
| Melee Lifesteal | 80% | 17% |
| Crushing Fists | 76% | 14% |
| Lifestrike | 76% | 14% |
| Rapid Recharge | 77% | 21% |
| Ballistic Enchantment | 64% | 9% |
| Extra Charge | 83% | 31% |
| Close Quarters | 41% | 1% |
| Spirit Strike | 79% | 47% |
| Point Blank | 31% | 1% |

### Yamato  (3 archetypes, n=6,280)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.362 | >= 0.35 |
| replication | 0.999 | >= 0.90 |
| separation | 0.633 | >= 0.45 |
| smallest share | 0.206 | >= 0.15 |

**Spirit Yamato** — 35% of players (n=2,220) — weapon 8%  vitality 19%  spirit 73%

| item | in this build | in the others |
|---|---|---|
| Boundless Spirit | 73% | 28% |
| Tankbuster | 74% | 30% |
| Mystic Burst | 65% | 22% |
| Extra Spirit | 78% | 47% |
| Torment Pulse | 68% | 37% |
| Spirit Burn | 35% | 9% |
| Cold Front | 34% | 9% |
| Improved Spirit | 84% | 60% |
| Superior Cooldown | 53% | 30% |
| Mystic Vulnerability | 29% | 7% |

**Spirit Yamato** — 44% of players (n=2,766) — weapon 15%  vitality 31%  spirit 54%

| item | in this build | in the others |
|---|---|---|
| Mystic Reverb | 59% | 46% |
| Improved Spirit | 75% | 64% |
| Spirit Resilience | 30% | 22% |
| Witchmail | 15% | 7% |
| Healing Booster | 60% | 52% |
| Dispel Magic | 29% | 22% |
| Melee Lifesteal | 58% | 52% |
| Extra Regen | 56% | 49% |
| Boundless Spirit | 47% | 41% |
| Indomitable | 10% | 4% |

**Tank Yamato** — 21% of players (n=1,294) — weapon 31%  vitality 35%  spirit 34%

| item | in this build | in the others |
|---|---|---|
| Hunter's Aura | 66% | 29% |
| Bullet Resist Shredder | 33% | 6% |
| Recharging Rush | 36% | 10% |
| Stalker | 53% | 29% |
| Spiritual Overflow | 33% | 13% |
| Restorative Shot | 82% | 63% |
| Melee Lifesteal | 65% | 48% |
| Colossus | 21% | 5% |
| Grit | 37% | 21% |
| Restorative Locket | 51% | 37% |

### Ivy  (2 archetypes, n=8,208)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.508 | >= 0.35 |
| replication | 0.999 | >= 0.90 |
| separation | 0.629 | >= 0.45 |
| smallest share | 0.457 | >= 0.15 |

**Spirit Ivy** — 46% of players (n=3,754) — weapon 12%  vitality 17%  spirit 71%

| item | in this build | in the others |
|---|---|---|
| Extra Charge | 76% | 23% |
| Greater Expansion | 77% | 24% |
| Superior Duration | 57% | 8% |
| Rapid Recharge | 63% | 20% |
| Mystic Expansion | 84% | 41% |
| Trophy Collector | 54% | 11% |
| Duration Extender | 48% | 11% |
| Echo Shard | 34% | 1% |
| Superior Cooldown | 48% | 16% |
| Compress Cooldown | 46% | 14% |

**Gun Ivy** — 54% of players (n=4,454) — weapon 45%  vitality 33%  spirit 22%

| item | in this build | in the others |
|---|---|---|
| Capacitor | 80% | 17% |
| Tesla Bullets | 95% | 35% |
| Titanic Magazine | 95% | 41% |
| Extended Magazine | 92% | 39% |
| Bullet Resist Shredder | 44% | 3% |
| Active Reload | 39% | 1% |
| Siphon Bullets | 29% | 2% |
| Fleetfoot | 30% | 7% |
| Enduring Speed | 28% | 5% |
| Healing Tempo | 38% | 17% |

### Bebop  (2 archetypes, n=13,017)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.547 | >= 0.35 |
| replication | 0.999 | >= 0.90 |
| separation | 0.621 | >= 0.45 |
| smallest share | 0.417 | >= 0.15 |

**Spirit Bebop** — 58% of players (n=7,586) — weapon 2%  vitality 35%  spirit 63%

| item | in this build | in the others |
|---|---|---|
| Improved Spirit | 74% | 14% |
| Mystic Burst | 90% | 32% |
| Tankbuster | 56% | 7% |
| Boundless Spirit | 53% | 6% |
| Extra Spirit | 66% | 20% |
| Echo Shard | 45% | 1% |
| Superior Cooldown | 44% | 5% |
| Trophy Collector | 81% | 44% |
| Mystic Reverb | 38% | 2% |
| Compress Cooldown | 35% | 3% |

**Tank Bebop** — 42% of players (n=5,431) — weapon 37%  vitality 40%  spirit 22%

| item | in this build | in the others |
|---|---|---|
| Headshot Booster | 67% | 4% |
| Headhunter | 65% | 3% |
| Stalker | 48% | 5% |
| Tesla Bullets | 43% | 5% |
| Capacitor | 36% | 2% |
| Fleetfoot | 31% | 2% |
| Siphon Bullets | 29% | 0% |
| Rapid Rounds | 26% | 1% |
| Weighted Shots | 26% | 0% |
| Slowing Hex | 59% | 35% |

### Drifter  (2 archetypes, n=11,741)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.534 | >= 0.35 |
| replication | 0.999 | >= 0.90 |
| separation | 0.593 | >= 0.45 |
| smallest share | 0.423 | >= 0.15 |

**Spirit Drifter** — 42% of players (n=4,972) — weapon 20%  vitality 28%  spirit 52%

| item | in this build | in the others |
|---|---|---|
| Tankbuster | 90% | 30% |
| Spirit Snatch | 95% | 37% |
| Spirit Strike | 94% | 39% |
| Veil Walker | 74% | 25% |
| Superior Duration | 50% | 6% |
| Spirit Burn | 42% | 1% |
| Cold Front | 41% | 2% |
| Mystic Burst | 85% | 46% |
| Melee Lifesteal | 82% | 48% |
| Arctic Blast | 29% | 1% |

**Gun Drifter** — 58% of players (n=6,769) — weapon 52%  vitality 37%  spirit 11%

| item | in this build | in the others |
|---|---|---|
| Kinetic Dash | 71% | 15% |
| Burst Fire | 65% | 9% |
| Close Quarters | 57% | 8% |
| Point Blank | 52% | 6% |
| Rapid Rounds | 52% | 8% |
| Extra Stamina | 54% | 11% |
| Fortitude | 46% | 10% |
| Lucky Shot | 30% | 2% |
| Bullet Lifesteal | 33% | 5% |
| Vampiric Burst | 31% | 3% |

### Kelvin  (3 archetypes, n=5,400)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.469 | >= 0.35 |
| replication | 0.998 | >= 0.90 |
| separation | 0.550 | >= 0.45 |
| smallest share | 0.160 | >= 0.15 |

**Spirit Kelvin** — 44% of players (n=2,375) — weapon 1%  vitality 18%  spirit 81%

| item | in this build | in the others |
|---|---|---|
| Escalating Exposure | 79% | 42% |
| Mystic Vulnerability | 79% | 46% |
| Boundless Spirit | 75% | 51% |
| Mystic Expansion | 79% | 55% |
| Greater Expansion | 66% | 45% |
| Duration Extender | 43% | 22% |
| Spirit Burn | 41% | 21% |
| Superior Cooldown | 75% | 57% |
| Superior Duration | 47% | 29% |
| Extra Spirit | 84% | 67% |

**Spirit Kelvin** — 40% of players (n=2,160) — weapon 2%  vitality 31%  spirit 67%

| item | in this build | in the others |
|---|---|---|
| Infuser | 19% | 7% |
| Boundless Spirit | 66% | 55% |
| Escalating Exposure | 61% | 51% |
| Transcendent Cooldown | 30% | 21% |
| Superior Cooldown | 69% | 60% |
| Greater Expansion | 57% | 49% |
| Superior Duration | 40% | 32% |
| Improved Spirit | 81% | 73% |
| Mystic Vulnerability | 62% | 55% |
| Extra Spirit | 77% | 70% |

**Spirit Kelvin** — 16% of players (n=865) — weapon 7%  vitality 46%  spirit 47%

| item | in this build | in the others |
|---|---|---|
| Rescue Beam | 46% | 16% |
| Healing Tempo | 42% | 15% |
| Healing Rite | 44% | 18% |
| Guardian Ward | 31% | 6% |
| Divine Barrier | 24% | 3% |
| Grit | 25% | 7% |
| Opening Rounds | 25% | 9% |
| High-Velocity Rounds | 27% | 12% |
| Healing Booster | 83% | 68% |
| Juggernaut | 17% | 7% |

### Infernus  (3 archetypes, n=11,884)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.356 | >= 0.35 |
| replication | 0.999 | >= 0.90 |
| separation | 0.508 | >= 0.45 |
| smallest share | 0.225 | >= 0.15 |

**Spirit Infernus** — 23% of players (n=2,677) — weapon 20%  vitality 25%  spirit 56%

| item | in this build | in the others |
|---|---|---|
| Rapid Recharge | 72% | 44% |
| Extra Charge | 63% | 37% |
| Escalating Exposure | 83% | 62% |
| Boundless Spirit | 62% | 44% |
| Spirit Burn | 21% | 4% |
| Healbane | 54% | 40% |
| Radiant Regeneration | 20% | 7% |
| Mystic Slow | 14% | 3% |
| Mystic Regeneration | 18% | 7% |
| Infuser | 17% | 8% |

**Gun Infernus** — 49% of players (n=5,797) — weapon 44%  vitality 19%  spirit 37%

| item | in this build | in the others |
|---|---|---|
| Ricochet | 69% | 29% |
| Toxic Bullets | 84% | 47% |
| Swift Striker | 80% | 50% |
| Rapid Rounds | 90% | 61% |
| Spiritual Overflow | 77% | 51% |
| Titanic Magazine | 88% | 66% |
| Extended Magazine | 86% | 66% |
| Spirit Shredder Bullets | 35% | 15% |
| Spirit Rend | 28% | 11% |
| Duration Extender | 78% | 66% |

**Tank Infernus** — 29% of players (n=3,410) — weapon 26%  vitality 39%  spirit 35%

| item | in this build | in the others |
|---|---|---|
| Indomitable | 26% | 7% |
| Extra Regen | 41% | 26% |
| Debuff Reducer | 20% | 6% |
| Unstoppable | 18% | 4% |
| Reactive Barrier | 24% | 11% |
| Juggernaut | 19% | 5% |
| Dispel Magic | 47% | 34% |
| Grit | 26% | 12% |
| Leech | 29% | 16% |
| Healbane | 53% | 41% |

### Victor  (2 archetypes, n=8,310)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.477 | >= 0.35 |
| replication | 0.999 | >= 0.90 |
| separation | 0.487 | >= 0.45 |
| smallest share | 0.266 | >= 0.15 |

**Spirit Victor** — 73% of players (n=6,102) — weapon 3%  vitality 37%  spirit 61%

| item | in this build | in the others |
|---|---|---|
| Escalating Exposure | 92% | 44% |
| Greater Expansion | 76% | 31% |
| Superior Cooldown | 58% | 18% |
| Mystic Vulnerability | 90% | 51% |
| Improved Spirit | 86% | 47% |
| Mystic Expansion | 82% | 44% |
| Transcendent Cooldown | 42% | 6% |
| Torment Pulse | 83% | 47% |
| Compress Cooldown | 53% | 17% |
| Infuser | 87% | 52% |

**Tank Victor** — 27% of players (n=2,208) — weapon 18%  vitality 47%  spirit 35%

| item | in this build | in the others |
|---|---|---|
| Opening Rounds | 45% | 7% |
| High-Velocity Rounds | 42% | 6% |
| Quicksilver Reload | 34% | 2% |
| Mercurial Magnum | 31% | 1% |
| Fleetfoot | 29% | 6% |
| Extended Magazine | 23% | 1% |
| Titanic Magazine | 23% | 0% |
| Spiritual Overflow | 24% | 1% |
| Swift Striker | 22% | 0% |
| Rapid Rounds | 20% | 0% |

### Calico  (2 archetypes, n=8,038)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.551 | >= 0.35 |
| replication | 0.999 | >= 0.90 |
| separation | 0.485 | >= 0.45 |
| smallest share | 0.197 | >= 0.15 |

**Spirit Calico** — 80% of players (n=6,451) — weapon 10%  vitality 19%  spirit 71%

| item | in this build | in the others |
|---|---|---|
| Boundless Spirit | 66% | 18% |
| Improved Spirit | 69% | 25% |
| Mystic Vulnerability | 55% | 15% |
| Arctic Blast | 97% | 58% |
| Scourge | 43% | 10% |
| Spirit Burn | 35% | 7% |
| Extra Spirit | 46% | 19% |
| Superior Cooldown | 45% | 19% |
| Escalating Exposure | 31% | 5% |
| Cold Front | 99% | 78% |

**Spirit Calico** — 20% of players (n=1,587) — weapon 26%  vitality 34%  spirit 40%

| item | in this build | in the others |
|---|---|---|
| Enduring Speed | 51% | 28% |
| Lifestrike | 30% | 8% |
| Close Quarters | 26% | 3% |
| Point Blank | 24% | 2% |
| Melee Charge | 25% | 3% |
| Crushing Fists | 19% | 1% |
| Extra Health | 24% | 7% |
| Titanic Magazine | 15% | 0% |
| Fortitude | 21% | 6% |
| Split Shot | 13% | 0% |

### Silver  (3 archetypes, n=3,764)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.369 | >= 0.35 |
| replication | 0.996 | >= 0.90 |
| separation | 0.477 | >= 0.45 |
| smallest share | 0.248 | >= 0.15 |

**Tank Silver** — 25% of players (n=935) — weapon 30%  vitality 39%  spirit 31%

| item | in this build | in the others |
|---|---|---|
| Spirit Snatch | 56% | 16% |
| Tankbuster | 55% | 20% |
| Spirit Strike | 43% | 15% |
| Mystic Burst | 37% | 14% |
| Cold Front | 35% | 15% |
| Arctic Blast | 15% | 2% |
| Veil Walker | 29% | 16% |
| Slowing Hex | 41% | 28% |
| Superior Duration | 31% | 21% |
| Superior Cooldown | 14% | 4% |

**Tank Silver** — 44% of players (n=1,671) — weapon 29%  vitality 60%  spirit 12%

| item | in this build | in the others |
|---|---|---|
| Unstoppable | 51% | 22% |
| Grit | 51% | 29% |
| Spirit Shielding | 52% | 30% |
| Debuff Reducer | 49% | 32% |
| Extra Health | 38% | 22% |
| Phantom Strike | 26% | 10% |
| Inhibitor | 25% | 10% |
| Warp Stone | 27% | 15% |
| Spirit Resilience | 49% | 37% |
| Veil Walker | 28% | 16% |

**Gun Silver** — 31% of players (n=1,158) — weapon 50%  vitality 41%  spirit 9%

| item | in this build | in the others |
|---|---|---|
| Close Quarters | 79% | 45% |
| Slowing Bullets | 66% | 34% |
| Point Blank | 55% | 24% |
| Weighted Shots | 70% | 40% |
| Frenzy | 39% | 11% |
| Silencer | 26% | 13% |
| Berserker | 63% | 54% |
| Extra Stamina | 47% | 39% |
| Spirit Resilience | 46% | 38% |
| Stamina Mastery | 31% | 23% |

### Apollo  (2 archetypes, n=5,178)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.580 | >= 0.35 |
| replication | 0.996 | >= 0.90 |
| separation | 0.474 | >= 0.45 |
| smallest share | 0.177 | >= 0.15 |

**Spirit Apollo** — 82% of players (n=4,264) — weapon 1%  vitality 27%  spirit 72%

| item | in this build | in the others |
|---|---|---|
| Tankbuster | 86% | 39% |
| Boundless Spirit | 88% | 41% |
| Mystic Expansion | 90% | 46% |
| Superior Cooldown | 69% | 27% |
| Mystic Burst | 96% | 59% |
| Greater Expansion | 59% | 22% |
| Improved Spirit | 91% | 58% |
| Extra Spirit | 87% | 54% |
| Cold Front | 52% | 21% |
| Spirit Burn | 41% | 11% |

**Tank Apollo** — 18% of players (n=914) — weapon 17%  vitality 45%  spirit 38%

| item | in this build | in the others |
|---|---|---|
| Close Quarters | 40% | 2% |
| Melee Charge | 49% | 12% |
| Melee Lifesteal | 38% | 2% |
| Point Blank | 32% | 1% |
| Lifestrike | 29% | 1% |
| Witchmail | 34% | 10% |
| Spirit Resilience | 42% | 18% |
| Crushing Fists | 24% | 1% |
| Stalker | 23% | 1% |
| Hunter's Aura | 19% | 1% |

### Celeste  (2 archetypes, n=6,931)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.395 | >= 0.35 |
| replication | 0.999 | >= 0.90 |
| separation | 0.459 | >= 0.45 |
| smallest share | 0.444 | >= 0.15 |

**Spirit Celeste** — 44% of players (n=3,078) — weapon 8%  vitality 28%  spirit 64%

| item | in this build | in the others |
|---|---|---|
| Superior Cooldown | 50% | 9% |
| Improved Spirit | 46% | 11% |
| Extra Spirit | 42% | 12% |
| Boundless Spirit | 36% | 7% |
| Escalating Exposure | 61% | 33% |
| Compress Cooldown | 31% | 5% |
| Mystic Vulnerability | 59% | 35% |
| Stamina Mastery | 52% | 30% |
| Transcendent Cooldown | 24% | 2% |
| Extra Stamina | 46% | 29% |

**Spirit Celeste** — 56% of players (n=3,853) — weapon 21%  vitality 39%  spirit 40%

| item | in this build | in the others |
|---|---|---|
| Spiritual Overflow | 59% | 13% |
| Witchmail | 72% | 35% |
| Opening Rounds | 79% | 44% |
| Spirit Lifesteal | 60% | 28% |
| Suppressor | 60% | 32% |
| Spirit Shielding | 56% | 33% |
| Spellslinger | 36% | 13% |
| Restorative Locket | 71% | 55% |
| Healing Booster | 90% | 74% |
| Extra Regen | 93% | 79% |

### Graves  (2 archetypes, n=8,247)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.490 | >= 0.35 |
| replication | 0.999 | >= 0.90 |
| separation | 0.454 | >= 0.45 |
| smallest share | 0.375 | >= 0.15 |

**Spirit Graves** — 63% of players (n=5,157) — weapon 15%  vitality 20%  spirit 65%

| item | in this build | in the others |
|---|---|---|
| Echo Shard | 62% | 17% |
| Superior Duration | 62% | 19% |
| Compress Cooldown | 50% | 11% |
| Superior Cooldown | 48% | 10% |
| Duration Extender | 54% | 17% |
| Boundless Spirit | 62% | 26% |
| Arcane Surge | 66% | 33% |
| Transcendent Cooldown | 34% | 4% |
| Improved Spirit | 84% | 54% |
| Heroic Aura | 70% | 42% |

**Gun Graves** — 37% of players (n=3,090) — weapon 38%  vitality 33%  spirit 29%

| item | in this build | in the others |
|---|---|---|
| Tesla Bullets | 45% | 4% |
| Ricochet | 42% | 4% |
| Toxic Bullets | 74% | 40% |
| Surge of Power | 36% | 6% |
| Active Reload | 28% | 1% |
| Spiritual Overflow | 35% | 12% |
| Stamina Mastery | 58% | 36% |
| Spirit Shielding | 37% | 18% |
| Spirit Lifesteal | 53% | 35% |
| Split Shot | 20% | 3% |

### Vindicta  (2 archetypes, n=8,652)

| criterion | value | threshold |
|---|---|---|
| silhouette | 0.451 | >= 0.35 |
| replication | 0.999 | >= 0.90 |
| separation | 0.451 | >= 0.45 |
| smallest share | 0.259 | >= 0.15 |

**Spirit Vindicta** — 26% of players (n=2,238) — weapon 30%  vitality 23%  spirit 47%

| item | in this build | in the others |
|---|---|---|
| Boundless Spirit | 49% | 7% |
| Extra Spirit | 79% | 37% |
| Improved Spirit | 74% | 36% |
| Mystic Burst | 42% | 7% |
| Mercurial Magnum | 55% | 28% |
| Mystic Vulnerability | 22% | 1% |
| Tankbuster | 21% | 1% |
| Surge of Power | 22% | 4% |
| Trophy Collector | 46% | 29% |
| Alchemical Fire | 19% | 2% |

**Gun Vindicta** — 74% of players (n=6,414) — weapon 53%  vitality 27%  spirit 20%

| item | in this build | in the others |
|---|---|---|
| Titanic Magazine | 71% | 26% |
| Spiritual Overflow | 68% | 30% |
| Swift Striker | 89% | 53% |
| Burst Fire | 83% | 48% |
| Long Range | 93% | 63% |
| Spirit Lifesteal | 57% | 27% |
| Extended Magazine | 40% | 12% |
| Sharpshooter | 94% | 69% |
| Enduring Speed | 50% | 25% |
| Blood Tribute | 24% | 6% |

## Heroes that did not split

| hero | n | why |
|---|---|---|
| Billy | 8,201 | single archetype: best k=2 fails silhouette, separation |
| Dynamo | 7,828 | single archetype: best k=2 fails separation |
| Grey Talon | 4,201 | single archetype: best k=2 fails smallest share |
| Haze | 11,825 | single archetype: best k=2 fails separation |
| Mina | 9,691 | single archetype: best k=2 fails separation |
| Mirage | 3,397 | single archetype: best k=2 fails silhouette, separation |
| Mo & Krill | 9,553 | single archetype: best k=2 fails separation |
| Paige | 8,994 | single archetype: best k=2 fails separation |
| Paradox | 9,477 | single archetype: best k=2 fails separation |
| Pocket | 7,085 | single archetype: best k=2 fails separation |
| Rem | 8,096 | single archetype: best k=2 fails separation |
| Seven | 9,575 | single archetype: best k=2 fails separation |
| Shiv | 7,631 | single archetype: best k=2 fails separation |
| The Doorman | 4,492 | single archetype: best k=2 fails separation |
| Vyper | 4,515 | single archetype: best k=2 fails silhouette, separation |
| Warden | 10,626 | single archetype: best k=2 fails silhouette, separation |
| Wraith | 10,934 | single archetype: best k=2 fails separation |
