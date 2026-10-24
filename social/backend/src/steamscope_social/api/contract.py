from fastapi import FastAPI

from steamscope_social.core.config import Settings
from steamscope_social.modules.auth.security import session_cookie


def document_account_security(app: FastAPI, config: Settings) -> None:
    """Describe the existing context-manager enforcement in the generated contract."""
    schema = app.openapi()
    schema.setdefault("components", {}).setdefault("securitySchemes", {})["SessionCookie"] = {
        "type": "apiKey",
        "in": "cookie",
        "name": session_cookie(config),
        "description": (
            "Opaque HttpOnly session; production uses __Host-steamscope_session with Secure."
        ),
    }
    public = {"/api/v1/auth/steam/login", "/api/v1/auth/steam/callback"}
    for path, methods in schema["paths"].items():
        if path in public or not path.startswith(
            (
                "/api/v1/me",
                "/api/v1/auth/",
                "/api/v1/users/",
                "/api/v1/discovery/",
                "/api/v1/connection",
                "/api/v1/blocks",
                "/api/v1/reports",
                "/api/v1/notifications",
                "/api/v1/conversations",
                "/api/v1/messages",
            )
        ):
            continue
        for method, operation in methods.items():
            if method not in {"get", "post", "patch", "delete"}:
                continue
            operation["security"] = [{"SessionCookie": []}]
            if method != "get":
                parameters = operation.setdefault("parameters", [])
                for name, description in [
                    ("Origin", "Exactly the configured browser origin"),
                    ("X-CSRF-Token", "Session-bound token from GET /api/v1/auth/csrf"),
                ]:
                    parameters.append(
                        {
                            "in": "header",
                            "name": name,
                            "required": True,
                            "schema": {"type": "string"},
                            "description": description,
                        }
                    )
