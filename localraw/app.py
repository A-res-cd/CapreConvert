"""Application factory. No decoder or runtime network dependencies in page serving."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from . import APP_NAME, __version__
from .api import router
from .config import Settings
from .errors import Problem
from .jobs import Jobs
from .security import Security, SecurityMiddleware, error_response
from .storage import Workspace
from .uploads import Uploads

STATIC = Path(__file__).parent / "static"


def create_app(settings: Settings | None = None, *, worker_target=None, start_scheduler=True):
    settings = settings or Settings.load()

    @asynccontextmanager
    async def lifespan(app):
        workspace = Workspace(settings).open()
        app.state.workspace = workspace
        try:
            app.state.security = Security(workspace, settings)
            app.state.uploads = Uploads(workspace, settings)
            arguments = {"worker_target": worker_target} if worker_target else {}
            app.state.jobs = Jobs(workspace, settings, app.state.uploads, **arguments)
            if start_scheduler:
                app.state.jobs.start()
            if callback := getattr(app.state, "on_ready", None):
                callback(app)
            yield
        finally:
            if hasattr(app.state, "jobs"):
                app.state.jobs.close()
            workspace.close()

    app = FastAPI(
        title=APP_NAME,
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.add_middleware(SecurityMiddleware, server=app)

    @app.exception_handler(Problem)
    async def problem_handler(request, exc):
        return error_response(exc, request.state.request_id)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request, exc):
        fields = [".".join(map(str, item["loc"])) for item in exc.errors()]
        return error_response(
            Problem(422, "INVALID_REQUEST", "Request settings are invalid.", fields=fields),
            request.state.request_id,
        )

    @app.exception_handler(HTTPException)
    async def http_handler(request, exc):
        return error_response(
            Problem(
                exc.status_code,
                "NOT_FOUND" if exc.status_code == 404 else "REQUEST_FAILED",
                "Resource not found." if exc.status_code == 404 else "Request could not be completed.",
            ),
            request.state.request_id,
        )

    @app.exception_handler(Exception)
    async def unexpected_handler(request, exc):
        return error_response(
            Problem(500, "INTERNAL_ERROR", "Host could not complete this request."),
            request.state.request_id,
        )

    app.include_router(router)

    @app.get("/health")
    @app.get("/api/v1/health")
    def health():
        return {"status": "ok"}

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
