# Test and screenshot data provenance

Automated providers are authored in `backend/tests/provider_fixtures.py`, `steam_fixtures.py` and `steam_details_fixtures.py`, with HTTP MockTransport and isolated database harnesses. Browser helpers seed only their controlled test environment. No original owner API payload, private avatar, real chat export or authentication cookie was copied into the public candidate.

SteamID-shaped constants in tests are deliberately synthetic; production-source occurrences are numeric protocol/range constraints. Some integration fixtures generate valid-shaped identities randomly. Valid shape is necessary to exercise validation and does not assert that a number belongs to a nonexistent Steam account. Tests never look these identifiers up on real Steam. Their construction and mock boundary, rather than an invented reserved Steam range, establish provenance.

UI captures use fictional Orbit Relay, Mosslight Vale and Ember Circuit with synthetic demo IDs, people Alex/Jun/Mira, invented playtime and authored chat. Two toy achievement rows demonstrate unknown/locked/unlocked semantics; they are not a commercial game's real schema. These routes are intercepted only in tests, with unexpected external requests blocked. No public login bypass or runtime demo mode was added.

Fixtures and browser dependencies are excluded from production image contexts. Test-only databases and Redis namespaces remain isolated. Cleanup targets only owned fixtures; no shared Redis flush is needed.
