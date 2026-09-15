#!/usr/bin/env python
"""Does ability point ORDER belong in the archetype clustering?

ADR 0001 rejected imbue from the clustering, and separately records that
ability *state* was tried and degraded every hero. It is explicit that ability
**order** -- how far into a player's spending each ability reached each level
-- was never tested there. This is that measurement, not a re-litigation.

Four fits over every hero, from the same purchase table in the same run:

    families      build-family shares alone -- the baseline the rule protects
    order         `point_order_features`, raw
    order_mean    the same twelve columns minus the hero's own mean
    order_rank    the same twelve columns as a within-hero percentile

The residual forms are the proposal. Raw order is largely hero-constant, so a
raw block mostly re-encodes hero identity, which `fit_hero` already conditions
on by running one hero at a time. `order` is carried anyway, because "the
residual is the load-bearing part" is a claim, and a claim with no control is
an assertion.

**The rule is pre-committed and applied as written**, copying ADR 0001's
discipline: written down before the numbers, and not renegotiated after.

    R1  No hero loses a split it had under build families alone.
    R2  The block gains something: at least one hero gains a split. A block
        that changes no k is complexity with no result, and stays out.
    R3  Separating items do not concentrate. Unlike imbue, this block is not
        derived from any item, so the structural version of the test is
        vacuous -- report it anyway as a guard against a degenerate split:
        no single item may carry the separating role for more than
        `MAX_TOP_ITEM_SHARE` of split heroes, and the top-three share may not
        exceed `MAX_CONCENTRATION_RATIO` times the families control measured
        in this same run.

Held-out next-item accuracy is the fourth leg and it is *not* here:
`scripts/score_archetype_fits.py --block` measures it, in its own single run,
because that comparison needs a train/test split this script has no use for.

    python scripts/compare_order_fits.py [--out docs/ORDER-FIT-COMPARISON.md]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# The families control is the same code path as the imbue comparison's, not a
# reimplementation of it -- that is what makes the two sheets comparable.
from compare_imbue_fits import COLUMNS, PURCHASES, hero_rows  # noqa: E402

from deadlock import abilities, archetype  # noqa: E402

ABILITIES = Path("data/processed/abilities.parquet")

# Full mass, the weight the shipped fit would use. Sweeping weights is a
# different question; this one is whether the block belongs at the weight it
# would ship at.
ORDER_WEIGHT = 1.0

# Fixed before the numbers.
MAX_TOP_ITEM_SHARE = 0.25
MAX_CONCENTRATION_RATIO = 2.0

FITS = ("families", "order", "order_mean", "order_rank")
CANDIDATES = ("order", "order_mean", "order_rank")


def item_concentration(table: pd.DataFrame, fit: str) -> dict:
    """How far the separating role concentrates in a few items, for one fit."""
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
    """Apply the pre-committed rule to a finished table."""
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
            f"R3 separating items do not concentrate: "
            f"{'yes' if r3 else 'NO'}.**",
            "",
            (
                f"The pre-committed rule keeps `{fit}` as a candidate; the "
                "held-out score decides."
                if kept[fit]
                else f"The pre-committed rule removes `{fit}` from the clustering."
            ),
            "",
        ]
    return lines, kept


def sheet(table: pd.DataFrame, verdict: list[str]) -> str:
    wide = table.pivot(index="hero", columns="fit", values="k")
    items = table.pivot(index="hero", columns="fit", values="item")
    seps = table.pivot(index="hero", columns="fit", values="separation")

    lines = [
        "# Does ability point order belong in the archetype clustering?",
        "",
        "Four fits over the same purchase table in the same run. `families` is",
        "build-family shares alone, `order` is `point_order_features` raw, and",
        "`order_mean` and `order_rank` are the same twelve columns residualised",
        "against the hero's own average -- a difference from the hero mean and a",
        "within-hero percentile respectively.",
        "",
        "The separating item is the item carrying each fit's weakest cluster",
        "pair: the claim behind the separation score, and the thing that says",
        "whether a split is a playstyle or a restatement of the block.",
        "",
        "Separation is **not comparable across columns** where k differs -- it",
        "falls when k rises, and a hero that did not split reports the score of",
        "a rejected candidate. Read the k columns; the separations are here to",
        "be read next to a k, not across a row.",
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
    verdict, kept = verdict_lines(table)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(sheet(table, verdict), encoding="utf-8")
    for line in verdict:
        print(line)
    print(f"\nwrote {out}")
    survivors = ", ".join(fit for fit, ok in kept.items() if ok) or "none"
    print(f"candidates surviving the clustering rule: {survivors}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="docs/ORDER-FIT-COMPARISON.md")
    parser.add_argument(
        "--from-csv",
        action="store_true",
        help="re-render the sheet from the last run's csv instead of refitting",
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
        logging.error("need %s and %s", PURCHASES, ABILITIES)
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
