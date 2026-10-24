# Professor demo — five minutes

[Project](../../README.md) · [Case study](CASE_STUDY.md) · [Architecture](ARCHITECTURE_OVERVIEW.md)

The main flow below takes 4:40. For a two-minute version, use the README hero (30s), Profile/Discover screenshots (45s), Chat screenshot (25s), then architecture and limits (20s). Label every screenshot as synthetic; do not imply a live demonstration.

This is a **planned private local review**, not a record of a demo already delivered. It uses the existing local application and accepted saved data. It does not authorize a public broadcast, tunnel, deployment, or automatic Steam request. If the venue requires public access or distribution, revisit the existing security/deployment restriction first.

## Before sharing the screen

Use `http://127.0.0.1:3100` consistently. `{handle}`, `{peer_handle}` and `{appid}` below are route placeholders; privately follow the application's links to the intended existing accounts and games. Do not paste personal identifiers into slides.

- Keep the five services running using the [development guide](../operations/DEVELOPMENT.md). Do not restart or migrate them just to demonstrate a healthy stack.
- Sign in privately before the demonstration. A second consenting participant may use a separate browser profile/context on the same local machine. Do not exchange credentials or cookies.
- Confirm the intended connection and both messaging preferences privately. Do not remove/recreate a real relationship merely for presentation.
- Prepare only the specific tabs needed; hide bookmarks, other windows, notifications and browser account details. Close terminals, `.env`, DevTools, network/storage panels and server logs.
- Use only participant-approved display names and message content. If existing chat history is private, omit that live pane and use the fallback below. Do not alter database history for a cleaner demo.
- Precheck saved data and its labels. **Do not click any Steam synchronization button during the demo.** A stale snapshot is a valid explanation, not something to conceal.
- Open the README architecture diagram and the case-study testing table in a Markdown viewer. No live external documentation or API request is needed for those tabs.

## Five-minute flow

| Time      | Exact page / action                                                                              | Suggested narration                                                                                                                                                                                                                                                                                                                            |
| --------- | ------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0:00–0:30 | README overview, then `/`                                                                        | “SteamScope is a Steam-data-driven social platform. Gaming history gives an introduction context before players connect and chat.”                                                                                                                                                                                                             |
| 0:30–1:00 | `/login` to show the entry, then the already authenticated `/account` or **Player profile** link | “Steam verifies identity through OpenID. SteamScope keeps its own account, profile preferences and revocable session. Authentication does not unlock private Steam data.” Do not enter passwords or expose an authentication callback on screen.                                                                                               |
| 1:00–1:40 | `/users/{handle}` → `/users/{handle}/games` → `/users/{handle}/games/{appid}`                    | “These are saved library and achievement snapshots. Known minutes and states remain distinct from Unknown. Historical data is labeled stale; an exact completion percentage requires current complete evidence.” Show one approved game, not an exhaustive personal library.                                                                   |
| 1:40–2:15 | `/discover`, then `/connections`; optionally `/users/{peer_handle}`                              | “Discovery explains the visible evidence used. A Steam friendship is not a platform connection: the recipient must accept a request.” Show an existing accepted connection. If discovery is empty, explain that privacy/freshness and positive evidence govern inclusion.                                                                      |
| 2:15–3:30 | `/messages` in the two separately signed-in contexts                                             | With both participants' consent, open the existing conversation using **Open conversation** or **Message**. Manually send one agreed non-sensitive demo message and reply. Show delivery without refresh, typing/presence, read state, then refresh one pane to show durable history. Do not include existing private text in the shared view. |
| 3:30–4:00 | README **Architecture** diagram                                                                  | “PostgreSQL stores durable truth. Redis coordinates transient delivery and presence. The independent Worker imports Steam data. WebSocket delivery can be lost without losing a committed message.”                                                                                                                                            |
| 4:00–4:40 | Case study **Major technical challenges** and **Testing**                                        | Explain one failure scenario: commit succeeds, acknowledgement is lost, retry reuses the client ID. Then explain authorization before scoring. “See the validation summary for the independently tested candidate; historical live Steam and real two-user checks are separate evidence.”                                                  |

The main flow takes **4 minutes 40 seconds**, leaving 20 seconds before the five-minute limit. Use the two-minute screenshot version above when time, network or a second account is unavailable. Skip creating any new relationship.

## What to emphasize, not click

- On `/account/privacy`, if time allows, point out independent resource and messaging visibility. Do not change Steam visibility or platform permissions just to produce a preferred result.
- Explain the already verified block/unblock behavior: blocking denies messaging; unblocking does not restore consent. Repeating this destructive-to-the-relationship interaction is unnecessary in a short demo.
- On `/notifications`, an empty state is appropriate if there are no current eligible events. Do not invent notifications or recommend placeholder users.
- For stale achievements, keep **completion unavailable** visible and explain the policy. Do not replace it with the earlier historical percentage.

## Fallbacks that preserve the evidence boundary

| Situation                                                           | Safe fallback                                                                                                                                                                                     | State explicitly                                                                                      |
| ------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| Steam unavailable or no network                                     | Use the already signed-in account and accepted saved owner snapshots; do not sync or retry. If login itself is unavailable, use the case study or a previously approved redacted screenshot.      | “This is persisted historical data; no new Steam call is being demonstrated.”                         |
| Second account unavailable or chat history not approved for display | Show the Messages entry/controls without exposing history, then the chat sequence diagram and recorded accepted results. An approved redacted recording may be used later if one actually exists. | “Live two-user chat was verified during acceptance; it is not being repeated in this demo.”           |
| Discovery empty                                                     | Show the truthful empty state and the documented scoring inputs. An already accepted connection can still illustrate the next step.                                                               | “No eligible positive evidence is available for this view; these are not fabricated recommendations.” |
| Schema or progress stale/restricted                                 | Keep its current status and show the privacy case study.                                                                                                                                          | “Unknown is not locked, and stale completion is not exact completion.”                                |
| API/Redis unavailable                                               | Stop the interactive flow; show diagrams and existing acceptance evidence. Do not run fault injection during the professor demo.                                                                  | “The live dependency is unavailable; this segment is a documented walkthrough.”                       |

## Screen exclusions and closing line

Never show SteamID64, session/conversation query identifiers, callback parameters, API keys, passwords, Cookie/storage values, full request URLs, raw provider responses, private messages or other accounts' personal details. Crop the address bar for recorded material; never share an original HAR file. Any later recording needs the [screenshot plan's](SCREENSHOT_INDEX.md) review boundary and participant consent.

Close with: “The local MVP is complete and tested. Communities and Looking for Group are planned; production hardening and deployment are separate work.” Do not say cloud deployed, production ready, or that remote CI has run.

Recheck the [current security record](../security/CURRENT_SECURITY_STATUS.md) before a demonstration. The former advisory is withdrawn and the exception closed; public access/deployment still requires separate approval.
