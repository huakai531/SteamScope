# Module boundaries

Phase 2 implements auth/users/privacy/administration; Phase 3A adds modules.steam for source validation, normalized snapshots, quotas and durable jobs. The existing worker calls this same module. Achievements/friends and later modules remain planned.
Current interfaces: auth.openid.verify_assertion, auth.security.authenticated, auth.service.finish_login,
privacy.policy.can_view and administration.cleanup.purge_expired. API/account.py orchestrates the
current owner-scoped settings/deletion transaction. Locale/timezone reside on users; future preference
tables below are not created. login_attempts belongs to auth.

Module packages are introduced only in their owning phase. UI never determines authorization.

## auth

- Responsibility: Verify Steam OpenID; rotate/revoke sessions.
- Owned data: steam_accounts, user_sessions.
- Public interfaces: `authenticate_callback, current_actor, revoke_sessions`.
- Dependencies: users identity creation; audit interface.
- Prohibited: Import libraries or infer privacy authorization from login.

## users

- Responsibility: Account/profile/preferences lifecycle.
- Owned data: users, user_play_preferences, user_favorite_games.
- Public interfaces: `get_account, update_profile, begin_deletion`.
- Dependencies: privacy settings; deletion coordinator invokes domain cleanup.
- Prohibited: Own Steam snapshots or bypass other modules.

## privacy

- Responsibility: Evaluate field visibility and interaction policies.
- Owned data: privacy_settings.
- Public interfaces: `can_view, can_discover, can_request, can_message`.
- Dependencies: Read-only relationship facts supplied by caller; account status.
- Prohibited: Read every module through cyclic service imports.

## steam

- Responsibility: Validate external data; jobs, snapshots and freshness.
- Owned data: games, user_games, achievement_definitions, user_achievements, steam_friend_edges, steam_sync_jobs, steam_sync_runs.
- Public interfaces: `enqueue_sync, get_snapshot, delete_subject_data`.
- Dependencies: users active/version check; PostgreSQL; Redis limiter; HTTP adapter.
- Prohibited: Authenticate ownership; create platform connections.

## profiles

- Responsibility: Project authorized profile/library/comparison views.
- Owned data: Read models only; no independent source of truth.
- Public interfaces: `profile_view, compare_players`.
- Dependencies: users, steam, privacy, social relationship facts.
- Prohibited: Return raw snapshots or hidden counts.

## discovery

- Responsibility: Filter and rank eligible players with explanations.
- Owned data: Read models; optional disposable cached rankings.
- Public interfaces: `search_players, matching_players`.
- Dependencies: users, steam, social facts, privacy.
- Prohibited: Persist opaque game recommendation scores as player truth.

## social

- Responsibility: Requests, canonical connections and directional blocks.
- Owned data: connection_requests, connections, user_blocks.
- Public interfaces: `request, accept, remove, block, relationship_facts`.
- Dependencies: users, privacy with supplied facts; notifications; audit.
- Prohibited: Call profiles/discovery/chat to make basic authorization decisions.

## chat

- Responsibility: Persistent member-scoped conversations/messages/read state.
- Owned data: conversations, conversation_members, messages.
- Public interfaces: `open_direct, send_message, history, mark_read`.
- Dependencies: users/auth, social facts, privacy, Redis transient transport.
- Prohibited: Treat Redis as message history; accept caller-supplied sender identity.

## notifications

- Responsibility: Idempotent recipient-scoped notifications.
- Owned data: notifications.
- Public interfaces: `record_notification, list_for_actor, mark_read`.
- Dependencies: privacy and social facts at delivery.
- Prohibited: Send sensitive content to newly blocked recipients.

## moderation

- Responsibility: Reports, evidence access and recorded decisions.
- Owned data: reports, moderation_actions.
- Public interfaces: `submit_report, review_report, apply_action`.
- Dependencies: authorized actor and bounded domain evidence interfaces.
- Prohibited: Give unrestricted message-history access to ordinary users.

## administration

- Responsibility: Restricted maintenance and security audit.
- Owned data: audit_logs.
- Public interfaces: `record_audit, authorized_admin_action`.
- Dependencies: auth/role boundary and explicit domain interfaces.
- Prohibited: Expose public administrative or generic SQL endpoints.

## Dependency discipline
Privacy evaluates explicit context/facts instead of importing social services. Social exposes
read-only relationship facts to caller orchestration. Profiles/discovery/chat depend on those
interfaces; social does not import them back. Deletion is an explicit users-owned coordinator
calling registered domain cleanup interfaces, with transaction/version fencing. Auditing is
append-only through a narrow interface. Avoid a catch-all repository or generic utility layer.


## Phase 4 player projection

`modules/players` is a read-only projection over accepted auth/privacy/Steam models, not a new
sync repository. `api/players.py` resolves only session viewers and bounded handles/app IDs.
The same authorization projection supplies profile, library, detail and comparison. No provider
client or Redis result cache is imported. `PlayerApp` renders generated DTOs through GET-only
fixed proxy routes. ADR0024 defines privacy/source and consistent-snapshot boundaries.

## Phase 5 concrete implementation

`modules/social/models.py` owns five graph/report/event tables; `policy.py` exposes read-only
relationship facts to `modules/players`. `social/service.py` owns transactional pair transitions.
`social/discovery.py` is explicit orchestration over the authorized player projection and social
facts; the policy layer does not import that orchestration (no cycle). `api/social.py` owns bounded
routes, lists and recipient reads; `administration/cleanup.py` implements the documented expiry.
Reports/notifications are small Phase5 domain pieces in this module, not a moderator UI or delivery
bus. Steam workers/provider clients are not dependencies of social reads or graph writes.

## Phase 6 concrete chat boundary

modules/chat owns four tables, schemas, one canonical durable service and a transient socket adapter.
api/chat.py exposes REST; modules/chat/realtime.py handles cookie-authenticated sockets, delivery and
TTL state. It consumes auth/privacy and Phase5 relationship policy/ordered locks, never Steam clients
or worker jobs. DB transaction exits before publish. Existing account FK cascades plus the additive
report erasure trigger coordinate deletion; cleanup extends the explicit administration command.
Next's exact-path runtime proxy handles WS Upgrade; existing bounded REST forwarding handles chat
HTTP routes. Generated DTOs and ChatApp share canonical server results, not a separate client store.
