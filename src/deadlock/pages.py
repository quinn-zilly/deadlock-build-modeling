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
        title="How the builds are made",
        description=(
            "Where these Deadlock builds come from, whose play they imitate, "
            "and what they do not claim."
        ),
        body=body,
    )


def _document(*, title: str, description: str, body: str) -> str:
    """Wrap a page's body in the site's shared head and stylesheet."""
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
{body}
</body>
</html>
"""
