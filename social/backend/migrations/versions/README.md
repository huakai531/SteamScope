# No business migrations in Phase 1

`alembic upgrade head` connects to the guarded social development/test
database and initializes Alembic's version infrastructure, with no business
tables. No revision exists yet. `alembic current` is therefore blank.
Phase 2 introduces the first domain migration. Never use the legacy chain.
