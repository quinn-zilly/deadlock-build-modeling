"""Generate a build for every hero and archetype, and gate every one.

The gate runs on the **purchase sequence**, not the held inventory. About 31%
of purchases are components absorbed into a composite, so a 12-slot inventory
cannot hold every staple -- hero 4's first archetype has 12 staples, 7 of them
sold more than half the time. Gating held items would fail correct builds.

Exits non-zero if any cell fails, so this is usable as a regression check.

    python scripts/generate_builds.py [--hero NAME] [--export DIR] [--samples N]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from deadlock import archetype, assets, build, buildfmt, evaluate, sequence  # noqa: E402

PURCHASES = Path("data/processed/purchases.parquet")
COLUMNS = [
    "match_id",
    "player_slot",
    "account_id",
    "hero_id",
    "item_id",
    "buy_index",
    "buy_time_s",
    "won",
    "average_badge",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hero", type=str, default=None)
    parser.add_argument("--export", type=Path, default=Path("data/builds"))
    parser.add_argument("--samples", type=int, default=0, help="calibration samples")
    parser.add_argument("--no-staples", action="store_true", help="greedy only (2a)")
    args = parser.parse_args()

    labels, meta = archetype.load()
    heroes = {h: v.name for h, v in assets.playable_heroes().items()}
    item_names = {i: it.name for i, it in assets.load_items().items()}

    df = pd.read_parquet(PURCHASES, columns=COLUMNS)
    if args.hero:
        wanted = {name.lower(): h for h, name in heroes.items()}[args.hero.lower()]
        df = df[df["hero_id"] == wanted]

    model = sequence.fit(df, labels)
    args.export.mkdir(parents=True, exist_ok=True)

    passed = failed = inconclusive = 0
    failures: list[str] = []
    order_rows: list[dict] = []

    for hero_id in sorted(df["hero_id"].unique()):
        hero_meta = meta["heroes"].get(str(hero_id), {})
        hero_name = heroes.get(int(hero_id), str(hero_id))
        hero_rows = df[df["hero_id"] == hero_id]

        for entry in hero_meta.get("archetypes", [{"archetype_id": 0, "name": hero_name}]):
            archetype_id = int(entry["archetype_id"])
            cell = hero_rows.merge(
                labels[
                    (labels["hero_id"] == hero_id)
                    & (labels["archetype_id"] == archetype_id)
                ][["match_id", "player_slot"]],
                on=["match_id", "player_slot"],
            )
            if cell.empty:
                continue

            prevalence = evaluate.item_prevalence(cell)
            staples = None
            if not args.no_staples:
                staples = {
                    int(i): float(v)
                    for i, v in prevalence[
                        prevalence >= evaluate.PREVALENCE_THRESHOLD
                    ].items()
                }

            generated = build.generate_build(
                int(hero_id),
                archetype_id,
                model,
                staples=staples,
                hero_name=hero_name,
                archetype_name=entry.get("name", ""),
            )
            result = evaluate.prevalence_gate(
                [item.item_id for item in generated.items],
                cell,
                hero_id=int(hero_id),
                archetype_id=archetype_id,
            )

            reference = evaluate.population_order(cell).index.tolist()
            order = evaluate.order_distance(
                [item.item_id for item in generated.items], reference
            )
            order_rows.append(
                {
                    "build": generated.label,
                    "kendall_tau": order.kendall_tau,
                    "n_shared": order.n_shared,
                    "jaccard_6": order.jaccard_6,
                    "jaccard_12": order.jaccard_12,
                    "reliable": order.reliable,
                }
            )

            if result.inconclusive:
                inconclusive += 1
                status = "INCONCLUSIVE"
            elif result.passed:
                passed += 1
                status = "pass"
            else:
                failed += 1
                status = "FAIL"
                names = [item_names.get(i, str(i)) for i in result.missing]
                failures.append(f"{generated.label}: missing {', '.join(names)}")

            print(
                f"{status:12s} {generated.label:34s} "
                f"{len(generated.items):2d} buys, {len(generated.held_items()):2d} held, "
                f"{len(result.staples):2d} staples, tau={order.kendall_tau:+.2f}"
            )

            buildfmt.export_build(
                generated,
                args.export / f"{hero_name}_{archetype_id}.json".replace(" ", "_"),
                description=(
                    "Purchase order. Only held items are exported: the build "
                    "schema cannot express a sale, and roughly a third of these "
                    "purchases are components absorbed into later items."
                ),
            )

            if args.samples:
                _report_calibration(
                    generated, model, int(hero_id), archetype_id, staples,
                    item_names, args.samples,
                )

    orders = pd.DataFrame(order_rows)
    reliable = orders[orders["reliable"]]
    print(f"\n{passed} passed, {failed} failed, {inconclusive} inconclusive")
    if len(reliable):
        print(
            f"order vs population: median tau {reliable['kendall_tau'].median():+.3f}, "
            f"median jaccard@12 {reliable['jaccard_12'].median():.3f} "
            f"({len(reliable)} of {len(orders)} reliable)"
        )
    for line in failures:
        print(f"  {line}")
    return 1 if failed else 0


def _report_calibration(
    generated, model, hero_id, archetype_id, staples, item_names, n
) -> None:
    """A staple appearing in 60% of sampled builds is a calibration problem
    that greedy generation hides."""
    if not staples:
        return
    samples = build.sample_builds(hero_id, archetype_id, model, n=n, staples=staples)
    for item_id, prevalence in sorted(staples.items(), key=lambda kv: -kv[1]):
        appeared = sum(
            1 for s in samples if any(i.item_id == item_id for i in s.items)
        )
        share = appeared / len(samples)
        if share < 0.9:
            print(
                f"     calibration: {item_names.get(item_id, item_id)} "
                f"in {share:.0%} of samples (prevalence {prevalence:.0%})"
            )


if __name__ == "__main__":
    raise SystemExit(main())
