"""FastAPI app: JSON API under /api and the dashboard (app/ folder) at /.

Run from the project root:  uvicorn api.main:app --reload
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from api.deps import cors_origins
from api.routes import catalogue, copilot, forecast, health, review, whatif
from feedforward import config as C

APP_DIR = C.PROJECT_ROOT / "app"


def create_app() -> FastAPI:
    """Build the app. CORS stays closed unless CORS_ORIGINS is set."""
    app = FastAPI(title="FeedForward", version="0.1.0", description="Predict. Prevent. Provide.")
    if cors_origins():
        app.add_middleware(CORSMiddleware, allow_origins=cors_origins(), allow_methods=["GET", "POST"], allow_headers=["*"])
    for module in (health, forecast, whatif, review, catalogue, copilot):
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
