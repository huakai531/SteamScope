import json

from steamscope_social.core.config import SOCIAL_ROOT, Settings
from steamscope_social.main import create_app


def main() -> None:
    # Fixed class defaults only; schema export must not read local environment or secrets.
    # No connection is opened. Untrusted values never reach model_construct here.
    config = Settings.model_construct()
    schema = create_app(config).openapi()
    target = SOCIAL_ROOT / "docs" / "api" / "openapi.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("Exported Phase 6 OpenAPI; no service connection required")


if __name__ == "__main__":
    main()
