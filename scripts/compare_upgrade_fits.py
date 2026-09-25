#!/usr/bin/env python
"""Test AP upgrade effects and gun-routed abilities as archetype inputs (#42).

Everything below comes from one run over the same purchase and ability
tables, so every number in the sheet compares with every other.

Fits (every hero, the same `archetype.fit_hero`):

    families        build family shares alone (the control)
    order           `abilities.point_order_features`, raw. Reference only: it
                    is the block ADR 0003 rejected, refitted here so the
                    upgrade blocks compare with it in the same run.
    effects         `upgrades.effect_features`: exposure to each effect
                    category over all three upgrade tiers
    effects_t5      the same, from the 5-point tier only
    gunproc         one column, spirit share x gun-routed exposure, given only
                    to heroes with a gun-routed ability (gated)
    reroute         no new column: family shares with the gun-routed part of
                    spirit counted as gun, on the same gated heroes

Representations, and why they differ from order. A player's unlocked upgrade
effects are fixed by which tiers they reached and when, so any effect feature
is a function of the point timeline. `effects` is a per-hero linear
projection of the twelve order columns: it pools (slot, level) columns by the
effect categories the tiers unlock, so two players who took their "shred"
tier early through different abilities look alike. It carries no information
order lacks, but KMeans depends on geometry, so it can cluster differently.
`effects_t5` keeps only the 5-point tier, where the ticket says builds
diverge. The gun-routed fits need a per-player form, because a per-hero
constant flag is the same for every player on a hero and cannot move a
within-hero clustering.

A gun-routed ability is a signature ability of a playable hero that scales
with spirit power (`upgrades.is_spirit_scaling`) and works through the
caster's gun (`upgrades.weapon_tier` is not None). Exposure is the
cost-weighted share of the player's upgrade tiers, held over their point
sequence, that sit in gun-routed abilities (`upgrades.gun_exposure`).

The rule, written down before any fit was run and applied as written:

    R1  No hero loses a split it had with build families alone.
    R2  At least one hero gains a split, or (gated fits only) at least one
        gated hero's split changes: k differs, or adjusted Rand index against
        families below CHANGED_ARI.
    R3  The separating items don't concentrate: no single item separates
        more than MAX_TOP_ITEM_SHARE of split heroes, and the top three
        items' share is at most MAX_CONCENTRATION_RATIO times the families
        control in this run.

A block passing R1-R3 then faces held-out top-1 (`score_archetype_fits.py
--blocks ...`): it may not fall more than two standard errors below
families. Every block is weighted 1.0 via `archetype.scale_block`, as ADR 0001
and ADR 0003 did.

The gun-routed signal is also measured directly, not only as a block:

- Roster shape. Every hero is fitted at a forced k=2 on families (the same k
  for all, so separations compare). Per hero: separation, its placebo floor
  (the largest separation over PLACEBO_DRAWS shuffles of the same labels),
  and the axis share, how much of the centroid gap lies on gun and spirit.
  Gun-routed heroes against the rest, by a permutation test on the hero
  labels (PERMUTATIONS draws). A difference counts at two-sided p < ALPHA.
- The slot-type boundary. Per hero, the mean total-variation distance
  between a player's shop-tab shares and family shares (weapon against gun
  and melee, spirit against spirit and ult where the code has that family,
  vitality against the rest),
  compared the same way. If gun-routed heroes are where tab and family
  disagree, the two phenomena overlap.
- Names. `archetype.propose_name` for every cluster of every fit. A name
  changes when the sorted list of a hero's proposed names differs from
  families.

The imbue interaction and the conditioning question (#31's bar):

- Population. For every imbue, the target ability's level when the item was
  bought: 0 (not unlocked), 1 (unlocked, no upgrade), 2-3, or 4 (5-point
  tier reached). Ult against the other slots.
- Generated builds (`data/builds`). An imbue in a build is a defect only if
  the build buys the item before its own ability order unlocks the target
  (tier 0), or, for an ult target, before the ult's first upgrade, AND fewer
  than half of that cell's players who imbue that item into that slot do the
  same. A build copying what its players do is imitation, not a defect.

    python scripts/compare_upgrade_fits.py [--out docs/UPGRADE-FIT-COMPARISON.md]
"""

