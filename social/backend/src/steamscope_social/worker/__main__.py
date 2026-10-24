import argparse
import asyncio
import logging
import signal

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from steamscope_social.core.config import Settings
from steamscope_social.core.logging import configure_logging
from steamscope_social.core.resources import Resources
from steamscope_social.modules.steam.client import SteamClient
from steamscope_social.modules.steam.jobs import claim_next, process_claim

logger = logging.getLogger("steamscope_social.worker")


async def run(settings: Settings, stop: asyncio.Event, *, check: bool = False) -> int:
    resources = Resources(settings)
    logger.info("worker_started:steam_sync")
    try:
        report = await resources.readiness()
        if report.status != "ready":
            logger.error("worker_startup_dependencies_unavailable")
            return 1
        if check:
            logger.info("worker_dependency_check_passed")
            return 0
        while not stop.is_set():
            try:
                if (await resources.readiness()).status == "ready":
                    claim = await claim_next(resources, settings)
                    if claim:
                        task = asyncio.create_task(
                            process_claim(resources, settings, SteamClient(settings), claim)
                        )
                        stopped = asyncio.create_task(stop.wait())
                        done, _ = await asyncio.wait(
                            {task, stopped}, return_when=asyncio.FIRST_COMPLETED
                        )
                        if stopped in done:
                            task.cancel()
                        else:
                            stopped.cancel()
                        await asyncio.gather(task, stopped, return_exceptions=True)
                        if not task.cancelled() and task.exception() is not None:
                            logger.warning("sync_attempt_interrupted:lease_recovery_pending")
                else:
                    logger.warning("worker_dependencies_unavailable:no_jobs_processed")
            except (SQLAlchemyError, OSError, TimeoutError):
                logger.warning("worker_database_unavailable:lease_recovery_pending")
            try:
                await asyncio.wait_for(stop.wait(), settings.steam_sync_poll_seconds)
            except TimeoutError:
                pass
        return 0
    finally:
        await resources.close()
        logger.info("worker_stopped")


async def start(check: bool) -> int:
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    previous = {}
    for sig in (signal.SIGINT, signal.SIGTERM):
        previous[sig] = signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stop.set))
    try:
        return await run(Settings(), stop, check=check)
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="SteamScope durable Steam synchronization worker")
    parser.add_argument("--check", action="store_true", help="Check dependencies and exit")
    args = parser.parse_args()
    configure_logging()
    try:
        code = asyncio.run(start(args.check))
    except ValidationError:
        logger.error("invalid_worker_configuration")
        code = 2
    raise SystemExit(code)


if __name__ == "__main__":
    main()
