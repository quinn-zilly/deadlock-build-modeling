# How a build gets from a website into Deadlock

Research for issue #18 (part of the #15 map). Established against Valve's own
protobuf definitions, the community API's OpenAPI schema and live responses,
and the shipped JavaScript of the one community site that actually does this.

**Bottom line.** There is no import feature in Deadlock. Builds live on Valve's
Game Coordinator, not on disk, and the only supported way to get one is to
build it by hand in the in-game build browser or favourite someone's published
build. The one working export path in the wild — Statlocker's — smuggles a
build in by rewriting the client's local **build cache** file, which is an
undocumented back door, not an import feature. A pure static site **cannot**
serve that path end to end: the file is a compressed binary KV3 blob, and the
site that does it uses a server endpoint to write it.

## 1. What the game actually accepts

**Builds are server-side objects on Valve's Game Coordinator, addressed by id.**
This is settled by Valve's own protobufs, dumped from the shipped client by
SteamDB's automated tracker.

From [`deadlock/citadel_gcmessages_client.proto`](https://github.com/SteamDatabase/Protobufs/blob/master/deadlock/citadel_gcmessages_client.proto),
the complete set of build messages the client can send:

```
k_EMsgClientToGCUpdateHeroBuild            = 9193
k_EMsgClientToGCFindHeroBuilds             = 9195
k_EMsgClientToGCDeleteHeroBuild            = 9201
k_EMsgClientToGCUpdateHeroBuildPreference  = 9215
```

Create/update, search, delete, and favourite-or-ignore. **There is no import
message and no file-load message.** `CMsgClientToGCUpdateHeroBuild` carries a
whole `CMsgHeroBuild` and the response returns the assigned
`hero_build_id` and `version` — the GC, not the client, owns build identity:

```protobuf
message CMsgClientToGCUpdateHeroBuildResponse {
	optional EResponse response = 1;
	optional uint32 hero_build_id = 2;
	optional uint32 version = 3;
}
```

Discovery is by search over GC-side records, not by code:

```protobuf
message CMsgClientToGCFindHeroBuilds {
	optional uint32 author_account_id = 1;
	optional uint32 hero_id = 2;
	repeated int32 language = 3;
	optional string search_text = 4;
	optional uint32 hero_build_id = 5;
	repeated uint32 tags = 6;
}
```

`search_text` is the field the "publish under a unique name, tell your friend
the name" workflow rides on. There is no share-code field anywhere in the
message set.

The player-facing consequence, as documented on
[SteamDB's builds page](https://steamdb.com/en/deadlock/mechanics/builds-and-recommendations):
"There is no copy-paste code or share link: you share a build by hitting
Publish (it needs a unique name) so friends can search it by name in the Public
tab." A [feature request for exactly this](https://forums.playdeadlock.com/threads/opportunity-to-search-for-builds-by-name-or-copy-the-code.18215/)
has sat on the official forums since August 2024 with no Valve response.

### The one file on disk

There is a local file, but it is a **cache**, not an import inbox:

```
Windows  C:\Program Files (x86)\Steam\userdata\<accountId>\1422450\remote\cfg\cached_hero_builds.kv3
macOS    ~/Library/Application Support/Steam/userdata/<accountId>/1422450/remote/cfg/
Linux    ~/.steam/steam/userdata/<accountId>/1422450/remote/cfg/
```

(`1422450` is Deadlock's Steam appid. Paths verbatim from Statlocker's shipped
exporter bundle, `static/js/5375.09d1c0a5.chunk.js`.)

It is a binary KV3 file with a compressed payload — the same bundle's error
handling enumerates the compression methods it must decode: "known: 0 = none,
1 = LZ4, 2 = Zstandard". Being under `remote/cfg/` also puts it in Steam Cloud's
sync path, so an edit made while the client is running is liable to be
overwritten, which is why the tool insists the game be closed.

## 2. Does a downloaded file work end to end? Not from a static page.

Statlocker's [Build Exporter](https://statlocker.gg/builds/build-exporter) is
the only shipped tool that gets a web build into the game, and its own four-step
wizard is the honest description of the path (text quoted from its bundle):

1. **Select a Build.**
2. **"Backup & Upload Cache File"** — *"Ensure Deadlock is completely closed. It
   is highly recommended to copy and backup your file to another folder first."*
   The player finds `cached_hero_builds.kv3` and **uploads it to the website**.
3. **"Merge and Export"** — the site decodes the player's cache, merges the new
   build in, and re-encodes it.
4. **"Finish Up"** — *"Replace the existing `cached_hero_builds.kv3` in your
   Steam directory with the downloaded file. Load up the game and swap to your
   chosen hero. The imported build should be selected automatically. Make any
   final changes you want in the game client and publish the build!"*

Two things in this kill the static-site version:

- **It is a round trip, not a download.** The player must upload their own
  existing cache file first, because the deliverable is *their* cache with one
  build merged into it — not a standalone build file. A page that only hands
  out a file cannot produce a valid cache.
- **The merge runs on a server.** The bundle posts to a first-party endpoint:

  ```js
  await fetch("/api/kv3/serialize", { method: "POST", ... })
  ```

  Encoding compressed binary KV3 is done server-side. A static host has no
  `/api/*`.

The first is the architectural blocker and the second is only mostly one — KV3
encoding *could* in principle be done in browser JS (their decoder already is),
so a determined static implementation is conceivable. But it would be
reimplementing an undecoded Valve binary format against a moving target, to
drive a back door Valve never documented and can change in any patch. **Treat
"downloadable importable JSON" as not viable.** The JSON `buildfmt.py` emits is
not a thing the game reads at all; it is the *API's* rendering of a GC object.

Note also step 4's last line: even Statlocker's path ends with the player
*publishing from the game client*. The GC assigns the id. Nothing outside the
client can mint a build.

**The honest static-site path** is the one every other community site walks:
show the build, and let the player **recreate it in the in-game build browser**.
That is the same path Deadlock Labs and BUILDLOCK land on —
[BUILDLOCK's](https://buildlock.io/) "publish the build into Deadlock" Build Lab
is marked *"Coming soon"* and *"Steam login required"*, i.e. it does not exist
yet and when it does it will need authenticated GC access, not a static page.

## 3. Shareability: by name and by third-party URL, not by code

- **In-game:** by published name only, via `search_text`. No codes, no links.
- **By URL:** only through third-party sites, which have read access to
  published builds through the community API. Per-build URLs work:
  `GET /v1/builds/{hero_id}/{build_id}` on
  [api.deadlock-api.com](https://api.deadlock-api.com/docs) returns a single
  build. So a site can absolutely give each build its own shareable URL — that
  part of "hand another player a link" is free. What the link cannot do is put
  the build in the recipient's game.

Worth noting the API is **read-only for builds**. Its whole build surface is
three GET endpoints (`/v1/builds`, `/v1/builds/by-author/{account_id}`,
`/v1/builds/{hero_id}/{build_id}`) — there is no POST, so no publish-on-behalf.

## 4. What the schema does and does not express

Confirmed against `CMsgHeroBuild` in
[`citadel_gcmessages_common.proto`](https://github.com/SteamDatabase/Protobufs/blob/master/deadlock/citadel_gcmessages_common.proto)
and against 200 live builds from `/v1/builds`.

**Ability point order survives.** `Details_V0.ability_order` is an
`AbilityOrder` of `CurrencyChange { ability_id, currency_type, delta,
annotation }`. 197 of 200 live builds carry one. The project's existing
`ability_order_json()` matches this shape exactly.

**Imbue targets survive.** `BuildModEntry.imbue_target_ability_id` is a real
field on every mod entry, and it is populated in the wild — 291 of 8,709 mod
entries in the sample. So an imbueable item can carry its target, and the
recent work wiring `imbue_targets` into the exporter is aimed at a field the
game genuinely reads.

**What is genuinely lost:**

- **Sales.** As the project already knows. `sell_priority` exists on
  `BuildModEntry` but it is a *priority ordering for the shop's sell
  suggestions*, not "buy this then sell it at 20 minutes". There is no
  timestamp and no way to say an item leaves the build.
- **Purchase order across categories.** Order is only implied by category order
  then position within a category. There is no buy-index or timing field. Every
  timing claim the project makes lives in `annotation` as free text, which the
  game shows but cannot act on.
- **Timing of ability points.** Same — `CurrencyChange.annotation` is free text.
- **Everything conditional.** `optional` (bool) on a category and
  `required_flex_slots` on an entry are the only expressive machinery. There is
  no counter-pick conditioning, no "if behind", no situational trigger.

## 5. Mismatch check: what `buildfmt.py` emits vs. what the schema requires

`src/deadlock/buildfmt.py` produces a well-formed `details` block — categories,
mods, `imbue_target_ability_id`, and `ability_order.currency_changes` all match
the live shape and the proto field-for-field. The nesting under
`{"hero_build": {...}}` matches too.

**But three fields the schema marks required are not emitted:**

| Required by `BuildHero` | Emitted by `buildfmt.py` |
| --- | --- |
| `hero_id` | yes |
| `name`, `language`, `version` | yes |
| `details` | yes |
| **`hero_build_id`** | **no** |
| **`author_account_id`** | **no** |
| **`origin_build_id`** | **no** |

This is not a bug to fix so much as proof of the finding. Those three fields are
**identity assigned by the Game Coordinator** — `hero_build_id` and `version`
come back in `CMsgClientToGCUpdateHeroBuildResponse`, and `author_account_id` is
the publisher's Steam account. A build generated offline *cannot* fill them
honestly. Their absence is exactly why the emitted JSON is not an importable
artifact: it is a build body with no identity, and nothing but the game client
can give it one.

The docstring on `to_deadlock_json` says the output is "the hero-build schema
Deadlock's build browser accepts". That claim is not supported. It is the shape
the *community API returns*, which is a faithful JSON rendering of the GC's
protobuf — but the build browser does not accept JSON from anywhere. **Recommend
rewording that docstring** and the `export_build` one ("Deadlock-importable
JSON") to say what is true: this is the interchange shape, useful for
third-party tools and for a future authenticated publisher, not a file the game
will read.

## Uncertainty, stated plainly

- **Confirmed from primary sources:** the GC message set and `CMsgHeroBuild`
  schema (Valve's own protos); the read-only build endpoints and live field
  population (community API OpenAPI + live responses); the cache file path,
  filename, compression set, and the exact four-step round trip (Statlocker's
  shipped bundle).
- **Not directly verified:** I did not have Deadlock installed, so I did not
  open a real `cached_hero_builds.kv3` or run the round trip myself. The path
  and format come from a working third-party tool's own code rather than from
  my own observation of the file.
- **Not knowable from outside:** whether Valve tolerates cache-file editing.
  It is undocumented, it is not an API, and it is the kind of thing a patch
  breaks without notice.
- **Moving target:** protobufs are tracked per-patch. Anything here could change
  in a build-browser update. Nothing suggests an import feature is coming; the
  2024 request is still unanswered.

## What this means for the site (#15)

1. **Drop "download an importable file" as the export story.** It does not work,
   and shipping a file that no game reads is worse than not shipping one.
2. **The export affordance should be "copy this build into the build browser"** —
   the item list in shop order, with the ability order beside it, laid out to be
   read while the game's build editor is open on the other monitor or the other
   half of the screen. This is a *design* problem, and it is the real one. It
   also fits the map's "phone for reading, desktop for export" note better than
   a download did.
3. **Per-build URLs are free and worth having** — one URL per hero/archetype
   build is the sharing mechanism, and it is the only one that exists.
4. **Keep `buildfmt.py`.** It is correct as an interchange format and it is the
   thing a future authenticated publisher would emit. It is carried forward to
   the in-match effort per the map. Just stop calling its output importable.
5. **If native publishing is ever wanted**, it needs GC access with a Steam
   login — a server, not a static host. That is a different product decision
   and belongs on its own ticket, not smuggled into the static site.

## Sources

- [SteamDatabase/Protobufs — `deadlock/citadel_gcmessages_client.proto`](https://github.com/SteamDatabase/Protobufs/blob/master/deadlock/citadel_gcmessages_client.proto) — build message set (primary; auto-dumped from the shipped client)
- [SteamDatabase/Protobufs — `deadlock/citadel_gcmessages_common.proto`](https://github.com/SteamDatabase/Protobufs/blob/master/deadlock/citadel_gcmessages_common.proto) — `CMsgHeroBuild` (primary)
- [Deadlock API OpenAPI spec](https://api.deadlock-api.com/openapi.json) and live `/v1/builds` responses — build schema and field population
- [Statlocker Build Exporter](https://statlocker.gg/builds/build-exporter), bundle `static/js/5375.09d1c0a5.chunk.js` — cache path, KV3 format, the four-step round trip, `/api/kv3/serialize`
- [SteamDB — Builds & the build browser](https://steamdb.com/en/deadlock/mechanics/builds-and-recommendations) — player-facing sharing behaviour
- [playdeadlock.com forums — build code request, Aug 2024](https://forums.playdeadlock.com/threads/opportunity-to-search-for-builds-by-name-or-copy-the-code.18215/) — unanswered
- [BUILDLOCK](https://buildlock.io/) — "publish into Deadlock" marked coming soon, Steam login required
