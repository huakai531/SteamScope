# Current security status

Checked **2026-10-24 America/Los_Angeles**. SteamScope is a local portfolio MVP; production hardening/deployment are planned.

## Dependencies

| Check | Exit | Current result |
| --- | ---: | --- |
| `npm audit --include=dev --json` | 0 | 0 findings |
| `npm audit --omit=dev --json` | 0 | 0 findings |
| `npm ls braces --all` | 0 | One dev-only path, below |
| `npm explain braces` | 0 | Same path |

`eslint-config-next@16.4.2 → @next/eslint-plugin-next@16.4.2 → fast-glob@3.3.1 → micromatch@4.0.8 → braces@3.0.3`.

**PREVIOUS SECURITY EXCEPTION: RESOLVED IN CURRENT DEPENDENCY STATE.**

The dependency path still exists; no package upgrade removed it. [GHSA-vfj7-8cjw-p6xm / CVE-2026-93687](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm) was withdrawn by the GitHub Advisory Database on **2026-10-23**, with the stated reason that it was not practically exploitable. This independently explains why the current registry no longer reports it. It is not a claim of a newly patched braces version.

Historical full-audit exit 1 / five high package entries remain historical evidence. The former local exception was approved 2026-10-22 and originally expired **2026-11-05 00:00 America/Los_Angeles**; closure on 2026-10-24 does not extend or reuse it for another issue. Re-evaluate any new advisory or dependency change. A zero npm result is not a complete security audit; backend dependency auditing and production hardening are separate work.

## Release boundaries

This separate candidate excludes private operational history, obsolete identity captures and commercial game art. Original demo SVGs and declared synthetic screenshots are included instead. Candidate-specific scan and test evidence is summarized in [validation](../development/VALIDATION.md).

**REMOTE CI: NOT EXECUTED.** The workflow uses isolated services and fixture Steam with no real API key. Local source-candidate preparation is separate from production deployment, which remains unsupported and unapproved. The original historical audit records remain in the private development archive.
