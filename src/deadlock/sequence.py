"""The next-item model: a backoff chain of frequency tables.

The model predicts what players buy next. It does not predict what wins.

Every recommendation traces to a table row with a raw count. `explain` prints
that row:

    Ricochet for Wraith, 8 owned, 10-15min
      L1 (prev1=Swift Striker)  n=212  lambda=0.91  P=0.198  -> 0.150

`docs/DIAGNOSIS.md` explains why this is a table and not a neural network.

The chain has six levels, most specific first:

    L0  (hero, archetype, prev2, prev1, bucket)
    L1  (hero, archetype, prev1, bucket)
    L2  (hero, archetype, n_owned, bucket)
    L3  (hero, archetype, n_owned)
    L4  (hero, n_owned)
    L5  (hero)

Each level blends its own table with the result of the levels below it:

    P_Lk = lambda_k * P_local + (1 - lambda_k) * P_backoff
    lambda_k = W_k / (W_k + kappa)

W_k is the total row weight in that level's context. A context with little data
gets a small lambda and barely moves the result. L0's median context holds
about two observations, so its lambda is near 0.09. A context with no data gets
lambda 0 and passes the level below through unchanged, so every state gets a
distribution.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from . import assets
from .state import TIME_BUCKET_BOUNDS_S, GameState, Recommendation

log = logging.getLogger(__name__)

# Smoothing strength. A context whose total weight equals kappa gets lambda 0.5.
DEFAULT_KAPPA = 20.0

# The badge that row weights center on, and the kernel's width. Badge 80
# (Oracle) was the top 29.6% of players when measured; the median was 56. A
# narrower kernel would leave thin hero-and-archetype cells with almost no
# weight. Filtering to the bracket instead of weighting would keep about a
# ninth of the data.
DEFAULT_TARGET_BADGE = 80.0
DEFAULT_BADGE_HALFWIDTH = 25.0

# The prev1/prev2 value for "nothing bought yet". It gives a match's first
# purchase its own context, so the chain predicts it like any other purchase.
# The bigram baseline has no such context and cannot predict first purchases.
NO_ITEM = -1

LEVEL_KEYS: tuple[tuple[str, ...], ...] = (
    ("hero_id", "archetype_id", "prev2", "prev1", "time_bucket"),
    ("hero_id", "archetype_id", "prev1", "time_bucket"),
    ("hero_id", "archetype_id", "n_owned", "time_bucket"),
    ("hero_id", "archetype_id", "n_owned"),
    ("hero_id", "n_owned"),
    ("hero_id",),
)
LEVEL_NAMES = ("L0", "L1", "L2", "L3", "L4", "L5")

_EMPTY_INT = np.empty(0, dtype=np.int64)
_EMPTY_FLOAT = np.empty(0, dtype=np.float64)


@dataclass(frozen=True)
class Level:
    """One backoff table, stored as flat arrays plus a context index.

    Each context's rows are contiguous. `offsets` maps a context to its
    (start, stop) slice, so a lookup is one dict hit. A dict per context would
    take hundreds of megabytes at 1.8M rows.

    `counts` holds raw observation counts and `weights` holds weighted counts.
    Probabilities come from `weights`. The `n` shown to users comes from
    `counts`, because users can check a count of matches but not a weighted
    one.

    `item_ids` must be int64. 73 of the 173 shop item ids don't fit in int32.
    Stored as int32 they wrap to negative numbers without raising an error,
    and a wrapped id can still outrank every real item.
    """

    name: str
    keys: tuple[str, ...]
    offsets: dict[tuple[int, ...], tuple[int, int]]
    item_ids: np.ndarray
    weights: np.ndarray
    counts: np.ndarray

    def lookup(self, context: tuple[int, ...]) -> tuple[np.ndarray, np.ndarray, int]:
        """Items, weights, and raw count for a context. Empty when unseen."""
        span = self.offsets.get(context)
        if span is None:
            return _EMPTY_INT, _EMPTY_FLOAT, 0
        start, stop = span
        return (
            self.item_ids[start:stop],
            self.weights[start:stop],
            int(self.counts[start:stop].sum()),
        )


@dataclass(frozen=True)
class Evidence:
    """Why one item got its probability.

    `level` is the level that contributed the most probability to this item.
    That is not always the most specific level with a matching row, because a
    thin context can match and still contribute almost nothing.
    """

    item_id: int
    probability: float
    level: str
    n: int
    context: tuple[int, ...]
    lambdas: tuple[float, ...]
    contributions: tuple[float, ...]


def parse_target_badge(raw: str) -> float | None:
    """Parse a badge argument: a number, or `all` for no badge weighting.

    The CLI, the build generator, the scoring script, and the site generator
    all call this, so they can't disagree about what a badge argument means.
    """
    if raw.strip().lower() == "all":
        return None
    return float(raw)


def describe_badge(badge: float | None) -> str:
    """Name a badge bracket for output: "badge ~80" or "all badges"."""
    return "all badges" if badge is None else f"badge ~{badge:g}"


def row_weights(
    df: pd.DataFrame,
    *,
    target_badge: float | None = None,
    badge_halfwidth: float = DEFAULT_BADGE_HALFWIDTH,
    win_weight: float = 1.0,
    familiarity_weight: float = 0.0,
) -> np.ndarray:
    """Weight each purchase row for building the tables.

    Badge, wins, and hero familiarity are weights, not table keys. Keying on
    badge would split every cell into three, and the median cell holds only
    about 3,200 player-matches. A weight doesn't split any cells.

    Every factor defaults to having no effect, so each can be tested alone. The
    weights are scaled to a mean of 1.0, which keeps weighted totals on the
    same scale as raw counts.
    """
    weights = np.ones(len(df), dtype=np.float64)

    if target_badge is not None and "average_badge" in df:
        badge = pd.to_numeric(df["average_badge"], errors="coerce").to_numpy(float)
        # A Gaussian kernel instead of a filter. See DEFAULT_BADGE_HALFWIDTH.
        kernel = np.exp(-(((badge - target_badge) / badge_halfwidth) ** 2))
        weights *= np.where(np.isnan(badge), 1.0, kernel)

    if win_weight != 1.0 and "won" in df:
        won = df["won"].fillna(False).to_numpy(bool)
        weights *= np.where(won, win_weight, 1.0)

    if familiarity_weight and {"account_id", "hero_id"} <= set(df.columns):
        games = df.groupby(["account_id", "hero_id"])["match_id"].transform("nunique")
        weights *= 1.0 + familiarity_weight * np.log1p(games.to_numpy(float) - 1.0)

    mean = weights.mean()
    return weights / mean if mean > 0 else weights


def prepare(
    purchases: pd.DataFrame, archetypes: pd.DataFrame | None = None
) -> pd.DataFrame:
    """Add the columns the levels key on.

    Adds prev1, prev2, n_owned, time_bucket, and archetype_id. Players with no
    archetype get archetype 0.

    `n_owned` is the number of purchases so far, not the number of items held.
    The two differ because about 31% of purchases are components that a
    composite later absorbs. Build generation counts purchases, so the tables
    must count purchases too.
    """
    df = purchases.sort_values(["match_id", "player_slot", "buy_index"])
    grouped = df.groupby(["match_id", "player_slot"], sort=False)["item_id"]
    df = df.assign(
        prev1=grouped.shift(1).fillna(NO_ITEM).astype(np.int64),
        prev2=grouped.shift(2).fillna(NO_ITEM).astype(np.int64),
        n_owned=df["buy_index"].astype(np.int64),
        time_bucket=np.digitize(df["buy_time_s"].to_numpy(float), TIME_BUCKET_BOUNDS_S),
    )
    if archetypes is not None:
        df = df.merge(
            archetypes[["match_id", "player_slot", "archetype_id"]],
            on=["match_id", "player_slot"],
            how="left",
        )
    if "archetype_id" not in df:
        df["archetype_id"] = 0
    df["archetype_id"] = df["archetype_id"].fillna(0).astype(np.int64)
    return df


def _build_level(
    df: pd.DataFrame, name: str, keys: tuple[str, ...], weights: np.ndarray
) -> Level:
    """Count each (context, item) pair and index the result by context."""
    frame = df[list(keys) + ["item_id"]].copy()
    frame["w"] = weights
    agg = (
        frame.groupby(list(keys) + ["item_id"], sort=True)
        .agg(w=("w", "sum"), n=("w", "size"))
        .reset_index()
    )
    if not len(agg):
        return Level(name, keys, {}, _EMPTY_INT, _EMPTY_FLOAT, _EMPTY_INT)

    key_values = [agg[k].to_numpy(np.int64) for k in keys]
    # Rows are sorted by the full key, so a new context starts wherever any key
    # column changes value.
    changed = np.zeros(len(agg), dtype=bool)
    changed[0] = True
    for col in key_values:
        changed[1:] |= col[1:] != col[:-1]
    starts = np.flatnonzero(changed)
    stops = np.append(starts[1:], len(agg))

    offsets = {
        tuple(int(col[start]) for col in key_values): (int(start), int(stop))
        for start, stop in zip(starts, stops)
    }
    return Level(
        name=name,
        keys=keys,
        offsets=offsets,
        item_ids=agg["item_id"].to_numpy(np.int64),
        weights=agg["w"].to_numpy(np.float64),
        counts=agg["n"].to_numpy(np.int32),
    )


@dataclass
class SequenceModel:
    """The backoff chain and the settings it was fitted with."""

    levels: tuple[Level, ...]
    kappa: float = DEFAULT_KAPPA
    archetype_shares: dict[int, dict[int, float]] | None = None
    # The badge the tables were weighted toward, or None for all players.
    # Stored so a model loaded from disk reports its own bracket.
    target_badge: float | None = None

    # -- prediction ------------------------------------------------------

    def _contexts(self, state: GameState, archetype_id: int) -> list[tuple[int, ...]]:
        """The key tuple to look up at each level, for one archetype."""
        prev1 = state.last_items[-1] if state.last_items else NO_ITEM
        prev2 = state.last_items[-2] if len(state.last_items) > 1 else NO_ITEM
        values = {
            "hero_id": int(state.hero_id),
            "archetype_id": int(archetype_id),
            "prev1": int(prev1),
            "prev2": int(prev2),
            "n_owned": int(state.n_bought),
            "time_bucket": int(np.digitize(state.game_time_s, TIME_BUCKET_BOUNDS_S)),
        }
        return [tuple(values[k] for k in level.keys) for level in self.levels]

    def _chain(self, state: GameState, archetype_id: int):
        """Run the backoff chain for one archetype.

        Returns (item_ids, probability, contributions, lambdas, raw counts).
        `contributions` has one row per level, giving how much probability
        that level added to each item. `evidence` uses it to find the level
        that mattered most.
        """
        contexts = self._contexts(state, archetype_id)

        # Put every level's items on one shared index, so mixing levels is
        # array arithmetic.
        seen = [
            ids
            for level, context in zip(self.levels, contexts)
            for ids, _, _ in [level.lookup(context)]
            if len(ids)
        ]
        n_levels = len(self.levels)
        if not seen:
            return (
                _EMPTY_INT,
                _EMPTY_FLOAT,
                np.empty((n_levels, 0)),
                np.zeros(n_levels),
                np.zeros(n_levels, dtype=int),
            )
        items = np.unique(np.concatenate(seen))
        index = {int(item): i for i, item in enumerate(items)}

        locals_: list[np.ndarray] = []
        lambdas = np.zeros(n_levels)
        counts = np.zeros(n_levels, dtype=int)
        for depth, (level, context) in enumerate(zip(self.levels, contexts)):
            ids, weights, raw = level.lookup(context)
            row = np.zeros(len(items))
            total = float(weights.sum())
            if total > 0:
                for item, weight in zip(ids, weights):
                    row[index[int(item)]] = weight / total
            locals_.append(row)
            lambdas[depth] = total / (total + self.kappa) if total > 0 else 0.0
            counts[depth] = raw

        # Mix from L5 up to L0. Each level blends its own table with the
        # result so far.
        probability = np.zeros(len(items))
        for depth in range(n_levels - 1, -1, -1):
            lam = lambdas[depth]
            probability = lam * locals_[depth] + (1.0 - lam) * probability

        # A level's contribution is its lambda times its table, scaled by the
        # weight that the more specific levels left over.
        contributions = np.zeros((n_levels, len(items)))
        remaining = 1.0
        for depth in range(n_levels):
            lam = lambdas[depth]
            contributions[depth] = remaining * lam * locals_[depth]
            remaining *= 1.0 - lam

        return items, probability, contributions, lambdas, counts

    def _posterior(self, state: GameState) -> dict[int, float]:
        """Archetype probabilities for this state.

        Uses the state's own posterior if it has one; a chosen archetype is a
        posterior of 1.0 on that archetype. Otherwise falls back to how often
        each of the hero's archetypes is played.
        """
        if state.archetype_posterior:
            total = sum(state.archetype_posterior.values())
            if total > 0:
                return {a: p / total for a, p in state.archetype_posterior.items()}
        shares = (self.archetype_shares or {}).get(int(state.hero_id))
        return dict(shares) if shares else {0: 1.0}

    def distribution(
        self, state: GameState, *, mask_owned: bool = True
    ) -> tuple[np.ndarray, np.ndarray]:
        """P(next item), averaged over the archetype posterior.

        Owned items are removed here, after the levels are mixed. Removing them
        inside each level would renormalize each level over a different set of
        items, and the lambdas would no longer mean what they say.
        """
        totals: dict[int, float] = {}
        for archetype_id, share in self._posterior(state).items():
            items, probability, _, _, _ = self._chain(state, archetype_id)
            for item, p in zip(items, probability):
                totals[int(item)] = totals.get(int(item), 0.0) + share * p

        if not totals:
            return _EMPTY_INT, _EMPTY_FLOAT
        items = np.array(sorted(totals), dtype=np.int64)
        probability = np.array([totals[int(i)] for i in items], dtype=float)

        if mask_owned and state.owned_item_ids:
            keep = ~np.isin(items, list(state.owned_item_ids))
            items, probability = items[keep], probability[keep]
        total = probability.sum()
        if total > 0:
            probability = probability / total
        return items, probability

    def evidence(self, state: GameState, item_id: int) -> Evidence | None:
        """The per-level trace for one item, under the most likely archetype."""
        posterior = self._posterior(state)
        archetype_id = max(posterior, key=posterior.get)
        items, probability, contributions, lambdas, counts = self._chain(
            state, archetype_id
        )
        where = np.flatnonzero(items == item_id)
        if not len(where):
            return None
        col = int(where[0])
        per_level = contributions[:, col]
        dominant = (
            int(np.argmax(per_level)) if per_level.max() > 0 else len(self.levels) - 1
        )
        return Evidence(
            item_id=int(item_id),
            probability=float(probability[col]),
            level=self.levels[dominant].name,
            n=int(counts[dominant]),
            context=self._contexts(state, archetype_id)[dominant],
            lambdas=tuple(float(x) for x in lambdas),
            contributions=tuple(float(x) for x in per_level),
        )

    def predict(
        self,
        state: GameState,
        *,
        top: int = 10,
        affordable_only: bool = True,
        candidates: Sequence[int] | None = None,
    ) -> list[Recommendation]:
        """The top next items, each with the level and count behind it.

        Filters to `candidates` if given, otherwise to items the player can
        afford (unless `affordable_only` is False).
        """
        items = assets.shopable_items()
        ids, probability = self.distribution(state)
        if not len(ids):
            return []

        allowed: set[int] | None = None
        if candidates is not None:
            allowed = set(candidates)
        elif affordable_only:
            allowed = {i for i, it in items.items() if it.cost <= state.souls_available}

        out: list[Recommendation] = []
        for idx in np.argsort(-probability):
            item_id = int(ids[idx])
            if allowed is not None and item_id not in allowed:
                continue
            item = items.get(item_id)
            if item is None:
                continue
            trace = self.evidence(state, item_id)
            out.append(
                Recommendation(
                    item_id=item_id,
                    item_name=item.name,
                    probability=float(probability[idx]),
                    n=trace.n if trace else 0,
                    backoff_level=trace.level if trace else self.levels[-1].name,
                    cost=item.cost,
                )
            )
            if len(out) >= top:
                break
        return out

    def explain(self, state: GameState, item_id: int) -> str:
        """One line per level: context, raw n, lambda, local P, contribution."""
        items = assets.shopable_items()
        name = items[item_id].name if item_id in items else str(item_id)
        posterior = self._posterior(state)
        archetype_id = max(posterior, key=posterior.get)
        trace = self.evidence(state, item_id)
        if trace is None:
            return f"{name}: no level has seen this item in this context."

        contexts = self._contexts(state, archetype_id)
        lines = [
            f"{name} for hero {state.hero_id} (archetype {archetype_id}), "
            f"{state.n_bought} bought, t={state.game_time_s:.0f}s"
        ]
        for depth, level in enumerate(self.levels):
            ids, weights, raw = level.lookup(contexts[depth])
            total = float(weights.sum())
            local = 0.0
            if total > 0:
                hit = np.flatnonzero(ids == item_id)
                if len(hit):
                    local = float(weights[hit[0]] / total)
            keys = ",".join(f"{k}={v}" for k, v in zip(level.keys, contexts[depth]))
            lines.append(
                f"  {level.name} ({keys})  n={raw:<7,} "
                f"lambda={trace.lambdas[depth]:.2f}  P={local:.4f}  -> "
                f"{trace.contributions[depth]:.4f}"
            )
        lines.append(
            f"  total P={trace.probability:.4f}   "
            f"dominant {trace.level} (n={trace.n:,})"
        )
        return "\n".join(lines)

    # -- persistence -----------------------------------------------------

    def save(self, path: Path) -> Path:
        """Save the arrays to `path` (.npz) and the index to .index.json.

        Don't switch this to pickle. A pickle can't be read by hand and can
        break between library versions.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        arrays: dict[str, np.ndarray] = {}
        index: dict = {
            "kappa": self.kappa,
            "target_badge": self.target_badge,
            "archetype_shares": {
                str(h): {str(a): p for a, p in shares.items()}
                for h, shares in (self.archetype_shares or {}).items()
            },
            "levels": [],
        }
        for level in self.levels:
            arrays[f"{level.name}_item_ids"] = level.item_ids
            arrays[f"{level.name}_weights"] = level.weights
            arrays[f"{level.name}_counts"] = level.counts
            index["levels"].append(
                {
                    "name": level.name,
                    "keys": list(level.keys),
                    "contexts": [
                        list(key) + [start, stop]
                        for key, (start, stop) in level.offsets.items()
                    ],
                }
            )
        np.savez_compressed(path, **arrays)
        path.with_suffix(".index.json").write_text(json.dumps(index))
        return path

    @classmethod
    def load(cls, path: Path) -> SequenceModel:
        path = Path(path)
        arrays = np.load(path)
        index = json.loads(path.with_suffix(".index.json").read_text())
        levels = []
        for spec in index["levels"]:
            name = spec["name"]
            width = len(spec["keys"])
            offsets = {
                tuple(row[:width]): (row[width], row[width + 1])
                for row in spec["contexts"]
            }
            levels.append(
                Level(
                    name=name,
                    keys=tuple(spec["keys"]),
                    offsets=offsets,
                    item_ids=arrays[f"{name}_item_ids"],
                    weights=arrays[f"{name}_weights"],
                    counts=arrays[f"{name}_counts"],
                )
            )
        shares = {
            int(h): {int(a): float(p) for a, p in v.items()}
            for h, v in index.get("archetype_shares", {}).items()
        }
        badge = index.get("target_badge")
        return cls(
            levels=tuple(levels),
            kappa=float(index["kappa"]),
            archetype_shares=shares or None,
            target_badge=None if badge is None else float(badge),
        )


