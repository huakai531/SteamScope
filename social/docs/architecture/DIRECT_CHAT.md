# Direct chat — Phase 6

This is SteamScope plain-text chat, not Steam messaging or end-to-end encryption.
PostgreSQL owns all durable truth. Redis coordinates transient delivery, typing and presence.
No chat read, write, refresh or socket operation calls Steam or enqueues a Steam job.

## Eligibility and revocation

Create/send requires two active accounts, an accepted SteamScope connection, neither direction
blocked, and both `privacy_settings.messaging = connections`. Imported Steam friendship and
discovery recommendations grant nothing. Direct creation resolves a verified account handle;
the caller cannot supply a sender ID. A conversation has one canonical ordered UUID pair.
The pair unique constraint and ordered user locks prevent simultaneous A–B/B–A duplication.

| Relationship/current state | Participant history | New messages/typing | Peer presence |
|---|---|---|---|
| Connected, both allow messages | Readable | Allowed | Only public/connections presence |
| Connection removed or either messaging=nobody | Readable | Denied | Unavailable |
| Either direction blocked | Hidden, generic 404 | Denied | Unavailable |
| Unrelated/anonymous/invalid session | Denied | Denied | Denied |
| Either account deleted | Conversation and its messages erased | Denied | Denied |

Removing a connection does not delete history. Unblocking does not reconnect; an explicitly
restored connection reuses the existing canonical conversation. Profile visibility still controls
whether the peer handle/display name appears; private profile data is not included in events.

Each durable operation and outgoing conversation event rechecks the session and current policy
under the same ascending user locks used by Phase 5 graph transitions, followed by session locks.
Once the policy mutation commits, subsequent protected operations deny access. Existing sockets
revalidate every second; bounded dependency checks are 4s, cleanup 2s, individual send 1s.
The tested operational revocation target is **within 8 seconds** for logout, logout-all, individual
session revoke, disabled/deleted account and block, without refresh. Already delivered/in-flight
packets cannot be retracted; the UI clears protected history on unavailable/disconnection.
The latency target assumes a functioning event loop/network, not an absolute distributed guarantee.

## Persistence, identity and pagination

`messages` has unique `(sender_id, client_message_id)` and `(conversation_id, sequence)`.
The client creates a UUID once per logical send. A failed acknowledgement keeps that UUID/body
in memory for the explicit Retry action. Same payload returns the original canonical record;
changed body/conversation returns 409. Different senders may use the same client UUID. No draft,
credential or pending-message store is written to localStorage. Reload loses an unsent draft;
committed messages remain recoverable from the database.

REST is the sole durable send path: validate/rate limit → lock pair → reauthorize → allocate
monotonic conversation sequence → insert → commit → publish safe hint → HTTP canonical result.
Redis failure before authorization/rate limiting is fail-closed 503, with no insertion. Redis
publication failure after commit does not undo persistence or create a false failure response.
Process death after commit/before response is recovered by retrying the same ID or reading history.
Persistence failure emits neither a success acknowledgement nor a message-created hint.

History uses exclusive integer `before` or `after`, never both; default 50/max 100, ascending
returned rows. Sequence is immutable and unique. New inserts do not shift older pages. Cursors
are not authority. Conversation lists use immutable descending UUID cursors, default 25/max 50;
they do not promise most-recent-first ranking. Last-message time/preview are displayed separately.

Messages are NFC-normalized plain text, CRLF/CR normalized to LF, at most 2000 Unicode characters
and 50 newlines, non-whitespace, without control characters except newline/tab or surrogate code
points. React renders text; no HTML, Markdown interpreter, shell, filesystem or glob evaluation.
URLs remain text. No attachments, group chat, voice, video, reactions or edit operation exist.

## Read state and unread

Each member stores a monotonic `last_read_sequence`. Acknowledgements take max(previous, requested)
and reject cursors past the durable end. Unread counts exclude own sends and tombstones. The
conversation/sequence/sender partial index supports unread queries; there is no memory-only counter.
Visible selected history acknowledges its durable end; another tab observes the persisted cursor
through a hint/state refresh. Read receipts describe this cursor, not proof that a human read text.

## WebSocket contract v1

Same-origin `ws[s]://<frontend>/api/v1/ws`, with the existing HttpOnly session cookie. All query
strings are rejected. The Next runtime proxy validates configured Host, exact Origin and Upgrade,
then rewrites only this fixed path to the private API. Invalid upgrades discard the client query
and use a fixed `?rejected=1` marker, which the API unconditionally rejects before cookie lookup.
This avoids Next leaving raw Upgrade sockets open for a middleware-only 403 response.
API independently checks Origin/session; the marker never grants authentication.
No token in URL, browser storage or application logs. Uvicorn handshake URL access records are
filtered as well as HTTP access logging being disabled; event/body debug logs are not enabled.

