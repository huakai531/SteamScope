# ADR-0003: Next.js frontend

Status: accepted design; future-phase behavior remains planned.

## Context

A real browser application must grow into profiles and social journeys.

## Decision

Next.js App Router with strict TypeScript, Tailwind and TanStack Query.

## Alternatives considered

Vite SPA; static HTML; hosted-only starter.

## Consequences

Node server hosts a fixed health proxy; builds do not depend on API availability.

## Revisit conditions

Static-only requirements or host constraints make the server unnecessary.
