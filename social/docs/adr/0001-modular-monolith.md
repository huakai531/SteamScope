# ADR-0001: Modular monolith

Status: accepted design; future-phase behavior remains planned.

## Context

A solo portfolio team needs clear boundaries without distributed coordination.

## Decision

One Python codebase with owned domain modules; API and worker are processes of that application.

## Alternatives considered

Microservices; undifferentiated single service file.

## Consequences

Cross-module contracts and transactions stay explicit; deployment remains small.

## Revisit conditions

Independent scaling or organizational ownership demonstrably requires a split.
