from __future__ import annotations

from contextlib import AsyncExitStack, asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from WebDashboard.server import app as dashboard_app
from WebTicketChecker.server import app as ticket_checker_app


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    async with AsyncExitStack() as stack:
        await stack.enter_async_context(
            dashboard_app.router.lifespan_context(dashboard_app)
        )
        await stack.enter_async_context(
            ticket_checker_app.router.lifespan_context(ticket_checker_app)
        )
        yield


app = FastAPI(
    title="NOC Web Tools",
    docs_url=None,
    redoc_url=None,
    lifespan=_lifespan,
)
app.mount("/dashboard", dashboard_app, name="dashboard")
app.mount("/ticket-checker", ticket_checker_app, name="ticket-checker")


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse("/dashboard/", status_code=307)