from __future__ import annotations

import argparse
import glob
import json
import logging
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import adjusted_rand_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from deadlock import abilities, archetype, assets, imbue, upgrades  # noqa: E402

PURCHASES = Path("data/processed/purchases.parquet")
ABILITIES = Path("data/processed/abilities.parquet")
IMBUES = Path("data/processed/imbues.parquet")
LABELS = Path("data/processed/archetypes.parquet")
BUILDS = Path("data/builds")
COLUMNS = ["match_id", "player_slot", "hero_id", "item_id"]
KEYS = ["match_id", "player_slot"]

# Set before the results.
BLOCK_WEIGHT = 1.0
MAX_TOP_ITEM_SHARE = 0.25
MAX_CONCENTRATION_RATIO = 2.0
CHANGED_ARI = 0.80
PLACEBO_DRAWS = 20
PERMUTATIONS = 10_000
ALPHA = 0.05
SEED = 0

FITS = ("families", "order", "effects", "effects_t5", "gunproc", "reroute")
CANDIDATES = ("effects", "effects_t5", "gunproc", "reroute")
GATED = ("gunproc", "reroute")


# ---------------------------------------------------------------- fits


def fit_rows(
    purchases: pd.DataFrame,
    blocks: dict[str, pd.DataFrame | None],
    exposure: pd.Series,
    gate: set[int],
) -> tuple[pd.DataFrame, dict[tuple[int, str], pd.Series]]:
    """One row per hero per fit, and every fit's labels by (hero_id, fit)."""
    hero_names = {h: v.name for h, v in assets.load_heroes().items()}
    item_names = {i: it.name for i, it in assets.load_items().items()}
    rows: list[dict] = []
    labels: dict[tuple[int, str], pd.Series] = {}
    for hero_id, group in purchases.groupby("hero_id"):
        hero_id = int(hero_id)
        name = hero_names.get(hero_id, str(hero_id))
        started = time.time()
        for fit_name in FITS:
            gated = fit_name in GATED and hero_id in gate
            extra = blocks.get(fit_name)
            if fit_name in GATED and not gated:
                extra = None
            if fit_name == "reroute" and gated:
                with upgrades.rerouted_families(exposure):
                    fit = archetype.fit_hero(group, hero_id=hero_id, hero_name=name)
            else:
                fit = archetype.fit_hero(
                    group, hero_id=hero_id, hero_name=name,
                    extra=None if fit_name == "reroute" else extra,
                )
            labels[(hero_id, fit_name)] = fit.labels
            item_id = gap = None
            names: list[str] = []
            if fit.split:
                prevalence = archetype.cluster_prevalence(group, fit.labels)
                found = archetype.separating_item(prevalence)
                if found is not None:
                    item_id, gap = found
                for cluster in sorted(fit.labels.unique()):
                    proposed, _ = archetype.propose_name(
                        pd.Series(dtype=float), name, prevalence, cluster
                    )
                    names.append(proposed)
            rows.append(
                {
                    "hero_id": hero_id,
                    "hero": name,
                    "fit": fit_name,
                    "gated": gated,
                    "k": fit.k,
                    "separation": fit.separation if fit.split else float("nan"),
                    "item_id": item_id,
                    "item": item_names.get(item_id, "") if item_id else "",
                    "gap": gap,
                    "names": " / ".join(sorted(names)) if names else name,
                }
            )
        logging.info(
            "  %-14s %s  (%.0fs)",
            name,
            " ".join(f"{r['fit']}={r['k']}" for r in rows[-len(FITS):]),
            time.time() - started,
        )

    table = pd.DataFrame(rows)
    table["ari"] = float("nan")
    for i, row in table.iterrows():
        mine = labels[(int(row["hero_id"]), row["fit"])]
        base = labels[(int(row["hero_id"]), "families")].reindex(mine.index)
        table.at[i, "ari"] = float(adjusted_rand_score(base, mine))
        if row["fit"] in GATED and not row["gated"] and not mine.equals(base):
            raise AssertionError(
                f"{row['hero']} is outside the gate but its {row['fit']} labels "
                "differ from families alone"
            )
    return table, labels


