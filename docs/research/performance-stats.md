# The discarded performance stats: what they can describe

Research for #17. Establishes which per-player performance measures separate
one hero's [[archetype]]s from each other, how to normalise them, what is wrong
with the source data, and what the pipeline change costs. It does not implement
anything.

Every number here was measured against the 125 cached pages that
`ingest.cached_pages()` enumerates — **299,999 players**, joined to
`data/processed/archetypes.parquet` on `(match_id, player_slot)`. No API pull
was made.

## Summary

The stats are real, clean, and discriminating — but almost none of the obvious
ones work.

- **Gun usage is the axis that separates archetypes.** `hero_bullets_hit`,
  `shots_hit` and `shots_missed` separate a hero's archetypes roughly twice as
  well as anything else. Kill-source composition (`ability_kills` vs
  `bullet_kills` as a share of kills) is second, healing third.
- **`kills`, `deaths`, `net_worth` and the gold breakdown do not
  discriminate.** These are the measures a description would reach for first,
  and they are the ones to leave out.
- **Normalise per soul**, not per minute and not against the match median.
- **The data is far cleaner than `net_worth_at_buy` was.** No missing fields,
  no unsorted arrays, no final-value corruption. One real defect: `net_worth`
  decreases somewhere in 0.52% of series.
- **A new player-grained table, not an allowlist extension.**
  `purchases.parquet` repeats each player 17.2 times.

## 1. Which measures discriminate

The crux is within-hero separation. A measure that differs across heroes but
says the same thing about both Ivy builds is useless for the description, so
every statistic below is computed **within a hero** and then pooled across the
28 heroes that split — never pooled first.

Separation is the absolute difference in archetype means over the within-hero
pooled SD (a standardised mean difference). Following CONTEXT.md's rule that
*every pair* of a hero's archetypes must be distinguishable, the headline is
the **minimum** pairwise SMD, not the widest pair.

Per soul, over 28 multi-archetype heroes:

| Measure | min-pair SMD | max-pair SMD |
|---|---|---|
| `hero_bullets_hit` | **0.429** | 0.729 |
| `shots_hit` | **0.426** | 0.712 |
| `hero_bullets_hit_crit` | 0.380 | 0.628 |
| `shots_missed` | 0.358 | 0.616 |
| `player_healing` | 0.281 | 0.526 |
| `player_barriering` | 0.281 | 0.353 |
| `bullet_kills` | 0.279 | 0.505 |
| `self_healing` | 0.273 | 0.536 |
| `damage_mitigated` | 0.246 | 0.373 |
| `ability_kills` | 0.247 | 0.404 |
| `player_damage` | 0.152 | 0.250 |
| `deaths` | 0.139 | 0.194 |
| `melee_kills` | 0.131 | 0.194 |

Scale-free ratios, which need no normalisation at all:

| Measure | min-pair SMD | max-pair SMD |
|---|---|---|
| `ability_kills / kills` | **0.321** | 0.551 |
| `bullet_kills / kills` | **0.292** | 0.534 |
| `damage_mitigated / damage_taken` | 0.235 | 0.382 |
| `headshot_kills / kills` | 0.164 | 0.291 |
| `boss+neutral / all damage` | 0.162 | 0.300 |
| `teammate_healing / player_healing` | 0.101 | 0.187 |
| `shots_hit / (hit+missed)` (accuracy) | 0.109 | 0.179 |

### What does not discriminate

Worth stating plainly, because these are the intuitive choices:

- **`kills`, `deaths`, `assists`** — 0.14 min-pair and below. Both Ivy builds
  die about as often.
- **`net_worth`** — 0.201 per minute, 0.132 against the match median. Souls
  measure how the match went, not which build was run.
- **The whole gold breakdown** — `gold_player`, `gold_lane_creep`,
  `gold_boss`, `gold_treasure` all sit at 0.09–0.16 against the match median,
  the weakest block measured.
- **Raw accuracy** (0.109). Hit *rate* is a skill measure; shots *fired* is a
  build measure. Only the second separates archetypes.

### Why this is not circular

The concern is that a description derived from performance merely restates the
item list the [[build family]] clustering already used. It does not: these are
behavioural counters the clustering never saw, and they recover the archetype
ordering independently.

Bullets hit per 1,000 souls, and ability kills as a share of kills:

