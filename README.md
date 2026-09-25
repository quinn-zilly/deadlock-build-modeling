# deadlock-build-modeling

Tells a Deadlock player what items to buy, in what order, and when.

Win rates and pick rates for single items are easy to look up. The order is
harder: what to buy first, when to buy it, and when to leave the standard
build. This project answers that in two ways:

- `deadlock build` gives a full ordered build for a hero and archetype before
  a match.
- `deadlock next` takes what you own and the game clock during a match and
  says what to buy next.

## How it works

The model copies what strong players buy. It never claims an item causes a
win, only that strong players buy it, in this order, at about this time. An
earlier version tried to estimate how much each item adds to win rate. It
passed every aggregate check and still left out every item that at least 70%
of Wraith players buy. `docs/DIAGNOSIS.md` explains why it was dropped.

Advice is per hero and archetype, not per hero. Ivy players split into a gun
build and a spirit build that share few items, and an average of the two
serves neither. Archetypes are fitted separately for each hero. 31 of 38
heroes split, for 80 hero and archetype pairs, and the other seven keep one
archetype. Each archetype has a name no other archetype of that hero uses, so
a player can always ask for it.

The model is a backoff table of purchase counts, not a neural network. A
hero and archetype pair has a median of 3,232 player-matches, and every
recommendation traces to a table row with its count. `deadlock why` prints
those rows.

The table has six levels, most specific first. The model mixes all six,
weighting each by how much data backs it:

    L0  (hero, archetype, last two items, time bucket)
    L1  (hero, archetype, last item, time bucket)
    L2  (hero, archetype, purchases so far, time bucket)
    L3  (hero, archetype, purchases so far)
    L4  (hero, purchases so far)
    L5  (hero)

## Results

Top-1 accuracy at predicting a player's next purchase, on held-out matches,
counting only items the player doesn't already own. One run of
`scripts/score_sequence.py` on 2026-09-15 produced every number in the table:

| | all heroes | Wraith |
|---|---|---|
| most popular item | 0.134 | 0.149 |
| most common item at that position | 0.212 | 0.251 |
| bigram, the bar to beat | 0.265 | 0.277 |
| **backoff table** | **0.362** | **0.384** |

Splitting by account instead of by match changes accuracy by 0.003, so the
model learns strategy, not individual players. Splitting by time changes it by
0.009, which is patch drift. Both come from the same run.

Older docs and issues quote 0.391 and 0.406 from 2026-09-04. That run used a
different population, so the numbers don't compare with these.

All 80 generated builds contain every item that at least 70% of that
archetype's players buy. Against the order players actually buy in, the median
Kendall tau is +0.794. Mean Jaccard@12 against real players is 0.409, higher
than the 0.339 two real players of the same archetype score against each
other. These come from the 2026-09-15 run that generated the builds.

