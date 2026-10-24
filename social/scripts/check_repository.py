"""Static source/configuration checks; this does NOT validate Docker runtime."""
from pathlib import Path
import json
import re
import subprocess

import yaml

root = Path(__file__).resolve().parents[1]
compose = yaml.safe_load((root / "compose.yaml").read_text(encoding="utf-8"))
assert set(compose["services"]) == {"postgres", "redis", "api", "frontend", "worker"}
for service in compose["services"].values():
    for binding in service.get("ports", []):
        assert binding.startswith("127.0.0.1:"), "Public development host binding"
    assert "healthcheck" in service
assert compose["services"]["api"]["image"] == compose["services"]["worker"]["image"]
assert "redis" not in compose.get("volumes", {}), "Redis is intentionally transient"
assert len(list((root / "docs/adr").glob("*.md"))) >= 15
assert (root / "docs/architecture/DIAGRAMS.md").read_text().count("```mermaid") >= 8
schema = json.loads((root / "docs/api/openapi.json").read_text())
assert set(schema["paths"]) == {
    "/api/v1/conversations/direct", "/api/v1/conversations",
    "/api/v1/conversations/{conversation_id}", "/api/v1/conversations/{conversation_id}/messages",
    "/api/v1/conversations/{conversation_id}/read", "/api/v1/messages/{message_id}",
    "/api/v1/messages/{message_id}/report",
    "/api/v1/users/search", "/api/v1/users/{handle}/relationship",
    "/api/v1/discovery/players", "/api/v1/discovery/steam-friends",
    "/api/v1/connection-requests", "/api/v1/connection-requests/incoming",
    "/api/v1/connection-requests/outgoing", "/api/v1/connection-requests/{request_id}/accept",
    "/api/v1/connection-requests/{request_id}/reject", "/api/v1/connection-requests/{request_id}",
    "/api/v1/connections", "/api/v1/connections/{handle}",
    "/api/v1/blocks", "/api/v1/blocks/{handle}", "/api/v1/reports",
    "/api/v1/notifications", "/api/v1/notifications/read-all", "/api/v1/notifications/{notification_id}/read",
    "/api/v1/users/{handle}", "/api/v1/users/{handle}/games",
    "/api/v1/users/{handle}/games/{appid}",
    "/api/v1/users/{handle}/games/{appid}/achievements",
    "/api/v1/users/{handle}/comparison",
    "/health/live", "/health/ready", "/api/v1/system",
    "/api/v1/auth/steam/login", "/api/v1/auth/steam/callback", "/api/v1/auth/steam/reauth",
    "/api/v1/auth/csrf", "/api/v1/auth/logout", "/api/v1/auth/logout-all",
    "/api/v1/me", "/api/v1/me/privacy", "/api/v1/me/sessions", "/api/v1/me/sessions/{session_id}",
    "/api/v1/me/steam/sync", "/api/v1/me/steam/sync-status",
    "/api/v1/me/steam/sync-jobs/{job_id}", "/api/v1/me/steam/profile",
    "/api/v1/me/steam/games", "/api/v1/me/steam/recent-games", "/api/v1/me/steam/data",
    "/api/v1/me/steam/games/{appid}/achievements/sync",
    "/api/v1/me/steam/games/{appid}/achievements",
    "/api/v1/me/steam/friends/sync", "/api/v1/me/steam/friends",
}
assert "SOCIAL_STEAM_API_KEY" not in compose["services"]["frontend"]["environment"]
assert not any("NEXT_PUBLIC" in key for key in compose["services"]["frontend"]["environment"])
assert {path.name for path in (root / "backend/migrations/versions").glob("*.py")} == {
    "0001_phase2_accounts.py",
    "0002_phase3a_steam_sync_phase3a_steam_sync.py",
    "0003_phase3b_steam_details_phase3b_achievements_and_friends.py",
    "0004_phase5_social_phase5_social_graph.py",
    "0005_phase6_chat_phase6_direct_chat.py",
}
assert "**/tests" in (root / ".dockerignore").read_text()
assert "logging: false" in (root / "frontend/next.config.ts").read_text()
for source in (root / "backend/src").rglob("*.py"):
    assert not re.search(r"(?:from|import) app(?:\.|\s)", source.read_text()), source.name
repo = root.parent
git = ["git", "-c", f"safe.directory={repo.as_posix()}"]
tracked = subprocess.check_output(git + ["ls-files", "social"], cwd=repo, text=True).splitlines()
for name in tracked:
    parts = Path(name).parts
    assert Path(name).name != ".env" and "node_modules" not in parts and ".venv" not in parts
    assert Path(name).suffix.lower() not in {".zip", ".log", ".pem", ".key"}
print("PASS: static Compose structure, isolated package, phase scope, ADRs/diagrams, contract, tracked file exclusions")
print("NOTE: static parsing does not prove Docker Compose validation, image build or service startup")