def fit(
    purchases: pd.DataFrame,
    archetypes: pd.DataFrame | None = None,
    *,
    kappa: float = DEFAULT_KAPPA,
    weights: np.ndarray | None = None,
    target_badge: float | None = None,
    badge_halfwidth: float = DEFAULT_BADGE_HALFWIDTH,
    levels: Sequence[int] | None = None,
) -> SequenceModel:
    """Build every backoff table from the training purchases.

    To weight toward a badge, pass `target_badge` rather than `weights`.
    `prepare` re-sorts the rows, so weights computed on the caller's row order
    would land on the wrong rows without any error. `fit` computes badge
    weights after the sort.

    Compute weights from the training split only. Weights computed on a frame
    that includes held-out rows leak those rows into the tables, and nothing
    in the score shows it.
    """
    df = prepare(purchases, archetypes)
    if weights is not None and target_badge is not None:
        raise ValueError("pass either weights or target_badge, not both")
    if weights is None and target_badge is not None:
        weights = row_weights(
            df, target_badge=target_badge, badge_halfwidth=badge_halfwidth
        )
    if weights is None:
        weights = np.ones(len(df), dtype=np.float64)
    else:
        weights = np.asarray(weights, dtype=np.float64)
        if len(weights) != len(df):
            raise ValueError(
                f"weights has {len(weights)} rows, prepared frame has {len(df)}"
            )

    wanted = range(len(LEVEL_KEYS)) if levels is None else levels
    built = []
    for depth in wanted:
        level = _build_level(df, LEVEL_NAMES[depth], LEVEL_KEYS[depth], weights)
        log.info(
            "built %s: %d rows, %d contexts",
            level.name,
            len(level.item_ids),
            len(level.offsets),
        )
        built.append(level)

    return SequenceModel(
        levels=tuple(built),
        kappa=kappa,
        archetype_shares=_archetype_shares(df),
        target_badge=target_badge,
    )


def _archetype_shares(df: pd.DataFrame) -> dict[int, dict[int, float]]:
    """Each archetype's share of its hero's players, as {hero: {archetype: share}}."""
    players = df[
        ["match_id", "player_slot", "hero_id", "archetype_id"]
    ].drop_duplicates()
    counts = players.groupby(["hero_id", "archetype_id"]).size()
    out: dict[int, dict[int, float]] = {}
    for (hero, archetype), n in counts.items():
        out.setdefault(int(hero), {})[int(archetype)] = float(n)
    for hero, shares in out.items():
        total = sum(shares.values())
        out[hero] = {a: n / total for a, n in shares.items()}
    return out
