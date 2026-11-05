"""FastAPI app: JSON API under /api and the dashboard (app/ folder) at /.

Run from the project root:  uvicorn api.main:app --reload

While the server runs, the automation (feedforward.admin.automation) runs once shortly after start and then every
AUTOMATION_EVERY_S seconds. It does nothing until an admin switches it on in the Daily log. Set FEEDFORWARD_AUTOMATION=off
to stop the background runs altogether (the Run now button still works).
"""

import logging
import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from api import services
from api.deps import _load, cors_origins
from api.routes import admin, calendar, catalogue, copilot, events, forecast, health, plans, review, whatif
from feedforward import config as C
from feedforward.admin import automation

APP_DIR = C.PROJECT_ROOT / "app"
AUTOMATION_FIRST_S, AUTOMATION_EVERY_S = 5, 300
log = logging.getLogger("feedforward.automation")


def _automation_loop(stop: threading.Event) -> None:
    """Run the automation now and then until the server stops. A failed run is logged and tried again later."""
    wait = AUTOMATION_FIRST_S
    while not stop.wait(wait):
        wait = AUTOMATION_EVERY_S
        try:
            if automation.load_settings()["auto_approve"] or automation.load_settings()["auto_log"]:
                automation.run(_load(), services.today())
        except Exception:  # noqa: BLE001  (a background job must never take the server down)
            log.exception("automatic run failed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Start the background automation with the server and stop it with the server."""
    stop = threading.Event()
    if os.getenv("FEEDFORWARD_AUTOMATION", "on").strip().lower() != "off":
        threading.Thread(target=_automation_loop, args=(stop,), name="automation", daemon=True).start()
    yield
    stop.set()


def create_app() -> FastAPI:
    """Build the app. CORS stays closed unless CORS_ORIGINS is set."""
    app = FastAPI(title="FeedForward", version="0.2.0", description="Predict. Prevent. Provide.", lifespan=lifespan)
    if cors_origins():
        app.add_middleware(CORSMiddleware, allow_origins=cors_origins(), allow_methods=["GET", "POST", "DELETE"], allow_headers=["*"])
    for module in (health, forecast, whatif, review, catalogue, copilot, admin, calendar, plans, events):
        app.include_router(module.router, prefix="/api")

    @app.exception_handler(ValueError)
    async def bad_value(_: Request, exc: ValueError) -> JSONResponse:
        """Friendly 400 for invalid dates, slots or settings."""
        return JSONResponse(status_code=400, content={"detail": {"message": str(exc), "fix": "Change the input and try again."}})

    @app.exception_handler(RequestValidationError)
    async def bad_request(_: Request, exc: RequestValidationError) -> JSONResponse:
        """422 with a plain message per field: what is wrong and how to fix it."""
        fields = [{"field": ".".join(str(p) for p in e["loc"][1:]) or str(e["loc"][0]),
                   "problem": str(e["msg"]).removeprefix("Value error, ")} for e in exc.errors()]
        message = "; ".join(f"{f['field']}: {f['problem']}" for f in fields)
        return JSONResponse(status_code=422, content={"detail": {"message": message, "fields": fields,
                                                                "fix": "Correct the fields listed and send the request again."}})

    if (APP_DIR / "index.html").exists():
        app.mount("/", StaticFiles(directory=APP_DIR, html=True), name="app")
    return app


app = create_app()
