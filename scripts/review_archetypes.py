#!/usr/bin/env python
"""Fit archetypes for every hero, save the labels, and write the review sheet.

Everything after this step depends on the archetypes, so someone who plays
the game should read the sheet. For example, Ivy's clusters should look like
the gun and spirit builds players know.

The names are proposals. Override them in `data/archetype_names.json`, which
is checked in and survives a refit.

Usage:
    python scripts/review_archetypes.py [--out docs/ARCHETYPES.md] [--no-save]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from deadlock import abilities, archetype

IMBUES = Path("data/processed/imbues.parquet")
ABILITIES = Path("data/processed/abilities.parquet")

PURCHASES = Path("data/processed/purchases.parquet")
COLUMNS = ["match_id", "player_slot", "hero_id", "item_id", "won"]

# Percentages from fewer players than this are marked thin. Otherwise "96%" of
# 24 players looks the same as "96%" of 5,000.
MIN_ROWS = 30


def thin_note(n: int) -> str:
    """" [thin: n players]" when n is below MIN_ROWS, else ""."""
    return "" if n >= MIN_ROWS else f" [thin: {n} players]"


def sheet(meta: dict, purchases: pd.DataFrame) -> str:
    """Render the review sheet as markdown."""
    heroes = meta["heroes"]
    split = {h: m for h, m in heroes.items() if m["k"] > 1}
    single = {h: m for h, m in heroes.items() if m["k"] == 1}

    lines = [
        "# Archetype review",
        "",
        "Fitted per hero on souls-weighted build-family shares -- how a player's",
        "souls divided across gun, spirit, melee, support, tank, sustain, control",
        "and mobility. A hero splits only if all four criteria pass; otherwise it",
        "stays single, which is a result and not a failure.",
        "",
        "Imbue is **not** in the fit. It was tried in two forms and rejected under",
        "a rule fixed before the numbers -- see",
        "`docs/adr/0001-imbue-out-of-the-clustering.md`. It names clusters below",
        "and tells the player what to imbue; it does not find clusters.",
        "",
        f"**{len(split)} of {len(heroes)} heroes split.** "
        f"Seed {meta['seed']}, so a refit reproduces this exactly.",
        "",
        "Names below are proposed from what each cluster's discriminative items",
        "do, sharpened by its ability focus where two would otherwise collide. Edit",
        "`data/archetype_names.json` (keyed `\"<hero_id>:<archetype_id>\"`) to",
        "overrule any of them.",
        "",
        "## Heroes that split",
        "",
    ]

    order = sorted(
        split.items(), key=lambda kv: -(kv[1]["criteria"]["separation"]["value"] or 0)
    )
    for hero_id, m in order:
        lines += [
            f"### {m['hero_name']}  ({m['k']} archetypes, n={m['n']:,})",
            "",
            "| criterion | value | threshold |",
            "|---|---|---|",
        ]
        for name, c in m["criteria"].items():
            value = "n/a" if c["value"] is None else f"{c['value']:.3f}"
            lines.append(f"| {name} | {value} | >= {c['threshold']:.2f} |")
        lines.append("")

        for cluster in m["archetypes"]:
            centroid = cluster["centroid"]
            shares = "  ".join(
                f"{k.replace('share_', '')} {v:.0%}" for k, v in centroid.items()
            )
            # The margin only covers the family part of the name. A cluster
            # with no family name can still be named by its ability focus
            # ("Ult Dynamo"), so don't call it unnamed.
            margin = cluster.get("naming_margin", 0.0)
            named_by_focus = cluster["name"] != cluster.get("family_name", "")
            if margin >= 1.3:
                confidence = f", named at {margin:.1f}x over the runner-up"
            elif margin and named_by_focus:
                confidence = (
                    ", named by what it imbues — the families are too close to call"
                )
            elif margin:
                confidence = ", **unnamed** — the families are too close to call"
            else:
                confidence = ""
            thin = thin_note(cluster["n"])
            lines += [
                f"**{cluster['name']}** — {cluster['share']:.0%} of players "
                f"(n={cluster['n']:,}){thin}{confidence}",
                "",
                f"_Souls by shop tab: {shares}. Shown for reference only — the "
                "name comes from what the items below do, not from the tab they "
                "are sold in._",
                "",
                "| item | in this build | in the others |",
                "|---|---|---|",
            ]
            for item in cluster["top_items"][:10]:
                lines.append(
                    f"| {item['name']} | {item['in_cluster']:.0%}{thin} "
                    f"| {item['elsewhere']:.0%} |"
                )
            lines.append("")

    lines += ["## Heroes that did not split", "", "| hero | n | why |", "|---|---|---|"]
    for hero_id, m in sorted(single.items(), key=lambda kv: kv[1]["hero_name"]):
        lines.append(f"| {m['hero_name']} | {m['n']:,} | {m['reason']} |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="docs/ARCHETYPES.md")
    parser.add_argument("--no-save", action="store_true", help="skip writing parquet/json")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    if not PURCHASES.exists():
        logging.error("no %s; run scripts/build_features.py first", PURCHASES)
        return 1

    purchases = pd.read_parquet(PURCHASES, columns=COLUMNS)
    logging.info("fitting %s heroes...", purchases["hero_id"].nunique())

    # Imbue is not a clustering input (ADR 0001), but it is used for naming:
    # it's what tells Dynamo's two builds apart.
    #
    # Naming inputs: imbue targets, and the ability maxed first for builds
    # that buy no imbueable item.
    imbue_rows = pd.read_parquet(IMBUES) if IMBUES.exists() else None
    imbue_indexed = (
        imbue_rows.set_index(["match_id", "player_slot"]) if imbue_rows is not None else None
    )
    first_maxed = (
        abilities.first_maxed_slot(pd.read_parquet(ABILITIES))
        if ABILITIES.exists()
        else None
    )

    labels, fits, meta = archetype.fit_all(
        purchases, extra=None, imbues=imbue_indexed, first_maxed=first_maxed
    )

    # Win rate per archetype, for display only. It reflects who plays a build,
    # not whether the build is better, and nothing uses it.
    outcomes = (
        purchases[["match_id", "player_slot", "won"]]
        .drop_duplicates()
        .merge(labels, on=["match_id", "player_slot"])
    )
    rates = outcomes.groupby(["hero_id", "archetype_id"])["won"].mean()
    for hero_id, entry in meta["heroes"].items():
        for cluster in entry["archetypes"]:
            key = (int(hero_id), cluster["archetype_id"])
            if key in rates.index:
                cluster["win_rate"] = float(rates.loc[key])

    if not args.no_save:
        archetype.save(labels, meta)
        logging.info("wrote data/processed/archetypes.parquet and archetype_meta.json")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(sheet(meta, purchases), encoding="utf-8")

    n_split = sum(1 for m in meta["heroes"].values() if m["k"] > 1)
    logging.info("%s of %s heroes split -> %s", n_split, len(meta["heroes"]), out)
    for fit in sorted(fits, key=lambda f: -(f.separation if f.separation == f.separation else 0)):
        if fit.split:
            logging.info("  %-14s k=%d  separation %.3f", fit.hero_name, fit.k, fit.separation)
    return 0


if __name__ == "__main__":
    sys.exit(main())
