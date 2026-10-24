# SteamScope product contract

Status: accepted rebuild direction; only Phase 1 foundation is implemented.

## Vision and problem
Players can see a name or avatar without knowing whether another person shares
their games, recent interests or preferred way to play. SteamScope will connect
verified Steam identity with public gaming context and consent-based social interaction.
The target users are Steam players seeking compatible people, returning players
reconnecting through common games, and small groups forming around a game.
The professor/demo audience evaluates an independently reproducible engineering project.

## Value proposition and primary journey
Steam sign-in → public data synchronization → complete profile → inspect games and
achievements → discover another player → compare mutual games → request connection
→ recipient accepts → persistent one-to-one text conversation. This entire loop,
including privacy, blocking and deletion, defines the MVP at the end of Phase 6.
SteamScope is an independent project, not affiliated with or endorsed by Valve Corporation.

## Success criteria
1. Two distinct test users complete the full journey without operator database edits.
2. Private source data, hidden platform fields and blocked users do not leak through
   profiles, counts, comparison, search, explanations, notifications or presence.
3. Retried synchronization and chat submission produce one logical result.
4. A worker crash or realtime disconnect does not lose durable work or message history.
5. Every implemented requirement maps to actual automated checks and recorded results.
6. A clean developer setup follows the documented PowerShell or CI commands.
Performance targets are provisional engineering budgets in the NFR document,
not measured performance claims. No engagement or user-count claims exist yet.

## Risks and assumptions
Steam source visibility changes independently of SteamScope. An authenticated user
may have no accessible library. Selected-game achievements are bounded, not a full-library
fan-out. Player matching starts as explainable deterministic rules, not learned inference.
The first release serves desktop and mobile browsers; hosting region, moderation staffing
and production capacity will be selected before public deployment. No migration of old
demo/imported users into verified accounts is assumed. See MVP_SCOPE and the threat model.
