"""Download the item icons and hero portraits the site renders.

The assets API already carries every image URL, so nothing here is scraped:
`shop_image` for items and `images.*` for heroes are fields on the same asset
records the model already joins against by id. That matters because the site
must show the same item the model recommended, and a name-matched icon from a
third-party wiki can drift from the id the table row was keyed on.

Two fields, not one, for items. `image` is missing for six items that real
builds buy -- Cultist Sacrifice, Stalker, Blood Tribute, Spellslinger, Express
Shot and Transcendent Cooldown -- while `shop_image` covers all 138 items that
appear across the 75 generated builds. So `shop_image` is the source and
`image` is only a fallback.

Files are named by **item id**, never by name: 57 of the 138 exceed int32 and
names are not stable across patches, while the id is what every table row in
the model is keyed on.

    python scripts/pull_assets.py [--out data/assets] [--force]
"""

from __future__ import annotations

import argparse
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from deadlock import api, assets  # noqa: E402

DEFAULT_OUT = Path("data/assets")

# A plain urllib User-Agent is refused by the CDN's bot protection, the same
# way it is on the main API.
UA = "deadlock-build-modeling/1.0 (+https://github.com/quinn-zilly/deadlock-build-modeling)"

# Which hero image to use for the page's portrait. `icon_hero_card` is the
# framed bust the game itself uses in the build browser, which is the context
# the site is read beside.
PORTRAIT = "icon_hero_card"


def fetch(url: str, dest: Path, force: bool = False) -> str:
    """Download one asset. Returns 'ok', 'cached' or an error string."""
    if dest.exists() and dest.stat().st_size > 0 and not force:
        return "cached"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
    except Exception as exc:  # noqa: BLE001 - report and carry on
        return f"error: {exc}"
    if not body:
        return "error: empty response"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(body)
    return "ok"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    raw_items = api.get("/v1/assets/items", cache_dir=assets.DEFAULT_CACHE)
    raw_heroes = api.get("/v1/assets/heroes", cache_dir=assets.DEFAULT_CACHE)

    jobs: list[tuple[str, Path]] = []

    for item in raw_items:
        if item.get("type") != "upgrade":
            continue
        url = item.get("shop_image") or item.get("image")
        if not url:
            continue
        ext = ".png" if url.endswith(".png") else Path(url).suffix or ".png"
        jobs.append((url, args.out / "items" / f"{item['id']}{ext}"))

    for hero in raw_heroes:
        if not hero.get("player_selectable") or hero.get("disabled"):
            continue
        url = (hero.get("images") or {}).get(PORTRAIT)
        if not url:
            continue
        ext = ".png" if url.endswith(".png") else Path(url).suffix or ".png"
        jobs.append((url, args.out / "heroes" / f"{hero['id']}{ext}"))

    # The four signature abilities of every playable hero: the build browser
    # shows the ability's own art beside each row of the point order, so the
    # site needs it to lay that section out the same way.
    by_class = {
        entry.get("class_name"): entry
        for entry in raw_items
        if entry.get("type") == "ability"
    }
    for hero in raw_heroes:
        if not hero.get("player_selectable") or hero.get("disabled"):
            continue
        for slot in ("signature1", "signature2", "signature3", "signature4"):
            entry = by_class.get((hero.get("items") or {}).get(slot))
            if not entry or not entry.get("image"):
                continue
            url = entry["image"]
            ext = ".png" if url.endswith(".png") else Path(url).suffix or ".png"
            jobs.append((url, args.out / "abilities" / f"{entry['id']}{ext}"))

    counts = {"ok": 0, "cached": 0, "error": 0}
    errors: list[str] = []
    for url, dest in jobs:
        status = fetch(url, dest, force=args.force)
        if status.startswith("error"):
            counts["error"] += 1
            errors.append(f"{dest.name}: {status}  <- {url}")
        else:
            counts[status] += 1
        if status == "ok":
            time.sleep(0.05)

    print(f"items+heroes: {counts['ok']} downloaded, {counts['cached']} cached, "
          f"{counts['error']} failed")
    for line in errors[:20]:
        print("  " + line, file=sys.stderr)
    return 1 if counts["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
