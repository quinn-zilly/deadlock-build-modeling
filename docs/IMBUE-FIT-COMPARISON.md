# Does imbue belong in the archetype clustering?

Three fits over the same purchase table in the same run. `families` is
build-family shares alone, `imbue` is the rejected first attempt with
`has_imbue` and depth in the block, `conditional` is direction only
with non-imbuers placed at their hero's mean.

The separating item is the item carrying each fit's weakest cluster
pair -- the claim behind the separation score. An asterisk marks one
of the nine imbueable items. `split` is what the conditional block did
to that hero against build families alone.

| hero | k families | k imbue | k conditional | split | separating item (families) | separating item (conditional) |
|---|---|---|---|---|---|---|
| Abrams | 2 | 3 | 3 | gained | Close Quarters | Close Quarters |
| Apollo | 1 | 3 | 2 | gained | -- | Mystic Reverb \* |
| Bebop | 2 | 3 | 2 | -- | Headshot Booster | Compress Cooldown \* |
| Billy | 2 | 2 | 1 | **lost** | Rapid Recharge | -- |
| Calico | 1 | 2 | 1 | -- | -- | -- |
| Celeste | 2 | 3 | 2 | -- | Spellslinger | Compress Cooldown \* |
| Drifter | 3 | 3 | 1 | **lost** | Kinetic Dash | -- |
| Dynamo | 2 | 3 | 3 | gained | Refresher | Duration Extender \* |
| Graves | 3 | 3 | 3 | -- | Tesla Bullets | Surge of Power \* |
| Grey Talon | 3 | 3 | 3 | -- | Sharpshooter | Compress Cooldown \* |
| Haze | 3 | 3 | 1 | **lost** | Unstoppable | -- |
| Holliday | 3 | 3 | 2 | **lost** | Sharpshooter | Duration Extender \* |
| Infernus | 2 | 3 | 2 | -- | Ricochet | Quicksilver Reload \* |
| Ivy | 3 | 3 | 3 | -- | Active Reload | Echo Shard \* |
| Kelvin | 2 | 1 | 2 | -- | Escalating Exposure | Mystic Reverb \* |
| Lady Geist | 3 | 3 | 3 | -- | Mystic Reverb \* | Mystic Reverb \* |
| Lash | 3 | 3 | 3 | -- | Unstoppable | Quicksilver Reload \* |
| McGinnis | 2 | 3 | 3 | gained | Mystic Vulnerability | Arcane Surge |
| Mina | 3 | 3 | 3 | -- | Mercurial Magnum \* | Mystic Expansion \* |
| Mirage | 2 | 3 | 2 | -- | Escalating Exposure | Quicksilver Reload \* |
| Mo & Krill | 1 | 2 | 2 | gained | -- | Mystic Expansion \* |
| Paige | 2 | 2 | 2 | -- | Rapid Recharge | Surge of Power \* |
| Paradox | 3 | 3 | 2 | **lost** | Spirit Burn | Mystic Expansion \* |
| Pocket | 1 | 1 | 1 | -- | -- | -- |
| Rem | 2 | 3 | 3 | gained | Superior Cooldown | Mystic Reverb \* |
| Seven | 3 | 3 | 3 | -- | Mercurial Magnum \* | Mercurial Magnum \* |
| Shiv | 2 | 3 | 3 | gained | Swift Striker | Mercurial Magnum \* |
| Silver | 2 | 3 | 2 | -- | Unstoppable | Unstoppable |
| Sinclair | 2 | 1 | 3 | gained | Rapid Recharge | Rapid Recharge |
| The Doorman | 1 | 2 | 2 | gained | -- | Mystic Reverb \* |
| Venator | 2 | 2 | 1 | **lost** | Rapid Recharge | -- |
| Victor | 2 | 3 | 3 | gained | Mercurial Magnum \* | Fleetfoot |
| Vindicta | 1 | 3 | 1 | -- | -- | -- |
| Viscous | 2 | 3 | 2 | -- | Melee Charge | Melee Lifesteal |
| Vyper | 2 | 1 | 1 | **lost** | Unstoppable | -- |
| Warden | 2 | 1 | 1 | **lost** | Boundless Spirit | -- |
| Wraith | 1 | 2 | 1 | -- | -- | -- |
| Yamato | 2 | 3 | 2 | -- | Mystic Reverb \* | Compress Cooldown \* |

## Verdict

- Splits gained against build families alone: Abrams, Apollo, Dynamo, McGinnis, Mo & Krill, Rem, Shiv, Sinclair, The Doorman, Victor
- Splits **lost** against build families alone: Billy, Drifter, Haze, Holliday, Paradox, Venator, Vyper, Warden
- Splits lost against the rejected first attempt: Apollo, Bebop, Billy, Calico, Celeste, Drifter, Haze, Holliday, Infernus, Mirage, Paradox, Silver, Venator, Vindicta, Viscous, Wraith, Yamato
- Separating item is imbueable: 5 of 31 split heroes (16%) under build families alone, 27 of 33 (82%) under the first attempt, 22 of 28 (79%) under the conditional block. The build-family figure is the control: it says whether nine items out of 173 carry these splits because of the heroes or because of the block.

**No hero loses a split: NO. Concentration drops by at least half: NO.**

The pre-committed rule removes imbue from the clustering. It serves naming and advice only.
