# ADR-0011: PostgreSQL synchronization jobs

Status: accepted design; future-phase behavior remains planned.

## Context

Workers can crash after claiming work or after an upstream response.

## Decision

Phase 3 implements SKIP LOCKED claims, expiring leases, fencing tokens, dedup keys and bounded retry.

## Alternatives considered

In-memory task lists; unbounded retries; early queue infrastructure.

## Consequences

DB transactions never span HTTP calls; handlers must tolerate at-least-once execution.

## Revisit conditions

Measured queue throughput requires dedicated infrastructure.
