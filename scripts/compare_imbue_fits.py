#!/usr/bin/env python
"""Does the imbue block belong in the archetype clustering?

Three fits over every hero, from the same purchase table in the same run:

    families      build-family shares alone -- the baseline the rule protects
    imbue         the first attempt: shares, depth and `has_imbue`
    conditional   direction only, non-imbuers placed at their hero's mean

The first attempt was rejected because it split heroes on *whether* a build
bought an imbueable item rather than on which ability it aimed at: nine
imbueable items out of 173 shopable supplied the separating item for 27 of 33
split heroes, and four heroes lost a genuine split when a sharp 6-11% niche
displaced their broad playstyle split. So this reports, per hero, the k each
fit reached and the item carrying its weakest pair -- the claim behind the
score, which is what shows whether a split is a playstyle or an ownership flag.

**The rule is pre-committed and applied as written.** The conditional block
stays in the clustering only if no hero loses a split it had under build
families alone, and the concentration of imbueable items among the separating
items drops materially. Otherwise imbue leaves the clustering and serves naming
and advice only.

    python scripts/compare_imbue_fits.py [--out docs/IMBUE-FIT-COMPARISON.md]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from deadlock import archetype, assets, imbue  # noqa: E402

PURCHASES = Path("data/processed/purchases.parquet")
IMBUES = Path("data/processed/imbues.parquet")
COLUMNS = ["match_id", "player_slot", "hero_id", "item_id"]

# Full mass, the weight the shipped fit uses. Sweeping weights is a different
# question; this one is whether the block belongs at the weight it ships at.
IMBUE_WEIGHT = 1.0

# "Materially" fixed before the numbers, so it cannot be renegotiated after.
# The first attempt concentrated 27 of 33, or 82%; half of that is the bar.
MATERIAL_DROP = 0.5


def hero_rows(
    purchases: pd.DataFrame, blocks: dict[str, pd.DataFrame | None]
) -> list[dict]:
    """One row per hero per fit: k, separation, and the item carrying it."""
    hero_names = {h: v.name for h, v in assets.load_heroes().items()}
    item_names = {i: it.name for i, it in assets.load_items().items()}
    imbueable = set(imbue.imbueable_items())
    rows = []
    for hero_id, group in purchases.groupby("hero_id"):
        name = hero_names.get(int(hero_id), str(hero_id))
        for fit_name, extra in blocks.items():
            fit = archetype.fit_hero(
                group, hero_id=int(hero_id), hero_name=name, extra=extra
            )
            item_id = gap = None
            if fit.split:
                found = archetype.separating_item(
                    archetype.cluster_prevalence(group, fit.labels)
                )
                if found is not None:
                    item_id, gap = found
            rows.append(
                {
                    "hero_id": int(hero_id),
                    "hero": name,
                    "fit": fit_name,
                    "k": fit.k,
                    "separation": fit.separation if fit.split else float("nan"),
                    "item_id": item_id,
                    "item": item_names.get(item_id, "") if item_id else "",
                    "imbueable": bool(item_id in imbueable) if item_id else False,
                    "gap": gap,
                }
            )
            logging.info(
                "  %-14s %-11s k=%d %s",
                name,
                fit_name,
                fit.k,
                f"on {item_names.get(item_id, item_id)}" if item_id else "",
            )
    return rows


def concentration(table: pd.DataFrame, fit: str) -> tuple[int, int]:
    """Split heroes whose separating item is imbueable, out of split heroes."""
    split = table[(table["fit"] == fit) & (table["k"] > 1)]
    return int(split["imbueable"].sum()), len(split)


def sheet(table: pd.DataFrame, verdict: list[str]) -> str:
    wide = table.pivot(index="hero", columns="fit", values="k")
    items = table.pivot(index="hero", columns="fit", values="item")
    flags = table.pivot(index="hero", columns="fit", values="imbueable")

    lines = [
        "# Does imbue belong in the archetype clustering?",
        "",
        "Three fits over the same purchase table in the same run. `families` is",
        "build-family shares alone, `imbue` is the rejected first attempt with",
        "`has_imbue` and depth in the block, `conditional` is direction only",
        "with non-imbuers placed at their hero's mean.",
        "",
        "The separating item is the item carrying each fit's weakest cluster",
        "pair -- the claim behind the separation score. An asterisk marks one",
        "of the nine imbueable items. `split` is what the conditional block did",
        "to that hero against build families alone.",
        "",
        "| hero | k families | k imbue | k conditional | split "
        "| separating item (families) | separating item (conditional) |",
        "|---|---|---|---|---|---|---|",
    ]

    def cell(hero: str, fit: str) -> str:
        item = items.loc[hero, fit]
        # A hero that did not split under this fit has no separating item, and
        # a csv round trip turns that empty cell into NaN rather than "".
        if pd.isna(item) or not str(item):
            return "--"
        return f"{item} \\*" if flags.loc[hero, fit] else str(item)

    for hero in sorted(wide.index):
        base = int(wide.loc[hero, "families"])
        conditional = int(wide.loc[hero, "conditional"])
        verdict_cell = (
            "gained" if conditional > base
            else "**lost**" if conditional < base
            else "--"
        )
        lines.append(
            f"| {hero} | {base} | {int(wide.loc[hero, 'imbue'])} | {conditional} "
            f"| {verdict_cell} | {cell(hero, 'families')} "
            f"| {cell(hero, 'conditional')} |"
        )

    lines += ["", "## Verdict", ""] + verdict + [""]
    return "\n".join(lines)


def report(table: pd.DataFrame, out: Path) -> None:
    """Apply the pre-committed rule to a finished table and write the sheet."""
    ks = table.pivot(index="hero", columns="fit", values="k")
    lost = sorted(ks.index[(ks["conditional"] < ks["families"])])
    gained = sorted(ks.index[(ks["conditional"] > ks["families"])])
    lost_vs_imbue = sorted(ks.index[(ks["conditional"] < ks["imbue"])])

    base_hits, base_splits = concentration(table, "families")
    imbue_hits, imbue_splits = concentration(table, "imbue")
    cond_hits, cond_splits = concentration(table, "conditional")
    base_share = base_hits / base_splits if base_splits else 0.0
    imbue_share = imbue_hits / imbue_splits if imbue_splits else 0.0
    cond_share = cond_hits / cond_splits if cond_splits else 0.0

    no_loss = not lost
    dropped = cond_share <= imbue_share * MATERIAL_DROP
    keep = no_loss and dropped

    verdict = [
        f"- Splits gained against build families alone: "
        f"{', '.join(gained) if gained else 'none'}",
        f"- Splits **lost** against build families alone: "
        f"{', '.join(lost) if lost else 'none'}",
        f"- Splits lost against the rejected first attempt: "
        f"{', '.join(lost_vs_imbue) if lost_vs_imbue else 'none'}",
        f"- Separating item is imbueable: {base_hits} of {base_splits} split "
        f"heroes ({base_share:.0%}) under build families alone, "
        f"{imbue_hits} of {imbue_splits} ({imbue_share:.0%}) under the first "
        f"attempt, {cond_hits} of {cond_splits} ({cond_share:.0%}) under the "
        f"conditional block. The build-family figure is the control: it says "
        f"whether nine items out of 173 carry these splits because of the "
        f"heroes or because of the block.",
        "",
        f"**No hero loses a split: {'yes' if no_loss else 'NO'}. "
        f"Concentration drops by at least half: {'yes' if dropped else 'NO'}.**",
        "",
        (
            "The pre-committed rule keeps the conditional imbue block in the "
            "clustering."
            if keep
            else "The pre-committed rule removes imbue from the clustering. It "
            "serves naming and advice only."
        ),
    ]

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(sheet(table, verdict), encoding="utf-8")
    for line in verdict:
        print(line)
    print(f"\nwrote {out}")




def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="docs/IMBUE-FIT-COMPARISON.md")
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
        # The fit is seeded and the csv is its full output, so re-rendering the
        # prose around the same numbers does not need 38 heroes refitted three
        # ways again.
        table = pd.read_csv(out.with_suffix(".csv"))
        report(table, out)
        return 0

    if not PURCHASES.exists() or not IMBUES.exists():
        logging.error("need %s and %s", PURCHASES, IMBUES)
        return 1

    purchases = pd.read_parquet(PURCHASES, columns=COLUMNS)
    players = archetype.player_index(purchases)
    heroes = archetype.hero_of(purchases)
    imbue_rows = pd.read_parquet(IMBUES)

    blocks = {
        "families": None,
        "imbue": archetype.scale_block(
            imbue.imbue_features(imbue_rows, players=players), IMBUE_WEIGHT
        ),
        "conditional": archetype.scale_block(
            imbue.conditional_features(imbue_rows, players, heroes), IMBUE_WEIGHT
        ),
    }

    table = pd.DataFrame(hero_rows(purchases, blocks))

    table.to_csv(Path(args.out).with_suffix(".csv"), index=False)
    report(table, Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
