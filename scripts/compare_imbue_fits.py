#!/usr/bin/env python
"""Test whether the imbue block belongs in the archetype clustering (ADR 0001).

Fits every hero three ways, from the same purchase table in one run:

    families      build family shares alone (the control)
    imbue         the first attempt: target shares, depth, and `has_imbue`
    conditional   target shares only, with non-imbuers at their hero's mean
    gated         the conditional block on contested heroes only (#40)
    gated9        the same, on the nine heroes #40 named (comparison only)

The first attempt split heroes on whether players bought an imbueable item,
not on what they aimed it at. The 9 imbueable items were the separating item
for 27 of 33 split heroes, and four heroes lost a real split to a 6-11% niche.
So for each hero and fit this reports k and the separating item.

The rule was written down before the results and applied as written. The
conditional block stays only if no hero loses a split it had with build
families alone, and the share of split heroes separated by an imbueable item
falls by at least MATERIAL_DROP. Otherwise imbue is used only for naming and
advice.

#40 asked whether the block works when given only to heroes whose players
disagree on where to aim an item (`imbue.gated_heroes`). Every other hero gets
no block, so its fit is identical to families alone, and the script checks
that. The gated fit has its own rule, posted on #40 before it was run: no hero
loses a split (R1), and at least one gated hero's split changes, with more
than half of the changed heroes separating on where players aimed the item
rather than on whether they bought it (R2). Held-out accuracy (R3) is scored
by `scripts/score_archetype_fits.py --blocks "gated imbue"`.

    python scripts/compare_imbue_fits.py [--out docs/IMBUE-FIT-COMPARISON.md] [--from-csv]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd
from sklearn.metrics import adjusted_rand_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from deadlock import archetype, assets, imbue  # noqa: E402

PURCHASES = Path("data/processed/purchases.parquet")
IMBUES = Path("data/processed/imbues.parquet")
COLUMNS = ["match_id", "player_slot", "hero_id", "item_id"]

# The weight the block would ship at: as much total weight as the families.
IMBUE_WEIGHT = 1.0

# The conditional block's imbueable-item share must be at most this fraction
# of the first attempt's (27 of 33, 82%). Set before the results.
MATERIAL_DROP = 0.5

# The gated fit's rule (#40), set before the results. A gated hero's split has
# changed when its k differs from families alone or its adjusted Rand index
# against the families labels is below CHANGED_ARI. A cluster needs
# MIN_CLUSTER_BUYERS buyers of an item before its aim at that item counts.
CHANGED_ARI = 0.80
MIN_CLUSTER_BUYERS = 30

# The heroes #40's text named as candidates from pooled entropy. Reported for
# comparison; the verdict rests on `gated`.
TICKET_CANDIDATES = (
    "Paige", "Sinclair", "Kelvin", "Ivy", "Victor",
    "Seven", "Viscous", "Graves", "The Doorman",
)
GATED_FITS = ("gated", "gated9")


def hero_rows(
    purchases: pd.DataFrame,
    blocks: dict[str, pd.DataFrame | None],
    gates: dict[str, set[int]] | None = None,
    labels: dict[tuple[int, str], pd.Series] | None = None,
) -> list[dict]:
    """One row per hero per fit: k, separation, and the separating item.

    A fit named in `gates` gives its block only to the heroes in its gate;
    every other hero is fitted with no block. Pass `labels` to collect each
    fit's cluster labels by (hero_id, fit).
    """
    gates = gates or {}
    hero_names = {h: v.name for h, v in assets.load_heroes().items()}
    item_names = {i: it.name for i, it in assets.load_items().items()}
    imbueable = set(imbue.imbueable_items())
    rows = []
    for hero_id, group in purchases.groupby("hero_id"):
        name = hero_names.get(int(hero_id), str(hero_id))
        for fit_name, extra in blocks.items():
            gated = fit_name in gates and int(hero_id) in gates[fit_name]
            if fit_name in gates and not gated:
                extra = None
            fit = archetype.fit_hero(
                group, hero_id=int(hero_id), hero_name=name, extra=extra
            )
            if labels is not None:
                labels[(int(hero_id), fit_name)] = fit.labels
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
                    "gated": gated,
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
    """(split heroes whose separating item is imbueable, split heroes) for one fit."""
    split = table[(table["fit"] == fit) & (table["k"] > 1)]
    return int(split["imbueable"].sum()), len(split)


def sheet(table: pd.DataFrame, verdict: list[str]) -> str:
    """The comparison sheet as markdown."""
    wide = table.pivot(index="hero", columns="fit", values="k")
    items = table.pivot(index="hero", columns="fit", values="item")
    flags = table.pivot(index="hero", columns="fit", values="imbueable")

    lines = [
        "# Does imbue belong in the archetype clustering?",
        "",
        "Generated by `scripts/compare_imbue_fits.py`. The decision is ADR 0001.",
        "",
        "Three fits of the same purchase table in one run. `families` uses build",
        "family shares alone. `imbue` is the rejected first attempt, which adds",
        "imbue target shares, `has_imbue`, and an imbue count. `conditional`",
        "adds target shares only, with players who imbued nothing placed at",
        "their hero's mean.",
        "",
        "The separating item is the item with the biggest pick-rate gap between",
        "the fit's two least distinct clusters. An asterisk marks one of the",
        "nine imbueable items. `split` is what the conditional block did to the",
        "hero's split compared with build families alone.",
        "",
        "| hero | k families | k imbue | k conditional | split "
        "| separating item (families) | separating item (conditional) |",
        "|---|---|---|---|---|---|---|",
    ]

    def cell(hero: str, fit: str) -> str:
        item = items.loc[hero, fit]
        # No split means no separating item. After a csv round trip that is
        # NaN, not "".
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
    """Apply the rule to the results, write the sheet to `out`, and print the verdict."""
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
        f"- Splits gained compared with build families alone: "
        f"{', '.join(gained) if gained else 'none'}",
        f"- Splits **lost** compared with build families alone: "
        f"{', '.join(lost) if lost else 'none'}",
        f"- Splits lost compared with the rejected first attempt: "
        f"{', '.join(lost_vs_imbue) if lost_vs_imbue else 'none'}",
        f"- Separating item is imbueable: {base_hits} of {base_splits} split "
        f"heroes ({base_share:.0%}) with build families alone, "
        f"{imbue_hits} of {imbue_splits} ({imbue_share:.0%}) with the first "
        f"attempt, and {cond_hits} of {cond_splits} ({cond_share:.0%}) with the "
        f"conditional block. The build-family number is the control: it shows "
        f"how often an imbueable item separates a hero's builds without the "
        f"block.",
        "",
        f"**No hero loses a split: {'yes' if no_loss else 'NO'}. "
        f"Share drops by at least half: {'yes' if dropped else 'NO'}.**",
        "",
        (
            "By the rule set before the results, the conditional imbue block "
            "stays in the clustering."
            if keep
            else "By the rule set before the results, imbue stays out of the "
            "clustering and is used only for naming and advice."
        ),
    ]

    gated = gated_sheet(table) if "gated" in set(table["fit"]) else []
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(sheet(table, verdict) + "\n".join(gated) + "\n", encoding="utf-8")
    for line in verdict + gated:
        print(line)
    print(f"\nwrote {out}")




def aim_versus_purchase(
    labels: pd.Series,
    imbue_rows: pd.DataFrame,
    items: list[tuple[int, int]],
) -> tuple[float, float]:
    """(D, P) for one hero's clusters over its contested items.

    `items` is (item_id, top_slot) per contested item, the top slot measured
    over the whole hero. D is the largest gap between two clusters in the
    share of their purchases of an item aimed at its top slot, counting only
    clusters with MIN_CLUSTER_BUYERS buyers. P is the largest gap between two
    clusters in the share of their players who bought the item. A split on
    aim has D > P. The first attempt's failure, a split on whether players
    bought the item, has P > D.
    """
    keys = ["match_id", "player_slot"]
    sizes = labels.value_counts()
    rows = imbue_rows.merge(labels.rename("cluster").reset_index(), on=keys)
    best_d = best_p = 0.0
    for item_id, top_slot in items:
        bought = rows[rows["item_id"] == item_id]
        buyers = bought[keys + ["cluster"]].drop_duplicates()["cluster"].value_counts()
        rate = buyers.reindex(sizes.index).fillna(0) / sizes
        best_p = max(best_p, float(rate.max() - rate.min()))
        enough = buyers.index[buyers >= MIN_CLUSTER_BUYERS]
        aim = (
            bought[bought["cluster"].isin(enough)]
            .assign(top=lambda f: f["signature_slot"] == top_slot)
            .groupby("cluster")["top"].mean()
        )
        if len(aim) >= 2:
            best_d = max(best_d, float(aim.max() - aim.min()))
    return best_d, best_p


def gated_analysis(
    table: pd.DataFrame,
    labels: dict[tuple[int, str], pd.Series],
    imbue_rows: pd.DataFrame,
    contested: pd.DataFrame,
) -> pd.DataFrame:
    """Add `ari`, `changed`, `aim_gap` and `buy_gap` to the gated fits' rows.

    Also checks that every hero outside a gate got exactly the families
    labels, which is true by construction. A mismatch means the gate leaked.
    """
    table = table.copy()
    for column in ("ari", "aim_gap", "buy_gap"):
        table[column] = float("nan")
    table["changed"] = False
    base_k = table[table["fit"] == "families"].set_index("hero_id")["k"]
    for i, row in table[table["fit"].isin(GATED_FITS)].iterrows():
        hero_id = int(row["hero_id"])
        mine = labels[(hero_id, row["fit"])]
        base = labels[(hero_id, "families")].reindex(mine.index)
        table.at[i, "ari"] = float(adjusted_rand_score(base, mine))
        if not row["gated"]:
            if not mine.equals(base):
                raise AssertionError(
                    f"{row['hero']} is outside the {row['fit']} gate "
                    "but its labels differ from families alone"
                )
            continue
        changed = (
            int(row["k"]) != int(base_k[hero_id])
            or table.at[i, "ari"] < CHANGED_ARI
        )
        table.at[i, "changed"] = changed
        if changed and int(row["k"]) > 1:
            items = contested[contested["hero_id"] == hero_id]
            d, p = aim_versus_purchase(
                mine,
                imbue_rows,
                list(zip(items["item_id"].astype(int), items["top_slot"].astype(int))),
            )
            table.at[i, "aim_gap"] = d
            table.at[i, "buy_gap"] = p
    return table


def gated_verdict(table: pd.DataFrame, fit: str) -> tuple[list[str], bool]:
    """Apply #40's rule to one gated fit: the verdict lines, and whether R1 and R2 pass."""
    ks = table.pivot(index="hero", columns="fit", values="k")
    rows = table[table["fit"] == fit].set_index("hero")
    gated = sorted(rows.index[rows["gated"].astype(bool)])
    lost = sorted(ks.index[ks[fit] < ks["families"]])
    gained = sorted(ks.index[ks[fit] > ks["families"]])
    changed = rows[rows["changed"].astype(bool)]
    # A change to k=1 leaves no clusters to compare aim across. It is a lost
    # split and fails R1, so it counts neither for nor against R2b.
    scored = changed[changed["k"] > 1]
    on_aim = sorted(scored.index[scored["aim_gap"] > scored["buy_gap"]])
    on_buy = sorted(scored.index[scored["aim_gap"] <= scored["buy_gap"]])

    r1 = not lost
    r2a = len(changed) > 0
    r2b = len(on_aim) > len(scored) / 2 if len(scored) else False
    lines = [
        f"- Heroes given the block: {len(gated)} ({', '.join(gated)})",
        f"- Splits gained: {', '.join(gained) if gained else 'none'}",
        f"- Splits **lost**: {', '.join(lost) if lost else 'none'}",
        f"- Gated heroes whose split changed (k differs, or ARI below "
        f"{CHANGED_ARI}): {len(changed)}"
        + (f" ({', '.join(sorted(changed.index))})" if len(changed) else ""),
        f"- Of those still split, separating on aim (D > P): "
        f"{', '.join(on_aim) if on_aim else 'none'}. On purchase: "
        f"{', '.join(on_buy) if on_buy else 'none'}.",
        "",
        f"**R1, no hero loses a split: {'yes' if r1 else 'NO'}. "
        f"R2a, a gated split changes: {'yes' if r2a else 'NO'}. "
        f"R2b, most changes are on aim: {'yes' if r2b else 'NO'}.**",
    ]
    return lines, r1 and r2a and r2b


