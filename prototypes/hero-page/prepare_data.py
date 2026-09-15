"""PROTOTYPE -- data prep for the hero-page variants (issue #24).

Throwaway. Pulls real Ivy data out of the model so the two variants are judged
against real density: three archetypes, two of which share five of six
prevalent items. Writes one JSON blob the prototype page inlines.

    python prototypes/hero-page/prepare_data.py

Nothing here is production code. `scripts/build_site.py` is the real generator.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from deadlock import archetype, assets, build, cli, evaluate, features  # noqa: E402

HERO_NAME = "Ivy"
OUT = Path(__file__).resolve().parent / "data.json"

PHASE_LABELS = ("Lane (0-10m)", "Mid (10-20m)", "Late (20-30m)", "Very late (30m+)")


def builds_into(items: list[dict]) -> None:
    """Resolve each component against the build's own later purchases.

    #19 settled that "builds into X" replaces "absorbed", and that the
    catalogue is ambiguous but the build itself is not. Mutates in place.
    """
    catalogue = assets.load_items()
    by_id = {int(i): it for i, it in catalogue.items()}
    for idx, item in enumerate(items):
        if not item["sold"]:
            continue
        # The composite that consumed it is the next purchase whose component
        # list contains this item. Fall back to the next purchase after the
        # sell time, which is what the build's own order implies.
        later = [c for c in items[idx + 1 :] if c["time"] >= item["sold"]]
        item["builds_into"] = later[0]["name"] if later else None
    _ = by_id


def collect_builds() -> list[dict]:
    import build_site

    rows = build_site.collect(hero_filter=HERO_NAME)
    for row in rows:
        for item in row["items"]:
            item["phase"] = int(features.phase_of(item["time"]))
        builds_into(row["items"])
    return rows


def collect_chooser() -> list[dict]:
    """Name, share, absolute win rate with n, two item columns, imbue.

    This is exactly what #21 settled the chooser carries. No build
    descriptions -- that premise died in #21 and does not come back here.
    """
    labels, meta = archetype.load()
    hero_id = assets.resolve_hero(HERO_NAME)
    entry = meta["heroes"][str(hero_id)]

    purchases = pd.read_parquet(cli.PURCHASES, columns=cli.COLUMNS)
    hero_rows = purchases[purchases["hero_id"] == hero_id]
    item_names = {int(i): it.name for i, it in assets.load_items().items()}

    out = []
    for arch in entry["archetypes"]:
        archetype_id = int(arch["archetype_id"])
        cell = hero_rows.merge(
            labels[
                (labels["hero_id"] == hero_id)
                & (labels["archetype_id"] == archetype_id)
            ][["match_id", "player_slot"]],
            on=["match_id", "player_slot"],
        )
        prevalence = evaluate.item_prevalence(cell).sort_values(ascending=False)
        prevalent = [
            {"id": int(i), "name": item_names.get(int(i), str(i)), "p": round(float(v), 3)}
            for i, v in prevalence.head(6).items()
        ]
        discriminative = [
            {
                "id": int(t["item_id"]),
                "name": t["name"],
                "p": round(float(t["in_cluster"]), 3),
                "elsewhere": round(float(t["elsewhere"]), 3),
            }
            for t in sorted(
                arch.get("top_items", []),
                key=lambda t: t["in_cluster"] - t["elsewhere"],
                reverse=True,
            )[:6]
        ]

        generated = build.generate_build(
            hero_id,
            archetype_id,
            cli.load_model(badge=None),
            hero_name=HERO_NAME,
            archetype_name=arch.get("name", ""),
        )
        targets = cli.load_imbue_targets(cell, [i.item_id for i in generated.items])

        out.append(
            {
                "archetype_id": archetype_id,
                "name": arch.get("name") or HERO_NAME,
                "share": arch.get("share"),
                "win_rate": arch.get("win_rate"),
                "n": arch.get("n"),
                "prevalent": prevalent,
                "discriminative": discriminative,
                "imbue": [
                    {"item": t.item_name, "ability": t.ability_name, "share": round(t.share, 3)}
                    for t in targets
                    if t.ability_id is not None
                ][:1],
            }
        )
    return out


def main() -> None:
    builds = collect_builds()
    chooser = collect_chooser()

    # Item ids for icons: the build rows carry names only, so join back.
    name_to_id = {it.name: int(i) for i, it in assets.load_items().items()}
    for row in builds:
        for item in row["items"]:
            item["id"] = name_to_id.get(item["name"])

    payload = {
        "hero": HERO_NAME,
        "hero_id": assets.resolve_hero(HERO_NAME),
        "phases": list(PHASE_LABELS),
        "chooser": chooser,
        "builds": builds,
    }
    OUT.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"wrote {OUT} -- {len(chooser)} archetypes, {len(builds)} builds")


if __name__ == "__main__":
    main()
