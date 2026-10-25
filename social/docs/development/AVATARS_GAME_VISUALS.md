# Avatar and game visual acceptance

Recorded 2026-10-25. This note covers the accepted avatar/artwork feature, not a
production deployment or a new phase of the product.

## Owner acceptance

- GAME VISUALS: PASSED — OWNER VISUALLY VERIFIED.
- SMALL THUMBNAILS: PASSED — OWNER VISUALLY VERIFIED.
- AVATAR SYSTEM: PASSED — OWNER VERIFIED.

These are owner-reported acceptance statements. Automated upload/replace/remove,
privacy and fallback tests below are separate evidence; no extra real-account
manual actions or new live Steam synchronization are claimed for this closeout.

## Public candidate checks

All commands were executed from this public candidate, using empty live Steam
credentials and isolated test fixtures. No real development database was reset.

| Check | Actual final result |
| --- | --- |
| `uv sync --frozen` | exit 0 |
| `ruff format --check .`, `ruff check .`, `mypy src` | exit 0 each |
| `alembic upgrade head`, `alembic check` | exit 0 each |
| `pytest -q` with real isolated PostgreSQL/Redis | exit 0, 345 passed |
| Worker `--check` | exit 0 |
| OpenAPI and TypeScript contract regeneration | exit 0, outputs match accepted contracts |
| `npm ci --ignore-scripts` | exit 0, lockfile unchanged |
| Frontend format, lint and typecheck | exit 0 each |
| `npm run test` | exit 0, 69 passed in 14 files |
| Combined authenticated and landing Playwright suites | exit 0, 38 passed |
| `npm run build` | exit 0 (Windows); Linux image build also exit 0 |
| `npm audit --json` | exit 0, zero findings including development dependencies |
| `npm audit --omit=dev --json` | exit 0, zero findings |
| Targeted private-data review and Gitleaks | passed; no identified leaks |
| Separate local Compose runtime | builds, migration, five healthy services and storage round-trip passed |

The additive migration is `0006_game_visuals_avatars`, following
`0005_phase6_chat`. Tests cover a fresh database to head and upgrading an existing
accepted schema with synthetic identity, session and imported data retained.
Downgrade with active avatar references is refused. An independent empty Compose
database also migrated to head with no schema drift. Temporary review containers
were stopped afterward; named volumes and the real local application's data were
preserved.

Earlier failures were retained in private command evidence: restricted-network
build dependency lookup; Docker build-cache access; a Windows standalone-output
EPERM; and the Windows repository checker using the default GBK decoder. Network/
filesystem permissions and explicit `python -X utf8` resolved those checks. An
initial public preview test failed because copied local sample labels differed
from the approved fictional public preview; preserving the existing public
preview and adapting only feature fixtures fixed it. No tests were removed.
An initial browser invocation completed its 38 assertions but stalled while
stopping the Windows test servers; it was terminated and is not counted as a
passing run. The complete suite was rerun with process permissions and exit 0.
The backend suite emits one existing Starlette/httpx deprecation warning.

## Publication and boundaries

The public source retains the approved fictional preview assets and synthetic
screenshots. No owner screenshot, uploaded avatar, commercial-art cache, raw Steam
response, local environment or private command report is published. AppID artwork
URLs resolve at runtime on the approved official hosts. Local filesystem avatar
storage remains development-oriented; managed object storage and operational
hardening require a separate deployment review.

Remote results are tied to the exact feature/merge commit in
[GitHub Actions](https://github.com/huakai531/SteamScope/actions/workflows/social-ci.yml).
This local result is not a substitute for required PR checks or post-merge main CI.
Public deployment is not executed. Phase 7 is not started. No security exception
is reopened or extended; the two audits above have zero findings.

[Avatar storage and authorization](../security/AVATAR_STORAGE.md) ·
[Game visual strategy](../architecture/GAME_VISUALS.md)
