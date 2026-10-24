# ADR 0021 — Minimal Phase 2 schema, private defaults and erasure

Status: implemented. Supersedes the Phase 1 proposed defaults for the implemented tables.

Six tables are required: users, steam_accounts, user_sessions, privacy_settings, audit_logs,
and **login_attempts**. The sixth table is short-lived authentication transaction state;
PostgreSQL provides atomic one-time consumption and cascade deletion of account-bound
attempts even across API instances. It is not a future business table. Migration
0001_phase2_accounts follows the accepted empty Phase 1 chain (down_revision=None).

Locale/timezone are validated on users. The proposed user_play_preferences table is deferred
until real play/LFG preferences exist; no empty future table is introduced. Profile fields
are user-selected, with New player as an honest platform placeholder. No Steam nickname,
avatar, level, visibility or synchronized data is fabricated. Handles use independent random
bytes, not SteamID, session credentials or personal information.

Defaults are private for profile/library/playtime/achievements/presence, discovery=false,
connection_requests=nobody, messaging=nobody. This is stricter than the Phase 1 connections
proposal because Phase 2 has no relationship source. can_view denies connections-only for
all non-owners; inactive accounts/unavailable sources deny everyone. All existing settings
endpoints are owner-only regardless of a saved public preference. Future consumers must
combine source availability, actor relationship and block policy; saving a preference does
not mean a nonexistent public/profile/chat endpoint enforces it.

Deletion requires session + Origin + CSRF + literal DELETE + Steam verification within the
configured recent-auth window. Reauth is a separate POST initiation bound to the current
user/session; another Steam identity fails without replacing the protected account.
Reverification may reuse Steam's browser session and does not guarantee password/Guard entry.

One database transaction hard-deletes the user, Steam association, settings, sessions and
bound attempts; audit actor FKs SET NULL. No soft-delete flag is used as erasure evidence.
Minimal audit records contain only event, timestamp and an unrelated event UUID after
account deletion. No IP/device fingerprint or arbitrary metadata payload is collected.
A cleanup CLI deletes expired attempts, expired/idle/revoked sessions and >90-day audits.
It must be run regularly by the local operator; this phase does not install a scheduler.
The UI describes this maintenance behavior rather than promising an automatic purge time.

A fresh allowed sign-in after deletion creates a new UUID/profile/private defaults; it never
restores erased settings. Stale account-bound attempts and credentials cannot resurrect the
old user. Unlink is not offered because Steam is the only authentication method. There are
no games/messages/jobs to delete yet. Future durable sync jobs require generation/lease
fencing and deletion integration before they ship; those tables are not created here.

The rollback test refuses unrelated or nonempty tables and targets only the dedicated
steamscope_social_migration_test database. Never downgrade development or shared test data.
