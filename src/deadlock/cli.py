"""The command line: what to build before a match, what to buy during one.

Five commands, matching the two products:

    deadlock heroes                     what can be built, and how
    deadlock build  --hero Ivy          a full ordered build (pre-match)
    deadlock next   --hero Ivy ...      what to buy now (in-match)
    deadlock watch  --hero Ivy          the same, without retyping
    deadlock why    --hero Ivy --item X the table row behind a recommendation

`why` is a command rather than a debug flag because inspectability is the
point of this project: every number here traces to a literal table row with a
count you can check.

Every command that gives advice takes `--badge`, which weights the tables
toward a bracket. It defaults high rather than to the population median: a
build tool exists to show what strong players do, and for a long time the
kernel that does this was implemented, tested, and never passed by any caller,
so the advice imitated the median player. `--badge all` asks for the whole
population instead.

The model is fitted once and cached under data/processed, since fitting takes
about a minute over 5M purchases and nobody wants that mid-match. Each bracket
caches its own file, and a cached model records the bracket it was fitted for,
so two brackets cannot quietly share one set of tables.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from . import (
    abilityorder,
    archetype,
    assets,
    build,
    buildfmt,
    counters,
    evaluate,
    imbue,
    sequence,
)
from .state import GameState

ABILITIES_PATH = Path("data/processed/abilities.parquet")
ABILITY_MODEL_PATH = Path("data/processed/ability_model.npz")
MODEL_PATH = Path("data/processed/sequence_model.npz")
COUNTERS_PATH = Path("data/processed/counter_lifts.parquet")
IMBUES_PATH = Path("data/processed/imbues.parquet")
PURCHASES = Path("data/processed/purchases.parquet")
COLUMNS = [
    "match_id",
    "player_slot",
    "account_id",
    "hero_id",
    "item_id",
    "buy_index",
    "buy_time_s",
    "won",
    "average_badge",
]


def parse_time(value: str) -> float:
    """Accept 8:30 or 510. A player reads the clock, not a second count."""
    value = value.strip()
    if ":" in value:
        minutes, _, seconds = value.partition(":")
        return int(minutes) * 60 + float(seconds)
    return float(value)


def target_badge(args: argparse.Namespace) -> float | None:
    """The bracket the advice should imitate, from `--badge`.

    A number weights the tables toward that badge; `all` asks for the whole
    population. The default is high rather than average on purpose -- a build
    tool exists to show what strong players do, and until this was wired the
    tool imitated the median player instead.

    Every command built by `build_parser` carries `--badge`, so the fallback is
    for callers that build a namespace by hand -- the tests do, and a namespace
    missing one field should not crash a command that never needed it.
    """
    if "badge" not in vars(args):
        return sequence.DEFAULT_TARGET_BADGE
    return args.badge


def badge_argument(raw: str) -> float | None:
    """`--badge` as argparse sees it, refusing anything that is not a bracket."""
    try:
        return sequence.parse_target_badge(raw)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"takes a number or 'all', not {raw!r}"
        ) from None


def model_path(badge: float | None) -> Path:
    """One cached model per bracket.

    Two brackets sharing a file would serve whichever was fitted last while
    reporting the one that was asked for, so the bracket is in the name.
    """
    if badge == sequence.DEFAULT_TARGET_BADGE:
        return MODEL_PATH
    suffix = "all" if badge is None else f"b{badge:g}"
    return MODEL_PATH.with_name(f"{MODEL_PATH.stem}_{suffix}.npz")


def ability_model_path(badge: float | None) -> Path:
    if badge == sequence.DEFAULT_TARGET_BADGE:
        return ABILITY_MODEL_PATH
    suffix = "all" if badge is None else f"b{badge:g}"
    return ABILITY_MODEL_PATH.with_name(f"{ABILITY_MODEL_PATH.stem}_{suffix}.npz")


def load_model(
    *, refit: bool = False, badge: float | None = sequence.DEFAULT_TARGET_BADGE
) -> sequence.SequenceModel:
    path = model_path(badge)
    if path.exists() and not refit:
        cached = sequence.SequenceModel.load(path)
        # A model fitted before the bracket was recorded, or under a different
        # one, is not the model that was asked for. Refit rather than serve it.
        if cached.target_badge == badge:
            return cached
    print("fitting the model (about a minute; cached afterwards)...", file=sys.stderr)
    purchases = pd.read_parquet(PURCHASES, columns=COLUMNS)
    labels, _ = archetype.load()
    model = sequence.fit(purchases, labels, target_badge=badge)
    model.save(path)
    return model


def load_ability_model(
    *, refit: bool = False, badge: float | None = sequence.DEFAULT_TARGET_BADGE
):
    """The ability-order model and the point frame its timings come from.

    Returns (None, None) when the ability table has not been built, so the tool
    degrades to item-only advice rather than failing. The frame comes back
    alongside the model because the clock is part of every deep context -- see
    `abilityorder.generate_order`.
    """
    if not ABILITIES_PATH.exists():
        return None, None
    raw = pd.read_parquet(ABILITIES_PATH)
    labels, _ = archetype.load()
    if badge is not None and PURCHASES.exists():
        # The badge lives on the purchase rows, so it is carried across before
        # anything reads it -- and before the frame is built, because the frame
        # is where the timings come from and those follow the bracket too.
        raw = abilityorder.attach_badges(
            raw,
            pd.read_parquet(
                PURCHASES, columns=["match_id", "player_slot", "average_badge"]
            ),
        )
    frame = abilityorder.point_frame(raw).merge(
        labels[["match_id", "player_slot", "archetype_id"]],
        on=["match_id", "player_slot"],
        how="left",
    )
    path = ability_model_path(badge)
    if path.exists() and not refit:
        cached = sequence.SequenceModel.load(path)
        if cached.target_badge == badge:
            return cached, frame
    print("fitting the ability-order model...", file=sys.stderr)
    model = abilityorder.fit(raw, labels, target_badge=badge)
    model.save(path)
    return model, frame


def load_counters(*, refit: bool = False) -> pd.DataFrame:
    if COUNTERS_PATH.exists() and not refit:
        return pd.read_parquet(COUNTERS_PATH)
    frame = pd.read_parquet(
        PURCHASES, columns=["match_id", "player_slot", "hero_id", "team", "item_id"]
    )
    lifts = counters.counter_lifts(frame)
    lifts.to_parquet(COUNTERS_PATH, index=False)
    return lifts


def resolve_archetype(hero_id: int, query: str | None, meta: dict) -> tuple[int, str]:
    """Which archetype the player declared. Declaration beats inference."""
    entries = (meta.get("heroes") or {}).get(str(hero_id), {}).get("archetypes") or []
    if not entries:
        return 0, ""
    if query is None:
        first = entries[0]
        if len(entries) > 1:
            names = [e.get("name") or str(e["archetype_id"]) for e in entries]
            raise SystemExit(
                f"this hero has {len(entries)} archetypes; pick one with "
                f"--archetype: {', '.join(names)}"
            )
        return int(first["archetype_id"]), first.get("name", "")
    names = {int(e["archetype_id"]): e.get("name", "") for e in entries}
    lowered = query.lower()
    for archetype_id, name in names.items():
        if name.lower() == lowered or name.lower().startswith(lowered):
            return archetype_id, name
    for archetype_id, name in names.items():
        if lowered in name.lower():
            return archetype_id, name
    raise SystemExit(
        f"no archetype matching {query!r}. Options: {', '.join(names.values())}"
    )


def cmd_heroes(args: argparse.Namespace) -> int:
    _, meta = archetype.load()
    heroes = assets.playable_heroes()
    for hero_id in sorted(meta.get("heroes", {}), key=lambda h: heroes[int(h)].name if int(h) in heroes else ""):
        entry = meta["heroes"][hero_id]
        name = entry.get("hero_name") or heroes.get(int(hero_id), "?")
        archetypes = entry.get("archetypes", [])
        if args.archetypes and len(archetypes) > 1:
            print(f"{name}")
            for a in archetypes:
                win = a.get("win_rate")
                win_text = f", {win:.0%} win" if isinstance(win, float) else ""
                print(
                    f"    {a.get('name', a['archetype_id']):32s} "
                    f"{a['share']:.0%} of players{win_text}"
                )
        elif not args.archetypes:
            print(f"{name:18s} {len(archetypes)} archetype(s)")
    return 0


def load_imbue_targets(
    cell: pd.DataFrame | None, item_ids: list[int]
) -> list[imbue.ImbueTarget]:
    """Which ability this cell points each recommended imbueable item at.

    Nine shopable items can be imbued, and for those the item is only half the
    advice -- Mystic Reverb aimed at the wrong ability is a wasted 3,200 souls.
    Restricted to the same (hero, archetype) rows the build was generated from,
    because the target is a property of the build and not of the item: Dynamo's
    ult cluster and its stomp cluster aim the same item at different abilities.

    Returns nothing when the imbue table has not been built, so the tool
    degrades to item-only advice the way the ability order does.
    """
    if cell is None or not IMBUES_PATH.exists():
        return []
    imbues = pd.read_parquet(
        IMBUES_PATH,
        columns=["match_id", "player_slot", "item_id", "imbued_ability_id"],
    ).merge(
        cell[["match_id", "player_slot"]].drop_duplicates(),
        on=["match_id", "player_slot"],
    )
    return imbue.targets_for_build(imbues, item_ids)


def cmd_build(args: argparse.Namespace) -> int:
    hero_id = assets.resolve_hero(args.hero)
    labels, meta = archetype.load()
    archetype_id, archetype_name = resolve_archetype(hero_id, args.archetype, meta)
    badge = target_badge(args)
    model = load_model(refit=args.refit, badge=badge)

    staples = None
    cell = None
    if PURCHASES.exists():
        purchases = pd.read_parquet(PURCHASES, columns=COLUMNS)
        cell = purchases[purchases["hero_id"] == hero_id].merge(
            labels[
                (labels["hero_id"] == hero_id)
                & (labels["archetype_id"] == archetype_id)
            ][["match_id", "player_slot"]],
            on=["match_id", "player_slot"],
        )
        prevalence = evaluate.item_prevalence(cell)
        staples = {
            int(i): float(v)
            for i, v in prevalence[
                prevalence >= evaluate.PREVALENCE_THRESHOLD
            ].items()
        }

    generated = build.generate_build(
        hero_id,
        archetype_id,
        model,
        staples=staples,
        hero_name=assets.playable_heroes()[hero_id].name,
        archetype_name=archetype_name,
    )
    bracket = sequence.describe_badge(badge)
    print(f"\n{generated.label}  ({len(generated.items)} buys, "
          f"{len(generated.held_items())} held, {generated.total_cost:,} souls, "
          f"{bracket})\n")
    for item in generated.items:
        print(f"  {item}")

    ability_order = []
    ability_model, ability_frame = load_ability_model(refit=args.refit, badge=badge)
    if ability_model is not None:
        try:
            ability_order = abilityorder.generate_order(
                ability_model,
                ability_frame,
                hero_id,
                archetype_id,
                target_badge=badge,
            )
        except ValueError as exc:
            print(f"\nno ability order: {exc}")
    if ability_order:
        print("\nability points:")
        for line in abilityorder.format_order(ability_order).splitlines():
            print("  " + line)

    targets = load_imbue_targets(cell, [item.item_id for item in generated.items])
    if targets:
        print("\nimbue:")
        for target in targets:
            print(f"  {target}")

    if args.explain:
        print("\nwhy each pick:")
        inventory = build.Inventory()
        components = assets.component_map()
        for item in generated.items:
            state = GameState(
                hero_id=hero_id,
                game_time_s=item.buy_time_s,
                souls_available=10**9,
                owned_item_ids=frozenset(inventory.purchased),
                purchased=tuple(inventory.purchased),
                archetype_posterior={archetype_id: 1.0},
            )
            print("\n" + model.explain(state, item.item_id))
            inventory.buy(item.item_id, components)

    if args.export:
        path = buildfmt.export_build(
            generated,
            args.export,
            ability_order=ability_order,
            imbue_targets={
                t.item_id: t.ability_id for t in targets if t.ability_id is not None
            },
            description=(
                "Purchase order. Only held items are exported: the build schema "
                "cannot express a sale, and about a third of these purchases are "
                "components absorbed into later items."
            ),
        )
        print(f"\nexported -> {path}")
    return 0


def _state_from_args(args, hero_id, archetype_posterior) -> GameState:
    owned = [assets.resolve_item(name) for name in _split(args.owned)]
    enemies = [assets.resolve_hero(name) for name in _split(getattr(args, "enemies", ""))]
    return GameState(
        hero_id=hero_id,
        game_time_s=parse_time(args.time),
        souls_available=args.souls if args.souls else 10**9,
        owned_item_ids=frozenset(owned),
        purchased=tuple(owned),
        enemy_hero_ids=tuple(enemies),
        archetype_posterior=archetype_posterior,
    )


def _split(value: str | None) -> list[str]:
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def _print_recommendations(
    model, state, lifts, *, top: int, item_names, hero_names, label: str = ""
) -> None:
    recommendations = model.predict(
        state, top=top, affordable_only=bool(state.souls_available < 10**9)
    )
    if not recommendations:
        print("  (no data for this state)")
        return
    annotated = counters.annotate(recommendations, state.enemy_hero_ids, lifts)
    for rec, counter in annotated:
        line = f"  {rec}"
        if counter is not None:
            line += f"   [{counter.describe(item_names, hero_names)}]"
        print(line)


def _print_ability_points(hero_id: int, archetype_id: int, args) -> None:
    """Where the next point goes, given the points already spent.

    The points so far have to be supplied: a slot at level 4 is the only
    illegal move in an ability order, and without knowing the current levels
    the tool would happily recommend a fifth point in a maxed ability.
    """
    spent = _split(getattr(args, "points", None))
    if not spent:
        return
    model, frame = load_ability_model(refit=args.refit, badge=target_badge(args))
    if model is None:
        print("\n  (no ability table built)")
        return

    signatures = assets.hero_signatures().get(hero_id, {})
    by_name = {ability.name.lower(): slot for slot, ability in signatures.items()}
    slots = []
    for name in spent:
        slot = by_name.get(name.lower())
        if slot is None:
            options = ", ".join(a.name for a in signatures.values())
            raise SystemExit(f"no ability {name!r} on this hero. Options: {options}")
        slots.append(slot)

    levels = {slot: slots.count(slot) for slot in set(slots)}
    over = [signatures[s].name for s, n in levels.items() if n > abilityorder.MAX_LEVEL]
    if over:
        raise SystemExit(f"more than four points in: {', '.join(over)}")

    state = GameState(
        hero_id=hero_id,
        game_time_s=parse_time(args.time),
        souls_available=0,
        purchased=tuple(slots),
        archetype_posterior={archetype_id: 1.0},
    )
    ranked = abilityorder.recommend(model, state, levels=levels)
    print(f"\nnext ability point ({len(slots)} spent):")
    if not ranked:
        print("  (nothing legal left -- every ability is maxed)")
    for point in ranked:
        print("  " + str(point))


def cmd_next(args: argparse.Namespace) -> int:
    hero_id = assets.resolve_hero(args.hero)
    _, meta = archetype.load()
    model = load_model(refit=args.refit, badge=target_badge(args))
    lifts = load_counters() if args.enemies else pd.DataFrame()
    item_names = {i: it.name for i, it in assets.load_items().items()}
    hero_names = {i: h.name for i, h in assets.load_heroes().items()}

    owned = [assets.resolve_item(name) for name in _split(args.owned)]
    entries = (meta.get("heroes") or {}).get(str(hero_id), {}).get("archetypes") or []

    if args.archetype:
        archetype_id, name = resolve_archetype(hero_id, args.archetype, meta)
        posterior = {archetype_id: 1.0}
        print(f"\n{name or assets.playable_heroes()[hero_id].name} "
              f"-- {len(owned)} items, {args.time}\n")
        state = _state_from_args(args, hero_id, posterior)
        _print_recommendations(
            model, state, lifts, top=args.top, item_names=item_names, hero_names=hero_names
        )
        _print_ability_points(hero_id, archetype_id, args)
        return 0

    # No declaration: infer, and when the evidence is thin show each archetype
    # separately rather than blending. A blend can recommend an item that
    # neither build actually wants.
    posterior = archetype.archetype_posterior(owned, hero_id, meta)
    names = {int(e["archetype_id"]): e.get("name", "") for e in entries}
    ordered = sorted(posterior.items(), key=lambda kv: -kv[1])
    summary = " / ".join(f"{share:.0%} {names.get(a, a)}" for a, share in ordered)
    print(f"\n{assets.playable_heroes()[hero_id].name} -- {len(owned)} items, {args.time}")
    print(f"archetype not declared; inferred {summary}\n")

    plausible = [(a, share) for a, share in ordered if share >= args.min_share]
    if len(plausible) <= 1:
        chosen = plausible[0][0] if plausible else max(posterior, key=posterior.get)
        state = _state_from_args(args, hero_id, {chosen: 1.0} if plausible else posterior)
        _print_recommendations(
            model, state, lifts, top=args.top, item_names=item_names, hero_names=hero_names
        )
        # The archetype was inferred rather than declared, but the points were
        # still spent, and dropping the ability advice here is the mid-match
        # case `--points` exists for.
        _print_ability_points(hero_id, chosen, args)
        return 0

    for archetype_id, share in plausible:
        print(f"  if {names.get(archetype_id, archetype_id)} ({share:.0%}):")
        state = _state_from_args(args, hero_id, {archetype_id: 1.0})
        _print_recommendations(
            model, state, lifts, top=args.top, item_names=item_names, hero_names=hero_names
        )
        _print_ability_points(hero_id, archetype_id, args)
        print()
    return 0


def cmd_why(args: argparse.Namespace) -> int:
    hero_id = assets.resolve_hero(args.hero)
    item_id = assets.resolve_item(args.item)
    _, meta = archetype.load()
    model = load_model(refit=args.refit, badge=target_badge(args))
    owned = [assets.resolve_item(name) for name in _split(args.owned)]
    if args.archetype:
        archetype_id, _ = resolve_archetype(hero_id, args.archetype, meta)
        posterior = {archetype_id: 1.0}
    else:
        posterior = archetype.archetype_posterior(owned, hero_id, meta)
    state = _state_from_args(args, hero_id, posterior)
    print()
    print(model.explain(state, item_id))
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    """A session that keeps the model loaded. Mid-match, nobody retypes."""
    hero_id = assets.resolve_hero(args.hero)
    _, meta = archetype.load()
    model = load_model(refit=args.refit, badge=target_badge(args))
    lifts = load_counters() if args.enemies else pd.DataFrame()
    item_names = {i: it.name for i, it in assets.load_items().items()}
    hero_names = {i: h.name for i, h in assets.load_heroes().items()}
    hero_name = assets.playable_heroes()[hero_id].name

    archetype_id = None
    archetype_name = ""
    if args.archetype:
        archetype_id, archetype_name = resolve_archetype(hero_id, args.archetype, meta)

    owned: list[int] = []
    enemies = tuple(assets.resolve_hero(n) for n in _split(args.enemies))
    clock = parse_time(args.time) if args.time else 0.0

    print(f"{hero_name}{' -- ' + archetype_name if archetype_name else ''}")
    print("  '+ Item' to add, '- Item' to remove, 't 12:30' to set the clock,")
    print("  'why Item' to trace, Enter to re-rank, Ctrl-C or 'q' to quit.\n")

    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if line in {"q", "quit", "exit"}:
            return 0

        try:
            if line.startswith("+"):
                item_id = assets.resolve_item(line[1:])
                owned.append(item_id)
                clock = build.buy_time(len(owned))
            elif line.startswith("-"):
                item_id = assets.resolve_item(line[1:])
                if item_id in owned:
                    owned.remove(item_id)
            elif line.startswith("t "):
                clock = parse_time(line[2:])
            elif line.startswith("why "):
                item_id = assets.resolve_item(line[4:])
                posterior = (
                    {archetype_id: 1.0}
                    if archetype_id is not None
                    else archetype.archetype_posterior(owned, hero_id, meta)
                )
                state = GameState(
                    hero_id=hero_id,
                    game_time_s=clock,
                    souls_available=10**9,
                    owned_item_ids=frozenset(owned),
                    purchased=tuple(owned),
                    enemy_hero_ids=enemies,
                    archetype_posterior=posterior,
                )
                print(model.explain(state, item_id))
                continue
        except KeyError as error:
            print(f"  {error}")
            continue

        posterior = (
            {archetype_id: 1.0}
            if archetype_id is not None
            else archetype.archetype_posterior(owned, hero_id, meta)
        )
        state = GameState(
            hero_id=hero_id,
            game_time_s=clock,
            souls_available=10**9,
            owned_item_ids=frozenset(owned),
            purchased=tuple(owned),
            enemy_hero_ids=enemies,
            archetype_posterior=posterior,
        )
        held = ", ".join(item_names.get(i, str(i)) for i in owned) or "nothing"
        print(f"  [{int(clock)//60}:{int(clock)%60:02d}] {held}")
        _print_recommendations(
            model, state, lifts, top=args.top, item_names=item_names, hero_names=hero_names
        )
        print()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="deadlock", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p):
        p.add_argument("--refit", action="store_true", help="rebuild the cached model")
        p.add_argument(
            "--badge",
            type=badge_argument,
            default=sequence.DEFAULT_TARGET_BADGE,
            help=(
                "badge to weight the advice toward "
                f"(default {sequence.DEFAULT_TARGET_BADGE:.0f}; 'all' for the "
                "whole population)"
            ),
        )
        return p

    heroes = sub.add_parser("heroes", help="list heroes and their archetypes")
    heroes.add_argument("--archetypes", action="store_true")
    heroes.set_defaults(func=cmd_heroes)

    make = common(sub.add_parser("build", help="a full build for a hero"))
    make.add_argument("--hero", required=True)
    make.add_argument("--archetype", default=None)
    make.add_argument("--export", type=Path, default=None)
    make.add_argument("--explain", action="store_true")
    make.set_defaults(func=cmd_build)

    nxt = common(sub.add_parser("next", help="what to buy now"))
    nxt.add_argument("--hero", required=True)
    nxt.add_argument("--archetype", default=None)
    nxt.add_argument("--owned", default="")
    nxt.add_argument("--time", default="0:00")
    nxt.add_argument("--souls", type=int, default=0)
    nxt.add_argument("--enemies", default="")
    nxt.add_argument("--top", type=int, default=5)
    nxt.add_argument(
        "--points",
        default="",
        help="ability points already spent, in order, comma separated",
    )
    nxt.add_argument("--min-share", type=float, default=0.25)
    nxt.set_defaults(func=cmd_next)

    watch = common(sub.add_parser("watch", help="an interactive session"))
    watch.add_argument("--hero", required=True)
    watch.add_argument("--archetype", default=None)
    watch.add_argument("--enemies", default="")
    watch.add_argument("--time", default=None)
    watch.add_argument("--top", type=int, default=5)
    watch.set_defaults(func=cmd_watch)

    why = common(sub.add_parser("why", help="the table row behind a pick"))
    why.add_argument("--hero", required=True)
    why.add_argument("--item", required=True)
    why.add_argument("--archetype", default=None)
    why.add_argument("--owned", default="")
    why.add_argument("--time", default="0:00")
    why.add_argument("--souls", type=int, default=0)
    why.set_defaults(func=cmd_why)


    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyError as error:
        print(str(error).strip('"'), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
