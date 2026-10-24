# GitHub public-source security

Published on **2026-10-24** to [huakai531/SteamScope](https://github.com/huakai531/SteamScope), following explicit owner authorization. The source is public; the web application is not publicly deployed.

## Verified repository settings

- Public visibility; default branch `main`; MIT license; reviewed description and ten relevant topics.
- Secret scanning and push protection enabled. Open secret-scanning alerts: zero at publication review; new alerts require triage, never automatic dismissal.
- Dependabot alerts and security updates enabled. No broad version-update schedule was added.
- Private vulnerability reporting enabled through GitHub.
- Actions defaults to read-only and cannot approve pull requests. All outside contributors' fork runs require approval.
- Only the four reviewed, exact SHA-pinned Actions are allowed; no blanket publisher or GitHub-owned action allowance.
- No Actions secrets or application deployment credentials were added. Issues remain for non-sensitive bugs.

## Main-branch maintenance policy

After actual successful checks on the latest publication commit, main is to require a pull request, up-to-date `backend`, `frontend`, `compose` and `dependency-audit` checks, and resolved conversations. Force pushes and deletion are prohibited. The solo maintainer does not need a second person's approval: the approval count is zero. Administrator enforcement is intended; no custom bypass is authorized. The GitHub branch-protection settings are the authoritative current state.

## CI boundary

[The publication validation run](https://github.com/huakai531/SteamScope/actions/runs/40084501360) passed. The [validation record](../development/VALIDATION.md) preserves initial failures, focused fixes and actual counts. Check Actions for any later commit rather than assuming this run covers it.

The workflow uses `contents: read`, SHA-pinned actions, checkout without persisted credentials, locked installs, isolated PostgreSQL/Redis, no real Steam key and fixture provider responses. Its only uploaded artifacts are npm audit JSON with seven-day retention; no environment files, traces, screenshots, chat history or database exports are uploaded. Never enable privileged `pull_request_target` execution for untrusted code.

Official references: [GitHub Actions secure use](https://docs.github.com/en/actions/reference/security/secure-use), [secret scanning](https://docs.github.com/en/code-security/secret-scanning/introduction/about-secret-scanning), [private reporting](https://docs.github.com/en/code-security/security-advisories/working-with-repository-security-advisories/configuring-private-vulnerability-reporting-for-a-repository).

**Public production deployment remains unapproved.** Production hardening is separate work.
