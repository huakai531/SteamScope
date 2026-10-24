# Phase 3A/3B Worker and private key operations

Canonical local UI: http://127.0.0.1:3100/account/steam. API is internal to the same-origin proxy;
browser requests must not use container DNS `api:8000`. Only the linked owner can enqueue/read.

`SOCIAL_STEAM_API_KEY` is a server-side **standard user** Web API key configured once by the project
owner. It is optional: blank/invalid syntax reports safe unconfigured capability and refuses new
jobs. OpenID and /health/live,/health/ready,/api/status do not require it. A well-formed but revoked
key may yield endpoint-specific unavailable outcomes; the application does not infer invalid key
from every 401/403. Fix configuration privately and make a new bounded request after cooldown.

The API receives the key only to validate capability; the Worker uses it for HTTP. Compose injects
it at runtime into those two services only. It is never a build argument, frontend environment,
job payload, database field or log value. No code copies the legacy .env or contacts live Steam
with a dummy test key. Test environments reject live transport outright.

From a PowerShell terminal, use the existing social directory:

```powershell
Set-Location social
notepad.exe .env
# Add/replace SOCIAL_STEAM_API_KEY privately in the editor; save and close.
# Do not paste the value into terminal commands, chat, git, screenshots or logs.
docker --context desktop-linux compose --env-file .env --project-name steamscope-social-dev config --quiet
docker --context desktop-linux compose --env-file .env --project-name steamscope-social-dev up -d --no-deps --force-recreate api worker
docker --context desktop-linux compose --env-file .env --project-name steamscope-social-dev exec -T worker python -m steamscope_social.worker --check
```

Do not run unfiltered `compose config`, `docker inspect` environment output, `Get-Content .env`,
debug HTTP logging or raw authenticated access logging. Normal logging disables HTTPX/httpcore
and uvicorn access logs; upstream failures become fixed safe codes, never stringified exceptions.
The proxy logs no credential-bearing URLs. Do not share HAR, cookies or callback query strings.

Worker operations (same directory, same project):

```powershell
docker --context desktop-linux compose --env-file .env --project-name steamscope-social-dev ps
docker --context desktop-linux compose --env-file .env --project-name steamscope-social-dev logs --tail 40 worker
docker --context desktop-linux compose --env-file .env --project-name steamscope-social-dev restart worker
```

Use safe events and owner job status/runs to diagnose, not raw provider payloads. `--check` is a
dependency check, not proof a daemon processed a job. Actual interrupted-process recovery is tested
with an isolated synthetic provider. A hard-killed worker's unfinished resource is eligible after
lease expiry; no operator SQL reset is required. Graceful shutdown requeues interrupted work;
PostgreSQL/Redis recovery lets the resident worker resume. Never FLUSHALL/FLUSHDB or delete volumes.

Application limits and state machine: [ADR-0022](../adr/0022-steam-sync-leases-snapshots-limits.md).
Snapshot/privacy semantics: [source mapping](../architecture/STEAM_DATA_FLOW.md).
Runtime knobs are documented in .env.example. All workers must use the same policy/configuration.
Public deployment, external-code CI, tunnels and broad account imports remain unauthorized.

## Phase 3B explicit actions and queue/cache policy

On `/account/steam`, **Sync my Steam data** still imports only profile/library/recent. Select one
eligible game from the displayed library page and click **Sync selected game achievements**; use
**Sync my Steam friends** separately. Opening/refreshing the page only reads PostgreSQL. Do not
use diagnostic commands to enqueue live jobs; the owner controls the first real calls.

Scopes are base/0, achievements/app_id, friends/0. One active compatible request is reused; at most
five active jobs per owner; 300s default cooldown per scope/app. Existing request budgets include
schema cache misses as well as player/friend calls. A cache hit does not spend a Steam call.
`SOCIAL_STEAM_SCHEMA_TTL_SECONDS` defaults to 86400 (allowed 60..604800); English only. Shared schema
refresh has a 30s lease and minimum 60s failed-refresh pause; other jobs defer rather than stampede.
Schema/player outcomes remain independent; partial/mismatch is not full success. Retry/lease expiry,
worker interruption and clear/delete fencing use the existing PostgreSQL machinery.

Friend source exposure expires after 15 minutes. Achievement stale player/schema state suppresses
exact percentage; last success is not advanced by errors. Investigate safe task outcomes and resource
codes, never raw payloads or complete real friend lists. The current fixture-only test helpers are
excluded from normal images. See ADR 0023 and the manual 3B checklist for bounded owner validation.

## Phase 3B access-denied diagnosis (2026-10-22)

New runs retain bounded allowlisted response facts in existing `steam_sync_runs.outcomes` under
resource.http_status/content_type/body/business_success/business_error. Old runs lack these fields;
absence is not proof of a status or business error. Content type excludes parameters; unknown error
strings become UNRECOGNIZED, never raw provider text. Cache hits make no HTTP call and have no response
metadata. Read owner job detail to inspect existing results; never enqueue work to gather diagnostics
without the owner's explicit action. A 401/403 alone does not establish privacy. Header authentication
is officially supported and remains outside request URLs. No schema migration is needed.

## Phase 3C verified job/recovery boundary

The integrated local run re-executes duplicate-click/cooldown, two-claimer, independent process-kill,
lease recovery/stale token, graceful cancellation, 429/5xx/Retry-After, durable quota and bounded
permanent-failure tests. All three scopes retain independent run history and resource outcomes.
Full-resource clear/delete tests now start with all personal imports, block an achievement HTTP
response, queue base/friend work, erase, then release the response and verify no resurrection.

Actual local PG and Redis interruption checks preserve volumes and accepted rows. Readiness/status
return 503 while liveness stays 200; after restoration readiness returns 200 and --check exits 0.
The same resident worker survives both interruptions without restart. No live Steam job is enqueued.
Incomplete personal responses over saved snapshots are hidden as unknown and keep prior success
time/rows until a later complete observation. The [public validation summary](../development/VALIDATION.md) separates
these current checks from earlier real user observations and from NOT EXECUTED remote CI.
