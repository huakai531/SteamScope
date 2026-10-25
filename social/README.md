# SteamScope application

The application lives in this directory to keep Compose, migrations, CI and test paths consistent.

[Project overview and screenshots](../README.md) · [Local development](docs/operations/DEVELOPMENT.md) · [Validation](docs/development/VALIDATION.md) · [Steam operations](docs/operations/STEAM_SYNC.md)

- `backend/`: API, Worker, domain modules, migrations and tests.
- `frontend/`: UI, same-origin proxy, generated types and tests.
- `infra/`: Dockerfiles and isolated test-database initialization.
- `scripts/`: development helpers and repository checks.
- `docs/`: architecture, contracts, security and portfolio documentation.

Do not copy a real `.env` into Git. Optional Steam imports require explicit owner action; routine browsing and automated tests do not call Steam.

## Game visuals and platform avatars

Authorized saved games use one visual model for official Steam artwork and icon
fallbacks. Browsers load remote CDN images; this does not trigger Steam Web API
synchronization. See [game visuals](docs/architecture/GAME_VISUALS.md).

Account → Profile → Change avatar previews a PNG/JPEG/WebP before explicit save.
Uploads are normalized to 256×256 WebP, separate from Steam identity, and obey
profile visibility on every read. API and Worker share the private `avatar_data`
volume; never publish it or delete volumes to upgrade. Apply migration
`0006_game_visuals_avatars` before starting the updated services. See
[storage, cleanup and local checks](docs/security/AVATAR_STORAGE.md).
