# ADR-0016: Isolated additive rebuild

Status: accepted design; future-phase behavior remains planned.

## Context

Old identity model and migration chain conflict with the social product.

## Decision

Preserve baseline and legacy paths; add social with independent DBs, volumes and package name.

## Alternatives considered

In-place table rewrites; deleting old project.

## Consequences

Temporary two-app repository; root changes limited to CI/pointer.

## Revisit conditions

Legacy retirement is explicitly approved after useful assets are preserved.
