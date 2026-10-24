# ADR-0017: Locked dependency management

Status: accepted design; future-phase behavior remains planned.

## Context

Windows and CI need reproducible compatible packages.

## Decision

uv with uv.lock for Python 3.12; npm with package-lock for Node 24. Frozen installs in CI.

## Alternatives considered

Multiple JS managers; unpinned pip installs.

## Consequences

Developer requires uv/npm; dependency upgrades are reviewed with checks.

## Revisit conditions

Chosen tool is unavailable or no longer maintained.
