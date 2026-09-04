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
build serving neither. Archetypes are fit per hero, and heroes that do not
genuinely split (Haze, Dynamo) stay single.

The model is a **backoff frequency table**, deliberately not a neural network.
Conditioning on hero × archetype leaves roughly 3,900 sequences per cell, and
the measured headroom is modest — a bigram already reaches 0.328 next-item
top-1 against 0.198 for the positional baseline. Every recommendation is
traceable to a table row with its observation count, which matters in a project
that was already burned once by a model that produced a number and no recourse.

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
| `src/deadlock/buildfmt.py` | Build representation and in-game export |
| `tests/` | Regression tests for known source-data defects |

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