| Hero | Archetype | n | bullets/1k souls | ability-kill share |
|---|---|---|---|---|
| Ivy | Spirit Ivy | 2,751 | 11.5 | 0.670 |
| Ivy | Ivy | 2,726 | 22.8 | 0.482 |
| Ivy | Gun Ivy | 2,731 | **30.3** | **0.376** |
| Paradox | Spirit Paradox | 1,239 | 13.1 | 0.598 |
| Paradox | Burn Gun Paradox | 4,401 | 15.5 | 0.448 |
| Paradox | Sharpshooter Gun Paradox | 3,837 | **18.8** | **0.393** |
| Lash | Spirit Lash | 4,722 | 7.3 | 0.632 |
| Lash | Hybrid-Tank Lash | 3,328 | 8.0 | 0.571 |
| Lash | Gun Lash | 4,901 | **12.5** | **0.385** |
| Kelvin | Spirit Kelvin | 3,436 | 2.5 | 0.773 |
| Kelvin | Support Kelvin | 1,964 | 3.1 | 0.669 |

The ordering is monotone in the family label every time, and the labels were
assigned from souls-weighted family shares, not from any of these counters.
Gun Ivy fires 2.6x the bullets of Spirit Ivy per soul spent.

### Coverage, and where it fails

Across all **46 archetype pairs** of the 28 split heroes, taking the best of
eight candidate measures:

| Threshold | Pairs separated |
|---|---|
| ≥ 0.20 SD | 44 / 46 (95.7%) |
| ≥ 0.35 SD | 41 / 46 (89.1%) |
| ≥ 0.50 SD | 35 / 46 (76.1%) |

Which measure wins the pair: `bullets_per_soul` 17, `mitigated_per_soul` 9,
`selfheal_per_soul` 9, `shots_missed_per_soul` 6, the rest 5.

The two pairs below 0.2 SD are **Lady Geist 0v1** (0.135) and **Graves 0v1**
(0.175) — in both cases the two same-family spirit builds. That is the same
boundary CONTEXT.md already documents: where the family label collides, the
name takes a second term. Performance describes what a build *does*, so two
builds that do the same thing by different routes are exactly the case it
cannot speak to. Measured, Lady Geist's two spirit archetypes sit at 3.362 and
3.345 bullets/1k souls — indistinguishable, and honestly so.

**The 10 single-archetype heroes get no within-hero comparison at all.** For
Wraith and Pocket the description has to be phrased against the hero
population, not against a sibling archetype.

## 2. Normalisation: per soul

Four denominators were measured against the same min-pair criterion. Best
measure in each:

| Normalisation | Best min-pair SMD |
|---|---|
| **per soul** (`/ final net_worth`) | **0.429** |
| raw (match total) | 0.384 |
| per minute (`/ duration_s`) | 0.389 |
| vs match median | 0.302 |

Per soul wins on all four leading measures. The reasoning behind the number:
souls are what a build spends, so "bullets landed per soul spent" asks what the
player bought their souls *for* — which is the question an archetype answers.
Per minute is nearly as good and defensible; **against the match median is
actively worse** and should not be used, which is the one genuinely surprising
result here, since `nw_vs_match_median` is the established precedent in
`dataset.py`. It fails because it divides out the between-archetype signal:
every player in the match is compared to a median that the archetypes
themselves move.

Ratio measures (`ability_kills / kills`) need no denominator and are the
easiest to state to a player.

### The denominator must not be snapshot count

The stats series is **not** sampled every 180s as the ticket assumed. Measured:

- The first snapshot is always at 180s (960/960 players checked).
- The cadence is **per match**: 180s for matches under ~2,400s, 300s above.
  Measured over 200 matches: 141 at 180s (duration median 2,061s), 59 at 300s
  (duration median 2,653s).
- Snapshot count is capped around 12 and the interval stretches to fit. Over
  299,999 players: median 10 snapshots, range 1–18, against a duration range of
  121–4,636s.

So averaging over snapshots would silently weight long matches differently.
Use `duration_s` or `net_worth`, never `n_snapshots`.

## 3. Source-data defects

This project has been burned by corrupt `net_worth_at_buy`, unsorted item
arrays and a missing per-player `won`. All three were checked. The verdict:
**these stats are clean**, with one exception.

| Check | Result |
|---|---|
| Players with no `stats` array | **0** / 299,999 |
| Unsorted `time_stamp_s` | **0** / 299,999 |
| Duplicate timestamps | **0** / 299,999 |
| All-zero final snapshot | **11** / 299,999 (0.004%) |
| Field missing from final snapshot | **0** for all 38 fields |
| Last snapshot `== duration_s` | **299,999 / 299,999 (100%)** |

