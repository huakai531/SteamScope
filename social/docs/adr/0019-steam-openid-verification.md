# ADR 0019 — Steam OpenID 2.0 relying party

Status: implemented in Phase 2; live owner login still requires manual verification.

Steam documents browser OpenID **2.0**, not OAuth/OIDC. Its documented claimed identifier is
`http://steamcommunity.com/openid/id/<steamid>`. We accept that exact namespace and its HTTPS
form, retain the asserted identifier, and use HTTPS for discovery transport. The provider is
fixed to `https://steamcommunity.com/openid/login`. Public XRDS GETs were inspected during
implementation; they returned OpenID 2.0 server/signon service types and that endpoint.
Those GETs are not evidence of a successful account login.

We evaluated python3-openid (actual OpenID 2.0 support; release 3.2.0 dated 2020-06-29).
Its synchronous discovery/network plumbing and older maintenance baseline are a poor fit
for this bounded async, single-provider adapter. OAuth/OIDC-only libraries do not implement
the required protocol. Decision: a small Steam-only adapter using provider-side
`check_authentication`; **no locally invented cryptographic signature verification**,
association cache or generalized OpenID provider support. Tradeoff: protocol validation code
is owned here and requires continued review against the final specification and live Steam.

Verification order:
1. Strict callback parsing: reject duplicate/conflicting fields, oversized input, absent state.
2. Atomically DELETE RETURNING an unexpired PostgreSQL attempt matched to both state digest
   and browser-binding-cookie digest. A wrong browser cannot consume the rightful attempt.
3. Require OpenID 2.0 id_res, fixed provider, exact configured return_to including state,
   matching identity/claimed_id, decimal individual SteamID64, and all six required signed
   fields. Bound signature syntax is checked; Steam makes the cryptographic decision.
4. Require timestamped response_nonce within the previous 300 seconds or next 60 seconds.
   Fetch the pinned HTTPS identity URL and validate XRDS signon endpoint and optional LocalID.
   XML DTD/entities are forbidden. Neither callbacks nor XML can select another fetch target.
5. POST the callback's OpenID fields (only mode changes to check_authentication) to the pinned
   provider. TLS certificate verification, no redirects, no inherited HTTP proxy, one 5-second
   overall timeout, at most 64 KiB response. Require strict ns/is_valid:true key-value output;
   reject duplicates, malformed output and non-200 responses.
6. Redis SET NX with 660-second TTL claims the provider nonce, then a DB transaction issues
   the account/session. A failed dependency never bypasses these checks.

Application state and provider nonce are separate protections. Attempts expire after 300s;
state and browser secret are independent 256-bit random values, stored as SHA-256 digests.
Per-attempt cookies allow parallel tabs. Account-bound callbacks additionally require the
original user/session still active. No DB transaction is held open while awaiting Steam.
Cancel/failure redirects to a clean local login URL; success redirects to a fixed allowlist.

Tests mock HTTP **transport**, not the verifier: all discovery/direct-verification checks,
PG consumption, Redis replay detection and account transactions still run. Browser fixtures
live under tests/, are excluded from Docker contexts, and expose no login-as-user endpoint.
Playwright's first-request-only redirect interception requires a test-only navigation bridge
around the genuine initiation response; production redirects are unchanged.

Sources: [Steam browser authentication](https://partner.steamgames.com/doc/features/auth),
[OpenID 2.0 final, assertion verification](https://openid.net/specs/openid-authentication-2_0.html),
[python3-openid release history](https://pypi.org/project/python3-openid/).
