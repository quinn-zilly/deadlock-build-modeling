# deadlock-build-modeling

Modeling **what order to buy items in, and when** for Deadlock players.

Item win rates and pick rates are easy to look up. The harder question, and the
one this project answers, is sequencing: what to buy first, when to buy it, and
when to diverge from the standard build.

Two products:

- **Pre-match build maker** — a full ordered build for a hero and playstyle.
- **In-match advisor** — given what you own and the clock, what to buy next.

## Approach

The model **imitates observed play**. It does not estimate causal item effects.
An earlier version of this project did, and `docs/DIAGNOSIS.md` records why that
was abandoned: the estimator cleared every aggregate gate while producing
builds that omitted all nine items ≥70% of Wraith players buy. Imitation
sidesteps the confounding entirely, because it never claims an item *causes* a
win — only that strong players buy it, in this order, at about this time.

Recommendations are conditioned on **(hero, archetype)**, not hero alone.
Heroes are played in materially different ways: Ivy splits cleanly into a gun
build and a spirit build that share few items, and averaging them produces a
build serving neither. Archetypes are fit per hero: 28 of 38 heroes
split, and the ten that do not stay single. Every archetype of a hero has a
name that selects only it -- two clusters sharing one name is a build a player
cannot ask for.

The model is a **backoff frequency table**, deliberately not a neural network.
Conditioning on hero × archetype leaves a median of 3,313 player-matches per
cell, and every recommendation stays traceable to a table row with its
observation count — which matters in a project already burned once by a model
that produced a number and no recourse.

Six levels, most specific first, interpolated rather than hard-switched:

    L0  (hero, archetype, last two items, time bucket)
    L1  (hero, archetype, last item, time bucket)
    L2  (hero, archetype, purchases so far, time bucket)
    L3  (hero, archetype, purchases so far)
    L4  (hero, purchases so far)
    L5  (hero)

### Measured, held out, owned items excluded

| | all heroes | Wraith |
|---|---|---|
| popularity | 0.137 | 0.141 |
| modal at position | 0.220 | 0.263 |
| bigram (the bar) | 0.267 | 0.277 |
| **backoff chain** | **0.391** | **0.406** |

The match-vs-account gap is 0.009, so the model is learning strategy rather
than memorising individual players; the match-vs-time gap is 0.021, which is
patch drift.

All **75 hero × archetype builds** carry every item ≥70% of that archetype's
players buy, at median Kendall tau +0.809 against the population's own
purchase order.

