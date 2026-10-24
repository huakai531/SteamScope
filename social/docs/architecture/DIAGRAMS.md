# Architecture diagrams

Only foundation components currently run. All business sequences are planned.

## 1. System context

```mermaid
flowchart LR
  Player[Player browser] --> Site[SteamScope]
  Site --> OpenID[Steam OpenID - planned P2]
  Site --> Steam[Steam Web API - planned P3]
  Moderator[Moderator - planned] --> Site
```

## 2. Components

```mermaid
flowchart LR
  Browser --> Next[Next.js shell and fixed status proxy]
  Next --> API[FastAPI modular monolith]
  API --> PG[(PostgreSQL durable data)]
  API --> Redis[(Redis transient state)]
  Worker[Shared-package worker] --> PG
  Worker --> Redis
  Worker -. planned P3 .-> Steam[Steam API]
```

## 3. Steam login - planned P2

```mermaid
sequenceDiagram
  actor User
  participant Web
  participant API
  participant Steam
  participant DB
  User->>Web: Sign in
  Web->>API: Begin login
  API-->>Web: Bound return target and nonce
  Web->>Steam: Provider login page
  Steam-->>API: OpenID callback
  API->>Steam: Verify assertion
  API->>API: Verify endpoint, return_to, nonce, claimed ID
  API->>DB: Transactional unique identity and session
  API-->>Web: Rotated secure session cookie
  Note over API,Steam: Identity verification grants no private-data access
```

## 4. Initial synchronization - planned P3

```mermaid
sequenceDiagram
  participant API
  participant PG
  participant Worker
  participant Steam
  API->>PG: Insert deduplicated resource jobs
  Worker->>PG: Claim with lease and ownership token
  Worker->>Steam: Fetch outside transaction
  Steam-->>Worker: Accessible data or resource failure
  Worker->>Worker: Validate and normalize
  Worker->>PG: Check account generation and lease; atomic upsert
  Worker->>PG: Record per-resource run outcome
  API->>PG: Read partial status and freshness
```

## 5. Achievements - planned P3

```mermaid
sequenceDiagram
  actor User
  participant API
  participant Worker
  participant Cache
  participant Steam
  User->>API: Select bounded game set
  API->>Worker: Persisted jobs via PostgreSQL
  Worker->>Cache: Check per-app schema freshness
  alt Schema missing or stale
    Worker->>Steam: GetSchemaForGame
    Worker->>Cache: Validated definitions and icons
  end
  Worker->>Steam: GetPlayerAchievements
  Worker->>Worker: Distinguish private, unsupported, unavailable
  Worker->>Cache: Upsert authorized player observations
```

## 6. Connection requests - planned P5

```mermaid
sequenceDiagram
  actor Sender
  participant API
  participant PG
  actor Recipient
  Sender->>API: Request connection
  API->>PG: Check actor, privacy, either-direction blocks
  API->>PG: Insert unique active canonical pair
  Recipient->>API: Accept request
  API->>PG: Lock request; recheck policy and recipient
  API->>PG: Accept and insert symmetric connection atomically
  API->>PG: Idempotent recipient notification
```

## 7. WebSocket message - planned P6

```mermaid
sequenceDiagram
  participant Browser
  participant API
  participant PG
  participant Redis
  participant PeerAPI
  Browser->>API: Session-authenticated socket and allowed Origin
  Browser->>API: Send text with client message ID
  API->>PG: Check membership, connection, blocks and active session
  API->>PG: Commit unique message or return existing result
  API-->>Browser: Durable message acknowledgement
  API->>Redis: Best-effort event with durable message ID
  Redis-->>PeerAPI: Fan out
  Browser->>API: Reconnect with history cursor
  API->>PG: Fetch authorized missing messages
```

## 8. Blocking - planned P5/P6

```mermaid
sequenceDiagram
  actor User
  participant API
  participant PG
  participant Cache
  participant Socket
  User->>API: Block another user
  API->>PG: Commit directional block and cancel pending requests
  API->>Cache: Invalidate discovery and policy caches
  API->>Socket: Revoke interaction and presence subscriptions
  Socket->>PG: Recheck policy on next protected event
  Note over API,PG: Either direction blocks applicable interaction; unblock does not auto-restore requests
```
