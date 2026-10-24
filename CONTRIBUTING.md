# Contributing

SteamScope is an individual portfolio project. Small, reviewable improvements and reproducible bug reports are welcome once the repository is published.

1. Follow `social/docs/operations/DEVELOPMENT.md` for local setup. Keep credentials in ignored environment files and use the isolated test database.
2. Use a descriptive branch such as `fix/chat-focus` or `docs/setup`. Preserve lockfiles and migrations.
3. Describe the problem, resulting behavior, and commands actually run. Separate automated checks from manual observations.
4. Run frontend format, lint, typecheck, unit/browser tests and build for affected changes; run backend checks when backend code changes. Use fixture Steam responses for automated tests.
5. Respect the frozen UI baseline in `social/docs/portfolio/UI_FREEZE.md`. Structural UI work and additional scope need an explicit discussion.

Do not submit secrets, personal account data, private conversations, unreviewed captures, or assets whose redistribution rights are unclear. Follow `SECURITY.md` for vulnerability reports. Never rely on a public issue to send confidential evidence.

There is no requirement to contact a second real Steam user or make live Steam requests for a pull request. Public deployment is outside the current supported scope.
