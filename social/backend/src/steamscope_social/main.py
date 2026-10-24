import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Literal
from uuid import uuid4

import httpx
from asyncpg.exceptions import PostgresConnectionError  # type: ignore[import-untyped]
from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

from steamscope_social.api.account import router as account_router
from steamscope_social.api.chat import router as chat_router
from steamscope_social.api.contract import document_account_security
from steamscope_social.api.health import router as health_router
from steamscope_social.api.players import router as players_router
from steamscope_social.api.social import router as social_router
from steamscope_social.api.steam import router as steam_router
from steamscope_social.api.steam_details import router as steam_details_router
from steamscope_social.core.config import Settings
from steamscope_social.core.logging import configure_logging
from steamscope_social.core.resources import Resources
from steamscope_social.modules.auth.security import AuthError
from steamscope_social.modules.chat.realtime import router as realtime_router

logger = logging.getLogger("steamscope_social.api")


class SystemInfo(BaseModel):
    version: Literal["0.6.0"] = "0.6.0"
    phase: Literal[6] = 6
    subphase: Literal["6"] = "6"
    business_features: Literal[True] = True


def create_app(
    settings: Settings | None = None, *, provider_transport: httpx.AsyncBaseTransport | None = None
) -> FastAPI:
    config = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging()
        app.state.resources = Resources(config)
        app.state.openid_client = httpx.AsyncClient(
            timeout=config.provider_timeout_seconds,
            follow_redirects=False,
            verify=True,
            trust_env=False,
            transport=provider_transport,
        )
        logger.info("api_started:phase_6_chat")
        try:
            yield
        finally:
            await app.state.resources.close()
            await app.state.openid_client.aclose()
            logger.info("api_stopped")

    app = FastAPI(title="SteamScope Social", version="0.6.0", lifespan=lifespan)
    app.state.config = config
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[config.browser_origin],
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["Content-Type"],
    )

    @app.middleware("http")
    async def safe_boundary(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = str(uuid4())
        request.state.request_id = request_id
        response: Response
        try:
            if len(request.scope.get("query_string", b"")) > 8192:
                response = JSONResponse(
                    {"error": {"code": "INVALID_REQUEST", "message": "Request too large"}},
                    status_code=400,
                )
            else:
                response = await call_next(request)
        except (SQLAlchemyError, PostgresConnectionError, OSError, TimeoutError):
            logger.warning("database_request_unavailable:%s", request_id)
            response = JSONResponse(
                {"error": {"code": "DATABASE_UNAVAILABLE", "message": "Please retry"}},
                status_code=503,
            )
        except Exception:
            logger.error("request_failed:%s", request_id)
            response = JSONResponse(
                {
                    "error": {"code": "INTERNAL_ERROR", "message": "Request unavailable"},
                    "request_id": request_id,
                },
                status_code=500,
            )
        response.headers["X-Request-ID"] = request_id
        if request.url.path.startswith("/api/v1"):
            response.headers["Cache-Control"] = "no-store, private"
            response.headers["Pragma"] = "no-cache"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["X-Content-Type-Options"] = "nosniff"
        if request.url.path == "/api/v1/auth/steam/callback" and response.status_code >= 400:
            response = RedirectResponse(
                config.browser_origin + "/login?error=LOGIN_FAILED",
                status_code=303,
                headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
            )
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            {
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": "Invalid request",
                    "fields": [
                        {"field": str(e["loc"][-1]), "code": e["type"]}
                        for e in exc.errors()
                        if e["loc"]
                        and e["loc"][-1]
                        in {
                            "handle",
                            "display_name",
                            "biography",
                            "locale",
                            "timezone",
                            "profile",
                            "library",
                            "playtime",
                            "achievements",
                            "presence",
                            "discovery",
                            "connection_requests",
                            "messaging",
                            "confirmation",
                        }
                    ],
                },
                "request_id": request.state.request_id,
            },
            status_code=422,
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            {
                "error": {"code": "HTTP_ERROR", "message": "Request unavailable"},
                "request_id": request.state.request_id,
            },
            status_code=exc.status_code,
        )

    @app.exception_handler(AuthError)
    async def auth_error(request: Request, exc: AuthError) -> JSONResponse:
        return JSONResponse(
            {
                "error": {"code": exc.code, "message": "Account request could not be completed"},
                "request_id": request.state.request_id,
            },
            status_code=exc.status,
            headers={"Retry-After": "60"} if exc.status == 429 else None,
        )

    app.include_router(health_router)
    app.include_router(account_router)
    app.include_router(chat_router)
    app.include_router(realtime_router)
    app.include_router(steam_router)
    app.include_router(steam_details_router)
    # Static /users/search must precede /users/{handle}.
    app.include_router(social_router)
    app.include_router(players_router)
    v1 = APIRouter(prefix="/api/v1", tags=["Foundation metadata"])

    @v1.get("/system", response_model=SystemInfo)
    async def system() -> SystemInfo:
        return SystemInfo()

    app.include_router(v1)
    document_account_security(app, config)
    return app
