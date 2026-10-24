import json
import logging
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # No exception tracebacks, request URLs, credentials or arbitrary request payloads.
        return json.dumps(
            {
                "time": datetime.now(UTC).isoformat(),
                "level": record.levelname,
                "event": record.getMessage(),
                "logger": record.name,
            }
        )


class WebSocketAccessFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Uvicorn's error logger also emits handshake access lines, even when
        # --no-access-log is set. Rejected queries must not reach logs either.
        return '"WebSocket ' not in record.getMessage()


def configure_logging() -> None:
    # HTTP client debug/access logs can contain callback queries or claimed identifiers.
    for name in ("httpx", "httpcore", "uvicorn.access"):
        logging.getLogger(name).disabled = True
    transport = logging.getLogger("uvicorn.error")
    transport.setLevel(logging.INFO)
    if not any(isinstance(f, WebSocketAccessFilter) for f in transport.filters):
        transport.addFilter(WebSocketAccessFilter())
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("steamscope_social")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
