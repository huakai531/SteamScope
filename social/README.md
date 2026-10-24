# SteamScope application

The application lives in this directory to keep Compose, migrations, CI and test paths consistent.

[Project overview and screenshots](../README.md) · [Local development](docs/operations/DEVELOPMENT.md) · [Validation](docs/development/VALIDATION.md) · [Steam operations](docs/operations/STEAM_SYNC.md)

- `backend/`: API, Worker, domain modules, migrations and tests.
- `frontend/`: UI, same-origin proxy, generated types and tests.
- `infra/`: Dockerfiles and isolated test-database initialization.
- `scripts/`: development helpers and repository checks.
- `docs/`: architecture, contracts, security and portfolio documentation.

Do not copy a real `.env` into Git. Optional Steam imports require explicit owner action; routine browsing and automated tests do not call Steam.
