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

from deadlock import abilities, archetype, assets, imbue

IMBUES = Path("data/processed/imbues.parquet")
ABILITIES = Path("data/processed/abilities.parquet")

# Full mass: the imbue block carries as much weight as the build families.
# Measured better than 0.25 and 0.5, which found three of the five new
# archetypes rather than all five.
IMBUE_WEIGHT = 1.0

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
        "Fitted per hero on souls-weighted item slot-type shares. A hero splits",
        "only if all four criteria pass; otherwise it stays single, which is a",
        "result and not a failure.",
        "",
        f"**{len(split)} of {len(heroes)} heroes split.** "
        f"Seed {meta['seed']}, so a refit reproduces this exactly.",
        "",
        "Names below are proposed from each cluster's dominant slot type. Edit",
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
            margin = cluster.get("naming_margin", 0.0)
            if margin >= 1.3:
                confidence = f", named at {margin:.1f}x over the runner-up"
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

    # Imbue joins the fit; ability order does not. Measured over 11 heroes at
    # weights 0/0.25/0.5/1.0: imbue gains an archetype on Dynamo, Bebop,
    # Wraith, The Doorman and Rem and loses none, while ability order adds
    # nothing imbue does not already add and costs Pocket's split when the two
    # are combined. Ability order earns its place in the recommendation and the
    # naming instead, which is where it measured strongly.
    #
    # Note the comparison that says so is "does the fit still clear every
    # criterion, and at what k" -- not `separation`, which is a minimum over
    # cluster pairs and so falls whenever k rises, and which reports a rejected
    # candidate's score when a hero ends at k=1.
    extra = None
    if IMBUES.exists():
        players = (
            purchases[["match_id", "player_slot"]]
            .drop_duplicates()
            .set_index(["match_id", "player_slot"])
            .index
        )
        extra = archetype.scale_block(
            imbue.imbue_features(pd.read_parquet(IMBUES), players=players),
            IMBUE_WEIGHT,
        )
        logging.info("imbue features in the fit at weight %.2f", IMBUE_WEIGHT)
    else:
        logging.info("no imbue table; fitting on build families alone")

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
        purchases, extra=extra, imbues=imbue_indexed, first_maxed=first_maxed
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
