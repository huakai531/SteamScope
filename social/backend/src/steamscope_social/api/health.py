from typing import Literal, cast

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from steamscope_social.core.resources import Readiness, Resources

router = APIRouter(tags=["Foundation health"])


class Liveness(BaseModel):
    status: Literal["alive"] = "alive"


@router.get("/health/live", response_model=Liveness)
async def live() -> Liveness:
    return Liveness()


@router.get("/health/ready", response_model=Readiness, responses={503: {"model": Readiness}})
async def ready(request: Request, response: Response) -> Readiness:
    report = await cast(Resources, request.app.state.resources).readiness()
    response.status_code = 200 if report.status == "ready" else 503
    response.headers["Cache-Control"] = "no-store"
    return report
