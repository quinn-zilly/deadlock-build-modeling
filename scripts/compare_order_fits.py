#!/usr/bin/env python
"""Test whether ability point order belongs in the archetype clustering (ADR 0003).

Fits every hero four ways, from the same purchase table in one run:

    families      build family shares alone (the control)
    order         `point_order_features`, raw
    order_mean    the same twelve columns minus the hero's mean
    order_rank    the same twelve columns as a percentile within the hero

The two relative forms were the proposal, because raw order is mostly the
same for everyone on a hero. Raw `order` is included to check that.

The rule was written down before the results and applied as written:

    R1  No hero loses a split it had with build families alone.
    R2  At least one hero gains a split. A block that changes no k adds
        complexity for nothing.
    R3  The separating items don't concentrate. No single item may separate
        more than MAX_TOP_ITEM_SHARE of split heroes, and the top three
        items' share may not exceed MAX_CONCENTRATION_RATIO times the
        families control from the same run.

Next-item accuracy is the other test, run separately by
`score_archetype_fits.py --blocks`, because it needs a train/test split.

    python scripts/compare_order_fits.py [--out docs/ORDER-FIT-COMPARISON.md] [--from-csv]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Reuse the imbue comparison's code so the two sheets are comparable.
from compare_imbue_fits import COLUMNS, PURCHASES, hero_rows  # noqa: E402

from deadlock import abilities, archetype  # noqa: E402

ABILITIES = Path("data/processed/abilities.parquet")

# The weight the block would ship at: as much total weight as the families.
ORDER_WEIGHT = 1.0

# R3 thresholds, set before the results.
MAX_TOP_ITEM_SHARE = 0.25
MAX_CONCENTRATION_RATIO = 2.0

FITS = ("families", "order", "order_mean", "order_rank")
CANDIDATES = ("order", "order_mean", "order_rank")


def item_concentration(table: pd.DataFrame, fit: str) -> dict:
    """For one fit: split heroes, the most common separating item, and its share and the top three's."""
    split = table[(table["fit"] == fit) & (table["k"] > 1)]
    n = len(split)
    if not n:
        return {"n": 0, "top_item": "", "top_share": 0.0, "top3_share": 0.0}
    counts = split["item"].value_counts()
    return {
        "n": n,
        "top_item": str(counts.index[0]),
        "top_share": float(counts.iloc[0]) / n,
        "top3_share": float(counts.iloc[:3].sum()) / n,
    }


def verdict_lines(table: pd.DataFrame) -> tuple[list[str], dict[str, bool]]:
    """Apply R1-R3 to the results. Returns the verdict lines and which fits pass."""
    ks = table.pivot(index="hero", columns="fit", values="k")
    base = item_concentration(table, "families")
    lines = [
        f"Families control: {base['n']} split heroes, top separating item "
        f"{base['top_item']!r} carries {base['top_share']:.0%}, "
        f"top three carry {base['top3_share']:.0%}.",
        "",
    ]
    kept: dict[str, bool] = {}
    for fit in CANDIDATES:
        lost = sorted(ks.index[ks[fit] < ks["families"]])
        gained = sorted(ks.index[ks[fit] > ks["families"]])
        conc = item_concentration(table, fit)
        r1 = not lost
        r2 = bool(gained)
        r3 = conc["top_share"] <= MAX_TOP_ITEM_SHARE and (
            base["top3_share"] <= 0
            or conc["top3_share"] <= base["top3_share"] * MAX_CONCENTRATION_RATIO
        )
        kept[fit] = r1 and r2 and r3
        lines += [
            f"### `{fit}`",
            "",
            f"- Splits gained: {', '.join(gained) if gained else 'none'}",
            f"- Splits **lost**: {', '.join(lost) if lost else 'none'}",
            f"- Split heroes: {conc['n']}; top separating item "
            f"{conc['top_item']!r} at {conc['top_share']:.0%}, "
            f"top three at {conc['top3_share']:.0%}",
            f"- **R1 no hero loses a split: {'yes' if r1 else 'NO'}. "
            f"R2 a hero gains a split: {'yes' if r2 else 'NO'}. "
            f"R3 separating items don't concentrate: "
            f"{'yes' if r3 else 'NO'}.**",
            "",
            (
                f"`{fit}` passes the rule and stays a candidate; next-item "
                "accuracy decides."
                if kept[fit]
                else f"`{fit}` fails the rule and stays out of the clustering."
            ),
            "",
        ]
    return lines, kept