def concentration(table: pd.DataFrame, fit: str) -> dict:
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


def verdicts(table: pd.DataFrame) -> tuple[list[str], dict[str, dict]]:
    ks = table.pivot(index="hero", columns="fit", values="k")
    base = concentration(table, "families")
    base_names = table[table["fit"] == "families"].set_index("hero")["names"]
    lines = [
        f"Families control: {base['n']} split heroes, top separating item "
        f"{base['top_item']!r} carries {base['top_share']:.0%}, top three "
        f"carry {base['top3_share']:.0%}.",
        "",
    ]
    out: dict[str, dict] = {}
    for fit in ("order",) + CANDIDATES:
        rows = table[table["fit"] == fit].set_index("hero")
        lost = sorted(ks.index[ks[fit] < ks["families"]])
        gained = sorted(ks.index[ks[fit] > ks["families"]])
        conc = concentration(table, fit)
        gated = sorted(rows.index[rows["gated"].astype(bool)])
        changed = sorted(
            h for h in (gated if fit in GATED else rows.index)
            if ks.loc[h, fit] != ks.loc[h, "families"] or rows.loc[h, "ari"] < CHANGED_ARI
        )
        renamed = sorted(h for h in rows.index if rows.loc[h, "names"] != base_names[h])
        r1 = not lost
        r2 = bool(gained) or (fit in GATED and bool(changed))
        r3 = conc["top_share"] <= MAX_TOP_ITEM_SHARE and (
            base["top3_share"] <= 0
            or conc["top3_share"] <= base["top3_share"] * MAX_CONCENTRATION_RATIO
        )
        out[fit] = {
            "lost": lost, "gained": gained, "changed": changed, "renamed": renamed,
            "r1": r1, "r2": r2, "r3": r3, "pass": r1 and r2 and r3, "conc": conc,
            "gated": gated,
        }
        title = f"### `{fit}`" + (" (reference, ADR 0003's rejected block)" if fit == "order" else "")
        lines += [title, ""]
        if fit in GATED:
            lines.append(f"- Heroes given the block: {len(gated)} ({', '.join(gated)})")
        lines += [
            f"- Splits gained: {', '.join(gained) if gained else 'none'}",
            f"- Splits **lost**: {', '.join(lost) if lost else 'none'}",
            f"- Split heroes: {conc['n']}; top separating item "
            f"{conc['top_item']!r} at {conc['top_share']:.0%}, top three at "
            f"{conc['top3_share']:.0%}",
            f"- Heroes whose split changed (k differs, or ARI below {CHANGED_ARI}): "
            f"{len(changed)}" + (f" ({', '.join(changed)})" if changed else ""),
            f"- Heroes whose proposed names changed: {len(renamed)}"
            + (f" ({', '.join(renamed)})" if renamed else ""),
        ]
        if fit != "order":
            lines += [
                "",
                f"**R1 no hero loses a split: {'yes' if r1 else 'NO'}. "
                f"R2 a split is gained{' or a gated split changes' if fit in GATED else ''}: "
                f"{'yes' if r2 else 'NO'}. "
                f"R3 separating items don't concentrate: {'yes' if r3 else 'NO'}.**",
                "",
                f"`{fit}` passes R1-R3; held-out top-1 decides."
                if out[fit]["pass"]
                else f"`{fit}` fails the rule and stays out of the clustering.",
            ]
        lines.append("")
    return lines, out


# ---------------------------------------------------------------- roster


def permutation_p(values: pd.Series, flags: pd.Series, rng: np.random.Generator) -> tuple[float, float, float]:
    """(mean flagged, mean other, two-sided p) for the difference in means."""
    values = values.astype(float)
    flags = flags.reindex(values.index).fillna(False).astype(bool)
    keep = values.notna()
    values, flags = values[keep].to_numpy(), flags[keep].to_numpy()
    observed = values[flags].mean() - values[~flags].mean()
    hits = 0
    for _ in range(PERMUTATIONS):
        perm = rng.permutation(flags)
        diff = values[perm].mean() - values[~perm].mean()
        hits += abs(diff) >= abs(observed) - 1e-12
    return float(values[flags].mean()), float(values[~flags].mean()), (hits + 1) / (PERMUTATIONS + 1)


