"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from spectra import __version__
from spectra.api import cases, evidence, jobs, misc, system
from spectra.api.middleware import HostCheckMiddleware, OriginCheckMiddleware, SecurityHeadersMiddleware
from spectra.config import Settings
from spectra.container import Container, build_container
from spectra.core.errors import NotFoundError, SpectraError
from spectra.core.security import resolve_within


def _error(status: int, code: str, message: str, details=None) -> JSONResponse:
    body: dict = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    return JSONResponse({"error": body}, status_code=status)


def create_app(settings: Settings | None = None, *, container: Container | None = None) -> FastAPI:
    settings = settings or Settings()
    logging.basicConfig(
        level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    container = container or build_container(settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        container.close()

    app = FastAPI(
        title="SPECTRA",
        version=__version__,
        description="Multimedia steganography & hidden data analysis workbench.",
        lifespan=lifespan,
        # The bundled Swagger UI loads scripts from a CDN, which breaks the offline-by-default guarantee.
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.state.container = container

    # Innermost first; the last one added is the outermost.
    app.add_middleware(OriginCheckMiddleware, allowed_origins=settings.allowed_origins)
    app.add_middleware(HostCheckMiddleware, allowed_hosts=settings.allowed_hosts)
    app.add_middleware(SecurityHeadersMiddleware)

    @app.exception_handler(SpectraError)
    async def _spectra_error(_req: Request, exc: SpectraError):
        return _error(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_req: Request, exc: RequestValidationError):
        details = [
            {"loc": list(e.get("loc", [])), "msg": e.get("msg", ""), "type": e.get("type", "")}
            for e in exc.errors()
        ]
        return _error(422, "validation_error", "Request validation failed.", details)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_req: Request, exc: StarletteHTTPException):
        return _error(exc.status_code, "http_error", str(exc.detail))

    for module in (system, cases, evidence, jobs, misc):
        app.include_router(module.router)

    _mount_frontend(app, settings)
    return app


def _mount_frontend(app: FastAPI, settings: Settings) -> None:
    dist = settings.frontend_dist
    if not (settings.serve_frontend and (dist / "index.html").is_file()):
        return

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        if full_path == "api" or full_path.startswith("api/"):
            raise NotFoundError("No such API endpoint.", code="endpoint_not_found")
        if full_path:
            candidate = resolve_within(dist, full_path)
            if candidate.is_file():
                return FileResponse(candidate)
        return FileResponse(dist / "index.html")
