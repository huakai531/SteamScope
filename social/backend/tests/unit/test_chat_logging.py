import logging

from steamscope_social.core.logging import WebSocketAccessFilter


def test_transport_handshake_queries_are_not_logged_but_safe_errors_remain():
    policy = WebSocketAccessFilter()
    for suffix in ("", "?token=PRIVATE_SENTINEL"):
        record = logging.LogRecord(
            "uvicorn.error",
            logging.INFO,
            __file__,
            1,
            '%s - "WebSocket %s" [accepted]',
            ("loopback", "/api/v1/ws" + suffix),
            None,
        )
        assert not policy.filter(record)
    record = logging.LogRecord(
        "uvicorn.error", logging.ERROR, __file__, 1, "Transport unavailable", (), None
    )
    assert policy.filter(record)
