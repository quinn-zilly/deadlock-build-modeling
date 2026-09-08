"""Generate a build for every hero and archetype, and gate every one.

The gate runs on the **purchase sequence**, not the held inventory. About 31%
of purchases are components absorbed into a composite, so a 12-slot inventory
cannot hold every staple -- hero 4's first archetype has 12 staples, 7 of them
sold more than half the time. Gating held items would fail correct builds.

Exits non-zero if any cell fails, so this is usable as a regression check. That
is what makes it the gate for the badge weighting too: a build weighted toward
strong play still has to contain the staples of its archetype, and an item
bought by 70% of a cell that the weighting quietly drops fails here.

    python scripts/generate_builds.py [--hero NAME] [--export DIR] [--samples N]
                                      [--badge N|all]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from deadlock import (  # noqa: E402
    abilityorder,
    imbue,
    archetype,
    assets,
    build,
    buildfmt,
    evaluate,
    sequence,
)

PURCHASES = Path("data/processed/purchases.parquet")
ABILITIES = Path("data/processed/abilities.parquet")
IMBUES = Path("data/processed/imbues.parquet")
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
    parser.add_argument(
        "--badge",
        default=str(sequence.DEFAULT_TARGET_BADGE),
        help="badge to weight toward, or 'all' for the whole population",
    )
    args = parser.parse_args()

    labels, meta = archetype.load()
    heroes = {h: v.name for h, v in assets.playable_heroes().items()}
    item_names = {i: it.name for i, it in assets.load_items().items()}

    df = pd.read_parquet(PURCHASES, columns=COLUMNS)
    if args.hero:
        wanted = {name.lower(): h for h, name in heroes.items()}[args.hero.lower()]
        df = df[df["hero_id"] == wanted]

    target_badge = sequence.parse_target_badge(args.badge)
    print(f"weighting toward {sequence.describe_badge(target_badge)}")

    model = sequence.fit(df, labels, target_badge=target_badge)

    # The ability order is the other half of a build, and it is a separate
    # sequence over the same players -- same chain, four outcomes instead of
    # 173. Absent only if the ability table has not been built.
    ability_model = None
    ability_frame = None
    if ABILITIES.exists():
        raw = pd.read_parquet(ABILITIES)
        if args.hero:
            raw = raw[raw["hero_id"] == wanted]
        if target_badge is not None:
            raw = abilityorder.attach_badges(raw, df)
        ability_model = abilityorder.fit(raw, labels, target_badge=target_badge)
        ability_frame = abilityorder.point_frame(raw).merge(
            labels[["match_id", "player_slot", "archetype_id"]],
            on=["match_id", "player_slot"],
            how="left",
        )
    else:
        print("no ability table; builds will export without an ability order")

    # Which ability the population points each imbueable item at. Nine items,
    # so this is a small lookup, but it is the difference between exporting a
    # build that says "buy Mystic Reverb" and one that says what to do with it.
    imbues = pd.read_parquet(IMBUES) if IMBUES.exists() else pd.DataFrame()

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

            generated_ids = [item.item_id for item in generated.items]
            reference = evaluate.population_order(cell).index.tolist()
            order = evaluate.order_distance(generated_ids, reference)
            # Order comes from the median-buy-position reference; membership
            # must not. See evaluate.membership_vs_players for why.
            membership = evaluate.membership_vs_players(generated_ids, cell)
            order_rows.append(
                {
                    "build": generated.label,
                    "kendall_tau": order.kendall_tau,
                    "n_shared": order.n_shared,
                    "jaccard_12": membership.generated,
                    "ceiling_12": membership.ceiling,
                    "ratio": membership.ratio,
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

            ability_order = []
            if ability_model is not None:
                try:
                    ability_order = abilityorder.generate_order(
                        ability_model,
                        ability_frame,
                        int(hero_id),
                        archetype_id,
                        target_badge=target_badge,
                    )
                except ValueError as exc:
                    # A cell with no ability points is a data gap, not a build
                    # that happens to have no order. Say which, and move on.
                    print(f"  no ability order for {generated.label}: {exc}")

            buildfmt.export_build(
                generated,
                args.export / f"{hero_name}_{archetype_id}.json".replace(" ", "_"),
                ability_order=ability_order,
                imbue_targets=imbue.dominant_targets(
                    imbues.merge(
                        cell[["match_id", "player_slot"]].drop_duplicates(),
                        on=["match_id", "player_slot"],
                    )
                ) if len(imbues) else None,
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
            f"order vs population: median tau {reliable['kendall_tau'].median():+.3f} "
            f"({len(reliable)} of {len(orders)} reliable)"
        )
    scored = orders.dropna(subset=["ratio"])
    if len(scored):
        print(
            f"membership vs real players: mean J@12 "
            f"{scored['jaccard_12'].mean():.3f} against a player-vs-player "
            f"ceiling of {scored['ceiling_12'].mean():.3f} "
            f"({int((scored['ratio'] >= 1.0).sum())} of {len(scored)} cells "
            f"at or above the ceiling)"
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
