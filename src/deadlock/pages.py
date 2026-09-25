"""Pages of the public site.

The public site is multi-page: one page per hero and archetype, a chooser,
and the methodology page. `scripts/build_site.py` is a different thing, one
self-contained page with every build inlined for review.

Each page is a pure function that takes the facts it states and returns
HTML. No model load, file write, or network call happens here, so a test can
assert on the returned string. Every number a page states is an argument, never
a literal in the prose: a figure typed into HTML is one a refit can make false
without anyone noticing. `scripts/build_pages.py` computes the facts and writes
the files.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from html import escape

REPO_URL = "https://github.com/quinn-zilly/deadlock-build-modeling"

# The site's look, from the visual direction #19 settled on: Variant B in
# prototypes/variant-b.built.html on the prototype/visual-direction branch.
# Dark-first, patinated stone ground, oxblood for structure, brass for
# numerals and staples, verdigris for the ability track. Alegreya Sans SC for
# nameplates, Sora for body text. Every page shares these tokens.
FONTS_URL = (
    "https://fonts.googleapis.com/css2?family=Alegreya+Sans+SC:wght@500;700;800"
    "&amp;family=Sora:wght@300;400;500;600&amp;display=swap"
)
SITE_CSS = """
:root {
  --ground: #14171A; --surface: #1B1F23; --raised: #232830;
  --edge: #2E343C; --edge-soft: #252A31;
  --oxblood: #7A2233; --oxblood-lit: #A63449;
  --brass: #C9973F; --brass-lit: #E3B663;
  --verdigris: #4E8C7D; --verdigris-lit: #6FB3A2;
  --text: #E9E2D4; --muted: #9C9484; --faint: #6E6759;
  color-scheme: dark;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--ground); color: var(--text);
  font-family: Sora, system-ui, -apple-system, "Segoe UI", sans-serif;
  font-size: 15px; line-height: 1.6; font-weight: 300;
  font-variant-numeric: tabular-nums;
}
h1, h2, h3 {
  font-family: "Alegreya Sans SC", Sora, sans-serif;
  margin: 0; line-height: 1.05; font-weight: 800;
}
a { color: var(--brass-lit); }
:focus-visible { outline: 2px solid var(--brass-lit); outline-offset: 2px; }

/* A page of reading: one column, nameplate heading, brass section titles. */
.prose { max-width: 42rem; margin: 0 auto; padding: 44px 16px 72px; }
.prose h1 {
  font-size: clamp(32px, 5.4vw, 48px);
  padding-bottom: 14px; border-bottom: 2px solid var(--oxblood);
}
.prose .lede { color: var(--muted); font-size: 16px; margin: 14px 0 8px; }
.prose h2 {
  font-size: 22px; color: var(--brass); letter-spacing: .02em;
  margin: 38px 0 10px;
}
.prose p { margin: 0 0 14px; }
.prose section:last-of-type {
  margin-top: 40px; border-top: 1px solid var(--edge); padding-top: 6px;
}
.prose section:last-of-type p { color: var(--muted); font-size: 13.5px; }

/* Site nav: the way home and to the methodology, on every page. */
nav.site {
  display: flex; gap: 20px; flex-wrap: wrap; padding: 12px 16px;
  border-bottom: 1px solid var(--edge); background: var(--surface);
  font-size: 13px;
}
nav.site a { color: var(--muted); text-decoration: none; }
nav.site a:first-child { color: var(--text); font-weight: 500; }
nav.site a:hover { color: var(--brass-lit); }

/* The hero surface: home, chooser, build page. */
.wide { max-width: 1120px; margin: 0 auto; padding: 0 16px 72px; }
.mast {
  display: flex; align-items: center; gap: 20px; padding: 30px 0 22px;
  border-bottom: 2px solid var(--oxblood); margin-bottom: 8px;
}
.portrait {
  width: 84px; height: 84px; flex: none; object-fit: cover;
  object-position: center top; border: 1px solid var(--edge);
  background: var(--raised);
}
.mast h1 { font-size: clamp(30px, 5.4vw, 46px); }
.kicker {
  margin: 0 0 6px; font-size: 12px; letter-spacing: .14em;
  text-transform: uppercase; color: var(--brass);
}
.mast .lede, .who { color: var(--muted); margin: 8px 0 0; max-width: 60ch; }
.prov { color: var(--faint); font-size: 12.5px; margin: 8px 0 0; }
.note, .legend { color: var(--faint); font-size: 12.5px; margin: 6px 0 12px; }
.sr {
  position: absolute; width: 1px; height: 1px; overflow: hidden;
  clip: rect(0 0 0 0); white-space: nowrap;
}

