# GitHub public-source settings plan

**Planning only — no repository created, settings changed, secrets configured or push performed.** Reviewed 2026-10-24. Public source is distinct from a public live service.

The owner approved Option B, clean history and MIT for the local candidate. After a separate explicit remote-publication approval:

- [ ] Create the approved `SteamScope` source repository with public visibility and default branch `main`.
- [ ] Enable/verify secret scanning and push protection. Review any alerts before inviting contributions; do not bypass a real credential finding.
- [ ] Enable Dependabot alerts. Enable security-update PRs where supported; review them and rerun tests before merging. No automatic acceptance of updates.
- [ ] Enable private vulnerability reporting under Security. Verify that **Report a vulnerability** is available before advertising it as an active channel.
- [ ] Set Actions default workflow permissions to read repository contents; do not allow Actions to create/approve PRs.
- [ ] Restrict allowed actions to approved publishers and the reviewed SHA-pinned actions. Review upstream updates explicitly.
- [ ] Require approval for **all outside collaborators' fork workflow runs**, not only first-time contributors. Use disposable GitHub-hosted runners; no self-hosted runners for untrusted PRs.
- [ ] Do not enable write tokens or repository/environment secrets for fork PRs. Keep `pull_request_target` and privileged artifact-driven execution out of these tests.
- [ ] Require a PR and review for `main`, prohibit force-push/deletion, and resolve review conversations. Add only the status-check names actually observed after the first successful CI run; do not invent a green required check now.
- [ ] Keep Issues enabled for non-sensitive bugs; direct security details to private reporting. Discussions are optional and can remain disabled.
- [ ] Confirm no deployment environments, credentials, public tunnels or live hosting are created by source publication.

The workflow retains `contents: read`, SHA-pinned actions, checkout without persisted credentials, lockfile installs, isolated PostgreSQL/Redis, no real Steam key, and fixture provider responses. Its only uploaded artifacts are npm audit JSON with seven-day retention; no environment, browser traces, screenshots, chat history or database exports are uploaded.

**CI PUBLIC SAFETY: READY** for the proposed retained `social/` layout and reviewed code. **REMOTE CI: READY TO EXECUTE AFTER PUBLICATION; execution status NOT EXECUTED.** Confirm runner/version availability on the first actual run; local checks do not prove GitHub-hosted execution.

Official references: [GitHub Actions secure use](https://docs.github.com/en/actions/reference/security/secure-use), [secret scanning](https://docs.github.com/en/code-security/secret-scanning/introduction/about-secret-scanning), [private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/working-with-repository-security-advisories/configuring-private-vulnerability-reporting-for-a-repository), [approving fork workflow runs](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/approve-runs-from-forks).

## Suggested repository metadata

Name: **SteamScope**. Recommend **A** for clear product scope:

A. A Steam-data-driven social platform for player profiles, discovery, connections, and real-time chat.

B. Turn Steam gaming history into player identity, discovery, and real-time social connections.

C. A privacy-aware Steam social platform built with FastAPI, Next.js, PostgreSQL, Redis, and WebSockets.

Topics: `steam`, `gaming`, `social-network`, `fastapi`, `nextjs`, `postgresql`, `redis`, `websocket`, `typescript`, `python`.

No public email is proposed. A Code of Conduct is optional for this individual portfolio; add one if a contributor community develops. `CONTRIBUTING.md` provides lightweight expectations now.