## Setup

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv venv --python 3.13
uv pip install -e ".[dev]"
```

Use the project venv (`.venv`), not the system Python — the system install has
a `typeguard` that breaks pytest on 3.14.

```bash
.venv/Scripts/python.exe -m pytest    # Windows
.venv/bin/python -m pytest            # POSIX
```

Tests marked `data` need the processed Parquet tables and are skipped without
them.

## Data

Match data comes from the community API at
[deadlock-api.com](https://api.deadlock-api.com) (unofficial; not endorsed by
Valve). Pulls are cached under `data/` (gitignored), so re-running a completed
pull costs no requests. 25,000 matches → 296,332 player-matches → 5.1M
purchases.

The population is Ranked + Normal matches, because `average_badge` — the rank
control — is only populated for Ranked.

Training uses **all** matches, with badge, outcome, and hero familiarity as row
*weights* rather than filters. Filtering to won + high-badge costs about 9× and
leaves the median hero with ~366 player-matches per archetype, too thin to
model.

The badge weight is **on by default**, centred at 80 -- roughly the top 30% of a
distribution whose median is 61 -- so the tool imitates strong play rather than
median play. `--badge N` asks for another bracket and `--badge all` for none;
each bracket caches its own model. What that buys, and what it does not, is
measured in `docs/adr/0002-badge-weighting-on-by-default.md`.

## Layout

| Path | Purpose |
|---|---|
| `src/deadlock/api.py` | Rate-limited, disk-cached HTTP client |
| `src/deadlock/ingest.py` | Match metadata pagination |
| `src/deadlock/assets.py` | Item, hero, and ability lookups |
| `src/deadlock/features.py` | Purchase cleaning, net-worth reconstruction |
| `src/deadlock/economy.py` | Purchase tempo and tier-ladder features |
| `src/deadlock/dataset.py` | Purchase-level table assembly |
| `src/deadlock/splits.py` | Train/test splits and leakage rules |
| `src/deadlock/state.py` | The buy decision point and its legal moves |
| `src/deadlock/semantics.py` | What items do, read from their tooltips |
| `src/deadlock/kits.py` | What abilities do, read from their descriptions |
| `src/deadlock/archetype.py` | Per-hero build archetypes, and inferring one mid-match |
| `src/deadlock/evaluate.py` | The prevalence gate and order metrics |
| `src/deadlock/sequence.py` | The backoff model |
| `src/deadlock/build.py` | Generation, with component absorption |
| `src/deadlock/counters.py` | Items bought because of the enemy team |
| `src/deadlock/abilityorder.py` | The order ability points are spent in |
| `src/deadlock/imbue.py` | Which ability an imbueable item is pointed at |
| `src/deadlock/buildfmt.py` | Build representation and in-game export |
| `src/deadlock/cli.py` | The command line |
| `tests/` | Regression tests for known source-data defects |
| `scripts/refit.py` | Rebuild every derived artifact, in dependency order |

## Using it

```bash
deadlock heroes --archetypes                     # what can be built
deadlock build --hero Ivy --archetype gun        # a full ordered build
deadlock build --hero Ivy --archetype gun --export ivy.json   # importable
deadlock next  --hero Ivy --owned "Extra Spirit,Mystic Burst" --time 8:30
deadlock next  --hero Wraith --owned "..." --enemies "Lash,Vindicta"
deadlock next  --hero Ivy --owned "..." --points "Air Drop,Air Drop"  # and where the next point goes
deadlock watch --hero Ivy                        # a session; "+ Ricochet"
deadlock why   --hero Ivy --item Ricochet --owned "..." --time 8:30
deadlock build --hero Ivy --badge 55             # weighted to your own bracket
```

`build` prints three things: the purchase order, the ability-point order, and
the imbue targets — for each of the nine imbueable items it recommends, the
ability that archetype actually points it at, with the count behind it. An
imbueable item is half an instruction without that, and the export carries the
same target in `imbue_target_ability_id`.

Declare your archetype when you know it. Without one the tool infers it from
what you have bought and, while the evidence is thin, shows the plausible
archetypes *separately* rather than blending them — a blend can recommend an
item that neither build actually wants.

`next` takes `--points` -- the ability points you have already spent, in order
-- and answers the other mid-match question: where the next one goes. It
refuses a fifth point in an ability, which is the only illegal move an ability
order has.

`why` prints the whole backoff chain for one item: the context at each level,
the raw count, the mixture weight, and which level carried the mass.

### The build browser

```bash
python scripts/build_site.py            # every build, one page
python scripts/build_site.py --hero Ivy --badge all
```

Writes `data/site/builds.html`, a self-contained page carrying the same four
things `build` prints — purchase order, ability order, imbue targets and
counter-picks — plus two things only a page can do: two archetypes of one hero
side by side with the purchases unique to each marked, and a download of the
importable JSON. Everything on it, including the figures in the masthead and
footer, is generated from the build data, so a refit updates it and no number
on the page is typed by hand.

The page is rendered at the bracket its builds came from, and says which. It
is regenerated as the last step of `refit.py`, never edited.

## Refitting

Everything derived from the cached pages rebuilds with one command, in
dependency order -- purchases, ability points, imbues, the archetype fit, the
builds, the page:

```bash
python scripts/refit.py                  # all six steps
python scripts/refit.py --from archetypes  # keep the three parquet passes
python scripts/refit.py --badge all --hero Ivy
```

It exits non-zero if any hero-and-archetype build misses a staple, so a refit
that produced unusable builds fails rather than reporting success.

Archetype names a person accepted live in `data/archetype_names.json`, which is
checked in and applied on every fit, so a refit cannot silently rename a build
a Deadlock player already ruled on.

## Source data caveats

Defects corrected in `features.py`, each pinned by a test:

- **~46% of `items` entries are ability points**, not purchases. These are not
  noise — they carry the ability leveling order and timing, which feeds
  archetype clustering.
- **~11.5% of players have unsorted item arrays**, so purchase order needs a
  sort. This one is load-bearing here: if order is wrong, every gap is wrong.
- **~9% of purchases report a corrupt `net_worth_at_buy`** equal to the
  player's *final* net worth, concentrated in the early game. Net worth is
  reconstructed from the 180s stats series instead.
- **The metadata endpoint has no per-player `won` field.** Reading it returns
  None, which silently becomes a 0% win rate.

The net-worth reconstruction recovers **rank, not absolute souls** (rank
correlation 0.987; median relative error ~21%). Use it for relative position
only, bucketed no finer than quintiles.

## Measured game constants

Each of these contradicted an obvious assumption, and each is asserted rather
than trusted, so a patch change fails loudly:

- **Tier 5 items are never purchased** — 0 rows out of 5.1M. They exist in the
  asset file (17 items at 9999 souls) but are not in the shop this patch. The
  real vocabulary is 156 items.
- **The inventory cap is 12 items held**, and there is no per-slot-type cap —
  83.5% of players hold more than four of some one type.
- **The component DAG cannot be a hard constraint.** Only 79% of players who
  buy a composite item ever bought its component separately.
- **No item is ever bought twice** by the same player.
- **Median player makes 17 purchases but holds 11–12 items**; 37.3% are sold.
  A build is a purchase sequence, not an inventory.
- **Most selling is component absorption, not a change of mind.** Sold rate is
  70.6% for items that are a component of something against 6.4% for items
  that are not (86.6% at tier 1, 1.1% at tier 4). Only ~6% of purchases are a
  genuine strategic sell. This is the mechanism that fits 17 purchases into 12
  slots — and the reason membership checks run over the purchase sequence, not
  held items: Mystic Burst is bought by 96% of one archetype and sold by 95%.
- **Buy time is linear in buy index**, about 110s per purchase. Timing is a
  lookup, not a model.
- **Item ids exceed int32.** 73 of the 173 shopable ids do. Stored narrower
  they wrap negative, still sort, still aggregate, and still win an argmax —
  so the failure is silent and looks like a merely mediocre model.