.heroes {
  list-style: none; margin: 24px 0 0; padding: 0; display: grid; gap: 12px;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
}
.hero {
  display: grid; grid-template-columns: 48px 1fr; gap: 0 12px;
  align-items: center; padding: 10px; text-decoration: none; color: var(--text);
  background: var(--surface); border: 1px solid var(--edge);
}
.hero:hover { border-color: var(--brass); }
.hero img {
  grid-row: 1 / 3; width: 48px; height: 48px; object-fit: cover;
  object-position: center top; background: var(--raised);
}
.hero .nm { font-weight: 500; }
.hero .sub { font-size: 12px; color: var(--faint); }

.chooser {
  display: grid; gap: 16px; margin-top: 22px;
  grid-template-columns: repeat(auto-fit, minmax(290px, 1fr));
}
.card {
  display: flex; flex-direction: column; background: var(--surface);
  border: 1px solid var(--edge);
}
.cardlink { display: block; padding: 16px 16px 0; color: inherit; text-decoration: none; }
.cardlink:hover h2 { color: var(--brass-lit); }
.card h2 { font-size: 24px; }
.stats { display: flex; flex-wrap: wrap; gap: 18px; padding: 10px 16px 14px; }
.stat { display: flex; flex-direction: column; }
.stat b { font-size: 18px; font-weight: 500; color: var(--brass); }
.stat span { font-size: 11px; color: var(--faint); }
.itemcol { padding: 12px 16px 6px; border-top: 1px solid var(--edge-soft); }
.itemcol h3 {
  font-family: Sora, sans-serif; font-size: 11px; font-weight: 600;
  letter-spacing: .12em; text-transform: uppercase; color: var(--faint);
  margin-bottom: 6px;
}
.itemcol ul { list-style: none; margin: 0; padding: 0; }
.itemcol li {
  display: grid; grid-template-columns: 26px 1fr auto; gap: 9px;
  align-items: center; padding: 3px 0; font-size: 13.5px;
}
.itemcol img { width: 26px; height: 26px; background: var(--raised); }
.itemcol .pc { font-size: 12px; color: var(--faint); text-align: right; }
.itemcol li.uniq {
  background: linear-gradient(90deg, rgba(122, 34, 51, .45), transparent 75%);
  margin: 0 -16px; padding-left: 16px; padding-right: 16px;
}
.itemcol li.uniq .nm { font-weight: 500; }
.itemcol li.uniq { box-shadow: inset 3px 0 0 var(--oxblood-lit); }
.cardfoot { margin-top: auto; padding: 12px 16px 16px; }
.imbue { font-size: 12.5px; color: var(--muted); margin: 0 0 10px; }
.imbue b { color: var(--text); font-weight: 500; }
.go {
  display: block; text-align: center; padding: 10px; font-weight: 500;
  background: var(--oxblood); color: #F6EFE2; text-decoration: none;
}
.go:hover { background: var(--oxblood-lit); }
.legend .swatch {
  display: inline-block; width: 20px; height: 9px; margin-right: 6px;
  background: linear-gradient(90deg, rgba(122, 34, 51, .8), transparent);
}

.bands {
  display: grid; gap: 0 22px; margin-top: 18px;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
}
.band h2 {
  font-size: 21px; color: var(--brass); padding-bottom: 6px;
  border-bottom: 2px solid var(--oxblood);
}
details.buy { border-bottom: 1px solid var(--edge-soft); }
details.buy summary {
  display: grid; grid-template-columns: 18px 40px 1fr auto; gap: 10px;
  align-items: center; min-height: 51px; padding: 5px 2px; cursor: pointer;
  list-style: none;
}
details.buy summary::-webkit-details-marker { display: none; }
details.buy summary:hover { background: var(--surface); }
.ix { font-size: 11.5px; color: var(--faint); }
.ico {
  width: 40px; height: 40px; object-fit: contain; padding: 2px;
  border: 1px solid var(--edge); background: var(--raised);
}
.txt .nm { display: block; font-size: 14.5px; font-weight: 400; line-height: 1.3; }
.txt .sub { display: block; font-size: 11.5px; color: var(--verdigris-lit); }
.cost { font-size: 13px; color: var(--muted); }
.detail { margin: 0; padding: 0 2px 12px 70px; font-size: 13px; color: var(--muted); }

