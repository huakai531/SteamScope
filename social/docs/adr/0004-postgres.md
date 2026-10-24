# ADR-0004: PostgreSQL durable truth

Status: accepted design; future-phase behavior remains planned.

## Context

Identity, relationships, jobs and messages require constraints and transactions.

## Decision

PostgreSQL is the durable source of truth with one new migration chain.

## Alternatives considered

SQLite; Redis-only state; reusing legacy schema.

## Consequences

Unique constraints and transactional state transitions are testable on real PostgreSQL.

## Revisit conditions

Measured storage requirements exceed the selected model.