def slot_family_distance(purchases: pd.DataFrame) -> pd.Series:
    """Per player, total-variation distance between shop-tab and family shares."""
    slots = archetype.slot_shares(purchases)
    fam = archetype.family_shares(purchases)
    both = slots.join(fam, how="inner")
    # `ult` is a family in CONTEXT.md; the code may not have it yet.
    groups = {
        "share_weapon": [c for c in ("gun", "melee") if c in fam.columns],
        "share_spirit": [c for c in ("spirit", "ult") if c in fam.columns],
    }
    used = {c for cols in groups.values() for c in cols}
    rest = [c for c in fam.columns if c not in used]
    diff = (
        (both["share_weapon"] - both[groups["share_weapon"]].sum(axis=1)).abs()
        + (both["share_spirit"] - both[groups["share_spirit"]].sum(axis=1)).abs()
        + (both["share_vitality"] - both[rest].sum(axis=1)).abs()
    )
    return 0.5 * diff


def roster_rows(
    purchases: pd.DataFrame,
    base_k: pd.Series,
    exposure: pd.Series,
    gate: set[int],
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Per hero: forced-k=2 separation, its placebo floor, axis share, and more."""
    hero_names = {h: v.name for h, v in assets.load_heroes().items()}
    rows = []
    for hero_id, group in purchases.groupby("hero_id"):
        hero_id = int(hero_id)
        features = archetype.feature_matrix(group)
        labels, _ = archetype._fit_k(features, 2)
        series = pd.Series(labels, index=features.index)
        separation = archetype._separation(archetype.cluster_prevalence(group, series))
        floor = 0.0
        for _ in range(PLACEBO_DRAWS):
            shuffled = pd.Series(rng.permutation(labels), index=features.index)
            floor = max(floor, archetype._separation(archetype.cluster_prevalence(group, shuffled)))
        centroids = features.groupby(series).mean()
        gap = (centroids.iloc[0] - centroids.iloc[1]).abs()
        axis = float((gap["gun"] + gap["spirit"]) / gap.sum()) if gap.sum() else float("nan")
        distance = slot_family_distance(group)
        spirit = features["spirit"]
        w = exposure.reindex(features.index).fillna(0.0)
        rho = rho_floor = float("nan")
        if hero_id in gate and w.std() > 0:
            rho = float(spirit.rank().corr(w.rank()))
            rho_floor = max(
                abs(float(spirit.rank().corr(pd.Series(rng.permutation(w.to_numpy()), index=w.index).rank())))
                for _ in range(PLACEBO_DRAWS)
            )
        rows.append(
            {
                "hero_id": hero_id,
                "hero": hero_names.get(hero_id, str(hero_id)),
                "gun_routed": hero_id in gate,
                "k_families": int(base_k.get(hero_id, 1)),
                "sep_k2": separation,
                "sep_k2_floor": floor,
                "sep_k2_excess": separation - floor,
                "axis_share": axis,
                "slot_family_tv": float(distance.mean()),
                "mean_gun_exposure": float(w.mean()),
                "rho_spirit_exposure": rho,
                "rho_floor": rho_floor,
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- imbue


def level_at(imbue_rows: pd.DataFrame, ability_rows: pd.DataFrame) -> pd.Series:
    """The target slot's level when each imbued item was bought."""
    points = ability_rows[ability_rows["signature_slot"] > 0][
        KEYS + ["signature_slot", "level", "game_time_s"]
    ].sort_values("game_time_s")
    target = imbue_rows[KEYS + ["signature_slot", "game_time_s"]].copy()
    target["_row"] = np.arange(len(target))
    target = target.sort_values("game_time_s")
    points = points.rename(columns={"game_time_s": "t"})
    points["level"] = points.groupby(KEYS + ["signature_slot"])["level"].cummax()
    merged = pd.merge_asof(
        target,
        points,
        left_on="game_time_s",
        right_on="t",
        by=KEYS + ["signature_slot"],
        direction="backward",
    )
    return merged.set_index("_row")["level"].fillna(0).astype(int).sort_index()


def imbue_level_table(imbue_rows: pd.DataFrame, levels: pd.Series) -> pd.DataFrame:
    df = imbue_rows.assign(level=levels.to_numpy(), ult=imbue_rows["signature_slot"] == 4)
    bucket = df["level"].map({0: "0 not unlocked", 1: "1 no upgrade", 2: "2-3", 3: "2-3", 4: "4 (5-pt tier)"})
    out = (
        df.assign(bucket=bucket)
        .groupby(["ult", "imbue_group", "bucket"]).size()
        .unstack("bucket").fillna(0).astype(int)
    )
    return out


def annotation_minute(text: str) -> int | None:
    match = re.search(r"~(\d+)min", text or "")
    return int(match.group(1)) if match else None


def build_defects(
    imbue_rows: pd.DataFrame, levels: pd.Series, labels: pd.DataFrame
) -> tuple[pd.DataFrame, list[str]]:
    """Every imbue target in the generated builds, checked against its own ability order."""
    signatures = assets.hero_signatures()
    names = {h: v.name for h, v in assets.load_heroes().items()}
    item_names = {i: it.name for i, it in assets.load_items().items()}
    tagged = imbue_rows.assign(level=levels.to_numpy()).merge(
        labels[KEYS + ["archetype_id"]], on=KEYS, how="left"
    )
    rows = []
    for path in sorted(glob.glob(str(BUILDS / "*.json"))):
        build = json.load(open(path, encoding="utf-8"))["hero_build"]
        hero_id = int(build["hero_id"])
        archetype_id = int(Path(path).stem.rsplit("_", 1)[1])
        slot_of = {a.id: s for s, a in signatures.get(hero_id, {}).items()}
        changes = build["details"].get("ability_order", {}).get("currency_changes", [])
        by_slot: dict[int, list[int | None]] = {}
        for change in changes:
            slot = slot_of.get(int(change["ability_id"]))
            if slot is not None:
                by_slot.setdefault(slot, []).append(annotation_minute(change.get("annotation", "")))
        for category in build["details"]["mod_categories"]:
            for mod in category["mods"]:
                target = mod.get("imbue_target_ability_id")
                if not target:
                    continue
                slot = slot_of.get(int(target))
                minute = annotation_minute(mod.get("annotation", ""))
                steps = by_slot.get(slot, [])
                unlock = steps[0] if steps else None
                first_upgrade = steps[1] if len(steps) > 1 else None
                cell = tagged[
                    (tagged["hero_id"] == hero_id)
                    & (tagged["archetype_id"] == archetype_id)
                    & (tagged["item_id"] == int(mod["ability_id"]))
                    & (tagged["signature_slot"] == slot)
                ]
                rows.append(
                    {
                        "build": f"{names.get(hero_id, hero_id)} {archetype_id}",
                        "item": item_names.get(int(mod["ability_id"]), mod["ability_id"]),
                        "slot": slot,
                        "buy_min": minute,
                        "unlock_min": unlock,
                        "first_upgrade_min": first_upgrade,
                        "before_unlock": minute is not None and unlock is not None and minute < unlock,
                        "ult_before_upgrade": slot == 4 and minute is not None
                        and first_upgrade is not None and minute < first_upgrade,
                        "cell_imbues": len(cell),
                        "cell_share_before_unlock": float((cell["level"] == 0).mean()) if len(cell) else float("nan"),
                        "cell_share_below_l2": float((cell["level"] <= 1).mean()) if len(cell) else float("nan"),
                    }
                )
    table = pd.DataFrame(rows)
    defects = []
    for row in table.itertuples():
        if row.before_unlock and not (row.cell_share_before_unlock >= 0.5):
            defects.append(f"{row.build}: {row.item} into slot {row.slot} before unlock")
        if row.ult_before_upgrade and not (row.cell_share_below_l2 >= 0.5):
            defects.append(f"{row.build}: {row.item} into the ult before its first upgrade")
    return table, defects


# ---------------------------------------------------------------- sheet


def fmt(value: float, spec: str = ".2f") -> str:
    return "--" if value is None or pd.isna(value) else format(value, spec)


def sheet(
    table: pd.DataFrame,
    verdict: list[str],
    roster: pd.DataFrame,
    tests: list[str],
    asset_lines: list[str],
    imbue_table: pd.DataFrame,
    builds: pd.DataFrame,
    defects: list[str],
) -> str:
    wide = table.pivot(index="hero", columns="fit", values="k")
    items = table.pivot(index="hero", columns="fit", values="item")
    aris = table.pivot(index="hero", columns="fit", values="ari")
    gated = table[table["fit"] == "gunproc"].set_index("hero")["gated"]

    def item(hero: str, fit: str) -> str:
        value = items.loc[hero, fit]
        return "--" if pd.isna(value) or not str(value) else str(value)

    lines = [
        "# Do AP upgrade effects or gun-routed abilities belong in the clustering?",
        "",
        "Generated by `scripts/compare_upgrade_fits.py` for #42. The decision is",
        "ADR 0004. Every number here comes from one run.",
        "",
        "## What the assets say",
        "",
    ] + asset_lines + [
        "",
        "## Six fits of the same purchase table",
        "",
        "`families` is the control and `order` is ADR 0003's rejected block,",
        "refitted as a same-run reference. `effects` and `effects_t5` add",
        "effect-category exposure (all tiers, 5-point tier only). `gunproc` and",
        "`reroute` touch only heroes with a gun-routed ability (marked `*`);",
        "every other hero's fit is identical to families, which the script checks.",
        "",
        "The separating item is the item with the biggest pick-rate gap between",
        "the fit's two least distinct clusters. ARI is against the families",
        "labels. Don't compare separations across different k.",
        "",
        "| hero | " + " | ".join(f"k {f}" for f in FITS)
        + " | ARI effects | ARI gunproc | ARI reroute | separating item (families) "
        "| separating item (effects) |",
        "|---|" + "---|" * (len(FITS) + 5),
    ]
    for hero in sorted(wide.index):
        mark = " \\*" if bool(gated.get(hero, False)) else ""
        ks = " | ".join(str(int(wide.loc[hero, f])) for f in FITS)
        lines.append(
            f"| {hero}{mark} | {ks} | {fmt(aris.loc[hero, 'effects'])} "
            f"| {fmt(aris.loc[hero, 'gunproc'])} | {fmt(aris.loc[hero, 'reroute'])} "
            f"| {item(hero, 'families')} | {item(hero, 'effects')} |"
        )
    lines += ["", "## Verdict", ""] + verdict

    lines += [
        "## Gun-routed heroes against the roster",
        "",
        f"Every hero fitted at a forced k=2 on families. `floor` is the largest",
        f"separation over {PLACEBO_DRAWS} shuffles of the same labels (same group",
        "sizes, same code). `axis` is the share of the k=2 centroid gap on gun",
        "plus spirit. `tab vs family` is the mean total-variation distance",
        "between a player's shop-tab and family shares. `rho` is the rank",
        "correlation between spirit share and gun-routed exposure, with its",
        f"shuffled floor (largest |rho| over {PLACEBO_DRAWS} shuffles).",
        "",
        "| hero | gun-routed | k families | sep k=2 | floor | axis | tab vs family | exposure | rho | rho floor |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in roster.sort_values("hero").itertuples():
        lines.append(
            f"| {row.hero} | {'yes' if row.gun_routed else ''} | {row.k_families} "
            f"| {fmt(row.sep_k2)} | {fmt(row.sep_k2_floor)} | {fmt(row.axis_share)} "
            f"| {fmt(row.slot_family_tv)} | {fmt(row.mean_gun_exposure)} "
            f"| {fmt(row.rho_spirit_exposure)} | {fmt(row.rho_floor)} |"
        )
    lines += ["", f"Permutation tests over heroes ({PERMUTATIONS:,} draws, two-sided):", ""] + tests

    lines += [
        "",
        "## Imbues against the target's upgrade tier",
        "",
        "Every imbue row, by the target ability's level when the item was bought.",
        "",
        "| target | group | " + " | ".join(imbue_table.columns) + " | total |",
        "|---|---|" + "---|" * (len(imbue_table.columns) + 1),
    ]
    for (ult, group), row in imbue_table.iterrows():
        total = int(row.sum())
        cells = " | ".join(f"{int(v):,} ({v / total:.1%})" for v in row)
        lines.append(f"| {'ult' if ult else 'slots 1-3'} | {group} | {cells} | {total:,} |")
    lines += [
        "",
        "## Imbue targets in the generated builds",
        "",
        f"{len(builds)} imbue targets across {builds['build'].nunique()} builds "
        "(`data/builds`, held items only). Minutes are the builds' own `~Nmin`",
        "annotations, so both sides carry the same rounding.",
        "",
        f"- Bought before the build's own order unlocks the target: "
        f"{int(builds['before_unlock'].sum())}",
        f"- Ult targets: {int((builds['slot'] == 4).sum())}; bought before the ult's first "
        f"upgrade: {int(builds['ult_before_upgrade'].sum())}",
        f"- Defects by the rule: {len(defects)}"
        + ("" if not defects else " (" + "; ".join(defects) + ")"),
        "",
        "| build | item | slot | buy | unlock | 1st upgrade | cell imbues | cell before unlock |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in builds.itertuples():
        lines.append(
            f"| {row.build} | {row.item} | {row.slot} | {fmt(row.buy_min, '.0f')} "
            f"| {fmt(row.unlock_min, '.0f')} | {fmt(row.first_upgrade_min, '.0f')} "
            f"| {row.cell_imbues:,} | {fmt(row.cell_share_before_unlock, '.1%')} |"
        )
    return "\n".join(lines) + "\n"


def asset_summary() -> list[str]:
    table = upgrades.ability_table()
    sig = upgrades.signature_table()
    heroes = {h: v.name for h, v in assets.load_heroes().items()}
    broad = table[table["weapon_broad"]]
    strict = table[table["weapon_attached"]]
    routed = sig[sig["weapon_attached"] & sig["spirit_scaling"]]
    tier_names = {0: "base", 1: "1-point", 2: "2-point", 3: "5-point"}
    by_tier = routed["weapon_tier"].map(tier_names).value_counts()
    listed_only = sig[sig["weapon_listed"] & ~sig["weapon_attached"]]
    raw = upgrades._raw_abilities()
    etech = sum(
        1 for a in broad["ability_id"]
        if any(
            isinstance(p, dict)
            and (p.get("scale_function") or {}).get("specific_stat_scale_type") == "ETechPower"
            for p in (raw[a].get("properties") or {}).values()
        )
    )
    upgrade_names = {
        u["name"]
        for e in raw.values()
        for t in e.get("upgrades") or []
        for u in t.get("property_upgrades") or []
    }
    return [
        f"- Hero ability records: {len(table)} across {table['hero_id'].nunique()} heroes; "
        f"{int(table['has_upgrades'].sum())} have `upgrades`, all with exactly 3 tiers "
        f"({int((table['n_tiers'] == 3).sum())}); {len(upgrade_names)} distinct upgrade "
        "property names.",
        f"- The old regex (docs/game-mechanics.md): {len(broad)} abilities on "
        f"{broad['hero_id'].nunique()} heroes. Of those, {etech} have a property whose "
        "`scale_function.specific_stat_scale_type` is `ETechPower`, and "
        f"{int(broad['spirit_scaling'].sum())} scale with spirit when "
        "`scale_function_tech_damage` is also counted. The documented 41 matches neither.",
        f"- Strict rule (the caster's own gun, set at base or by an upgrade): {len(strict)} "
        f"abilities on {strict['hero_id'].nunique()} heroes, "
        f"{int(strict['spirit_scaling'].sum())} of them spirit-scaling.",
        f"- Gun-routed signature abilities of playable heroes: {len(routed)} on "
        f"{routed['hero_id'].nunique()} of 38 heroes. The gun effect arrives: "
        + ", ".join(f"{tier_names[t]} {int(by_tier.get(tier_names[t], 0))}" for t in range(4))
        + ".",
        f"- Signature abilities with a weapon property listed but never set (value 0, no "
        f"upgrade gives it): {len(listed_only)} ("
        + ", ".join(f"{heroes[int(r.hero_id)]} {r.name}" for r in listed_only.itertuples())
        + ").",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", default="docs/UPGRADE-FIT-COMPARISON.md")
    parser.add_argument(
        "--heroes",
        default="",
        help="comma-separated hero names, for a quick smoke run only; the sheet needs all",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    for path in (PURCHASES, ABILITIES, IMBUES, LABELS):
        if not path.exists():
            logging.error("needs %s; run scripts/refit.py first", path)
            return 1

    rng = np.random.default_rng(SEED)
    purchases = pd.read_parquet(PURCHASES, columns=COLUMNS)
    ability_rows = pd.read_parquet(ABILITIES)
    if args.heroes:
        wanted = {assets.resolve_hero(name) for name in args.heroes.split(",")}
        purchases = purchases[purchases["hero_id"].isin(wanted)]
        ability_rows = ability_rows[ability_rows["hero_id"].isin(wanted)]
    logging.info("%s purchases, %s ability points", f"{len(purchases):,}", f"{len(ability_rows):,}")

    routed = upgrades.gun_routed_slots()
    gate = set(routed)
    exposure = upgrades.gun_exposure(ability_rows, routed)

    gated_purchases = purchases[purchases["hero_id"].isin(gate)]
    families = archetype.family_shares(gated_purchases)
    blocks: dict[str, pd.DataFrame | None] = {
        "families": None,
        "order": archetype.scale_block(abilities.point_order_features(ability_rows), BLOCK_WEIGHT),
        "effects": archetype.scale_block(upgrades.effect_features(ability_rows), BLOCK_WEIGHT),
        "effects_t5": archetype.scale_block(
            upgrades.effect_features(ability_rows, levels=(4,)), BLOCK_WEIGHT
        ),
        "gunproc": archetype.scale_block(upgrades.gun_block(families, exposure), BLOCK_WEIGHT),
        "reroute": None,
    }

    table, _ = fit_rows(purchases, blocks, exposure, gate)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(out.with_suffix(".csv"), index=False)
    verdict, results = verdicts(table)

    base_k = table[table["fit"] == "families"].set_index("hero_id")["k"]
    roster = roster_rows(purchases, base_k, exposure, gate, rng)
    flags = roster.set_index("hero")["gun_routed"]
    tests = []
    for column, label in (
        ("k_families", "split under families (k>1)"),
        ("sep_k2_excess", "forced k=2 separation above its placebo floor"),
        ("axis_share", "share of the k=2 centroid gap on gun and spirit"),
        ("slot_family_tv", "tab vs family distance"),
    ):
        values = roster.set_index("hero")[column]
        if column == "k_families":
            values = (values > 1).astype(float)
        mine, rest, p = permutation_p(values, flags, rng)
        tests.append(
            f"- {label}: gun-routed {mine:.3f}, others {rest:.3f}, p = {p:.3f}"
            + (" (differs)" if p < ALPHA else " (no difference)")
        )
    floor_pass = roster[roster["gun_routed"]]
    above = floor_pass[floor_pass["rho_spirit_exposure"].abs() > floor_pass["rho_floor"]]
    tests.append(
        f"- Spirit share and gun-routed exposure are correlated above their shuffled "
        f"floor on {len(above)} of {len(floor_pass)} gun-routed heroes "
        f"(median rho {floor_pass['rho_spirit_exposure'].median():+.3f})."
    )

    imbue_rows = pd.read_parquet(IMBUES)
    levels = level_at(imbue_rows, ability_rows)
    imbue_table = imbue_level_table(imbue_rows, levels)
    labels = pd.read_parquet(LABELS)
    builds, defects = build_defects(imbue_rows, levels, labels)

    out.write_text(
        sheet(table, verdict, roster, tests, asset_summary(), imbue_table, builds, defects),
        encoding="utf-8",
    )
    roster.to_csv(out.with_name(out.stem + "-ROSTER.csv"), index=False)
    for line in verdict + tests:
        print(line)
    print(f"\nimbue defects in generated builds: {len(defects)}")
    print(f"wrote {out}")
    passing = [f for f in CANDIDATES if results[f]["pass"]]
    print(f"fits that pass R1-R3: {', '.join(passing) if passing else 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
