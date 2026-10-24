# Scope and phase gates

| Phase | Scope | Current state |
|---|---|---|
| 1 | Product contract, data/architecture design, API/web/worker foundation, PostgreSQL/Redis, migrations, checks and CI | Implemented; see actual validation report |
| 2 | Steam OpenID, UUID users, unique Steam identity, sessions, settings, privacy, deletion and account audit | Planned |
| 3 | Public Steam summaries, libraries, recent play, friends, selected achievements and durable sync jobs | Planned |
| 4 | Privacy-filtered profile/library/achievement UI and player comparison | Planned |
| 5 | Discovery, explainable player matching, accepted platform connections, blocks, reports and notifications | Planned |
| 6 | Persistent one-to-one text chat, authenticated WebSocket, read/unread, presence, typing, reconnect and deletion | Planned; MVP endpoint |
| 7 | Communities, posts/comments/reactions, following, LFG, applications, temporary group chat, moderation | Post-MVP |
| 8 | Production security/performance/operations, deployment, recovery, analytics and portfolio demo | Post-MVP strengthening |

Phase 1 has no auth callbacks, user tables, sessions/cookies, Steam client, job handlers,
library, discovery, social, block, report, notification, messaging or WebSocket behavior.
The worker only verifies dependencies and waits for shutdown. Health describes infrastructure,
not availability of future product features. Future diagrams and table designs are plans.

Excluded from Phases 1–6: purchases, prices, news, inventory/trading/marketplace,
voice/video, files/images, large groups, native mobile apps, other gaming platforms,
Steam private messages, ML/AI chat, cryptocurrency, microservices, Kubernetes,
complex event-driven infrastructure and paid subscriptions.

Each phase requires implementation, migration where relevant, meaningful executed tests,
lint/types, updated traceability, exact file/command evidence and limitations. Environment
blocks remain incomplete gates. Stop at the requested phase; do not auto-start the next.