.sec { margin-top: 36px; border-top: 1px solid var(--edge); padding-top: 18px; }
.sec h2 { font-size: 22px; color: var(--brass); }
.sec h3 {
  font-family: Sora, sans-serif; font-size: 11px; font-weight: 600;
  letter-spacing: .12em; text-transform: uppercase; color: var(--faint);
  margin: 6px 0;
}
.copygrid {
  display: grid; gap: 8px 32px; background: var(--surface);
  border: 1px solid var(--edge); padding: 12px 16px;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
}
ol.copy { margin: 0; padding-left: 26px; font-size: 14px; }
.track { overflow-x: auto; background: var(--surface); border: 1px solid var(--edge); }
.track table { border-collapse: collapse; }
.track th {
  display: flex; align-items: center; gap: 10px; min-width: 190px;
  padding: 4px 12px 4px 4px; font-weight: 400; text-align: left;
}
.track th img { width: 36px; height: 36px; background: var(--raised); }
.track td {
  width: 28px; min-width: 28px; height: 28px; text-align: center;
  font-size: 12px; border-left: 1px solid var(--edge-soft);
}
.track td.on { color: var(--ground); background: var(--verdigris-lit); font-weight: 600; }
.track tr + tr { border-top: 1px solid var(--edge-soft); }
ul.lines { list-style: none; margin: 8px 0 0; padding: 0; }
ul.lines li {
  display: flex; flex-wrap: wrap; justify-content: space-between; gap: 4px 16px;
  padding: 9px 0; border-bottom: 1px solid var(--edge-soft);
}
ul.lines b { font-weight: 500; }
ul.lines .num { color: var(--muted); font-size: 13px; }

@media (max-width: 600px) {
  .mast { align-items: flex-start; }
  .portrait { width: 60px; height: 60px; }
}
"""


@dataclass(frozen=True)
class Bracket:
    """The skill level the builds are weighted toward, as a player reads it."""

    tier_name: str   # the rank tier at the target badge, from the assets API
    share: float     # player-matches at that tier or above, 0 to 1


def methodology(
    *,
    bracket: Bracket | None,
    window_start: dt.date,
) -> str:
    """The page that says where the builds come from and what they claim.

    `bracket` is None when the builds carry no badge weighting. It states two
    numbers, the bracket's share and the window's start, and no accuracy,
    count, or split figure: those describe the model, and the reader is asking
    about the build. The repo link is where those live.
    """
    # Unweighted builds imitate every ranked player, so the page must not
    # call them strong players anywhere.
    players = "ranked players" if bracket is None else "strong players"
    if bracket is None:
        skill = (
            "These builds weight every ranked match equally, so they imitate "
            "the average ranked player rather than the strongest."
        )
    else:
        # "Weighted toward", with no mechanism clause: lower brackets still
        # count, for less, so the page must not claim they are left out. ADR
        # 0002 records that the weighting changes the builds, not accuracy,
        # so the page makes no accuracy claim for it.
        skill = (
            f"The builds are weighted toward {escape(bracket.tier_name)} and "
            f"above, roughly the top {round(bracket.share * 100)}% of players, "
            "so they imitate strong play rather than average play."
        )
    window = f"{window_start.day} {window_start:%B %Y}"
    repo = escape(REPO_URL, quote=True)
    repo_label = escape(REPO_URL.removeprefix("https://"))

    body = f"""<main class="prose">
<h1>How the builds are made</h1>
<p class="lede">Where these builds come from, whose play they imitate, and what
they do not claim.</p>

<section>
<h2>What this is</h2>
<p>Each build here is what {players} of a hero actually buy, pooled
across many players and many matches, and worked out separately for each way
the hero gets played.</p>
<p>A community build guide is one strong player's opinion about how to play a
hero. That is worth a lot: a guide can explain its reasoning and try things
nobody else has. It is also one opinion, and it can't tell you whether the
hero's other good players agree. These builds answer that question: where do
a hero's {players}, taken together, converge? Read a guide for the
reasoning and these builds for the consensus. Neither replaces the other.</p>
</section>

<section>
<h2>We model the order</h2>
<p>Most Deadlock stats sites show which items win. This one shows the order
{players} buy them in: what comes first, what follows it, and roughly
when.</p>
<p>It never claims that an item causes a win. A late item with a high win rate
may be strong, or it may only be what players who are already ahead can
afford. The builds claim one thing: {players} buy these items, in this
order.</p>
</section>

