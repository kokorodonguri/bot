from __future__ import annotations

import asyncio
import contextlib
import errno

from aiohttp import web

from config import (
    ENABLE_LISTING_SERVER,
    ENABLE_UPLOAD_SERVER,
    HTTP_HOST,
    HTTP_LISTING_PORT,
    HTTP_LOGIN_PORT,
    HTTP_PORT,
)
from web_server import create_listing_app, create_uploader_app


async def start_site(app: web.Application, host: str, port: int) -> web.AppRunner:
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    return runner


async def run_servers() -> None:
    runners: list[web.AppRunner] = []
    stop_event = asyncio.Event()

    try:
        if ENABLE_UPLOAD_SERVER:
            runners.append(await start_site(create_uploader_app(), HTTP_HOST, HTTP_PORT))
            print(f"Upload server started on {HTTP_HOST}:{HTTP_PORT}")
        else:
            print("Skipping upload server (ENABLE_UPLOAD_SERVER=0)")

        if ENABLE_LISTING_SERVER:
            listing_runner = web.AppRunner(create_listing_app())
            await listing_runner.setup()
            runners.append(listing_runner)
            listing_site = web.TCPSite(listing_runner, HTTP_HOST, HTTP_LISTING_PORT)
            await listing_site.start()
            if HTTP_LOGIN_PORT != HTTP_LISTING_PORT:
                login_site = web.TCPSite(listing_runner, HTTP_HOST, HTTP_LOGIN_PORT)
                await login_site.start()
                print(f"Login server started on {HTTP_HOST}:{HTTP_LOGIN_PORT}")
            print(f"Listing server started on {HTTP_HOST}:{HTTP_LISTING_PORT}")
        else:
            print("Skipping listing/login server (ENABLE_LISTING_SERVER=0)")

        await stop_event.wait()
    finally:
        for runner in reversed(runners):
            with contextlib.suppress(Exception):
                await runner.cleanup()


def port_error_message(exc: OSError) -> str:
    if exc.errno != errno.EADDRINUSE:
        return f"Server startup failed: {exc}"
    return (
        "Port is already in use. Update .env to use a free port. "
        f"Details: {exc}"
    )


def main() -> None:
    try:
        asyncio.run(run_servers())
    except KeyboardInterrupt:
        print("Stopped")
    except OSError as exc:
        print(port_error_message(exc))


if __name__ == "__main__":
    main()