def sheet(table: pd.DataFrame, verdict: list[str]) -> str:
    """The comparison sheet as markdown."""
    wide = table.pivot(index="hero", columns="fit", values="k")
    items = table.pivot(index="hero", columns="fit", values="item")
    seps = table.pivot(index="hero", columns="fit", values="separation")

    lines = [
        "# Does ability point order belong in the archetype clustering?",
        "",
        "Generated by `scripts/compare_order_fits.py`. The decision is ADR 0003.",
        "",
        "Four fits of the same purchase table in one run. `families` uses build",
        "family shares alone and `order` adds `point_order_features` as is.",
        "`order_mean` and `order_rank` add the same twelve columns relative to",
        "the hero: minus the hero's mean, and as a percentile within the hero.",
        "",
        "The separating item is the item with the biggest pick-rate gap between",
        "the fit's two least distinct clusters. It shows what a split rests on.",
        "",
        "Don't compare separation across columns where k differs: separation",
        "falls as k rises, and a hero with no split reports the score of its",
        "rejected split. Read each separation next to its k.",
        "",
        "| hero | " + " | ".join(f"k {f}" for f in FITS) + " | sep families "
        "| sep order_mean | separating item (families) "
        "| separating item (order_mean) |",
        "|---|" + "---|" * (len(FITS) + 4),
    ]

    def cell(hero: str, fit: str) -> str:
        item = items.loc[hero, fit]
        if pd.isna(item) or not str(item):
            return "--"
        return str(item)

    def sep(hero: str, fit: str) -> str:
        value = seps.loc[hero, fit]
        return "--" if pd.isna(value) else f"{float(value):.2f}"

    for hero in sorted(wide.index):
        ks = " | ".join(str(int(wide.loc[hero, f])) for f in FITS)
        lines.append(
            f"| {hero} | {ks} | {sep(hero, 'families')} "
            f"| {sep(hero, 'order_mean')} | {cell(hero, 'families')} "
            f"| {cell(hero, 'order_mean')} |"
        )

    lines += ["", "## Verdict", ""] + verdict + [""]
    return "\n".join(lines)


def report(table: pd.DataFrame, out: Path) -> None:
    """Write the sheet to `out` and print the verdict."""
    verdict, kept = verdict_lines(table)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(sheet(table, verdict), encoding="utf-8")
    for line in verdict:
        print(line)
    print(f"\nwrote {out}")
    survivors = ", ".join(fit for fit, ok in kept.items() if ok) or "none"
    print(f"fits that pass the clustering rule: {survivors}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--out",
        default="docs/ORDER-FIT-COMPARISON.md",
        help="where to write the sheet; the csv goes beside it (default: %(default)s)",
    )
    parser.add_argument(
        "--from-csv",
        action="store_true",
        help="rewrite the sheet from the last run's csv instead of refitting",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S"
    )
    out = Path(args.out)
    if args.from_csv:
        report(pd.read_csv(out.with_suffix(".csv")), out)
        return 0

    if not PURCHASES.exists() or not ABILITIES.exists():
        logging.error("needs %s and %s; run scripts/refit.py first", PURCHASES, ABILITIES)
        return 1

    purchases = pd.read_parquet(PURCHASES, columns=COLUMNS)
    ability_rows = pd.read_parquet(ABILITIES)
    logging.info(
        "%s purchases, %s ability points",
        f"{len(purchases):,}",
        f"{len(ability_rows):,}",
    )

    raw = abilities.point_order_features(ability_rows)
    blocks = {
        "families": None,
        "order": archetype.scale_block(raw, ORDER_WEIGHT),
        "order_mean": archetype.scale_block(
            abilities.residual_point_order_features(ability_rows, form="mean"),
            ORDER_WEIGHT,
        ),
        "order_rank": archetype.scale_block(
            abilities.residual_point_order_features(ability_rows, form="rank"),
            ORDER_WEIGHT,
        ),
    }

    table = pd.DataFrame(hero_rows(purchases, blocks))
    table.to_csv(out.with_suffix(".csv"), index=False)
    report(table, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
