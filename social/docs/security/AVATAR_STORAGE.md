# SteamScope avatar storage

The platform avatar is independent of Steam persona/avatar. Steam synchronization
and clearing imported Steam data never overwrite it. `users.avatar_key` is an
opaque generated `32-hex.webp` key; `avatar_updated_at` records a change. Binary
content, filenames and uploaded metadata are not stored in the users table.

## API and authorization

| Endpoint | Contract |
| --- | --- |
| `POST /api/v1/me/avatar` | Raw PNG/JPEG/WebP body; session, exact Origin, synchronizer CSRF and existing sensitive-action rate limit; returns AccountView |
| `DELETE /api/v1/me/avatar` | Same mutation checks; idempotent removal; returns fallback state |
| `GET /api/v1/users/{handle}/avatar/{key}` | Current authenticated viewer, active verified target, profile visibility and block checks; key must be the current active key |

No client-supplied owner ID is accepted. Public profiles mean visible to eligible
signed-in SteamScope viewers under the existing policy; avatar reads do not add
anonymous profile access. Directed connection consent that permits limited person
information does not override avatar privacy. Blocked-player DTOs expose no avatar.
Old, missing, unauthorized and replaced avatar URLs cannot retrieve an image.

Images are served as `image/webp`, `Cache-Control: no-store, private`, `nosniff`,
same-origin resource policy and restrictive content policy. The Next route copies
binary content through its explicit route allowlist; the upload limit is 5 MiB
only for this upload endpoint (other mutation bodies remain 16 KiB). The canonical
PlayerAvatar uses unoptimized same-origin image requests so session cookies reach
the authorization endpoint, rather than a public Next image optimizer cache.

## Validation and normalization

Both proxy and API enforce a 5 MiB input ceiling, including streamed bodies.
The API accepts only JPEG, PNG and WebP content matching the declared MIME, with
at most 16 million pixels and 8192 pixels per side. It rejects malformed/truncated
files, animation, SVG/GIF/HTML and detected appended container payloads. Extension
and client filename are never trusted. Re-encoding does not promise detection of
every possible polyglot; only freshly decoded pixels reach the served output.

Pillow verifies and fully decodes, applies EXIF orientation, center-crops to
256×256 RGB and re-encodes a new WebP image. Fresh pixel storage strips EXIF/GPS,
ICC, XMP and comments. Only normalized bytes are written; original uploads are not
retained. File readback is independently bounded at 256 KiB.
See Pillow's [image validation API](https://pillow.readthedocs.io/en/stable/reference/Image.html)
and [security guidance](https://pillow.readthedocs.io/en/stable/handbook/security.html).

## Storage, consistency and erasure

`AvatarStorage` has `put/read/delete`; the local adapter validates opaque keys,
rejects traversal/symlink paths and creates files exclusively. It flushes and
fsyncs before publishing the reference. File writing precedes the serialized user
transaction's reference switch; a failed upload leaves the prior reference active.
Concurrent replacements serialize on the existing account lock.

The same transaction enqueues the retired key in `avatar_deletions`. API cleanup
attempts after commit; the Worker retries batches of 20 each normal poll. An active
reference is checked again before deletion, including ambiguous commit failures.
On confirmed account deletion, the reference disappears atomically and its file
enters this durable deletion queue. Disk failures retain the queue for retry and
emit a generic warning. There is no guaranteed erasure deadline while storage or
the Worker is unavailable; monitor queue backlog. No account deletion was tested
against the owner's real account.

Files abandoned by a crash before a transaction can be reconciled explicitly:

```powershell
docker compose exec -T api python -m steamscope_social.modules.users.avatar_gc
```

This scans only the configured directory without recursion or following links,
queues up to 100 unreferenced opaque files older than 24 hours, then drains a batch.
Active references and recent in-flight files are preserved. This is mutating
maintenance, not a health check; no automatic orphan-maintenance schedule is
installed. A persisted reference to a missing disk file safely falls back in UI.

## Local configuration and deployment boundary

Default direct-run storage: `social/storage/{environment}/avatars/`.
Optional server-only setting: `SOCIAL_AVATAR_STORAGE_DIR`.
Compose API and Worker share `avatar_data` at `/app/storage/avatars`, owned by the
unprivileged application user. Frontend has no storage mount. The directory is
never mounted as static content; uploads are excluded by Git and Docker build
context rules. Integration tests use temporary isolated directories; browser tests
generate synthetic images in memory and use a temporary server directory.

Local filesystem storage is development-oriented. A future public deployment
should use managed object storage with a separately reviewed operational policy.
Do not copy real uploads, snapshots, environment files or data volumes into a
public repository. An object-storage adapter can implement the interface, but must
preserve per-read authorization and deletion retry semantics. Public buckets,
long-lived public URLs, cloud storage and production deployment are not implemented.

## Owner check

Open `/account/profile` → **Change avatar** → **Choose image** → inspect preview
→ **Save avatar**. Selection/cancel sends no upload. Refresh and inspect your profile;
an authorized second viewer can inspect Discover/Connections/Notifications/chat.
Replace, then **Remove avatar** to confirm fallback. Keep your intended profile
privacy; no need to make it public. Do not provide credentials or upload private
photos for testing. Other browsers update on normal refetch; instant avatar
WebSocket propagation is outside this local MVP feature.