<section>
<h2>Archetypes</h2>
<p>Some heroes are played in more than one way, and an average of those ways
is a build nobody plays. Ivy is the clearest case. Some Ivy players build
around her gun and others around her spirit damage, and those builds share
few items. So each hero's players are grouped by what they buy, and each
group, an archetype, gets its own build.</p>
<p>A hero is split only where the evidence is there: a second build has to be
clearly different and common enough to learn from. When no second build
clears that bar, the hero keeps one. A single build is the method declining to
guess, not unfinished work.</p>
</section>

<section>
<h2>Skill level</h2>
<p>{skill}</p>
</section>

<section>
<h2>Data window and patches</h2>
<p>The builds come from ranked matches played since the {window} balance
patch.</p>
<p>New matches are pulled and the builds refitted as a deliberate step, not on
a timer, so that each set of builds comes from one patch. A patch can age a
build: if an item has changed since {window}, the build shows how players
used it before the change. If the game has patched since then, treat a build
as a starting point.</p>
</section>

<section>
<h2>The fine print</h2>
<p>A build's win rate is the win rate of the matches the model placed in that
archetype: how those players did, not a prediction of how you will. The
model, the data, and the decisions behind them are public at
<a href="{repo}">{repo_label}</a>.</p>
</section>
</main>"""
    return _document(
        root="",
        title="How the builds are made",
        description=(
            "Where these Deadlock builds come from, whose play they imitate, "
            "and what they do not claim."
        ),
        body=body,
    )


# --- the hero surface -------------------------------------------------------
#
# Three page kinds, all fed facts the caller computed:
#
#   home         every hero, linking to its page
#   chooser      a split hero's page: its archetypes side by side (#21, #24)
#   build_page   one hero and archetype; a single-archetype hero's page (#20)
#
# Links are relative, so the site works under the Pages project path and
# from a file. `root` is the path from the page back to the site root.


@dataclass(frozen=True)
class ColumnEntry:
    """One item in a chooser column. `elsewhere` is set on defining items."""

    item_id: int
    name: str
    rate: float
    elsewhere: float | None = None


@dataclass(frozen=True)
class Imbue:
    """The ability this archetype's players imbue an item into."""

    item: str
    ability: str
    share: float   # of this item's imbues that chose this ability
    n: int         # imbues counted


@dataclass(frozen=True)
class Card:
    """One archetype on its hero's chooser."""

    archetype: str
    href: str
    share: float      # of the hero's players
    win_rate: float   # absolute, of the matches placed in this archetype
    n: int            # player-matches placed in this archetype
    most_common: tuple[ColumnEntry, ...]
    defining: tuple[ColumnEntry, ...]
    imbues: tuple[Imbue, ...]


@dataclass(frozen=True)
class Item:
    """One purchase in a build."""

    item_id: int
    name: str
    cost: int
    phase: int                  # index into BuildFacts.phases
    share: float                # of players at this point who bought it next
    n: int                      # purchases behind that share
    builds_into: str | None = None


@dataclass(frozen=True)
class AbilityPoint:
    ability_id: int
    name: str


@dataclass(frozen=True)
class Matchup:
    """An item in the build that players buy more often against one enemy.

    Measured across every hero's players (`counters.counter_lifts`), not per
    archetype: split six ways by enemy, one archetype's cell would hold too
    little to measure.
    """

    enemy: str
    item: str
    facing: float     # pick rate in player-matches against the enemy
    baseline: float   # pick rate in all player-matches
    n: int            # player-matches against the enemy


@dataclass(frozen=True)
class BuildFacts:
    """Everything one build page states."""

    hero: str
    hero_id: int
    archetype: str
    share: float
    n: int
    items: tuple[Item, ...]
    phases: tuple[str, ...]           # a name per phase index, e.g. "Lane"
    abilities: tuple[AbilityPoint, ...]
    imbues: tuple[Imbue, ...]
    matchups: tuple[Matchup, ...]
    chooser_href: str | None          # None when the hero has one archetype


@dataclass(frozen=True)
class HeroLink:
    hero: str
    hero_id: int
    href: str
    builds: int


SITE_NAME = "Deadlock builds"


