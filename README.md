# deadlock-build-modeling

Using predictive analytics to help Deadlock players choose items.

Deadlock snowballs on souls: players who are ahead buy more and pricier items
*and* win. A naive "items owned → win" model mostly relearns "rich players
win". This project controls for net worth at time of purchase so item effects
can be read separately from economic lead.

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

## Data

Match data comes from the community API at
[deadlock-api.com](https://api.deadlock-api.com) (unofficial; not endorsed by
Valve). Pulls are cached under `data/` (gitignored), so re-running a completed
pull costs no requests.

The population is Ranked + Normal matches, because `average_badge` — the rank
control — is only populated for Ranked.

## Layout

| Path | Purpose |
|---|---|
| `src/deadlock/api.py` | Rate-limited, disk-cached HTTP client |
| `src/deadlock/ingest.py` | Match metadata pagination |
| `src/deadlock/assets.py` | Item and hero lookups |
| `src/deadlock/features.py` | Purchase cleaning, net-worth reconstruction |
| `tests/` | Regression tests for known source-data defects |

## Source data caveats

Three defects are corrected in `features.py`, each pinned by a test:

- **~47% of `items` entries are ability points**, not purchases.
- **~13% of players have unsorted item arrays**, so purchase order needs a sort.
- **~8% of purchases report a corrupt `net_worth_at_buy`** equal to the
  player's *final* net worth, concentrated in the early game. Net worth is
  reconstructed from the 180s stats series instead.

The reconstruction recovers **rank, not absolute souls** (rank correlation
0.987; median relative error ~21%). Use it for relative position only, bucketed
no finer than quintiles.
