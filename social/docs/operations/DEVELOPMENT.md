# Local development and validation

[Project overview](../../README.md) · [Steam operations](STEAM_SYNC.md) · [Validation summary](../development/VALIDATION.md)

This is the canonical setup guide for the implementation in `social/`. The parent project is historical and uses separate code/data. The commands below are instructions for future development, not commands executed by the documentation packaging task.

## Prerequisites and working directory

Use PowerShell with Git, Docker Compose v2, Python, uv, Node and npm on PATH. The accepted local environment used Python 3.12.14, uv 0.13.5 and Node 24.19.0 with Docker Desktop Linux containers. Package constraints allow Python `>=3.12,<3.14` and Node `>=22.14,<25`; these ranges do not claim every combination was tested.

From the repository root:

```powershell
Set-Location social
docker context show
docker version
```

On the accepted Windows setup, the context is `desktop-linux`; verify the intended local engine before running Compose. Do not switch to a remote Docker context. All following commands assume the `social/` directory unless stated otherwise.

## First setup and private configuration

```powershell
.\scripts\dev.ps1 -Task setup
```

The script copies `.env.example` only when `.env` is absent, then installs backend/frontend dependencies from their lockfiles. It preserves an existing `.env`. Do not copy the legacy environment or delete a lockfile to resolve installation errors.

