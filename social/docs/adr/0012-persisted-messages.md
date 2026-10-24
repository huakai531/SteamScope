# ADR-0012: PostgreSQL messages

Status: accepted design; future-phase behavior remains planned.

## Context

Clients reconnect and Redis events can be lost.

## Decision

Commit text message with unique sender/conversation/client ID before acknowledgement.

## Alternatives considered

Redis-only history; in-memory conversation state.

## Consequences

History backfill is authoritative; conflicting ID payloads are rejected.

## Revisit conditions

A proven durability/capacity need justifies another store.