def home(
    *, heroes: list[HeroLink], bracket: Bracket | None, window_start: dt.date
) -> str:
    """The site's front page: every hero, each linking to its page."""
    tiles = "\n".join(
        f"""<li><a class="hero" href="{escape(h.href, quote=True)}">
<img src="{_hero_image(h.hero_id, "")}" alt="" loading="lazy">
<span class="nm">{escape(h.hero)}</span>
<span class="sub">{_plural(h.builds, "build")}</span></a></li>"""
        for h in heroes
    )
    body = f"""<main class="wide">
<header class="mast">
<div>
<h1>{SITE_NAME}</h1>
<p class="lede">What {_players(bracket)} buy on each hero, in the order they
buy it, split by the different ways each hero is played.</p>
<p class="prov">{_provenance(bracket, window_start, "")}</p>
</div>
</header>
<ul class="heroes">
{tiles}
</ul>
</main>"""
    return _document(
        root="",
        title=SITE_NAME,
        description="Deadlock build orders for every hero, from what strong players buy.",
        body=body,
    )


def chooser(
    *,
    hero: str,
    hero_id: int,
    cards: list[Card],
    bracket: Bracket | None,
    window_start: dt.date,
    root: str,
) -> str:
    """A split hero's page: its archetypes side by side, each linking to its build.

    The comparison is the point, so two things are computed across the cards
    rather than per card. An item in exactly one card's column is marked, per
    column. An imbue target shows only where the cards disagree about it:
    another archetype imbues the same item into a different ability. A hero with one archetype has nothing to choose between; its page is
    `build_page`, and this raises.
    """
    if len(cards) < 2:
        raise ValueError(f"{hero} has {len(cards)} archetype(s); use build_page")

    unique_common = _in_one_card([c.most_common for c in cards])
    unique_defining = _in_one_card([c.defining for c in cards])
    targets: dict[str, set[str]] = {}
    for c in cards:
        for i in c.imbues:
            targets.setdefault(i.item, set()).add(i.ability)

    articles = []
    for c in cards:
        # Only where the archetypes disagree: another one imbues this item
        # into a different ability.
        imbues = [i for i in c.imbues if len(targets[i.item]) > 1]
        imbue_lines = "".join(
            f'<p class="imbue">Imbue <b>{escape(i.item)}</b> into '
            f"<b>{escape(i.ability)}</b></p>"
            for i in imbues
        )
        href = escape(c.href, quote=True)
        articles.append(
            f"""<article class="card">
<a class="cardlink" href="{href}"><h2>{escape(c.archetype)}</h2></a>
<div class="stats">
{_stat(_pct1(c.win_rate), "win rate")}
{_stat(f"{c.n:,}", "matches")}
{_stat(_pct(c.share), f"of {escape(hero)} players")}
</div>
{_column("Most common", c.most_common, unique_common, root)}
{_column("Defining", c.defining, unique_defining, root)}
<div class="cardfoot">{imbue_lines}
<a class="go" href="{href}">See the full build</a></div>
</article>"""
        )

    body = f"""<main class="wide">
{_masthead(
    kicker=SITE_NAME,
    title=hero,
    hero_id=hero_id,
    root=root,
    lines=[
        f"{escape(hero)}'s players split {len(cards)} ways. Compare what each "
        "build buys and pick the one that matches how you play.",
    ],
    prov=_provenance(bracket, window_start, root),
)}
<div class="chooser">
{"".join(articles)}
</div>
<p class="legend"><span class="swatch"></span>Highlighted items are in that column
for one {escape(hero)} build and none of the others. Defining items are the ones
this build buys far more often than {escape(hero)}'s other builds; the second
rate is how often the others buy them.</p>
</main>"""
    return _document(
        root=root,
        title=f"{hero} builds",
        description=f"The ways {hero} is built in Deadlock, side by side.",
        body=body,
    )