Before the **first startup of a new local database**, privately review the new `.env` using the [example's field definitions](../../.env.example):

| Setting                              | Required local relationship                                                                                                          |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------ |
| `POSTGRES_USER`, `POSTGRES_PASSWORD` | Credentials for this isolated social PostgreSQL instance; replace example credentials before initialization                          |
| `SOCIAL_DATABASE_URL`                | Native async PostgreSQL connection to the same role, matching password and local host port; database exactly `steamscope_social_dev` |
| `SOCIAL_REDIS_URL`                   | Native connection to the isolated Redis host port, database 0 for development                                                        |
| `SOCIAL_BROWSER_ORIGIN`              | Canonical local origin `http://127.0.0.1:3100`                                                                                       |
| `SOCIAL_COOKIE_SECURE`               | `false` only for the permitted loopback HTTP development setup                                                                       |
| `SOCIAL_STEAM_API_KEY`               | Optional server-only configuration for owner-requested data sync; not needed for OpenID login or health checks                       |
| `NEXT_TELEMETRY_DISABLED`            | Keep `1` on its own line                                                                                                             |

Use a private editor, not command-line arguments or screenshots, for secrets. Preserve an existing configured environment. Changing `POSTGRES_PASSWORD` alone does not rotate an already initialized database role; do not overwrite working credentials or remove its volume. Actual rotation is a separate coordinated database/environment operation.

Compose supplies container connection settings and injects the Steam key only into API/Worker at runtime. Native processes use `SOCIAL_DATABASE_URL` and `SOCIAL_REDIS_URL` from the social environment. The frontend must never receive the key or database credentials. [Key operations and diagnostics](STEAM_SYNC.md)

## Start the five-service stack

```powershell
docker compose --env-file .env config --quiet
.\scripts\dev.ps1 -Task up
docker compose --env-file .env ps
docker compose --env-file .env exec -T api alembic current
docker compose --env-file .env exec -T api alembic check
docker compose --env-file .env exec -T worker python -m steamscope_social.worker --check
Invoke-RestMethod http://127.0.0.1:8100/health/ready
Invoke-RestMethod http://127.0.0.1:3100/api/status
```

`up` builds and waits for five healthy services, then explicitly runs `alembic upgrade head` in the API container. Application startup itself does not migrate. Current accepted head is `0005_phase6_chat`; migrations are additive. For a future migration on an existing stack, follow the [migration procedure](../database/MIGRATIONS.md) rather than assuming readiness proves schema compatibility.

Open **http://127.0.0.1:3100/**. Browser account calls use `/api/v1` on that same origin. Steam's callback path is `/api/v1/auth/steam/callback`; generated authentication parameters must never be copied into reports. Do not mix `localhost` with `127.0.0.1`.

| Service    | Default host access |
| ---------- | ------------------- |
| Frontend   | `127.0.0.1:3100`    |
| API        | `127.0.0.1:8100`    |
| PostgreSQL | `127.0.0.1:55433`   |
| Redis      | `127.0.0.1:56379`   |
| Worker     | No published port   |

Check occupied ports without terminating unrelated processes. A deliberate port change requires updating corresponding native connections and the canonical browser origin. Compose uses `http://api:8000` for its frontend's server-only API target; that container name is not a browser URL. Forwarded headers never select the trusted origin.

To stop while keeping the existing containers/volumes:

```powershell
docker compose --env-file .env stop
```

Do not use `down -v`, remove database directories, or flush Redis. PostgreSQL uses a named data volume; Redis persistence is disabled, but its existing image-created `/data` volume is still not a disposable target for verification. A separate exploratory native PostgreSQL cluster must not compete for the same host port.

## Native edit-and-run workflow

With isolated PostgreSQL/Redis already available and native connection settings correct:

```powershell
.\scripts\dev.ps1 -Task migrate
```

Use separate PowerShell terminals in `social/` for `-Task api`, `-Task frontend` and `-Task worker`. Do not run native API/frontend concurrently on ports already occupied by the Compose equivalents. The native frontend uses server-only `INTERNAL_API_URL` (default `http://127.0.0.1:8100`) and `BROWSER_ORIGIN` (default `http://127.0.0.1:3100`), supplied through process environment or ignored `frontend/.env.local` when customized.

The existing `SOCIAL_CORS_ORIGINS` field remains for compatibility; account operations use one canonical origin and same-origin browser writes. Secure cookies and HTTPS require a separately configured deployment, not a public use of these loopback instructions.

## Local checks without integration data

```powershell
.\scripts\dev.ps1 -Task validate
.\scripts\dev.ps1 -Task types
uv run --frozen --project backend python -X utf8 scripts/check_repository.py
```

`validate` checks the development helper, formatting, lint, types, non-integration backend tests, frontend unit tests and build. It does not run the complete real-service suite. `types` regenerates OpenAPI and frontend contracts; inspect its diff when a contract changes.

From `frontend/`, run both audits independently and retain each exit code, including nonzero JSON:

```powershell
npm audit --include=dev --json
npm audit --omit=dev --json
```

The 2026-10-24 full and production audits both returned exit 0 with zero findings. The original braces dependency path remains, but the upstream advisory was withdrawn; the [current security record](../security/CURRENT_SECURITY_STATUS.md) explains closure of that exception. Historical failures and its original **2026-11-05 00:00 America/Los_Angeles** deadline remain recorded privately. Production-only success never replaces the full audit, and the former exception does not authorize unreviewed external-code CI or cover another advisory.

## Isolated real-service and browser tests

Use a separate terminal/process environment, privately supplying the following test settings; do not rewrite development `.env` or print credentials. The database connection uses the isolated social server/role but the **test database name**, with no query parameters.

| Process setting          | Test value / constraint                                                           |
| ------------------------ | --------------------------------------------------------------------------------- |
| `SOCIAL_ENVIRONMENT`     | `test`                                                                            |
| `SOCIAL_DATABASE_URL`    | Private async connection to exactly `steamscope_social_test`                      |
| `SOCIAL_REDIS_URL`       | Isolated Redis, database **1**                                                    |
| `SOCIAL_REDIS_NAMESPACE` | Dedicated test namespace; browser harness additionally creates a random namespace |
| `SOCIAL_INTEGRATION`     | `1`                                                                               |
| `SOCIAL_STEAM_API_KEY`   | Empty; automated providers use fixtures, never a live key                         |

The first creation of the Compose PostgreSQL volume initializes `steamscope_social_test`. That initialization does not rerun on an existing volume. If the test database is missing, have it created on this isolated server; do not reset the server/volume to rerun initialization. Settings reject database names outside the environment allowlist.

Run sequentially, preserving the caller's environment or closing only the dedicated test terminal afterward:

```powershell
# From social/backend, in the already configured test-only environment:
uv run --frozen alembic upgrade head
uv run --frozen pytest -q

# Then from social/frontend, preserving the same test-only environment:
npm exec playwright install chromium
npm run build
npm run test:e2e:auth
# Also run cleanup if the browser command fails or Windows force-stops its server:
uv run --frozen --project ../backend python ../backend/tests/browser_cleanup.py
```

The browser harness uses API 8200/frontend 3200, normal isolated sessions and deterministic provider responses. It refuses pre-existing fixture identities, exposes no authentication bypass endpoint, and is excluded from production images. Cleanup targets owned fixture rows/namespaces, not all test data or shared Redis keys. Do not run browser and backend mutation suites concurrently against the same test database.

The independent landing-page suite (`npm run test:e2e` from `frontend/`) can use the running local frontend. It is separate from the full authenticated browser suite and must not be added to its count without explanation.

Migration round-trip tests use only `steamscope_social_migration_test`, require that database to be empty and unrelated data to be absent, and need permission to create it when missing. A restricted test runner may provision the empty database first. Development and main test databases remain upgrade-only; a nonempty Phase 6 downgrade is refused.

## Build evidence and historical boundary

The 2026-10-24 UI freeze passed the default Windows Turbopack build; it did not rebuild the running Docker image.

A historical Phase 6 Windows default Turbopack build failed because a PostCSS child process exited before IPC initialization. Windows webpack and Linux Docker's default build passed. If reproducing that same limitation, from `frontend/` use `npm run build -- --webpack` and record it as the alternative build, retaining the original failure. Do not alter the package script, suppress a failing check, or claim every platform passed. Next's current lint toolchain remains pinned compatibly; dependency upgrades require their own review.

## Health, data access and evidence boundaries

| Signal                  | Proves                                        | Does not prove                                |
| ----------------------- | --------------------------------------------- | --------------------------------------------- |
| `/health/live` 200      | API process responds                          | Database/Redis availability                   |
| `/health/ready` 200     | Bounded PostgreSQL and Redis checks succeeded | Migration head or Steam data availability     |
| Worker `--check` exit 0 | The check process reached its dependencies    | A daemon processed a particular job           |
| Worker running          | The process is active                         | A specific resource synchronized successfully |
| Frontend page 200       | Rendering is available                        | All protected API operations work             |
| Static checks           | Expected repository/config structure          | Image, runtime or live-user acceptance        |

The Worker now claims durable Steam jobs; Redis Pub/Sub/presence/typing are implemented chat capabilities, not future placeholders. Profile, social and chat browsing do not enqueue Steam synchronization. Verify individual existing job outcomes when diagnosing imports; never trigger a new live call just to inspect status.

Account routes include `/account/profile`, `/account/privacy`, `/account/sessions` and `/account/delete`. Deletion requires the literal confirmation and recent authentication; Steam-data clearing has different effects. Use the [erasure policy](../security/DATA_RETENTION_AND_DELETION.md) before either action. The explicit retention command is `uv run --frozen --project backend python -m steamscope_social.modules.administration.cleanup`; it mutates expired records and is **not** a health/demo check. No automatic maintenance schedule is installed.

Do not print full Compose interpolation, container environments, `.env`, credential-bearing URLs or raw provider/chat payloads. HTTP client/access logging is restricted by the application. Report unit, real-service, browser, runtime and live-user evidence separately; a weaker layer does not prove a stronger one.

The [public validation summary](../development/VALIDATION.md) separates current UI checks from historical backend/live acceptance. Detailed original command/phase evidence is retained privately. Actual remote runs are linked in that summary; public deployment is not authorized.
