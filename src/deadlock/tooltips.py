"""Item tooltips for the site, from the game's own tooltip data.

The assets API carries each item's in-game tooltip: `tooltip_sections`, each
with prose (`loc_string`, HTML with the game's `highlight` and `diminish`
classes and inline SVG glyphs) and the names of the properties that section
shows. This turns one item entry into what the site renders.

Three findings from #19 and #23 shape it:

- Prose comes from `loc_string` first and `description.desc` only as a
  fallback. `loc_string` covers more of the items real builds buy.
- Stats come from the properties each section names, never the item's whole
  `properties` dict, whose raw order surfaces placeholders the game doesn't
  show (a "-1.0s Charge Delay" on an item with no charge).
- The game ranks its own stats: `elevated_properties`, then named conditions
  (`important_properties_with_icon`), then `important_properties`. The row's
  one-stat headline is a lookup in that order, not a judgement call. It
  prefers what the item does over the flat stats every item in its shop tab
  grants (the innate section): Healbane's headline is its healing
  reduction, not its +7 Spirit Power.

The prose is HTML from a third party, so it is rebuilt under an allowlist.
Today's catalogue holds no scripts or event handlers, but that is a
measurement, not a guarantee.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape
from html.parser import HTMLParser
from typing import Any

# Tags and attributes the game's tooltip prose uses, and nothing else.
ALLOWED_TAGS = {
    "span", "br", "b", "i", "em", "strong", "img",
    "svg", "path", "g", "defs", "clippath", "rect",
}
VOID_TAGS = {"br", "img"}
ALLOWED_ATTRS = {
    "class", "style", "d", "fill", "fill-rule", "clip-rule", "width", "height",
    "viewbox", "xmlns", "clip-path", "id", "transform", "alt", "src",
}
# The only host an <img> in the prose may load from.
ASSET_HOST = "https://assets-bucket.deadlock-api.com/"
# Tags whose text is dropped along with them.
DROP_CONTENT = {"script", "style", "iframe", "object"}
# SVG attribute names are case-sensitive, and html.parser lowercases them.
SVG_CASE = {"viewbox": "viewBox", "clippath": "clipPath"}


@dataclass(frozen=True)
class Stat:
    label: str
    value: str   # formatted as the game shows it: "+30%", "1.9%/sec"

    def __str__(self) -> str:
        return f"{self.value} {self.label}"


@dataclass(frozen=True)
class Section:
    kind: str | None             # "active", "passive", "innate", or None
    prose: str                   # sanitized HTML, possibly empty
    stats: tuple[Stat, ...]
    conditions: tuple[str, ...]  # named effects, e.g. "Silenced"


@dataclass(frozen=True)
class ItemTooltip:
    sections: tuple[Section, ...]
    headline: str | None         # the one-stat line for a row (#23)


def item_tooltip(entry: dict[str, Any]) -> ItemTooltip:
    """The tooltip for one /v1/assets/items entry."""
    properties = entry.get("properties") or {}
    sections = []
    # Candidates for the headline, best first: what the item does (its active
    # and passive sections), then its flat shop stats (the innate section).
    # Within each, elevated stats, then named conditions, then important ones.
    effects: list[list[str]] = [[], [], []]
    innate: list[list[str]] = [[], [], []]

    for section in entry.get("tooltip_sections") or []:
        for attrs in section.get("section_attributes") or []:
            elevated = _stats(attrs.get("elevated_properties"), properties)
            important = _stats(attrs.get("important_properties"), properties)
            plain = _stats(attrs.get("properties"), properties)
            conditions = tuple(
                c.get("localized_name", "")
                for c in attrs.get("important_properties_with_icon") or []
                if c.get("localized_name")
            )
            ranked = innate if section.get("section_type") == "innate" else effects
            ranked[0] += [str(s) for s in elevated]
            ranked[1] += list(conditions)
            ranked[2] += [str(s) for s in important]
            sections.append(
                Section(
                    kind=section.get("section_type"),
                    prose=sanitize(attrs.get("loc_string") or ""),
                    stats=tuple(_unique(elevated + important + plain)),
                    conditions=conditions,
                )
            )

    if not any(s.prose for s in sections):
        desc = (entry.get("description") or {}).get("desc")
        if desc:
            sections.insert(0, Section(None, sanitize(desc), (), ()))

    headline = next((r[0] for r in effects + innate if r), None)
    if headline is None:
        headline = _first_sentence(" ".join(s.prose for s in sections))
    return ItemTooltip(sections=tuple(sections), headline=headline)


def _stats(names: list[str] | None, properties: dict[str, Any]) -> list[Stat]:
    out = []
    for name in names or []:
        prop = properties.get(name)
        if not isinstance(prop, dict):
            continue
        value = str(prop.get("value", "")).strip()
        label = prop.get("label") or ""
        if not label or value in ("", "0", "0.0"):
            continue
        prefix = prop.get("prefix") or ""
        if prefix == "{s:sign}":
            prefix = "" if value.startswith("-") else "+"
        elif value.startswith(("-", "+")):
            prefix = ""
        postfix = prop.get("postfix") or ""
        if value.endswith(postfix):
            postfix = ""   # distances arrive as "20m" with postfix "m"
        out.append(Stat(label=label, value=f"{prefix}{value}{postfix}"))
    return out


def _unique(stats: list[Stat]) -> list[Stat]:
    seen: set[str] = set()
    out = []
    for stat in stats:
        if stat.label not in seen:
            seen.add(stat.label)
            out.append(stat)
    return out


def _first_sentence(html: str) -> str | None:
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()
    if not text:
        return None
    match = re.match(r"(.+?[.!?])(\s|$)", text)
    return match.group(1) if match else text


def sanitize(html: str) -> str:
    """Rebuild tooltip HTML keeping only allowlisted tags and attributes.

    Text is escaped. An <img> keeps its src only when it points at the assets
    host, and a style that could load anything is dropped.
    """
    parser = _Sanitizer()
    parser.feed(html)
    parser.close()
    return "".join(parser.out)


class _Sanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.dropping = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._open(tag, attrs, closed=tag in VOID_TAGS)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._open(tag, attrs, closed=True)

    def _open(self, tag: str, attrs: list[tuple[str, str | None]], closed: bool) -> None:
        if tag in DROP_CONTENT:
            if not closed:
                self.dropping += 1
            return
        if self.dropping or tag not in ALLOWED_TAGS:
            return
        kept = []
        for name, value in attrs:
            value = value or ""
            if name not in ALLOWED_ATTRS:
                continue
            if name == "style" and re.search(r"url|expression|@import", value, re.I):
                continue
            if name == "src" and (tag != "img" or not value.startswith(ASSET_HOST)):
                continue
            kept.append(f' {SVG_CASE.get(name, name)}="{escape(value, quote=True)}"')
        if tag == "img" and not any(k.startswith(" src=") for k in kept):
            return
        name = SVG_CASE.get(tag, tag)
        end = "/>" if closed and tag not in VOID_TAGS else ">"
        self.out.append(f"<{name}{''.join(kept)}{end}")

    def handle_endtag(self, tag: str) -> None:
        if tag in DROP_CONTENT:
            self.dropping = max(0, self.dropping - 1)
            return
        if self.dropping or tag not in ALLOWED_TAGS or tag in VOID_TAGS:
            return
        self.out.append(f"</{SVG_CASE.get(tag, tag)}>")

    def handle_data(self, data: str) -> None:
        if not self.dropping:
            self.out.append(escape(data, quote=False))
