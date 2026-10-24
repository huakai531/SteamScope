# ADR-0018: No business tables in Phase 1

Status: accepted design; future-phase behavior remains planned.

## Context

The foundation has no accounts, messages or sync jobs yet.

## Decision

Configure and validate Alembic without a domain revision; its version table is infrastructure only.

## Alternatives considered

Placeholder users table; all-MVP migrations before features.

## Consequences

Current revision is blank; Phase 2 owns the first business revision.

## Revisit conditions

A genuinely required foundation table has its own justification.