def build_page(
    build: BuildFacts, *, bracket: Bracket | None, window_start: dt.date, root: str
) -> str:
    """One hero and archetype: the purchase order and everything that goes with it.

    Sections in #20's order: purchase order in phase bands, the block to copy
    into the game's build browser, ability order, imbue targets, and matchup
    items. A section with nothing in it is left out, heading and all. No
    per-item clock: buy time is linear in buy index, so a clock would claim a
    precision the model doesn't have.
    """
    lines = []
    if build.chooser_href is not None:
        lines.append(
            f"{_pct(build.share)} of {escape(build.hero)} players "
            f'· <a href="{escape(build.chooser_href, quote=True)}">'
            f"All {escape(build.hero)} builds</a>"
        )

    sections = [_purchases(build, root), _copy_block(build)]
    if build.abilities:
        sections.append(_ability_order(build.abilities, root))
    if build.imbues:
        sections.append(_imbues(build.imbues))
    if build.matchups:
        sections.append(_matchups(build.matchups))

    body = f"""<main class="wide">
{_masthead(
    kicker=f"{escape(build.hero)} build",
    title=build.archetype,
    hero_id=build.hero_id,
    root=root,
    lines=lines,
    prov=_provenance(bracket, window_start, root, n=build.n),
)}
{"".join(sections)}
</main>"""
    return _document(
        root=root,
        title=f"{build.archetype} build",
        description=(
            f"What {_players(bracket)} buy for {build.archetype}, in order."
        ),
        body=body,
        script=DISCLOSURE_SCRIPT,
    )


# Keeps aria-expanded true to each item row's state. The toggle itself is the
# browser's: without this script the rows still open and close, and only the
# announced state goes stale. scripts/build_pages.py runs it under node before
# writing, because a page once shipped with a script that died on load.
DISCLOSURE_SCRIPT = """
document.querySelectorAll("details.buy").forEach(function (row) {
  var summary = row.querySelector("summary");
  row.addEventListener("toggle", function () {
    summary.setAttribute("aria-expanded", String(row.open));
  });
});
"""


def _purchases(build: BuildFacts, root: str) -> str:
    bands = []
    number = 0
    for phase, name in enumerate(build.phases):
        rows = []
        for item in build.items:
            if item.phase != phase:
                continue
            number += 1
            sub = (
                f'<span class="sub">builds into {escape(item.builds_into)}</span>'
                if item.builds_into
                else ""
            )
            rows.append(
                f"""<details class="buy"><summary role="button" aria-expanded="false">
<span class="ix">{number}</span>
<img class="ico" src="{_item_image(item.item_id, root)}" alt="">
<span class="txt"><span class="nm">{escape(item.name)}</span>{sub}</span>
<span class="cost">{item.cost:,}</span></summary>
<p class="detail">{_pct(item.share)} of this build's players at this point bought
it next, from {item.n:,} purchases made in the same spot.</p></details>"""
            )
        if rows:
            bands.append(
                f'<section class="band"><h2>{escape(name)}</h2>{"".join(rows)}</section>'
            )
    return f"""<section class="purchases">
<h2 class="sr">Purchase order</h2>
<div class="bands">{"".join(bands)}</div>
<p class="note">Costs are in souls. Tap an item for how firmly players agree on it.</p>
</section>"""


def _copy_block(build: BuildFacts) -> str:
    items = "".join(f"<li>{escape(i.name)}</li>" for i in build.items)
    points = "".join(f"<li>{escape(a.name)}</li>" for a in build.abilities)
    abilities = (
        f'<div><h3>Ability points</h3><ol class="copy">{points}</ol></div>'
        if points
        else ""
    )
    return f"""<section class="sec">
<h2>Copy into the build browser</h2>
<p class="note">Open the game's build editor beside this and add the items in
this order.</p>
<div class="copygrid">
<div><h3>Items</h3><ol class="copy">{items}</ol></div>
{abilities}
</div>
</section>"""


def _ability_order(points: tuple[AbilityPoint, ...], root: str) -> str:
    abilities: dict[int, str] = {}
    for point in points:
        abilities.setdefault(point.ability_id, point.name)
    rows = []
    for ability_id, name in abilities.items():
        cells = "".join(
            f'<td class="on">{number}</td>' if point.ability_id == ability_id else "<td></td>"
            for number, point in enumerate(points, start=1)
        )
        rows.append(
            f"""<tr><th scope="row"><img src="{_ability_image(ability_id, root)}" alt="">
<span>{escape(name)}</span></th>{cells}</tr>"""
        )
    return f"""<section class="sec">
<h2>Ability order</h2>
<p class="note">Each number is a point, in the order to spend them.</p>
<div class="track"><table>{"".join(rows)}</table></div>
</section>"""


def _imbues(imbues: tuple[Imbue, ...]) -> str:
    rows = "".join(
        f"""<li><span>Imbue <b>{escape(i.item)}</b> into <b>{escape(i.ability)}</b></span>
<span class="num">{_pct(i.share)} of {i.n:,} imbues</span></li>"""
        for i in imbues
    )
    return f"""<section class="sec">
<h2>What to imbue</h2>
<ul class="lines">{rows}</ul>
</section>"""


