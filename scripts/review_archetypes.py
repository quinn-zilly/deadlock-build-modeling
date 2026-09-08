#!/usr/bin/env python
"""Fit archetypes for every hero and emit a review sheet.

The Stage 3 artifact, and a hard stop. Everything downstream conditions on
these clusters, so a person who plays the game reads this before the sequence
model is built. If Ivy's two groups do not read as the gun and spirit builds a
player would recognize, the design is wrong and it is cheap to find out here.

Names are proposed, not decided. Edit `data/archetype_names.json` to overrule
them; the file is checked in and survives a refit.

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
            # The margin scores the FAMILY half of the name only. A cluster can
            # decline a family and still be named by its ability focus --
            # "Ult Dynamo" is what players call that build -- so reporting a
            # named cluster as unnamed because its families tied is a
            # contradiction the reader can see on the same line.
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
            lines += [
                f"**{cluster['name']}** — {cluster['share']:.0%} of players "
                f"(n={cluster['n']:,}){confidence}",
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
                    f"| {item['name']} | {item['in_cluster']:.0%} "
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

    # **Imbue is not in the fit**, in either of the two forms that were tried.
    # The rule was fixed before the numbers and the numbers are recorded in
    # docs/adr/0001-imbue-out-of-the-clustering.md, next to the sheet the
    # experiment wrote. It still earns its place below, in naming and in the
    # advice: which ability a cluster points its items at is what names
    # Dynamo's two builds, and the items cannot.

    # Naming inputs. Imbue says what a build is aimed at; the ability levelled
    # first says the same thing for builds that buy no imbueable item.
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

    # Win rate per archetype: descriptive only. It says who plays a build, not
    # whether the build is better, so it informs the reader and nothing else.
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
