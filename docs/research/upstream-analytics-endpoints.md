# Four upstream analytics endpoints as cross-checks

Answers [#51](https://github.com/quinn-zilly/deadlock-build-modeling/issues/51):
what the four `/v1/analytics` endpoints contain, whether they carry counts,
whether our population can be reproduced through their filters, and what each
can honestly be used for.

**Short answer.** All four return integer counts (`wins`, `losses`, `matches`,
and usually `players`), never bare rates. On identical input, three of them
compute exactly what we compute. Over 208 matches that both sides hold in
full, every item-flow node, every item-flow edge, every item pair, and every
Wraith and Ivy ability sequence matched our raw data count for count.

The training population itself can't be reproduced, for two reasons:

1. The endpoints filter by `match_id` range, and our pull is not a whole
   range. Upstream now holds 31,621 Ranked Normal matches in our range
   (105,284,527 to 105,717,970). We pulled 24,999 of them on 2026-09-14,
   because the rest hadn't arrived yet. The late arrivals are a lower-badge
   population, with a median badge of 44 against our 56.
2. The endpoints count every player, and we count only in-scope players.
   No filter drops the `NotScored` players, who are 1.2% of our pull.

So for the shipped model, every number from these endpoints is a **smell test
only**, from a different population. None of them should replace local
modeling. `hero-build-stats` is of no use to this project. The one change
worth making is to how we pull. If the next pull takes a closed, settled
`match_id` range, then `item-flow-stats`, `item-permutation-stats` and
`ability-order-stats` become exact external checks on raw counts, short only
the not-in-scope players.

All numbers below come from calls made on 2026-09-25 against the local tables
from the 2026-09-14 pull. Numbers computed over the upstream superset and
numbers from our pull are two different populations, and aren't a comparison
in this project's sense. Where both appear, the gap is reported as a gap.

## Sources

- OpenAPI spec: `openapi.json` in
  [deadlock-api/openapi-clients](https://github.com/deadlock-api/openapi-clients),
  branch `master`, commit `c20389b`.
- Server source: [deadlock-api/deadlock-api](https://github.com/deadlock-api/deadlock-api),
  branch `master`, commit `ed26c94`, `api/src/routes/v1/analytics/`:
  `ability_order_stats.rs`, `item_flow_stats.rs`,
  `item_permutation_stats.rs`, `hero_build_stats.rs`, and
  `common_filters.rs`. Each handler builds one ClickHouse query over
  `match_player`. Line numbers below refer to that commit.
- Live calls to `https://api.deadlock-api.com/v1/analytics/*` using curl.
  Upstream table checks went through the MCP SQL server
  (`/v1/mcp`, `execute_query`), and the current match list came from
  `/v1/matches/metadata` with no include flags.
- Our population: `scripts/pull_data.py`, `src/deadlock/ingest.py`
  (`BASE_PARAMS`), `src/deadlock/features.py` (`in_scope`,
  `clean_purchases`, `phase_of`), and `src/deadlock/sequence.py`
  (`row_weights`). The local tables are `data/processed/purchases.parquet`,
  `abilities.parquet`, the raw pages in `data/raw/matches/`, and
  `data/builds/Wraith_0.json`.

## Our population

Every local table comes from one pull:

| Filter | Value | Where |
|---|---|---|
| `match_mode` | Ranked | `ingest.BASE_PARAMS` |
| `game_mode` | normal | `ingest.BASE_PARAMS` |
| start time | on or after 2026-08-22 (`PATCH_START`) | `pull_data.py` |
| which matches | the newest 25,000 the metadata endpoint returned on 2026-09-14, paged by `match_id` descending | `ingest.pull_matches` |
| `match_id` | 105,284,527 to 105,717,970, 24,999 distinct | `purchases.parquet` |
| start time, observed | 2026-09-12 20:03 to 2026-09-15 00:43 UTC | MCP `match_player` |
| players | in scope: known outcome, and bought at least one item. 296,478 players. | `features.in_scope` |
| badge | not filtered. Rows are **weighted** by a Gaussian kernel centred on Oracle (80, half-width 25) | `sequence.row_weights`, ADR 0002 |
| cell | hero and archetype | `archetypes.parquet` |

Every endpoint accepts `match_mode`, `game_mode`, `min/max_match_id`,
`min/max_unix_timestamp`, `min/max_average_badge`, `min/max_duration_s` and a
hero filter. They map directly onto `match_player` columns
(`common_filters.rs`, `MatchInfoFilters::build`). A few details matter for
reproduction:

- Timestamps are widened to whole hours before the query runs
  (`round_timestamps`, `common_filters.rs:261`). Match ids are exact, so use
  match ids to bound a population.
- `min_average_badge` of 11 or below applies no filter at all
  (`common_filters.rs:40`).
- `match_mode` defaults to `ranked,unranked`, and `min_unix_timestamp`
  defaults to 30 days ago. Pass both.
- Results are cached for an hour per query string.

Three things can't be expressed through any endpoint's filters:

1. **Our match set.** The range 105,284,527 to 105,717,970 now holds 31,621
   Ranked Normal matches, and every one of our 24,999 is among them. The
   6,622 extras arrived after the pull. Our share of the range falls from 87%
   of the oldest 12 hours to 42% of the newest. The extras aren't random:
   their median badge is 44 against our 56. So an endpoint pointed at our
   range measures a larger, lower-badge population.
2. **In scope.** Upstream counts every player row. We drop players whose
   outcome is `NotScored`/`Invalid` or who bought nothing (1.2% of players
   across the pull).
3. **Badge weighting and archetypes.** A badge filter can't reproduce a
   kernel weight, and no endpoint has an archetype key. `account_ids` (at
   most 1,000) and `include/exclude_item_ids` don't define a cell. So an
   endpoint can check **unweighted, hero-level** counts at best. It can
   never check a weighted cell count that `why` prints.

### The exact check

To separate "same definition?" from "same population?", I looked for
stretches of the range where our pull holds every match upstream has. The
five longest runs contain 208 matches: 105299751-105300338,
105451351-105451898, 105412781-105413321, 105417950-105418522 and
105431702-105432259. Over each run, filtered to `ranked` and `normal`,
upstream's match set is ours, so the population is reproducible. I called
the three endpoints over each run with `min_matches=1`, summed the results,
and recounted the same quantities from the raw pages:

| Quantity | Local | Upstream | Keys that differ |
|---|---:|---:|---:|
| players (all 12 per match) | 2,496 | 2,496 (`baseline.matches`) | - |
| players reaching each flow column | 2495 / 2496 / 2457 / 1713 | same | 0 |
| item-flow nodes, purchases | 42,673 | 42,673 | 0 of 551 |
| item-flow edges | 152,104 | 152,104 | 0 of 23,585 |
| item pairs (`comb_size=2`) | 357,934 | 357,934 | 0 of 10,836 |
| Wraith and Ivy ability sequences | 161 | 161 | 0 of 134 |
| players in matches with badge ≥ 80 | 756 | 756 | - |

Restricted to our in-scope players, the local node total drops to 42,055 and
235 of 551 nodes differ. The whole gap is 40 `NotScored` players, which
upstream counts and we don't. So **the definitions agree exactly, and the
only structural gap is in-scope.**

## `/v1/analytics/ability-order-stats`

**Contents.** One row per distinct full-match sequence of ability points for
one hero. Trimmed Wraith response, over our range:

```json
[{"abilities": [1999680326, 1999680326, 1842576017, 4147641675, 1999680326,
                2981692841, 2981692841, 1999680326, 1842576017, 4147641675,
                1842576017, 1842576017, 4147641675, 4147641675, 2981692841],
  "wins": 335, "losses": 368, "matches": 703, "players": 501,
  "total_kills": 4370, "total_deaths": 3786, "total_assists": 6485}, ...]
```

The SQL is `GROUP BY abilities` over `match_player`
(`ability_order_stats.rs:181`).

**Counts.** Yes. `matches` is player rows (`wins + losses`), and `players`
is distinct accounts.

**Order or levels.** Order. Each id is one ability point: the first
occurrence unlocks the ability, and later ones level it. The array runs 11 to
16 long depending on how far the match went. It's the same thing
`abilities.parquet` holds, and the same thing ADR 0003 tested, though ADR
0003 used per-(slot, level) timing columns rather than whole-sequence keys.
One difference: upstream keeps the order of the raw `items` list, and we sort
by `game_time_s`. In the 208-match sample, 151 of 2,496 players (6.0%) have
ability entries out of time order, so upstream files the same order under
two keys for those players. The exact check above used raw list order on
both sides.

**Sparsity.** Whole-sequence keys are sparse. Over our range, 14,107 Wraith
player rows spread over 4,761 distinct sequences. The most common covers 5.0%.
The code's default `min_matches` is 10, not the 20 the spec states
(`ability_order_stats.rs:23`). At that default the response has 113 rows
covering 55% of Wraith players. At 20 it covers 50%.

**Reproducible?** Not for the shipped pull (see above). It is for a closed,
settled range, apart from in-scope and the sort-order difference.

**Honest use: smell test only**, until a reproducible pull exists. One smell
test passes already. The first 15 points of our generated Wraith order
(`data/builds/Wraith_0.json`, Wraith's only cell) are exactly upstream's most
common sequence. That sequence is 15 points long, and ours adds the final
Telekinesis level 4. That is two populations agreeing on a mode, not a
measurement. With a reproducible pull it becomes a real check on the
ability-order block at hero level, as long as both sides sort by time the
same way, or we compare on raw list order as above.

## `/v1/analytics/item-flow-stats`

**Contents.** Nodes (an item within a phase column), edges (an item in
column c to an item in column c+1), a `summary` and `baseline` for the
population, and `reached_per_column`. Trimmed Wraith response, over our
range:

```json
{"summary":  {"wins": 7165, "losses": 6942, "matches": 14107, "players": 7912,
              "avg_net_worth": 45979.8, "avg_duration_s": 2193.7, ...},
 "baseline": {... same when nothing is locked ...},
 "reached_per_column": [14090, 14088, 13872, 10104],
 "nodes": [{"column": 0, "item_id": 1009965641, "wins": 6317, "losses": 6040,
            "matches": 12357, "players": 12355,
            "adjusted_win_rate": 0.509, "avg_net_worth_at_buy": 36945.2, ...}],
 "edges": [{"from_column": 0, "from_item_id": 1009965641,
            "to_item_id": 1292979587, "wins": 4190, "losses": 3843,
            "matches": 8033}]}
```

That call returned 488 nodes and 17,060 edges.

**Counts.** Yes, per node and per edge. A node's `matches` counts purchases
(`count()`, `item_flow_stats.rs:444`), and `players` counts distinct
(match, account) pairs. The two differ only for repeat buys in one phase. An
edge counts players who bought item A in column c and item B in column c+1,
at most once each (`arrayDistinct`, `:515`). `summary.matches` is the
pick-rate denominator. `reached_per_column` is the number of players who
bought anything in each column, which shows how survivorship-selected the late
columns are.

**It isn't our phase grid, and it isn't the bigram.** For `normal`,
`phase_interval_s` and `phase_count` are ignored. The columns are fixed at
0-9, 9-20, 20-30 and 30+ minutes (`TIME_PHASE_BOUNDARIES = [540, 1200, 1800]`,
`:210`). Our `phase` is 600 s wide (`features.PHASE_INTERVAL_S`), and the
model's time buckets are 0-5, 5-10, 10-15, 15-20, 20-30 and 30+. An edge is
also phase-to-next-phase co-occurrence, not consecutive purchases, so it
isn't the bigram and it isn't any backoff level's `prev1`/`prev2` context.

**Corrupt field.** `adjusted_win_rate` and `avg_net_worth_at_buy` are built
on upstream's `net_worth_at_buy`. That's the field we measured as reporting
final net worth on 7.5% of purchases. In the sample above, Monster Rounds,
an 800-soul item bought in the first nine minutes, has an average net worth
at buy of 36,945. Both fields are win-rate machinery as well, which this
project keeps out, so ignore them.

**Reproducible?** Not for the shipped pull. For a closed, settled range, yes,
exactly on raw counts once not-in-scope players are dropped, as the exact
check shows. Any comparison with our tables has to rebin our purchases onto
the 540/1200/1800 grid.

**Honest use: smell test only** for the shipped model. For example: is an
item's hero-level pick share in 9-20 minutes about the same upstream and
here? Label any such number as a different population. With a reproducible
pull, the nodes become a real external check on the purchase table's
hero-level counts per phase. The edges don't check anything the model uses.

## `/v1/analytics/item-permutation-stats`

**Contents.** One row per item combination. Trimmed Wraith response,
`comb_size=2`, over our range:

```json
[{"item_ids": [84321454, 3919289022], "wins": 6663, "losses": 6018, "matches": 12681},
 {"item_ids": [1009965641, 84321454], "wins": 6132, "losses": 5899, "matches": 12031}, ...]
```

(Quicksilver Reload with Mercurial Magnum, and Monster Rounds with
Quicksilver Reload.)

**Counts.** Yes. `matches` is the number of players who bought every item in
the set at any point in the match. Items are de-duplicated per player and
filtered to upgrades (`item_permutation_stats.rs:206-207`), so sold items and
absorbed components count, and order and timing are gone. There is no
`players` field, and no per-population total. A share needs a denominator
from another call, such as `item-flow-stats` `summary.matches` with the same
filters. `comb_size` starts at 2, so single-item counts aren't available
here.

**What it touches.** Less than the issue assumed. Build-family shares are
per-player **spend shares** by family. This endpoint counts **co-presence**
of specific items. It can't reproduce a family share, and it can't check a
staple on its own, because a staple is a single-item share per cell.

**Reproducible?** Not for the shipped pull. For a closed, settled range, yes,
exactly (the exact check above), with the in-scope caveat.

**Honest use: smell test only**, and a weak one, because nothing the model
publishes is a pair count. Its one real use would be as an external check on
the co-purchase counts behind the staple list, at hero level, once a
reproducible pull exists.

## `/v1/analytics/hero-build-stats/{hero_id}`

**Contents.** Win and loss counts per **intended build** (`hero_build_id`).
Trimmed Wraith response, over our range:

```json
[{"hero_id": 7, "hero_build_id": 271880, "wins": 1, "losses": 6, "matches": 7, "players": 7},
 {"hero_id": 7, "hero_build_id": 245681, "wins": 3, "losses": 2, "matches": 5, "players": 5}, ...]
```

That call returned 15 builds and 31 player rows.

**Counts.** Yes, per build. There is no denominator: nothing says how many of
the hero's players were analysed, so coverage can't be computed from it.

**Filters.** Beyond the common ones, the SQL requires `demo_processed = 1`,
`game_mode = 1`, and a non-null `hero_build_id` (`hero_build_stats.rs:147`).
It forces `min_unix_timestamp` to at least March 2026, and it then drops any
build id missing from upstream's hero builds database (`retain_valid_builds`,
`:203`). There is no `game_mode` parameter. That last filter is visible in
the numbers. Upstream `match_player` has 50 Wraith player rows with an
intended build over our range, across 33 build ids. The endpoint returns 31
rows across 15 builds, and our pull has 26.

**Reproducible?** No. The analysed-match subset and the build database filter
can't be expressed locally. Our window is also still inside the four-to-six
week backlog: 1,297 of 379,281 upstream player rows (0.34%) have an intended
build today.

**Honest use: nothing.** It only reports win rates per build, and win rate is
out of every objective here. Measure coverage with the MCP SQL server, as
before. The description does settle one point, in upstream's words: the
intended build is "the first build the player had selected when the game
started".

## What upstream's method teaches (issue Q5)

- **Upstream uses the same raw data.** Nothing it computes is better data
  than ours. The exact check shows the definitions agree, so a difference
  between the endpoints and our tables is a population difference until
  proven otherwise.
- **`reached_per_column` is worth copying as a display.** Late-phase shares
  come from a survivor population: in the Wraith sample, 10,104 of 14,107
  players bought anything after 30 minutes. Printing a "players who reached
  this time bucket" count beside late-bucket recommendations would make that
  selection visible. It's a count, so it fits the rules.
- **Whole-sequence ability keys are too sparse to model on.** The most common
  Wraith sequence covers 5% of players. Our per-point approach is the right
  one. That the generated order matches upstream's most common sequence
  exactly is mild reassurance, not evidence.
- **Upstream's ability order depends on list order.** It inherits the raw
  list-order defect that `features.clean_purchases` fixes by sorting.
- **Win rate adjusted by net-worth bucket** is upstream's answer to wealth
  confounding. It uses the corrupt `net_worth_at_buy` field and sits in
  territory `docs/DIAGNOSIS.md` already closed. Nothing to adopt.
- **Spec traps.** The spec types item ids as `int32`, both in responses and
  in `include_item_ids`, `locked_item_ids` and `item_ids`. The server uses
  `u32`, and the responses carry values such as 3,919,289,022 (Mercurial
  Magnum). A client generated from the spec wraps them negative, the same silent
  failure this project already hit with int32 item ids. Parse with int64,
  and don't use the generated clients. The spec also says `min_matches` defaults
  to 20 on ability-order-stats. The code uses 10.

## Should any endpoint replace local modeling? (issue Q6)

No, anywhere. Each endpoint lacks at least one of the archetype key, badge
weighting, the in-scope filter, and the backoff contexts
(`prev1`/`prev2`, time bucket). None of those can be added through query
parameters. The endpoints also move under us: results are cached for an hour,
and the population grows as late matches arrive, so a number fetched twice
can differ. We can't publish anything that doesn't trace to a stable table
row.

## Summary

| Endpoint | Reproducible? | Counts? | Honest use |
|---|---|---|---|
| `ability-order-stats` | Not the shipped pull (the match set isn't a range, and there's no in-scope filter). Exact on a closed range, except `NotScored` and list order. | Yes: `matches`, `players`, `wins` per full sequence | Smell test only. With a reproducible pull, an external check on the ability-order block at hero level. |
| `item-flow-stats` | Same as above. Exact on a closed range. The phase grid is fixed at 9/20/30 min, so ours must be rebinned. | Yes, per node and per edge, plus population totals and `reached_per_column` | Smell test only. With a reproducible pull, a check on hero-level purchase counts per phase. Edges aren't the bigram. |
| `item-permutation-stats` | Same as above. Exact on a closed range. | Yes per combination, but no population total | Smell test only, and weak: pairs aren't build-family shares or staples. |
| `hero-build-stats/{hero_id}` | No (analysed matches only, and the build database filter) | Yes per build, no coverage denominator | Nothing. It only reports win rates, and coverage is better measured in SQL. |

## Follow-up questions

1. Should the next pull take a closed `match_id` range, after the range stops
   growing, so the three endpoints become exact external checks? How many
   days after a match's start time does `/v1/matches/metadata` stop gaining
   matches in a range? It had gained 26.5% ten days after our pull.
2. Is our pull's badge skew a problem in its own right? It is a median of 56
   against 44 for the matches that arrived late. Does "newest matches
   available at pull time" bias the population toward higher badges in
   every pull, and does that shift the Oracle-weighted tables?
3. Should `abilities.parquet` and upstream agree on ability order? Is the
   raw `items` order ever the true spend order, or is `game_time_s` always
   right for the 6% of players where the two disagree?
4. Should late time buckets print a "players who reached this bucket" count,
   as `reached_per_column` does, so survivorship shows next to late
   recommendations?