def _matchups(matchups: tuple[Matchup, ...]) -> str:
    rows = "".join(
        f"""<li><span><b>{escape(m.enemy)}</b>: {escape(m.item)}</span>
<span class="num">{_pct1(m.facing)} against {escape(m.enemy)}, {_pct1(m.baseline)}
overall · {m.n:,} matches</span></li>"""
        for m in matchups
    )
    return f"""<section class="sec">
<h2>If you're facing…</h2>
<p class="note">Items in this build that players buy more often against one
enemy hero, measured across every hero's players.</p>
<ul class="lines">{rows}</ul>
</section>"""


def _column(
    title: str, entries: tuple[ColumnEntry, ...], unique: set[int], root: str
) -> str:
    rows = []
    for e in entries:
        rate = _pct(e.rate)
        if e.elsewhere is not None:
            rate += f" · {_pct(e.elsewhere)} elsewhere"
        marked = e.item_id in unique
        # Marked by weight, a bar and a tint; the words are for screen readers.
        mark = '<span class="sr"> (only in this build)</span>' if marked else ""
        rows.append(
            f"""<li class="{"uniq" if marked else ""}">
<img src="{_item_image(e.item_id, root)}" alt="">
<span class="nm">{escape(e.name)}{mark}</span><span class="pc">{rate}</span></li>"""
        )
    return f'<div class="itemcol"><h3>{title}</h3><ul>{"".join(rows)}</ul></div>'


def _in_one_card(columns: list[tuple[ColumnEntry, ...]]) -> set[int]:
    """Item ids that appear in exactly one card's version of a column."""
    seen: dict[int, int] = {}
    for entries in columns:
        for item_id in {e.item_id for e in entries}:
            seen[item_id] = seen.get(item_id, 0) + 1
    return {item_id for item_id, count in seen.items() if count == 1}


def _masthead(
    *, kicker: str, title: str, hero_id: int, root: str, lines: list[str], prov: str
) -> str:
    extra = "".join(f'<p class="who">{line}</p>' for line in lines)
    return f"""<header class="mast">
<img class="portrait" src="{_hero_image(hero_id, root)}" alt="">
<div>
<p class="kicker">{kicker}</p>
<h1>{escape(title)}</h1>
{extra}
<p class="prov">{prov}</p>
</div>
</header>"""


def _provenance(
    bracket: Bracket | None, window_start: dt.date, root: str, n: int | None = None
) -> str:
    """One line: how much play, whose, and since when, with the methodology link."""
    matches = f"{n:,} matches" if n is not None else "Ranked matches"
    weighted = (
        "" if bracket is None
        else f", weighted toward {escape(bracket.tier_name)} and above"
    )
    return (
        f"{matches}{weighted}, played since {_date(window_start)}. "
        f'<a href="{root}methodology.html">How the builds are made</a>'
    )


def _document(
    *, root: str, title: str, description: str, body: str, script: str = ""
) -> str:
    """Wrap a page's body in the site's shared head, stylesheet and nav."""
    tail = f"<script>{script}</script>\n" if script else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<meta name="description" content="{escape(description, quote=True)}">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{FONTS_URL}">
<style>{SITE_CSS}</style>
</head>
<body>
<nav class="site"><a href="{root}index.html">{SITE_NAME}</a>
<a href="{root}methodology.html">How the builds are made</a></nav>
{body}
{tail}</body>
</html>
"""


def _stat(value: str, label: str) -> str:
    return f'<div class="stat"><b>{value}</b><span>{label}</span></div>'


def _players(bracket: Bracket | None) -> str:
    return "ranked players" if bracket is None else "strong players"


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _date(day: dt.date) -> str:
    return f"{day.day} {day:%B %Y}"


def _pct(x: float) -> str:
    return f"{round(x * 100)}%"


def _pct1(x: float) -> str:
    """A percentage to one decimal, without a trailing .0."""
    return f"{x * 100:.1f}".removesuffix(".0") + "%"


def _item_image(item_id: int, root: str) -> str:
    return f"{root}assets/items/{item_id}.png"


def _hero_image(hero_id: int, root: str) -> str:
    return f"{root}assets/heroes/{hero_id}.png"


def _ability_image(ability_id: int, root: str) -> str:
    return f"{root}assets/abilities/{ability_id}.png"
