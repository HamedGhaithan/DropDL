"""The HTTP API and the static web page."""
from __future__ import annotations

import contextlib
import logging
import math
import threading
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__, config, runner, safety
from .engine import Engine
from .errors import ApiError
from .jobs import FINAL, JobManager
from .ratelimit import Limiter, client_address, client_key

STATIC = Path(__file__).resolve().parent.parent / "static"
log = logging.getLogger("dropdl.web")

CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' https: data:; font-src 'self'; "
       "connect-src 'self'; manifest-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}


class InfoRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)


class JobRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    kind: str = Field(default="video", max_length=8)
    height: int | None = Field(default=None, ge=1, le=10000)
    format: str | None = Field(default=None, max_length=8)
    start: float | None = Field(default=None, ge=0, le=1e7)
    end: float | None = Field(default=None, ge=0, le=1e7)


def create_app(settings: config.Settings | None = None, *, run_fn=None, info_fn: Callable | None = None,
               background: bool = True) -> FastAPI:
    s = settings or config.load()
    engine = Engine(s)
    manager = JobManager(s, engine, run_fn)
    lookup = info_fn or runner.fetch_info
    info_slots = threading.BoundedSemaphore(3)
    limits = {"info": Limiter(s.info_per_min, 60), "jobs": Limiter(s.jobs_per_hour, 3600),
              "poll": Limiter(s.poll_per_min, 60), "file": Limiter(30, 60)}
    stop = threading.Event()

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI):
        s.data_dir.mkdir(parents=True, exist_ok=True)
        manager.start()
        if background:
            threading.Thread(target=engine.run_forever, args=(stop,), name="engine", daemon=True).start()
        yield
        stop.set()
        manager.stop()

    app = FastAPI(title="DropDL Web", version=__version__, lifespan=lifespan,
                  docs_url="/api/docs" if s.enable_docs else None, redoc_url=None,
                  openapi_url="/api/openapi.json" if s.enable_docs else None)
    app.state.manager, app.state.engine, app.state.settings = manager, engine, s

    def who(request: Request) -> str:
        peer = request.client.host if request.client else None
        return client_key(request.headers, peer, s.trusted_proxy_hops)

    def throttle(name: str, request: Request) -> str:
        key = who(request)
        ok, wait = limits[name].hit(key)
        if not ok:
            raise ApiError(429, "rate_limited", f"Too many requests. Try again in {math.ceil(wait)} seconds.", wait)
        return key

    def check(url: str) -> safety.Checked:
        return safety.validate_url(url, allowed=s.allowed_sites, blocked=s.blocked_sites, youtube=s.youtube)

    # ------------------------------------------------------------------ errors and headers
    @app.exception_handler(ApiError)
    async def api_error(_: Request, exc: ApiError):
        headers = {"Retry-After": str(max(1, math.ceil(exc.retry_after)))} if exc.retry_after else None
        return JSONResponse({"error": {"code": exc.code, "message": exc.message}}, status_code=exc.status, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def invalid(_: Request, __: RequestValidationError):   # never echo the input back
        return JSONResponse({"error": {"code": "bad_request", "message": "That request wasn't valid."}}, status_code=422)

    @app.middleware("http")
    async def harden(request: Request, call_next):
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > 16 * 1024:
            return JSONResponse({"error": {"code": "bad_request", "message": "Request too large."}}, status_code=413)
        response = await call_next(request)
        for key, value in SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        if request.headers.get("x-forwarded-proto") == "https":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        path = request.url.path
        if path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        elif path.endswith((".woff2", ".svg")):
            response.headers.setdefault("Cache-Control", "public, max-age=86400")
        else:
            response.headers.setdefault("Cache-Control", "no-cache")
        return response

    # ------------------------------------------------------------------ API
    @app.get("/api/health")
    def health():
        stats = manager.stats()
        return {
            "ok": True, "version": __version__, "engine": engine.version(), "queued": stats["queued"], "active": stats["active"],
            "youtube": s.youtube, "contact": s.abuse_contact,
            "limits": {"max_height": s.max_height, "default_height": s.default_height, "max_filesize": s.max_filesize_bytes,
                       "max_duration": s.max_duration_min * 60, "max_clip": s.max_clip_min * 60, "ttl": s.job_ttl_min * 60,
                       "video_formats": list(runner.VIDEO_FORMATS), "audio_formats": list(runner.AUDIO_FORMATS)},
        }

    @app.post("/api/info")
    def info(body: InfoRequest, request: Request):
        throttle("info", request)
        checked = check(body.url)
        if not info_slots.acquire(timeout=8):
            raise ApiError(503, "busy", "The server is busy right now. Try again in a minute.", 20)
        try:
            return lookup(checked.url, s, engine.env())
        finally:
            info_slots.release()

    @app.post("/api/jobs", status_code=202)
    def create_job(body: JobRequest, request: Request):
        owner = throttle("jobs", request)
        checked = check(body.url)
        spec = runner.normalise_spec(checked.url, body.kind, body.height, body.format, body.start, body.end, s)
        return manager.view(manager.submit(spec, owner))

    def find(job_id: str):
        job = manager.get(job_id)
        if job is None:
            raise ApiError(404, "not_found", "This download has expired or doesn't exist.")
        return job

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str, request: Request):
        throttle("poll", request)
        return manager.view(find(job_id))

    @app.get("/api/jobs/{job_id}/file")
    def get_file(job_id: str, request: Request):
        throttle("file", request)
        job = find(job_id)
        if job.status != "done" or job.path is None or not job.path.is_file():
            raise ApiError(409, "not_ready", "This file isn't ready yet.")
        return FileResponse(job.path, media_type=runner.MIME.get(job.ext, "application/octet-stream"), filename=job.filename,
                            content_disposition_type="attachment",
                            headers={"Cache-Control": "private, no-store", "Content-Security-Policy": "sandbox; default-src 'none'"})

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: str, request: Request):
        throttle("poll", request)
        job = find(job_id)
        if job.status not in FINAL:
            manager.cancel(job)
        return manager.view(job)

    @app.delete("/api/jobs/{job_id}", status_code=204)
    def delete_job(job_id: str, request: Request):
        throttle("poll", request)
        manager.delete(find(job_id))

    if s.debug_client_ip:
        @app.get("/api/whoami")
        def whoami(request: Request):
            """Setup aid, off by default: shows which address the server takes to be you, so TRUSTED_PROXY_HOPS can be checked."""
            peer = request.client.host if request.client else None
            return {"peer": peer, "forwarded_for": request.headers.get("x-forwarded-for", ""), "hops": s.trusted_proxy_hops,
                    "detected": client_address(request.headers, peer, s.trusted_proxy_hops)}

    if STATIC.is_dir():
        app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
    return app


app = create_app()
