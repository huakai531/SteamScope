# Threat model

Assets: verified identity, sessions, private profile data, relationship graph, messages, reports, credentials and deletion intent. Browser/external APIs are untrusted; moderator access is privileged and audited.

Current release review, 2026-10-24: full and production npm audits both passed with zero findings. The braces path remains but its advisory was withdrawn upstream; the former exception is closed. See [current security status](CURRENT_SECURITY_STATUS.md). The phase sections below record when controls were introduced, including the dependency risk accepted at that time. They do not reauthorize that historical exception. Production deployment remains unsupported.

| Threat | Mitigation / verification target | Phase |
|---|---|---|
| Forged callback / replay | Verify provider response, claimed identity, endpoint, nonce and return target; one-time state; no caller-controlled verification URL | 2 |
| Session theft / fixation | Opaque hashed sessions, rotation, expiry, Secure/HttpOnly cookies, per-device revocation and socket invalidation | 2,6 |
| CSRF / socket impersonation | CSRF and Origin validation on state changes; permitted socket Origin and verified session; never query-string session secrets | 2,6 |
| XSS | React escaping, no untrusted HTML, bounded plain text messages/bios; add deployment CSP | 2,6,8 |
| SQL injection / IDOR | Bound SQL, typed values, actor-scoped service interfaces and object authorization for every read/write | 2–6 |
| API key / log leakage | Server-only SecretStr settings; no URLs/raw error payloads in logs; scan tracked candidates and bundles | 1,3 |
| Privacy bypass / enumeration | Filter source/platform privacy, counts, caches, recommendations and pair comparisons; throttle lookup; generic no-result | 2–5 |
| Unauthorized conversations | Verify membership, active connection/message policy and either-direction blocks for every event/history read | 6 |
| Spam and abusive reports | Per-actor/pair budgets, bounded bodies, deduplication windows and restricted moderator evidence | 5,6 |
| Duplicate replay / jobs | DB unique client IDs; durable task keys; leases and fencing; reject mismatched replay payload | 3,6 |
| Redis exposure / transient loss | Loopback host binding, private container network, short TTLs; PostgreSQL source of truth; production authenticated network policy | 1,6,8 |
| Deletion failure / resurrection | Advance deletion generation, revoke sessions, fence/cancel tasks, purge caches, retry cleanup, replay tombstones on restore | 2–8 |
| Dependency outage | Liveness stays up; bounded readiness; safe error response; circuit/cooldown in future external adapters | 1,3 |
| Supply-chain / build exposure | Frozen dependency installs; no .env in Docker contexts; nonroot images; review package updates and deployment controls | 1,8 |

Phase 2 implemented controls: fixed-provider discovery/direct verification; single-use browser-bound
transactions; provider nonce replay detection; digest-only expiring/revocable sessions; exact Origin
and CSRF checks; owner-derived access; conservative privacy; atomic erasure; bounded Redis rates;
no request/exception secret logging. These are covered by unit, real PG/Redis and browser tests.
Phase 3A adds generation/token/lease fencing under the deletion user lock, committed claims before
network calls, strict fixed-destination bounded HTTP, independent privacy/snapshot states, persistent
quotas and owner-only uncached reads. Tests cover in-flight deletion/clear and worker crash recovery.
Phase 3B added selected-game achievements and owner-imported Steam friends;
sockets, report intake and chat were introduced in later phases below.

Residual risks: live OpenID is historically USER VERIFIED; Phase 3 real data paths have historical
USER VERIFIED and SERVER VERIFIED evidence;
no new upstream validation was requested in Phase 3C. The Steam-only protocol
adapter needs ongoing review; local proxy peers share an authentication quota; maintenance is
operator-run; deployment CSP, backup deletion handling and broad browser/accessibility audits
remain future work. The Phase 3 full npm audit failed and was covered by a conditional local-development exception with the original 2026-11-05 deadline. Its later closure is described in the current status above; full original evidence stays private. Local isolation is not public-release approval.

## Phase 3C completed control review

