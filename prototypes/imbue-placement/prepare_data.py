"""PROTOTYPE -- data prep for the imbue-placement variants (issue #25).

Throwaway. Pulls three real builds out of the model and reduces each item row
to what the three variants need: the #23 row (icon, name, cost, subline, one
ranked stat), "builds into" resolved against the catalogue's component list,
and the imbue target with its evidence.

    uv run python prototypes/imbue-placement/prepare_data.py

Nothing here is production code. `scripts/build_site.py` is the real generator.
"""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from deadlock import assets, features, imbue  # noqa: E402

# Spirit Ivy is the build the ticket asks for: three imbue rows, two of which
# also build into something. Spirit Paradox is the density worst case (four
# imbue rows, three absorbed). Gun Ivy is the weapon-side case, one imbue row
# that is absorbed (Quicksilver Reload).
BUILDS = [("Ivy", "Spirit Ivy"), ("Paradox", "Spirit Paradox"), ("Ivy", "Gun Ivy")]
PHASES = ("Lane (0-10m)", "Mid (10-20m)", "Late (20-30m)", "Very late (30m+)")
RAW_ITEMS = ROOT / "data/raw/assets/v1_assets_items__c2557efa885c5123.json"
OUT = Path(__file__).resolve().parent / "data.js"

TAG = re.compile(r"<[^>]+>")


def ranked_stat(raw: dict) -> str:
    """One stat, ranked by the game's own tooltip fields (#23, section 7)."""
    props = raw.get("properties") or {}
    for section in raw.get("tooltip_sections") or []:
        for attr in section.get("section_attributes") or []:
            for field in ("elevated_properties", "important_properties_with_icon",
                          "important_properties"):
                for key in attr.get(field) or []:
                    if isinstance(key, dict):
                        # Status effects come through as named conditions.
                        return key.get("localized_name") or key.get("name", "")
                    p = props.get(key)
                    if not p or str(p.get("value", "0")) in ("0", ""):
                        continue
                    value = str(p["value"])
                    sign = "+" if not value.startswith("-") else ""
                    label = p.get("label") or p.get("postvalue_label") or key
                    return f"{sign}{value}{p.get('postfix', '')} {label}"
    for section in raw.get("tooltip_sections") or []:
        for attr in section.get("section_attributes") or []:
            text = attr.get("loc_string")
            if text:
                return html.unescape(TAG.sub("", text)).split(".")[0].strip() + "."
    return ""


def main() -> None:
    import build_site

    raw = {int(x["id"]): x for x in json.loads(RAW_ITEMS.read_text(encoding="utf-8"))}

    catalogue = assets.load_items()
    name_to_id = {it.name: int(i) for i, it in catalogue.items() if it.cost}
    imbueable = imbue.imbueable_items()
    abilities = assets.load_abilities()

    out = []
    for hero, archetype_name in BUILDS:
        rows = build_site.collect(hero_filter=hero)
        row = next(r for r in rows if r["archetype"] == archetype_name)
        hero_id = assets.resolve_hero(hero)
        ability_ids = {a.name: int(i) for i, a in abilities.items() if a.hero_id == hero_id}
        targets = {t["item"]: t for t in row["imbue"]}

        items = []
        for idx, it in enumerate(row["items"]):
            item_id = name_to_id[it["name"]]
            builds_into = None
            if it["sold"]:
                # The catalogue names components by class; resolve against the
                # build's own later purchases (#19: 96.6% resolve this way).
                me = raw[item_id]["class_name"]
                for later in row["items"][idx + 1:]:
                    comps = raw[name_to_id[later["name"]]].get("component_items") or []
                    if me in comps:
                        builds_into = later["name"]
                        break
            t = targets.get(it["name"]) if item_id in imbueable else None
            items.append({
                "id": item_id,
                "name": it["name"],
                "cost": it["cost"],
                "phase": int(features.phase_of(it["time"])),
                "time": it["time"],
                "p": it["p"],
                "n": it["n"],
                "builds_into": builds_into,
                # The composite carries no imbue field for 3 of the 4 imbueable
                # components: its bonus is global, so the single-ability imbue ends.
                "into_keeps_imbue": bool(builds_into) and name_to_id[builds_into] in imbueable,
                "sold_unresolved": bool(it["sold"]) and builds_into is None,
                "stat": ranked_stat(raw[item_id]),
                "imbue": None if t is None else {
                    "ability": t["ability"],
                    "ability_id": ability_ids.get(t["ability"]),
                    "share": t["share"],
                    "n": t["n"],
                    "split": t["split"],
                },
            })
        out.append({
            "hero": hero,
            "hero_id": hero_id,
            "archetype": archetype_name,
            "share": row["share"],
            "win_rate": row["win_rate"],
            "n": row["n"],
            "items": items,
        })
        n_imb = sum(1 for i in items if i["imbue"])
        n_both = sum(1 for i in items if i["imbue"] and i["builds_into"])
        print(f"{archetype_name}: {len(items)} items, {n_imb} imbue rows, {n_both} also build into")

    payload = {"phases": list(PHASES), "builds": out}
    OUT.write_text("window.DATA = " + json.dumps(payload, indent=1) + ";\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