That last row is the important one. **The final snapshot is a true match-end
total.** Unlike `net_worth_at_buy`, nothing needs reconstructing — read the
last element of the sorted series and it is correct.

### The one real defect

`net_worth` **decreases** somewhere in its series for **1,563 players
(0.521%)**. Souls spent do not reduce net worth in this game, so a decreasing
series is a source error. Every other cumulative counter is effectively
monotone: `player_damage` 3 players (0.001%), `player_damage_taken` 1 player,
and **exactly zero** for the other 35 fields.

Since `net_worth` is the proposed denominator, this matters: drop or clamp
those 1,563 players rather than dividing by a corrupt value.

### Two apparent defects that are not defects

**Flat series are genuine, not corruption.** The "every snapshot equals the
final value" pattern — the `net_worth_at_buy` signature — appears for `denies`
(8.03%), `gold_denied` (3.49%), `melee_kills` (2.91%) and `bullet_kills`
(1.56%). These are low-activity players, not corrupt rows: `melee_kills` has a
median of 0 and is zero for 57.9% of players, so a flat non-zero series is a
player who scored their one melee kill before 180s. This is the same reasoning
CONTEXT.md applies to a low [[imbue]] rate — a build fact, not missing data.

**Top-level counters disagree with the final snapshot, and the snapshot is the
one to trust:**

| Field | Top-level == final snapshot |
|---|---|
| `assists` | 299,855 / 299,999 (99.95%) |
| `denies` | 299,807 / 299,999 (99.94%) |
| `net_worth` | 210,174 / 299,999 (70.06%) |
| `deaths` | 203,978 / 299,999 (67.99%) |
| `kills` | 194,163 / 299,999 (64.72%) |

Top-level `kills` disagrees with the series for over a third of players. Read
the series, not `player["kills"]`.

### Gauges are not counters

Three fields in the same series are **gauges**, not cumulative counters, and go
down legitimately: `max_health` (non-monotone for 17.3% of players),
`tech_power` (27.5%), `weapon_power` (34.0%). Measured over 480 players. They
are readable as mid-match state but a "final value" of them means current
value, not a total. `level` and `ability_points` are monotone (0%).

## 4. Pipeline shape: a new table

**A new player-grained processed table, not an allowlist extension.**

The shape mismatch the ticket flags is decisive, measured:

- `purchases.parquet`: **5,095,598 rows**, 189.1 MB, covering **296,332**
  distinct player-matches — **17.2 purchase rows per player**.
- `archetypes.parquet`: 296,332 rows, one per player-match, no duplicates.

Extending `PURCHASE_COLUMNS` would replicate every performance stat 17.2 times.
For ~20 float columns that is roughly 100M redundant values on a table already
at 189 MB, and it would put a player-grained fact on a purchase-grained table
where any naive `groupby` over it double-counts by a factor of 17.

The natural shape is `data/processed/player_stats.parquet`, keyed
`(match_id, player_slot)` — the same key `archetypes.parquet` already uses, so
it joins 1:1 with no fan-out. Roughly 296k rows against 20-ish columns.

The extraction is a single pass over the cached pages reading the last element
of each player's sorted `stats` array; it needs no new API call and no change
to `features.networth_series`, which reads the same array for a different
purpose. Suggested caveats to carry into implementation: drop the 1,563
non-monotone `net_worth` players, prefer the series over top-level counters,
and store raw totals plus `duration_s` so the denominator stays a downstream
choice rather than being baked in.

## Measures worth carrying

For a one-line "play this if…" description, in order of measured value:

1. `hero_bullets_hit` per soul — the gun/spirit axis, the single strongest.
2. `ability_kills / kills` and `bullet_kills / kills` — scale-free, and the
   easiest to phrase to a player.
3. `shots_missed` per soul — separates high-volume from selective shooters,
   and is not redundant with (1).
4. `player_healing` and `self_healing` per soul — carries support and sustain.
5. `damage_mitigated / player_damage_taken` — carries tank; wins 9 of 46 pairs
   and is the only measure that speaks for several tank pairs.

Leave out kills, deaths, assists, net worth, the gold breakdown, raw accuracy
and `player_damage`. They are the intuitive picks and they do not separate.

## Reproducing

Scripts were run from the project venv against the cached pages only; no
pipeline code was modified. The scan is one pass over the 125 cached pages
(~10 min), joining to `data/processed/archetypes.parquet` on
`(match_id, player_slot)` and aggregating to `(hero_id, archetype_id)`.