def gated_sheet(table: pd.DataFrame) -> list[str]:
    """The gated fits' section of the sheet: verdicts, then one row per gated hero."""
    lines = [
        "",
        "## Gated per hero (#40)",
        "",
        "The conditional block given only to heroes whose players disagree on",
        "where to aim an item (`imbue.gated_heroes`). Every other hero gets no",
        "block and an identical fit, which the script checks. `gated` uses the",
        "gate posted on #40 before the run and carries the verdict. `gated9` is",
        "the nine heroes #40's text named, reported for comparison only.",
        "",
        "D is the largest gap between two clusters in how often they aim a",
        "contested item at its usual slot. P is the largest gap in how often",
        "they buy it. A split on aim has D > P.",
        "",
    ]
    for fit in GATED_FITS:
        verdict, passes = gated_verdict(table, fit)
        lines += [f"### {fit}", ""] + verdict + [""]
        if fit == "gated":
            lines += [
                "R1 and R2 pass. The block enters if held-out accuracy (R3) "
                "also passes."
                if passes
                else "By the rule set before the results, the gated block "
                "stays out of the clustering.",
                "",
            ]

    def num(value: float) -> str:
        return "--" if pd.isna(value) else f"{value:.2f}"

    families = table[table["fit"] == "families"].set_index("hero")
    for fit in GATED_FITS:
        rows = table[(table["fit"] == fit) & table["gated"].astype(bool)].set_index("hero")
        lines += [
            f"#### {fit}, per gated hero",
            "",
            f"| hero | k families | k {fit} | ARI | D (aim) | P (buy) |",
            "|---|---|---|---|---|---|",
        ]
        for hero in sorted(rows.index):
            row = rows.loc[hero]
            lines.append(
                f"| {hero} | {int(families.loc[hero, 'k'])} | {int(row['k'])} "
                f"| {num(row['ari'])} | {num(row['aim_gap'])} | {num(row['buy_gap'])} |"
            )
        lines.append("")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--out",
        default="docs/IMBUE-FIT-COMPARISON.md",
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
        # The fit is seeded, so the csv from the last run has the same numbers.
        # This skips refitting 38 heroes three ways.
        table = pd.read_csv(out.with_suffix(".csv"))
        report(table, out)
        return 0

    if not PURCHASES.exists() or not IMBUES.exists():
        logging.error("needs %s and %s; run scripts/refit.py first", PURCHASES, IMBUES)
        return 1

    purchases = pd.read_parquet(PURCHASES, columns=COLUMNS)
    players = archetype.player_index(purchases)
    heroes = archetype.hero_of(purchases)
    imbue_rows = pd.read_parquet(IMBUES)

    conditional = imbue.conditional_features(imbue_rows, players, heroes)
    hero_names = {h: v.name for h, v in assets.load_heroes().items()}
    gates = {
        "gated": imbue.gated_heroes(imbue_rows, heroes),
        "gated9": {h for h, name in hero_names.items() if name in TICKET_CANDIDATES},
    }

    def gated_block(gate: set[int]) -> pd.DataFrame | None:
        """The conditional block for the gate's players only, scaled over them."""
        inside = heroes.reindex(conditional.index).isin(gate).to_numpy()
        return archetype.scale_block(conditional[inside], IMBUE_WEIGHT)

    blocks = {
        "families": None,
        "imbue": archetype.scale_block(
            imbue.imbue_features(imbue_rows, players=players), IMBUE_WEIGHT
        ),
        "conditional": archetype.scale_block(conditional, IMBUE_WEIGHT),
        "gated": gated_block(gates["gated"]),
        "gated9": gated_block(gates["gated9"]),
    }

    labels: dict[tuple[int, str], pd.Series] = {}
    table = pd.DataFrame(hero_rows(purchases, blocks, gates, labels))
    table = gated_analysis(
        table, labels, imbue_rows, imbue.contested_items(imbue_rows, heroes)
    )

    table.to_csv(Path(args.out).with_suffix(".csv"), index=False)
    report(table, Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
