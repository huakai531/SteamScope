# Security policy

SteamScope is a **local portfolio MVP**. Production deployment and hardening are planned; running the supplied development stack as a public service is not supported. Publishing source does not authorize or validate a public live service.

## Scope

The current maintained implementation is `social/`: identity and sessions, Steam import boundaries, resource authorization, social relationships, blocking, and persistent direct chat. The earlier implementation outside `social/` is historical and is not supported for deployment. There is no production support SLA or guarantee of response time.

## Reporting a vulnerability

If this repository has GitHub private vulnerability reporting enabled, use **Security → Report a vulnerability**. Include the affected revision, a concise impact description, and reproduction steps using synthetic data.

Do **not** include passwords, API keys, cookies, authentication callback parameters, account identifiers, private messages, database dumps, or raw HAR files in public issues or pull requests. If private reporting is unavailable, open a non-sensitive issue asking the maintainer for a private reporting channel; wait before sharing details. No private email is designated for publication.

Use your own isolated local instance. Do not test against other users, third-party services, or real Steam accounts without permission. Report exposed credentials privately; revoke/rotate them and decide how to remediate any affected history before release.

## Development boundaries

- Keep `.env` private. The example contains placeholders; configure your own credentials before initializing a database.
- Steam Web API keys belong only in API/Worker runtime configuration, never browser variables or images.
- Automated checks use isolated PostgreSQL/Redis and fixture Steam responses, without real Steam credentials.
- Dependency and source scans have finite coverage. Current results and limitations are described in `social/docs/security/CURRENT_SECURITY_STATUS.md`.

SteamScope is independent of Valve and Steam, with no affiliation or endorsement. Source privacy restrictions remain authoritative.
