# ADR-0006: Steam OpenID identity

Status: accepted design; future-phase behavior remains planned.

## Context

SteamID input does not prove account ownership.

## Decision

Phase 2 verifies Steam OpenID assertions before account creation.

## Alternatives considered

Password collection; trusting a supplied SteamID; assuming OAuth scopes.

## Consequences

No Steam passwords; OpenID does not unlock private API data.

## Revisit conditions

Valve changes the supported browser authentication mechanism.