## Setup

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv venv --python 3.13
uv pip install -e ".[dev]"
```

Run the tests with the project venv. The system Python has a `typeguard` that
breaks pytest on 3.14.

```bash
.venv/Scripts/python.exe -m pytest    # Windows
.venv/bin/python -m pytest            # POSIX
```

Tests marked `data` need the processed Parquet tables and skip without them.

## Using it

```bash
deadlock heroes --archetypes                     # what can be built
deadlock build --hero Ivy --archetype gun        # a full ordered build
deadlock build --hero Ivy --archetype gun --export ivy.json   # importable in game
deadlock next  --hero Ivy --owned "Extra Spirit,Mystic Burst" --time 8:30
deadlock next  --hero Wraith --owned "..." --enemies "Lash,Vindicta"
deadlock next  --hero Ivy --owned "..." --points "Air Drop,Air Drop"  # and the next ability point
deadlock watch --hero Ivy                        # interactive; type "+ Ricochet" as you buy
deadlock why   --hero Ivy --item Ricochet --owned "..." --time 8:30
deadlock build --hero Ivy --badge 55             # weighted to another badge
```

`build` prints three things: the purchase order, the order to spend ability
points, and imbue targets. Nine items are imbued into one of the hero's
abilities. For each one in the build, `build` names the ability that
archetype's players pick most, with the count behind it. The export stores
the same target in `imbue_target_ability_id`.

Give `--archetype` when you know it. Without it, the tool guesses from what
you have bought. While the evidence is thin it shows each likely archetype
separately. Blending them could recommend an item neither build wants.

`next --points` takes the ability points you have spent, in order, and says
where the next one goes. It never suggests a fifth point in one ability, since
four is the maximum.

`next --enemies` lists items strong players buy against those heroes. They
appear beside the recommendations and don't change their order.

`why` prints the whole backoff chain for one item: the context at each level,
the raw count, the level's weight, and which level contributed most.

Every command that gives advice weights players by badge. The default is 80,
the Oracle tier, which was the top 29.6% of players when measured, so the
advice follows strong players rather than the median one. `--badge N` weights
toward another badge and `--badge all` turns weighting off. Each setting
caches its own model. `docs/adr/0002-badge-weighting-on-by-default.md` measures
what the weighting changes.

## Data

Match data comes from the community API at
[deadlock-api.com](https://api.deadlock-api.com), which Valve doesn't endorse.
`scripts/pull_data.py` caches every page under `data/`, which git ignores, so
rerunning a finished pull sends no requests. The 2026-09-15 rebuild has 24,999
matches, 296,478 player-matches, and 5,119,990 purchases.

The matches are Ranked and Normal. Only Ranked matches have `average_badge`,
the rank used for weighting.

Each cached page also has the match's objectives, its Mid-Boss kills, and the
community build each player picked. From these the purchase table records the
Walker kill that unlocked each of slots 10, 11 and 12, the team's first
Mid-Boss, and the player's selected build. Each is null when unknown, never
zero. The `src/deadlock/dataset.py` docstring lists the columns and how often
each is filled in. `docs/game-mechanics.md` explains the game rules behind them
and three traps in the raw data.

Pulls run without an API key by default, paced under the per-IP rate limits.
Set `DEADLOCK_API_KEY` and the client sends it and runs faster. No command
needs a key.

Training uses every match, with badge as a row weight rather than a filter.
Keeping only won, high-badge matches throws away about eight in nine rows and
leaves the median archetype about 366 player-matches, too few to model.
`sequence.row_weights` can also weight by wins and hero experience, but
nothing turns those on.

## Refitting

One command rebuilds everything derived from the cached pages, in order:

```bash
python scripts/refit.py                    # all seven steps
python scripts/refit.py --from archetypes  # reuse the three parquet tables
python scripts/refit.py --badge all --hero Ivy
```

It exits non-zero if any build is missing a staple, so a refit that makes an
unusable build fails.

It also deletes the models the `deadlock` command caches next to the tables:
`sequence_model*`, `ability_model*`, and `counter_lifts.parquet` when it
rebuilds the purchase table. The command uses a cached model for as long as
the file exists, so without this it would keep answering from the old fit. The
first command after a refit fits them again, about a minute each.

Timings from 2026-09-15, over 125 cached pages and 24,999 matches:

| Step | Writes | Time |
| --- | --- | --- |
| `purchases` | `purchases.parquet` | 7m 25s |
| `abilities` | `abilities.parquet` | 2m 01s |
| `imbues` | `imbues.parquet` | 1m 23s |
| `archetypes` | the fit, labels and review sheet | 53s |
| `builds` | 80 builds, and the staple check | 27s |
| `site` | `builds.html`, the review page | 14s |
| `pages` | `data/site/public/methodology.html` (2026-09-25) | 2s |

About 12 minutes in total. The first three steps reread the cached JSON and
take 87% of that. Everything after them takes under two minutes, so use
`--from archetypes` unless the pages changed.

Archetype names a person has approved live in `data/archetype_names.json`. The
file is checked in and applied on every fit, so a refit can't rename a build
someone already reviewed.

## Publishing the site

The public site is at https://quinn-zilly.github.io/deadlock-build-modeling/.
Publish it by hand after a refit:

```bash
python scripts/deploy_site.py              # build, push, and start the deploy
python scripts/deploy_site.py --no-push    # build and commit locally only
```

The pages are built from `data/`, which git ignores, so CI can't build them.
The script builds them locally and commits the output to the `site` branch,
which holds only the published files. Then it pushes that branch and starts
the `Pages` workflow, which publishes it. It never changes your checkout. Pass
the same `--badge` as the refit.

The site isn't redeployed on a schedule. Each deploy describes one data window,
and the methodology page states it.

## Source data problems

`features.py` fixes these, and a test covers each one:

- About 46% of entries in a player's `items` list are ability points, not
  purchases. They aren't noise: `abilities.py` reads them for the order
  players spend ability points in.
- 11.5% of players have an `items` list out of time order, so purchases are
  sorted. Everything here depends on purchase order.
- 9% of purchases report the player's final net worth as `net_worth_at_buy`,
  mostly early in the game. The code never reads that field and rebuilds net
  worth from the stats series, which is sampled every 180 seconds.
- The metadata endpoint has no per-player `won` field. Reading it returns
  None, which would silently become a 0% win rate.

The rebuilt net worth gets the order of players right, with rank correlation
0.987, but the amounts are off by a median of 21%. Use it to compare players,
and bucket it no finer than quintiles.

## Game facts the code checks

Each of these went against an obvious assumption. The code asserts them, so a
patch that changes one fails loudly:

- Nobody buys tier 5 items: 0 of 5.1M purchases. The asset file has 17 of
  them at 9999 souls, but they aren't in the shop this patch. The real shop
  has 156 items.
- A player holds at most 12 items. There is no cap per slot type: 83.5% of
  players hold more than four items of one type.
- The component tree can't be a hard rule. Only 79% of players who buy a
  composite item bought its component first.
- No player buys the same item twice.
- The median player makes 17 purchases but ends with 11 or 12 items. About
  37% of purchases are sold. A build is a purchase sequence, not an inventory.
- Most selling is a component making room for the item it builds into. 70.6%
  of items that are a component get sold, against 6.4% of items that aren't.
  By tier it is 86.6% at tier 1 and 1.1% at tier 4. Only about 6% of purchases
  are sold because the player changed plans. So the staple check reads the
  purchase sequence, not held items: one archetype buys Mystic Burst 96% of
  the time and sells it 95% of the time.
- Buy time rises in a straight line with purchase number, about 110 seconds per
  purchase, so timing is a lookup, not a model.
- Item ids don't fit in int32: 73 of the 173 shop ids are larger. Stored as
  int32 they wrap negative and everything still runs, so the only symptom is a
  worse model.

## Layout

| Path | What it does |
|---|---|
| `src/deadlock/api.py` | HTTP client with rate limiting and a disk cache |
| `src/deadlock/ingest.py` | Pages through match metadata |
| `src/deadlock/assets.py` | Item, hero, and ability lookups |
| `src/deadlock/features.py` | Cleans purchases and rebuilds net worth |
| `src/deadlock/abilities.py` | Reads ability points out of the `items` list |
| `src/deadlock/economy.py` | Purchase tempo and tier features; only tests use it |
| `src/deadlock/dataset.py` | Builds the purchase table |
| `src/deadlock/splits.py` | Train and test splits that don't leak |
| `src/deadlock/state.py` | A buy decision and the items that can be bought |
| `src/deadlock/semantics.py` | What items do, read from their tooltips |
| `src/deadlock/kits.py` | What abilities do, read from their descriptions |
| `src/deadlock/archetype.py` | Fits archetypes per hero and guesses one mid-match |
| `src/deadlock/evaluate.py` | The staple check and order metrics |
| `src/deadlock/sequence.py` | The backoff model |
| `src/deadlock/build.py` | Generates builds, including component absorption |
| `src/deadlock/counters.py` | Items bought against specific enemy heroes |
| `src/deadlock/abilityorder.py` | Models the order ability points are spent in |
| `src/deadlock/imbue.py` | Which ability each imbued item targets |
| `src/deadlock/buildfmt.py` | Build format and in-game export |
| `src/deadlock/cli.py` | The `deadlock` command |
| `src/deadlock/pages.py` | The public site's pages, starting with the methodology page |
| `scripts/build_pages.py` | Writes the public pages from the model's facts |
| `scripts/deploy_site.py` | Publishes the public pages to GitHub Pages |
| `scripts/refit.py` | Rebuilds every derived file in order |
| `tests/` | Unit tests, plus `data` tests that run against the real tables |