Client event schemas reject extra fields; transport and application frames are at most 1024 bytes:

| Input | Fields | Effect |
|---|---|---|
| ping | type | Refresh client heartbeat only |
| watch | type, conversation_id UUID or null | Replace the one watched conversation; reauthorize |
| typing | type, conversation_id UUID, active boolean | Ephemeral typing only, never a draft/body |

All server events have `v: 1`:

| Output | Other fields | Client action |
|---|---|---|
| ready | none | Reload durable summaries, restore watch and history |
| message.created / message.deleted / conversation.read / conversation.changed | conversation_id | Authorized REST reconciliation; no message body in Pub/Sub |
| conversation.state | conversation_id, can_send, presence, typing, unread_count, last_read_sequence, peer_read_sequence, latest_sequence | Render current permitted state and refresh canonical data |
| conversation.unavailable | conversation_id | Clear protected rows/detail/presence and recheck list |
| error | safe code | Show bounded generic feedback |

Invalid/extra event fields return INVALID_EVENT. Wrong conversation/permission returns generic
CHAT_UNAVAILABLE. Invalid session closes 4401, other auth denial 4403; dependency failure closes
1013, invalid/binary interruption 1008. Pre-upgrade denials are HTTP 403. These are application
semantics, not permission bypass fallbacks. No arbitrary subscription/user ID or durable WS send.

Namespaced Redis `chat:events` carries only version/type/conversation UUID. Each API instance has
independent DB/Redis resources, subscribes and reauthorizes before delivering even that UUID.
No message bodies, Steam identity, credentials or report details are published. Pub/Sub is not
durable; no exactly-once transport or reliable delivery queue is claimed.

## Reconnect, presence and typing

Reconnect backs off 1–10s, authenticates anew, restores watch and reloads canonical summaries.
`after` paging fills gaps; recent 50 rows repair deleted-message changes; UUID/sequence reconciliation
deduplicates/reorders hints. A very large gap exceeding 20 pages resets to a contiguous recent
window with older cursor loading still available. A 15s reconciliation also repairs lost hints
without a transport disconnect. Older history is loaded explicitly, not an unbounded initial dump.

Presence is SteamScope socket presence, never “playing on Steam”. Redis sorted sets hold independent
random connection IDs with 30s expiry; heartbeat is every 10s, idle sockets close after 25s without
client ping. One tab closing removes only its own entry; crash residue expires. Peer exposure
requires current messaging eligibility plus public/connections presence; private is unavailable.
Typing uses the same per-connection model with 4s expiry, explicit stop and 2s UI debounce.
It is not persisted in PostgreSQL. Disconnect, switching watch or policy denial clears own typing;
TTL bounds crash residue. Empty/unknown presence never grants identity discovery.

## Limits, erasure and reporting

Per-account Redis expiry-based counters: conversation creation 10/min, send 60/min, read APIs 240/min,
read acknowledgement 60/min, own delete 30/min, report 3/hour, WS connect 30/min, inbound frames
180/min, typing 60/min; max 16 active socket entries. Existing sensitive-write limit (local default
30/min shared across sensitive REST writes) also applies, so it may bind before the chat-specific
limit. Rate-limit dependency failure denies new writes. These are MVP bounds, not load-test results.

Own-message deletion persists a tombstone and hides the body in every ordinary DTO/preview.
The original body remains in its single original row and becomes eligible for cleanup 90 days
after deletion; running cleanup then blanks it. Reports reference that message, never copy its body.
Same reporter/message/reason reuses the receipt. Six allowed reasons, description <=1000, no report
listing/target notification; target cannot edit evidence. Reports expire 90 days after creation.

Deleting either account erases its paired conversations, including both participants' message
history, by FK cascade. Related report references become NULL and description is redacted by the
user-deletion trigger; only minimal reason/status/timestamps remain until expiry. This policy is
deliberately stronger than disconnect/block. Clearing Steam imports leaves chat/social data intact.
No moderator UI or automated retention scheduler is installed. Operators must run the existing
documented cleanup command; 90 days is a purge eligibility threshold, not a claim of unattended
physical deletion. Backups require separate production retention work before public deployment.

## Evidence boundaries

Real PostgreSQL/Redis tests cover transactions, races, isolation, constraints and failure modes.
Two independent local API instances and browser contexts cover actual WS delivery/reconnect.
All automated users/provider responses are synthetic and isolated; no live Steam requests.
Current counts, owner UI evidence and runtime checks belong to [the public validation summary](../development/VALIDATION.md).
Missing a second real user is explicitly separate from the automated two-user acceptance gate.
