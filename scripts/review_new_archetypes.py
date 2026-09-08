#!/usr/bin/env python
"""What the imbue-augmented fit actually found, for a person to judge.

**The fit this reviews was rejected** --
`docs/adr/0001-imbue-out-of-the-clustering.md` holds the decision and the
numbers. This script stays because it is how a candidate block gets judged by a
player rather than by a score, and any future block should be read the same way.

The numbers cannot answer the question that matters here. Every new cluster
clears every acceptance criterion, but `docs/DIAGNOSIS.md` records a model that
passed five aggregate gates and still produced unusable builds, and `CONTEXT.md`
warns that a dimension varying for a reason other than playstyle manufactures
archetypes out of nothing -- which is exactly how counter-picks fail.

So this prints the readout a player can check: each cluster's **discriminative
items** with in-cluster against elsewhere pick rates, plus what the cluster
imbues and which ability it maxes first. If a cluster does not read as a build
someone plays, it is not an archetype however good its silhouette is.

    python scripts/review_new_archetypes.py [--heroes changed|all|A,B] [--out FILE]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from deadlock import abilities, archetype, assets, imbue  # noqa: E402

PURCHASES = Path("data/processed/purchases.parquet")
ABILITIES = Path("data/processed/abilities.parquet")
IMBUES = Path("data/processed/imbues.parquet")

# The heroes the imbue block changed when it was measured. Kept as a record of
# that run, not as the list to read: `--heroes changed` recomputes which heroes
# a candidate block actually moves, so a block that moves different heroes is
# not reviewed against the last block's list.
CHANGED = ("Dynamo", "Bebop", "Wraith", "The Doorman", "Rem")


# Below this many observations a percentage is not a finding. The sheet once
# printed "96%" from 24 rows next to a "96%" from 5,110 and made them look like
# the same claim, so every share here carries its count and is marked when the
# count is too small to state plainly.
MIN_ROWS = 30


def thin_note(n: int) -> str:
    return "" if n >= MIN_ROWS else f" [thin: {n} rows]"


def cluster_report(
    hero_name: str,
    purchases: pd.DataFrame,
    labels: pd.Series,
    imbues: pd.DataFrame,
    ability_rows: pd.DataFrame,
    item_names: dict[int, str],
    ability_names: dict[int, str],
    signatures: dict[int, object],
    has_imbue: pd.Series,
) -> list[str]:
    lines = [f"### {hero_name}", ""]
    prevalence = archetype.cluster_prevalence(purchases, labels)
    shares = labels.value_counts(normalize=True)

    first_maxed = abilities.first_maxed_slot(ability_rows)
    for cluster in sorted(labels.unique()):
        members = labels[labels == cluster].index
        lines.append(
            f"**cluster {cluster}** -- {shares[cluster]:.0%} of players "
            f"({len(members):,})" + thin_note(len(members))
        )
        lines.append("")

        top = archetype.discriminative_items(prevalence, cluster, top=8)
        lines.append(f"| item | here (n={len(members):,}) | elsewhere |")
        lines.append("|---|---|---|")
        for row in top.itertuples():
            lines.append(
                f"| {item_names.get(int(row.item_id), row.item_id)} "
                f"| {row.in_cluster:.0%}{thin_note(len(members))} "
                f"| {row.elsewhere:.0%} |"
            )
        lines.append("")

        # How many of this cluster's players imbue at all comes FIRST. A share
        # over 24 rows and a share over 5,000 are not the same claim, and the
        # first draft of this sheet printed them identically -- it reported
        # "Exploding Uppercut 96%" for a Bebop cluster of 5,110 players whose
        # imbue rows numbered 24, which reads as a strong signal and is noise.
        coverage = float(has_imbue.reindex(members).fillna(0.0).mean())
        mine = imbues[imbues.index.isin(members)] if len(imbues) else imbues
        lines.append(
            f"- imbues at all: {coverage:.0%} of players ({len(mine):,} imbues)"
        )
        if len(mine) >= MIN_ROWS:
            counts = mine["imbued_ability_id"].value_counts(normalize=True).head(3)
            imbued = ", ".join(
                f"{ability_names.get(int(a), a)} {v:.0%}" for a, v in counts.items()
            )
            lines.append(f"- imbue targets: {imbued}")
        elif len(mine):
            lines.append(
                f"- imbue targets: too few to state ({len(mine)} rows) [thin]"
            )

        maxed = first_maxed[first_maxed.index.isin(members)]
        maxed = maxed[maxed > 0]
        if len(maxed):
            counts = maxed.value_counts(normalize=True).head(3)
            named = ", ".join(
                f"{getattr(signatures.get(int(slot)), 'name', slot)} {v:.0%}"
                for slot, v in counts.items()
            )
            lines.append(
                f"- maxes first: {named} ({len(maxed):,} players)"
                + thin_note(len(maxed))
            )
        lines.append("")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--heroes",
        default="changed",
        help=(
            "'changed' for every hero whose archetype count the block moves, "
            "'all' for all of them, or a comma-separated list of names"
        ),
    )
    parser.add_argument("--out", default="docs/NEW-ARCHETYPES.md")
    args = parser.parse_args()

    purchases = pd.read_parquet(
        PURCHASES,
        columns=["match_id", "player_slot", "hero_id", "item_id", "buy_index"],
    )
    players = (
        purchases[["match_id", "player_slot"]]
        .drop_duplicates()
        .set_index(["match_id", "player_slot"])
        .index
    )
    imbue_rows = pd.read_parquet(IMBUES)
    extra = archetype.scale_block(
        imbue.imbue_features(imbue_rows, players=players), 1.0
    )
    ability_rows = pd.read_parquet(ABILITIES)

    item_names = {i: it.name for i, it in assets.load_items().items()}
    ability_names = {a.id: a.name for a in assets.load_abilities().values()}
    all_signatures = assets.hero_signatures()
    heroes = {h.name.lower(): i for i, h in assets.playable_heroes().items()}

    imbue_indexed = imbue_rows.set_index(["match_id", "player_slot"])
    imbue_coverage = imbue.imbue_features(imbue_rows, players=players)["has_imbue"]

    lines = [
        "# Archetypes the imbue features found",
        "",
        "Every cluster below clears every acceptance criterion. That is not the",
        "question. The question is whether each reads as a build someone plays,",
        "which only a player can answer -- so the readout is discriminative",
        "items, what the cluster imbues, and which ability it maxes first.",
        "",
        "Reject any that do not, and the fit drops back to build families alone",
        "for that hero.",
        "",
    ]
    selector = args.heroes.strip().lower()
    if selector in {"changed", "all"}:
        playable = assets.playable_heroes()
        wanted = [
            (playable[h].name, h)
            for h in sorted(heroes.values(), key=lambda h: playable[h].name)
        ]
    else:
        wanted = [
            (n.strip(), heroes.get(n.strip().lower()))
            for n in args.heroes.split(",")
            if n.strip()
        ]

    reviewed = 0
    for name, hero_id in wanted:
        if hero_id is None:
            continue
        group = purchases[purchases["hero_id"] == hero_id]
        before = archetype.fit_hero(group, hero_id=hero_id, hero_name=name)
        after = archetype.fit_hero(group, hero_id=hero_id, hero_name=name, extra=extra)
        # The point of the sheet is the archetypes nobody has judged yet. A
        # hero the block leaves alone needs no second reading, and printing all
        # 38 buries the handful that do.
        if selector == "changed" and before.k == after.k:
            continue
        reviewed += 1
        lines.append(f"## {name}: {before.k} -> {after.k} archetypes")
        lines.append("")
        lines.append(f"`{after.reason}`")
        lines.append("")
        if not after.split:
            lines.append("(no split accepted)")
            lines.append("")
            continue
        lines += cluster_report(
            name,
            group,
            after.labels,
            imbue_indexed,
            ability_rows[ability_rows.hero_id == hero_id],
            item_names,
            ability_names,
            all_signatures.get(hero_id, {}),
            imbue_coverage,
        )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if selector == "changed" and not reviewed:
        lines.append("No hero's archetype count changes under this block.")
        lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out} ({reviewed} hero(es) to judge)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
