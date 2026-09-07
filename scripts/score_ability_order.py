"""Score the ability-order model against the baselines it has to beat.

The item model clears a 0.267 bigram. That bar means nothing here: ability
order has **four** outcomes rather than 173, so a coin-flip scores 0.25 and a
positional lookup scores far more. A number like "0.6 top-1" is meaningless
until it is put beside what a trivial rule gets on the same decisions, which is
the correction `docs/DIAGNOSIS.md` records for the item baselines.

Every candidate here respects the one hard rule of an ability order -- a slot
at level 4 cannot take another point -- so the baselines are not handicapped
against the model.

    python scripts/score_ability_order.py [--matches N] [--hero NAME]
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from deadlock import abilityorder, assets, splits  # noqa: E402
from deadlock.state import GameState  # noqa: E402

ABILITIES = Path("data/processed/abilities.parquet")
ARCHETYPES = Path("data/processed/archetypes.parquet")
PURCHASES = Path("data/processed/purchases.parquet")


def load(matches: int | None, hero_id: int | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = pd.read_parquet(ABILITIES)
    if hero_id is not None:
        df = df[df["hero_id"] == hero_id]
    if matches:
        keep = df["match_id"].drop_duplicates().head(matches)
        df = df[df["match_id"].isin(keep)]
    # account_id lives on the purchase table; the account split needs it.
    accounts = (
        pd.read_parquet(PURCHASES, columns=["match_id", "player_slot", "account_id"])
        .drop_duplicates(["match_id", "player_slot"])
    )
    df = df.merge(accounts, on=["match_id", "player_slot"], how="left")
    return df, pd.read_parquet(ARCHETYPES)


def sequences(frame: pd.DataFrame, labels: pd.Series) -> list[tuple[int, int, list[int], list[float]]]:
    """(hero, archetype, slot sequence, times) per player."""
    out = []
    for (match_id, slot), group in frame.groupby(["match_id", "player_slot"], sort=False):
        out.append(
            (
                int(group["hero_id"].iloc[0]),
                int(labels.get((match_id, slot), 0)),
                group["item_id"].tolist(),
                group["buy_time_s"].tolist(),
            )
        )
    return out


def legal(levels: Counter) -> list[int]:
    """Slots that can still take a point."""
    return [
        slot
        for slot in range(1, abilityorder.N_SLOTS + 1)
        if levels[slot] < abilityorder.MAX_LEVEL
    ]


def build_baselines(train: pd.DataFrame, labels: pd.Series) -> dict:
    """Three trivial rules, each keyed the way a person would guess."""
    overall: dict[int, Counter] = defaultdict(Counter)
    positional: dict[tuple[int, int, int], Counter] = defaultdict(Counter)
    bigram: dict[tuple[int, int, int], Counter] = defaultdict(Counter)
    for hero, archetype, slots, _times in sequences(train, labels):
        previous = 0
        for position, slot in enumerate(slots):
            overall[hero][slot] += 1
            positional[(hero, archetype, position)][slot] += 1
            bigram[(hero, archetype, previous)][slot] += 1
            previous = slot
    return {"overall": overall, "positional": positional, "bigram": bigram}


def _pick(counter: Counter, allowed: list[int]) -> int | None:
    for slot, _n in counter.most_common():
        if slot in allowed:
            return int(slot)
    return None


def score(model, test: pd.DataFrame, labels: pd.Series, baselines: dict, limit: int) -> dict:
    """Teacher-forced next-slot accuracy for the model and every baseline."""
    hits = Counter()
    level_counts: Counter = Counter()
    total = 0

    for hero, archetype, slots, times in sequences(test, labels):
        levels: Counter = Counter()
        for position, actual in enumerate(slots):
            if total >= limit:
                break
            allowed = legal(levels)
            if len(allowed) <= 1:
                # No decision to make; scoring it would inflate every rule.
                levels[actual] += 1
                continue

            state = GameState(
                hero_id=hero,
                game_time_s=float(times[position]),
                souls_available=0,
                purchased=tuple(slots[:position]),
                archetype_posterior={archetype: 1.0},
            )
            ids, probability = model.distribution(state, mask_owned=False)
            chosen = None
            if len(ids):
                for index in np.argsort(-probability):
                    if int(ids[index]) in allowed:
                        chosen = int(ids[index])
                        break
            if chosen == actual:
                hits["model"] += 1
                trace = model.evidence(state, actual)
                if trace:
                    level_counts[trace.level] += 1

            previous = slots[position - 1] if position else 0
            for name, key, table in (
                ("overall", hero, baselines["overall"]),
                ("positional", (hero, archetype, position), baselines["positional"]),
                ("bigram", (hero, archetype, previous), baselines["bigram"]),
            ):
                guess = _pick(table.get(key, Counter()), allowed)
                if guess == actual:
                    hits[name] += 1
            if _pick(Counter({slot: 1 for slot in allowed}), allowed) is not None:
                hits["chance"] += 1.0 / len(allowed)

            levels[actual] += 1
            total += 1
        if total >= limit:
            break

    return {
        "n_decisions": total,
        "scores": {name: hits[name] / total for name in
                   ("model", "bigram", "positional", "overall", "chance")} if total else {},
        "levels": dict(level_counts),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matches", type=int, default=20000)
    parser.add_argument("--hero", type=str, default=None)
    parser.add_argument("--limit", type=int, default=20000, help="decisions to score")
    args = parser.parse_args()

    hero_id = None
    if args.hero:
        heroes = {h.name.lower(): i for i, h in assets.playable_heroes().items()}
        hero_id = heroes[args.hero.lower()]

    df, archetypes = load(args.matches, hero_id)
    labels = archetypes.set_index(["match_id", "player_slot"])["archetype_id"]
    print(f"{len(df):,} ability points, {df['match_id'].nunique():,} matches")

    for split_name, splitter in (
        ("match", splits.split_by_match),
        ("account", splits.split_by_account),
        ("time", splits.split_by_time),
    ):
        train_raw, test_raw = splitter(df)
        model = abilityorder.fit(train_raw, archetypes)
        train = abilityorder.point_frame(train_raw)
        test = abilityorder.point_frame(test_raw)
        baselines = build_baselines(train, labels)
        result = score(model, test, labels, baselines, args.limit)
        scores = result["scores"]
        print(
            f"\nsplit by {split_name}: {result['n_decisions']:,} decisions"
            f"\n  model      {scores['model']:.3f}"
            f"\n  bigram     {scores['bigram']:.3f}"
            f"\n  positional {scores['positional']:.3f}"
            f"\n  overall    {scores['overall']:.3f}"
            f"\n  chance     {scores['chance']:.3f}"
        )
        if split_name == "match":
            print(f"  levels carrying a hit: {result['levels']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
