# ADR-0007: Server-side Steam credentials

Status: accepted design; future-phase behavior remains planned.

## Context

Keys can appear in request query strings and logs.

## Decision

Only API/worker server settings hold future keys; redact URLs and raw errors.

## Alternatives considered

Browser key configuration; committed .env; user-entered Steam passwords.

## Consequences

Mocks need no live keys; logging must not capture upstream credential URLs.

## Revisit conditions

Provider supports a safer credential mechanism.
