# Migration notes — Phase 2 baseline and Phase 3A extension

Revision: 0001_phase2_accounts. Parent: None (the accepted Phase 1 chain had no business revision).
Six domain tables plus alembic_version. Explicit Alembic operations; no ORM create_all.

Development steamscope_social_dev and integration steamscope_social_test were inspected at
the Phase 1 empty head, upgraded without reset, and verified with alembic current/check.
The isolated migration test additionally verifies a fresh database, exact tables, six foreign
keys including audit SET NULL, downgrade to base and re-upgrade. PostgreSQL internal char
constraint codes are explicitly cast to text in the test for consistent asyncpg handling.

Commands from backend/: uv run --frozen alembic upgrade head; alembic current; alembic check.
In containers use docker compose --env-file .env exec -T api alembic <command> from social/.
The main database is always upgrade-only during validation. No volume deletion or legacy schema access.

Tests require SOCIAL_ENVIRONMENT=test and the exact steamscope_social_test URL. Only
steamscope_social_migration_test may be rolled back; the harness refuses any unrelated or
nonempty table first. It creates that database if absent and leaves it migrated/empty at head.
Never reuse this name for user data. Run mutation suites sequentially, not against a shared
live test run. Future migration revisions must preserve this chain and test upgrade/rollback
with fixtures appropriate to their own data transformations.

## Phase 3A: 0002_phase3a_steam_sync

Parent 0001_phase2_accounts. Adds seven tables and five nullable/defaulted steam_accounts columns;
the import generation has a server default 0 for existing links. No reset, legacy import or
create_all is used. Current schema is 13 domain tables plus alembic_version, with 14 foreign keys.

The migration test first upgrades a disposable empty DB to Phase 2, inserts a synthetic user,
verified link, session and private settings, then upgrades to 3A. It validates preservation,
schema/constraints, downgrades only that disposable DB to 0001, re-upgrades and verifies the same
records. It removes only those fixtures before the base rollback/fresh re-upgrade checks.
Development is upgrade-only; the acceptance run compares safe pre/post aggregate digests of
existing account records. See the public validation summary for evidence boundaries.

For an existing running Phase 2 stack, build first, then migrate using the new image before
recreating API/Worker. From social/:

```powershell
docker compose --env-file .env --project-name steamscope-social-dev build api frontend
docker compose --env-file .env --project-name steamscope-social-dev run --rm --no-deps api alembic upgrade head
docker compose --env-file .env --project-name steamscope-social-dev up -d --wait
docker compose --env-file .env --project-name steamscope-social-dev exec -T api alembic check
```

Downgrading 0002 removes imported data/jobs and is deliberately tested only on disposable data.
It is not a rollback recipe for the owner's development database.

## Phase 3B: 0003_phase3b_steam_details

Parent is the inspected actual 0002 head. Five new tables, job scope/app defaults, scoped active index
and extended resource CHECK are additive to existing account/library data. No database recreation.
The isolated migration test inserts representative Phase 3A game/minutes/recent/state/job plus
user/link/session/settings, upgrades, checks 18 domain tables / 21 FKs and preservation, then exercises
0003-to-0002 and fresh-base upgrade only in the guarded disposable migration database. 0003 downgrade
refuses populated 3B tables or scoped histories; never use it against development as a rollback recipe.

Actual container upgrade on 2026-10-22: first verify no active jobs, stop idle Worker, run the new
image's `alembic upgrade head`, then `compose up -d --wait`; `alembic current`, `alembic check` and
Worker --check all exit 0. All 13 existing tables' original-column counts and private sorted row digests
matched before/after (normal session last_seen_at updates excluded). Environment files, volumes,
existing sessions and legacy data were preserved. See the public validation summary for evidence boundaries.

## Phase 3C migration acceptance

No new revision: 0001 → 0002 → 0003_phase3b_steam_details remains the chain. The current integrated
test additionally seeds shared schema/definition, personal state/unlock and friend edge in the
disposable migration DB. Upgrade head preserves every table digest; downgrade to 0002 must exit 1
with the explicit nonempty-data guard and preserve all rows and alembic_version. Only those fixtures
are then removed to test empty downgrade/base/fresh head. Unique active-scope/claim and personal
achievement/friend indexes, 18 domain tables and 21 FKs are checked. This is included in the current
214-test run. Development current/check/no-op upgrade pass with all 18 table digests preserved;
no development downgrade or database recreation occurred. See the public validation summary .

## Phase 5: 0004_phase5_social

Additive child of 0003: five social tables, 11 new FKs (32 total), canonical/partial unique indexes
and a report-description redaction trigger on account deletion. No existing Steam rows are rewritten.
Test migration path covers Phase2 fixture→3A→3B→5, preserved rows, fresh-base→head, and isolated
empty downgrade/re-upgrade. A nonempty Phase5 table makes downgrade fail explicitly and atomically.
Never downgrade development as a test. No database or volume deletion is required.

After image build, verify no active sync jobs, run the new image's `alembic upgrade head` before
serving the new API, then recreate API/Worker/frontend using Compose. Run current/check/no-op
upgrade and worker --check; compare the 18 accepted tables before/after (excluding session activity).
Actual results and failure/retry history are retained in Phase5 report .

## Phase 6 migration

0005_phase6_chat follows 0004_phase5_social; adds four chat tables, constraints, indexes and two
membership/erasure triggers. It does not rewrite existing user/Steam/social rows. Downgrade refuses
when any chat table is nonempty; never clear real chat data to make rollback succeed.
Actual fresh/upgrade/disposable roundtrip and nonempty downgrade refusal run only in the explicitly
isolated migration_test database. Container development migration is additive, followed by current,
check and no-op upgrade; original table digests are compared before/after. Evidence: COMMANDS.
