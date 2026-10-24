# ADR-0015: OpenAPI-generated client types

Status: accepted design; future-phase behavior remains planned.

## Context

Hand-written DTO duplicates drift.

## Decision

Export actual FastAPI schema; generate TypeScript with openapi-typescript; CI checks diffs.

## Alternatives considered

Manually maintained mirrored types; generating future pretend endpoints.

## Consequences

Only current health/system types exist; runtime validation remains necessary.

## Revisit conditions

A different public contract protocol is deliberately adopted.