An incomplete upstream player response could destructively replace a previously accepted snapshot.
The four-line repository guard and failing-before/passing-after isolated tests now preserve old
content/time/revision and hide unknown current progress. No signature, nonce, state, CSRF, owner,
lease or generation check was weakened. Full privacy/deletion/race/worker tests passed again.
Existing safe diagnostics plus current runtime logs were checked privately for configured secrets
and real identity leakage; no matches. Frontend input flow and final artifacts remain outside the
known braces tool-chain implementation. The private historical audit retains full FAILED and the original exception
expiry. This is bounded local assurance, not a penetration test or public deployment approval.

## Phase 4 added read surfaces

Cross-user IDOR and indirect leakage now have executable tests for resource/visibility/source
combinations, cursor reuse, filter/sort probing, totals, partial achievements, account deletion,
clear and handle reassignment. Viewer identity comes only from the validated server session;
profile invisibility shares not-found semantics. Consistent read-only policy/data snapshots avoid
mixed-revision disclosure; overlapping reads are explicitly snapshot-linearized. No claim of
retroactively withdrawing already-read browser content is made.

New q input is literal substring data; React escapes profile/Steam text (including tested HTML-like
bio). No glob/brace, template evaluation, shell, remote image proxy or arbitrary origin routing.
Final production artifacts and secret injection are checked independently of devDependencies.
The then-active finite GHSA exception was not extended to new advisories or paths. Read projection
loads the bounded imported library in memory; high-load/public attack resistance is not certified.
No discovery, relationship graph or chat permission has been added.

## Phase 5 threat controls

| Threat | Implemented control / evidence |
|---|---|
| Enumerating hidden accounts | min query3, max20, no registry cursor/SteamID lookup, active verified discovery/profile filter, bilateral block, per-actor Redis limits |
| Private data affecting rank | authorize before projection/scoring; fresh permitted fields only; private value changes leave rank/reasons unchanged in tests |
| Reciprocal/concurrent writes | canonical user-row lock order + partial pending unique and canonical pair PK; real PG races and terminal retry tests |
| CSRF/IDOR/spoofed actor | established Origin/CSRF/session; intended receiver/sender and recipient checks; no supplied acting user ID |
| Block inference or leakage | generic hidden response, remove relationship/pending/events, read-time notification policy, minimal explicit owner lists |
| Report spam / disclosure | reason allowlist, 1000-char bound, 3/hour, same-reason24h dedup, no ordinary report read, deletion redaction and 90-day cleanup |
| Stored text / accepted brace vulnerability | React escaped text; parameterized literal SQL; no glob/fs/shell/build sink; unchanged dependency chain and runtime scan |
| Redis outage | limits fail closed; no new events/connection without protected write; PostgreSQL keeps persisted notifications |

Per-account limits do not prevent coordinated Sybil abuse; production anti-abuse/moderation
operations remain future prerequisites. No public release, external PR automation or tunnel is
authorized by the Phase 5 acceptance. The then-active GHSA exception retained its original expiry; new findings require separate action.

## Phase 6 chat threats and controls

| Threat | Implemented control / evidence |
|---|---|
| Cross-site WebSocket hijack / token leakage | Exact configured Origin and Host proxy; cookie authentication; query rejection; no token storage/URL; handshake URL logging filter |
| Conversation/message IDOR or arbitrary subscriptions | Participant DB policy before every read/write/event; generic404; unrelated socket tests |
| Block/session TOCTOU | Ordered pair/user/session locks shared with graph changes;1s revalidation and bounded8s target; race tests |
| Duplicate/lost message | DB unique sender/client ID and sequence; commit before hint/ack; actual post-commit process crash test; retry/gap reconciliation |
| XSS / pattern injection | Plain text NFC/length/newline/control bounds; React escaped text; no glob, shell, file or rich-text interpretation |
| Flooding / stale presence | Explicit per-account REST/WS quotas,1024-byte frames,16sockets; TTL and multi-tab independent entries |
| Redis failure | Fail-closed before write; post-commit hints may be lost but history persists; reconnect from DB |
| Deleted/report exposure | Tombstone everywhere; no report body duplication/list/target identity disclosure;90d cleanup/redaction/cascades |

Residual: no E2EE, no production load test/moderation operation/retention scheduler or backup policy.
No public deployment authorization. The Phase 6 review retained the original GHSA exception and required review of
new input/transport boundaries. Current dependency findings and closure of that exception are documented in [current security status](CURRENT_SECURITY_STATUS.md).
