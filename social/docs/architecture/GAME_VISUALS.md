# Game visuals

## Stored metadata and canonical projection

The shared `games` record stores `app_id`, `name` and `icon_hash`, mapped from
`GetOwnedGames` with `include_appinfo=true`. The source field `img_icon_url` is a
hash, not a large cover. `user_games` stores ownership/playtime. There is no stored
header, capsule, library artwork, logo, store metadata or image-cache table.
A valid icon hash does not guarantee that the remote file still exists.

`modules/steam/visuals.py` returns one `GameVisual` with nullable `icon_url`,
`thumbnail_url`, `card_url` and `source`. A strict positive 32-bit AppID derives
the two artwork candidates independently of icon availability. Only an additional
valid 40-character hexadecimal hash produces an icon URL. Invalid AppIDs produce
all-null URLs and `unavailable`. `source: steam` describes the candidate family,
not a successful remote fetch. The frontend validates/selects these URLs; it does
not independently construct them.

| Field | Exact official source |
| --- | --- |
| `card_url` | `https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{appid}/library_hero.jpg` |
| `thumbnail_url` | `https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{appid}/header.jpg` |
| `icon_url` | `https://media.steampowered.com/steamcommunity/public/images/apps/{appid}/{hash}.jpg` |

No new migration, stored URL, per-user artwork copy, store metadata fetch, provider
call, automatic sync or per-game mapping is needed. Existing icon-upsert semantics
remain unchanged: malformed/missing optional icons do not destroy valid snapshots.

## Source investigation and limits

Valve documents [store graphical assets](https://partner.steamgames.com/doc/store/assets/standard)
and [library assets](https://partner.steamgames.com/doc/store/assets/libraryassets).
These describe asset types/upload sizes, not a promise that every AppID exposes
every historical filename. The canonical candidates use the official Steam static asset hosts listed above.
Availability, cropping and future CDN changes remain fallible. A bounded public
asset probe for AppID 620 returned a 1920×620 library hero and a 460×215 header;
these served dimensions are observations, not a guarantee for every game.
No downloaded commercial image is included in this source repository. Browser/CDN
caching uses the response policy as provided. Missing artwork falls back in UI.

## Variants, layout and failure behavior

| Variant | Consumer | Sequential priority |
| --- | --- | --- |
| `card` | Profile Gaming Identity, Library grid | library hero → header → icon → glyph |
| `thumbnail` | Most Played/recent rows (48px), Discover chips (36px), comparison (44px); existing wide detail preview | library hero → header → icon → glyph |
| `icon` | Reserved for tiny inline use (24px) | icon → glyph |

`GameArt`, `GameIcon` and `GameChip` share `lib/game-art.ts`. Large frames retain a
460:215 ratio. The wide library image is center-cropped to that frame; game titles
remain separate text. Mobile library rows retain their accepted arrangement while
the artwork retains its own ratio, rather than stretching to the row height.
Small icons use `object-fit: contain`, at most 48px, including inside a large
fallback panel. Only wide artwork uses `cover`. No optional full-page hero is added.

### Compact thumbnail refinement (2026-10-25)

`GameThumbnail` is the shared list-row renderer, also used by `GameChip`. Its
square frame keeps the existing row size, and the same library URL as the card
is cropped with `object-fit: cover; object-position: center`. This reuses cached
art instead of requesting a separate low-resolution icon first. Visual review at 28, 32, 36, 40 and 48px supported retaining
36px Discover chips and 48px profile rows. Artwork can be visually busy at 28px;
labels remain the identifying text. No per-game focal-point map or filter is used.

Compact icon fallback is contained at no more than 32px, further capped to its
actual `naturalWidth`/`naturalHeight` after load; it is not stretched to fill 48px.
The accepted large-card fallback remains unchanged. Missing art stays a glyph,
and the existing bounded failure cache is shared by every variant.

The explicit unoptimized Next Image path serves the original pixels, with no
quality recompression or responsive `srcset` selection. The component passes its
actual fixed square `sizes` hint; this Next version deliberately omits `sizes`
and `srcset` when unoptimized. The browser therefore receives the full 1920×620
library image (or 460×215 header fallback), enough for a 48px square at 2× DPR.
Tests exercise 2× DPR and assert the absence of a smaller responsive source.
There is no claim that the hint resizes this unoptimized response, and no new
quality=100, image optimizer, sharpening, pixelated rendering or global preload.
Original image transfer size is the tradeoff; browser/CDN reuse and lazy loading
remain in place. Backend DTOs, source derivation and accepted card priority are
unchanged by this compact-only refinement.

Only one `<img>` is mounted per renderer and all are lazy-loaded. A failed request
advances sequentially; variants are not prefetched together. A bounded in-memory
negative cache (512 URLs, five minutes) avoids repeated failures on rerenders and
client-side remounts. It contains no user data and does not survive a full reload.
There is no timed background retry; after expiry a later render may retry. Complete
failure leaves an accessible “Artwork unavailable” glyph, never a failed game sync.

## Authorization and remote host boundary

Library/privacy/block filtering runs before the shared DTO projection on owner,
player profile/games/detail and comparison routes. Discovery receives only currently
authorized mutual games. URLs do not expose otherwise hidden membership. Images
cannot mutate playtime, achievement coverage or freshness. The accepted avatar
implementation is independent and frozen for this upgrade.

The renderer accepts only the two exact hosts and the matching AppID/path/filename;
credentials, arbitrary query strings and alternate domains are rejected. Next Image
is explicitly unoptimized, using direct browser loading, so no wildcard
`remotePatterns` or image proxy is introduced. Existing labeled landing samples
retain a narrowly validated local `demoSrc`, separate from account data.

The CDN sees the viewer IP and requested AppID. `no-referrer` prevents sending a
profile URL; SteamScope cookies, API keys and Steam account IDs are not appended or
sent to these hosts. An image GET is distinct from authenticated Steam API sync.
