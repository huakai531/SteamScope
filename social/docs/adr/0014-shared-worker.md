# ADR-0014: Worker shares backend code

Status: accepted design; future-phase behavior remains planned.

## Context

Duplicated models diverge and complicate deletion safeguards.

## Decision

One installed package and image; independent worker command.

## Alternatives considered

Separate worker repository; HTTP-only synchronous job processing.

## Consequences

Phase 1 worker verifies dependencies and reports no handlers; no fake successes.

## Revisit conditions

A separate runtime becomes demonstrably necessary.
