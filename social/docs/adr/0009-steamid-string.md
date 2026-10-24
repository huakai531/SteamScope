# ADR-0009: SteamID64 strings

Status: accepted design; future-phase behavior remains planned.

## Context

JavaScript numbers cannot preserve all 64-bit identifiers.

## Decision

Store validated decimal text and serialize it as string; active Steam association unique.

## Alternatives considered

JSON numeric IDs; truncated identifiers.

## Consequences

Generated types and exact round-trip tests enforce the boundary.

## Revisit conditions

Only a future API contract with explicit bigint serialization could change this.
