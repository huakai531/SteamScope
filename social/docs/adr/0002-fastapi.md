# ADR-0002: FastAPI backend

Status: accepted design; future-phase behavior remains planned.

## Context

The existing team has Python integration and typed API experience.

## Decision

Use FastAPI, Pydantic, SQLAlchemy asyncio and asyncpg; no legacy runtime imports.

## Alternatives considered

Django; Node backend; copying the entire old app.

## Consequences

Generated OpenAPI and async probes; async transaction discipline is required.

## Revisit conditions

Team or operational requirements invalidate Python choice.
