from __future__ import annotations

import asyncio
import os
import sys
import mimetypes
import zipfile
import logging
import hmac
from fastapi import Header
from starlette.background import BackgroundTask
from uuid import uuid4
from threading import Lock
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from .downloader import inspect_url, run_download, _ffmpeg_location, _tool
from .playlist_process import inspect_playlist_isolated as inspect_playlist
from .diagnostics import configure_diagnostics
from .jobs import jobs
from .version import VERSION
from .settings import Settings, CONFIG_ROOT, site_folder, NETWORK_DEFAULTS, valid_network_value, network_snapshot
from .security import UnsafeUrlError, validate_remote_url

BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
DEFAULT_DOWNLOAD_ROOT = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "DropDL" / "downloads" if getattr(sys, "frozen", False) else BASE_DIR / "downloads"
DOWNLOAD_ROOT = Path(os.getenv("DOWNLOAD_ROOT", str(DEFAULT_DOWNLOAD_ROOT))).resolve()
DOWNLOAD_ROOT.mkdir(parents=True, exist_ok=True)
settings = Settings(CONFIG_ROOT / "settings.json", DOWNLOAD_ROOT)
jobs.enable_persistence(CONFIG_ROOT / "queue.json")

MAX_WORKERS = max(1, int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "2")))
from .scheduler import Scheduler
from .media_worker import run_isolated
from .converter import run_conversion

def execute_task(job):
    # Snapshot network/reliability preferences when the task actually starts.
    job.network = network_snapshot(settings.get())
    if job.purpose in {'conversion','conversion_sample'} or job.conversion_options.get('edit'):run_conversion(job)
    else:run_isolated(job)

executor = Scheduler(MAX_WORKERS, settings.get, execute_task)
# Local editing runs independently of download pause, bandwidth and waiting downloads.
editor = Scheduler(1, lambda: {}, execute_task)

def submit_task(job):
    target=editor if job.purpose=="clip" or (job.purpose=="preview" and job.source_filename) else executor
    target.submit(run_download,job)

@asynccontextmanager
async def lifespan(application):
    configure_diagnostics()
    logging.getLogger('dropdl').info('API starting: version=%s', VERSION)
    for job in jobs.recover_interrupted(settings.get().get('auto_recover',True)):
        submit_task(job)
    if settings.get().get('auto_cleanup',True):
        try:workspace.cleanup(min_age_seconds=7*86400)
        except OSError:logging.getLogger('dropdl.storage').exception('Temporary cleanup failed')
    from . import subscriptions
    subscriptions.start(sys.modules[__name__])
    from . import engine_update
    if os.name=="nt":engine_update.start()
    yield
    subscriptions.stop.set()
    engine_update.stop.set()
    executor.close();editor.close()
    jobs.checkpoint_for_shutdown()


app = FastAPI(title="DropDL API", version=VERSION, lifespan=lifespan)

@app.middleware("http")
async def fresh_desktop_interface(request, call_next):
    response = await call_next(request)
    # A persistent WebView profile must not reuse an older index after an upgrade.
    if request.url.path in {"/", "/index.html", "/build.json", "/api/health"}:
        response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


origins = [origin.strip() for origin in os.getenv(
    "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://tauri.localhost,https://tauri.localhost,tauri://localhost"
).split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class UrlRequest(BaseModel):
    url: str = Field(min_length=8, max_length=4096)


class ClipRange(BaseModel):
    clip_enabled: bool = False
    clip_start: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    clip_end: float | None = Field(default=None, gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def check_range(self):
        if self.clip_enabled and (self.clip_start is None or self.clip_end is None):
            raise ValueError("Clipping is enabled; provide both start and finish.")
        if (self.clip_start is None) != (self.clip_end is None):
            raise ValueError("Provide both clip start and finish.")
        if self.clip_start is not None and self.clip_end <= self.clip_start:
            raise ValueError("Clip finish must be later than start.")
        return self


class DownloadExtras(BaseModel):
    """2.0 per-download extras. Every option degrades gracefully if a site
    or container cannot support it (see downloader.fallback_for)."""
    codec: str = Field(default="auto", pattern="^(auto|compatible|any)$")
    sponsorblock: str = Field(default="off", pattern="^(off|mark|remove)$")
    embed_thumbnail: bool = False
    embed_subtitles: bool = False
    audio_quality: str = Field(default="best", pattern="^(best|320|256|192|128)$")

    def as_options(self):
        values = self.model_dump()
        if values["codec"] == "auto":
            values.pop("codec")
        return values


AUDIO_PATTERN = "^(mp3|m4a|opus|flac|wav)$"
AUDIO_FORMATS = {"mp3", "m4a", "opus", "flac", "wav"}


class DownloadRequest(ClipRange, UrlRequest):
    kind: str = Field(default="video", pattern="^(video|audio)$")
    container: str = Field(default="mp4", pattern="^(mp4|webm|mkv|mp3|m4a|opus|flac|wav)$")
    quality: str = Field(default="1080p", pattern="^(best|[0-9]{3,4}p)$")
    download_options: DownloadExtras = Field(default_factory=DownloadExtras)


class PlaylistRequest(UrlRequest):
    start: int = Field(default=1, ge=1)
    limit: int = Field(default=100, ge=1, le=200)


class BatchRequest(ClipRange):
    collection: str = Field(default="", max_length=200)
    skip_duplicates: bool = False
    scheduled_at: float = Field(default=0,ge=0,allow_inf_nan=False)
    subtitle_languages: list[str] = Field(default_factory=list,max_length=10)
    embed_metadata: bool = False
    urls: list[str] = Field(min_length=1, max_length=500)
    mode: str = Field(default="video", pattern="^(video|audio|both)$")
    video_container: str = Field(default="mp4", pattern="^(mp4|webm|mkv)$")
    audio_container: str = Field(default="mp3", pattern=AUDIO_PATTERN)
    quality: str = Field(default="1080p", pattern="^(best|[0-9]{3,4}p)$")
    download_options: DownloadExtras = Field(default_factory=DownloadExtras)


class PreviewRequest(BaseModel):
    force_transcode: bool = False
    proxy: bool = False
    url: str | None = Field(default=None, min_length=8, max_length=4096)
    source_job_id: str | None = None
    quality: str = Field(default="1080p", pattern="^(best|[0-9]{3,4}p)$")

    @model_validator(mode="after")
    def one_source(self):
        if bool(self.url) == bool(self.source_job_id):
            raise ValueError("Provide either a URL or a completed source job.")
        return self


class LocalClipRequest(ClipRange):
    show_in_downloads: bool = False
    clip_start: float = Field(ge=0, allow_inf_nan=False)
    clip_end: float = Field(gt=0, allow_inf_nan=False)
    mode: str = Field(default="video", pattern="^(video|audio|both)$")
    video_container: str = Field(default="mp4", pattern="^(mp4|webm|mkv)$")
    audio_container: str = Field(default="mp3", pattern=AUDIO_PATTERN)


def check_storage(destination=None):
    import shutil
    from tempfile import TemporaryFile
    destination=Path(destination or settings.get()["download_directory"])
    try:
        destination.mkdir(parents=True,exist_ok=True)
        with TemporaryFile(dir=destination): pass
        free=shutil.disk_usage(destination).free
    except OSError as exc:
        raise HTTPException(422,"The output folder is unavailable or not writable. Choose another location.") from exc
    if free<100*1024**2:
        raise HTTPException(507,"Less than 100 MB of storage remains. Free space before starting a new task.")


def enqueue(url: str, kind: str, container: str, quality: str, **options):
    preferences = settings.get()
    destination=options.pop('destination', str(Path(preferences["download_directory"]) / site_folder(url)) if preferences["group_by_site"] else preferences["download_directory"])
    check_storage(destination)
    options.setdefault("organization", {key:preferences[key] for key in ("folder_rule","name_rule")})
    options.setdefault("cookie_file",str(CONFIG_ROOT/"cookies.txt") if (CONFIG_ROOT/"cookies.txt").is_file() else None)
    job = jobs.create(url=url, kind=kind, container=container, quality=quality,
                      directory=str(CONFIG_ROOT / "work" / uuid4().hex),
                      destination=destination,
                      site=site_folder(url), speed_limit_kbps=preferences["speed_limit_kbps"], **options)
    submit_task(job)
    return job.public()


def checked_url(url: str) -> str:
    try:
        return validate_remote_url(url)
    except UnsafeUrlError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def checked_batch_urls(urls):
    hosts = {}
    try:
        return list(dict.fromkeys(validate_remote_url(url, hosts) for url in urls))
    except UnsafeUrlError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/health")
def health() -> dict[str, object]:
    try:
        _tool("ffprobe")
        ffprobe = True
    except RuntimeError:
        ffprobe = False
    import shutil
    try:
        free = shutil.disk_usage(settings.get()["download_directory"]).free
    except OSError:
        free = None
    try:
        from yt_dlp.version import __version__ as engine
    except Exception:
        engine = None
    return {"revision": jobs.revision, "disk_free": free, "engine_version": engine,
            "max_parallel": settings.get().get("max_concurrent_downloads", MAX_WORKERS),
            "queue_checkpoint_ok":not jobs.persistence_error,"recovered_count":jobs.recovered_count,"restored_from_backup":jobs.restored_from_backup,"ok": True, "version": VERSION, "max_concurrent_downloads": MAX_WORKERS, "ffmpeg": bool(_ffmpeg_location()), "ffprobe": ffprobe}


class SettingsRequest(BaseModel):
    group_by_site: bool
    speed_limit_kbps: int = Field(default=0, ge=0, le=1000000)
    global_speed_limit_kbps: int = Field(default=0, ge=0, le=1000000)
    auto_recover: bool = True
    auto_cleanup: bool = True
    keep_in_tray: bool = False
    skip_duplicates: bool = False
    folder_rule: str = Field(default="none", pattern="^(none|creator|playlist|date|media_type)$")
    name_rule: str = Field(default="original", pattern="^(original|title|date_title)$")
    max_concurrent_downloads: int = Field(default=NETWORK_DEFAULTS["max_concurrent_downloads"], ge=1, le=8)
    max_auto_retries: int = Field(default=NETWORK_DEFAULTS["max_auto_retries"], ge=0, le=10)
    stall_timeout: int = Field(default=NETWORK_DEFAULTS["stall_timeout"], ge=0, le=900)
    concurrent_fragments: int = Field(default=NETWORK_DEFAULTS["concurrent_fragments"], ge=1, le=16)
    proxy: str = Field(default="", max_length=300)
    force_ipv4: bool = False
    impersonate: str = Field(default="auto", pattern="^(auto|always)$")
    cookies_browser: str = Field(default="", pattern="^(|firefox|chrome|edge|brave|opera|vivaldi|chromium)$")

    @model_validator(mode="after")
    def check_network(self):
        self.proxy = self.proxy.strip()
        if not valid_network_value("proxy", self.proxy):
            raise ValueError("Proxy must look like http://host:port, socks5://host:port or socks5h://user:pass@host:port.")
        if not valid_network_value("stall_timeout", self.stall_timeout):
            raise ValueError("Stall timeout must be 0 (off) or between 30 and 900 seconds.")
        return self


@app.get("/api/settings")
def get_settings():
    return dict(settings.get(), native_folder_picker=bool(getattr(app.state, "desktop", False)))


@app.post("/api/settings")
def change_settings(payload: SettingsRequest):
    try:
        return dict(settings.change(**payload.model_dump()), native_folder_picker=bool(getattr(app.state, "desktop", False)))
    except OSError as exc:
        raise HTTPException(status_code=422, detail="The download directory is not writable.") from exc


@app.post("/api/info")
def info(payload: UrlRequest) -> dict[str, object]:
    url = checked_url(payload.url)
    try:
        return inspect_url(url)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not inspect this URL: {exc}") from exc


@app.post("/api/download", status_code=202)
def download(payload: DownloadRequest) -> dict[str, object]:
    url = checked_url(payload.url)
    if payload.kind == "audio" and payload.container not in AUDIO_FORMATS:
        raise HTTPException(status_code=400, detail="Audio mode supports MP3, M4A, Opus, FLAC or WAV.")
    if payload.kind == "video" and payload.container not in {"mp4", "webm", "mkv"}:
        raise HTTPException(status_code=400, detail="Video mode supports MP4, WebM or MKV.")

    return enqueue(url, payload.kind, payload.container, payload.quality,
                   clip_start=payload.clip_start, clip_end=payload.clip_end,
                   download_options=payload.download_options.as_options())


@app.post("/api/playlist")
def playlist(payload: PlaylistRequest):
    logging.getLogger('dropdl.playlist').info('Load playlist request received: start=%s limit=%s',payload.start,payload.limit)
    url = checked_url(payload.url)
    try:
        return inspect_playlist(url, payload.start, payload.limit)
    except Exception as exc:
        logging.getLogger('dropdl.playlist').exception('Load playlist request failed')
        raise HTTPException(status_code=422, detail=f"Could not load playlist: {exc}") from exc


class InterfaceDiagnostic(BaseModel):
    event: str = Field(max_length=80)
    message: str = Field(default='', max_length=6000)


@app.post('/api/diagnostics')
def interface_diagnostic(payload: InterfaceDiagnostic):
    logging.getLogger('dropdl.interface').info('%s: %s',payload.event,payload.message)
    return {'ok':True}


batch_lock=Lock()

@app.post("/api/batch", status_code=202)
def batch(payload: BatchRequest):
    with batch_lock:return commit_batch(payload)

def commit_batch(payload: BatchRequest):
    logging.getLogger('dropdl.queue').info('Batch requested: %s sources, mode=%s',len(payload.urls),payload.mode)
    # Validate all destinations before creating any jobs.
    urls = checked_batch_urls(payload.urls)
    check_storage()
    batch_id = uuid4().hex
    specifications = []
    preferences = settings.get()
    skipped=0
    from .duplicates import existing_keys,output_key
    known=existing_keys() if payload.skip_duplicates else set()
    for url in urls:
        for kind in (["video", "audio"] if payload.mode == "both" else [payload.mode]):
            container=payload.video_container if kind=='video' else payload.audio_container
            quality=payload.quality if kind=='video' else 'best'
            key=output_key(url,kind,container,quality,payload.clip_start,payload.clip_end)
            if payload.skip_duplicates and key in known:
                skipped+=1;continue
            known.add(key)
            specifications.append(dict(download_options=payload.download_options.as_options(), organization={key:preferences[key] for key in ("folder_rule","name_rule")}, collection=payload.collection, scheduled_at=payload.scheduled_at,subtitle_languages=payload.subtitle_languages,embed_metadata=payload.embed_metadata,
                cookie_file=str(CONFIG_ROOT/'cookies.txt') if (CONFIG_ROOT/'cookies.txt').is_file() else None,url=url,kind=kind,container=payload.video_container if kind=='video' else payload.audio_container,
                quality=payload.quality if kind=='video' else 'best',batch_id=batch_id,clip_start=payload.clip_start,clip_end=payload.clip_end,
                directory=str(CONFIG_ROOT/'work'/uuid4().hex),site=site_folder(url),speed_limit_kbps=preferences['speed_limit_kbps'],
                destination=str(Path(preferences['download_directory'])/site_folder(url)) if preferences['group_by_site'] else preferences['download_directory']))
    created = jobs.create_many(specifications)
    response = {'batch_id':batch_id,'jobs':[job.public() for job in created],'skipped':skipped}
    logging.getLogger('dropdl.queue').info('Batch committed: %s tasks',len(created))
    for job in created:
        executor.submit(run_download,job)
    return response


class SelectedTasksRequest(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=500)


@app.post("/api/queue/remove")
def remove_selected_tasks(payload: SelectedTasksRequest):
    # Removing queue records never deletes downloaded files or library entries.
    return jobs.remove_selected(payload.ids)


@app.get("/api/queue/archive")
def selected_task_archive(ids: str):
    identities = list(dict.fromkeys(ids.split(',')))
    if not identities or len(identities) > 500 or any(len(i) != 32 or any(c not in '0123456789abcdef' for c in i) for i in identities):
        raise HTTPException(400, "Choose between 1 and 500 tasks.")
    files = []
    for identity in identities:
        job = jobs.get(identity)
        if not job or job.status != "completed" or not job.filename:
            raise HTTPException(409, "Select completed tasks to save copies.")
        if not Path(job.filename).is_file():
            raise HTTPException(410, "A selected file is no longer available.")
        files.append(job)
    return archive_files(files, "DropDL-selected.zip")


class ClearQueueRequest(BaseModel):
    include_active: bool = False


@app.post("/api/queue/clear")
def clear_queue(payload: ClearQueueRequest):
    return jobs.clear(payload.include_active)


@app.get("/api/jobs")
def list_jobs(revision: int | None = None):
    """Full queue, or {"unchanged": true} when the client already has this revision."""
    if revision is not None and revision == jobs.revision:
        return {"revision": revision, "unchanged": True}
    current, records = jobs.snapshot()
    return {"revision": current, "jobs": records}


@app.get('/api/jobs/{job_id}')
def get_job(job_id: str):
    job = jobs.get(job_id)
    if not job: raise HTTPException(status_code=404,detail='Task not found.')
    return job.public()


def require_native_token(token):
    expected=os.getenv('DROPDL_NATIVE_TOKEN','')
    if not expected or not hmac.compare_digest(token or '',expected):
        raise HTTPException(status_code=403,detail='Desktop authorization required.')


class NativeDestination(BaseModel):
    download_directory: str = Field(min_length=1,max_length=4096)


@app.post('/api/native/destination')
def native_destination(payload: NativeDestination,x_dropdl_native_token: str | None=Header(default=None)):
    require_native_token(x_dropdl_native_token)
    if not Path(payload.download_directory).is_absolute():
        raise HTTPException(status_code=400,detail='Choose an absolute destination path.')
    return dict(settings.change(download_directory=payload.download_directory),native_folder_picker=True)


class NativeExportDestination(BaseModel):
    export_directory: str = Field(min_length=1,max_length=4096)


@app.post('/api/native/export-destination')
def native_export_destination(payload: NativeExportDestination,x_dropdl_native_token: str | None=Header(default=None)):
    require_native_token(x_dropdl_native_token)
    if not Path(payload.export_directory).is_absolute() or '\x00' in payload.export_directory:
        raise HTTPException(400,'Choose an absolute export folder path.')
    try:
        return dict(settings.change(export_directory=payload.export_directory),native_folder_picker=True)
    except OSError as exc:
        raise HTTPException(422,'The export folder is unavailable or not writable.') from exc


@app.post('/api/native/shutdown')
def native_shutdown(x_dropdl_native_token: str | None=Header(default=None)):
    require_native_token(x_dropdl_native_token)
    # Record restart intent *before* stopping workers: active and queued tasks
    # become paused+interrupted and resume on the next launch instead of being
    # reported as cancelled by user.
    jobs.checkpoint_for_shutdown()
    server=getattr(app.state,'server',None)
    if server: server.should_exit=True
    return {'ok':True}


@app.post("/api/preview", status_code=202)
def request_preview(payload: PreviewRequest):
    if payload.source_job_id:
        source = jobs.get(payload.source_job_id)
        if not source or source.status != "completed" or not source.filename:
            raise HTTPException(status_code=409, detail="Choose a completed source to preview.")
        if not Path(source.filename).exists():
            raise HTTPException(status_code=410, detail="The source file is no longer available.")
        if not payload.force_transcode and not payload.proxy:
            # Serve the saved file directly; no job, conversion or download is needed.
            return dict(source.public(), preview_ready=True)
        if not payload.proxy and source.preview_filename and source.preview_filename != source.filename and Path(source.preview_filename).exists():
            return source.public()
        for item in jobs.list():
            cached = jobs.get(item["id"])
            if cached.purpose == "preview" and cached.status == "completed" and cached.filename == source.filename and bool(cached.conversion_options.get("proxy")) == payload.proxy and cached.preview_filename and cached.preview_filename != cached.filename and Path(cached.preview_filename).exists():
                return cached.public()
        return enqueue(source.url, source.kind, source.container, source.quality, purpose="preview",
                       source_filename=source.filename, title=source.title or Path(source.filename).stem,conversion_options={"proxy":payload.proxy})
    return enqueue(checked_url(payload.url), "video", "mp4", payload.quality, purpose="preview")


@app.post("/api/jobs/{job_id}/clip", status_code=202)
def make_local_clip(job_id: str, payload: LocalClipRequest):
    source = jobs.get(job_id)
    if not source or source.status != "completed" or not source.filename:
        raise HTTPException(status_code=409, detail="Choose a completed download to clip.")
    if not Path(source.filename).exists():
        raise HTTPException(status_code=410, detail="The source file is no longer available.")
    if source.kind == "audio" and payload.mode != "audio":
        raise HTTPException(status_code=400, detail="An audio file can only produce audio clips.")
    batch_id = uuid4().hex
    created = [enqueue(source.url, kind, payload.video_container if kind == "video" else payload.audio_container, "best",
                       purpose="download" if payload.show_in_downloads else "clip", source_filename=source.filename, clip_start=payload.clip_start, clip_end=payload.clip_end,
                       batch_id=batch_id, title=source.title or Path(source.filename).stem)
               for kind in (["video", "audio"] if payload.mode == "both" else [payload.mode])]
    return {"batch_id": batch_id, "jobs": created}


@app.get("/api/batches/{batch_id}/archive")
def get_batch_archive(batch_id: str):
    items = [jobs.get(item["id"]) for item in jobs.list() if item["batch_id"] == batch_id and item["status"] == "completed"]
    files = [item for item in items if item and item.filename and Path(item.filename).exists()]
    if not files:
        raise HTTPException(status_code=409, detail="This batch has no completed files available.")
    return archive_files(files, "DropDL-batch.zip")


def archive_files(files, name):
    directory = DOWNLOAD_ROOT / "_archives"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{uuid4().hex}.zip"
    try:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as archive:
            for index, item in enumerate(files, 1):
                archive.write(item.filename, f"{index:04d}-{item.kind}-{Path(item.filename).name}")
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return FileResponse(path, filename=name, media_type="application/zip",
                        background=BackgroundTask(path.unlink, missing_ok=True))


@app.post("/api/jobs/{job_id}/retry", status_code=202)
def retry_job(job_id: str):
    previous = jobs.get(job_id)
    if not previous or previous.status not in {"failed", "cancelled", "paused"}:
        raise HTTPException(status_code=409, detail="Only failed, cancelled or paused tasks can be resumed.")
    if previous.source_filename and not Path(previous.source_filename).exists():
        raise HTTPException(status_code=410, detail="The clip source is no longer available.")
    job = jobs.retry(job_id)
    if not job:
        raise HTTPException(status_code=409, detail="The task is already active.")
    submit_task(job)
    return job.public()


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict[str, object]:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status in {"completed", "failed", "cancelled"}:
        return job.public()
    job.pause_requested=False
    job.cancel_event.set()
    jobs.update(job_id, interrupted=False, phase='', status="cancelled" if job.status in {"queued","paused"} else "cancelling")
    return job.public()


@app.get("/api/jobs/{job_id}/file")
def get_file(job_id: str, preview: bool = False, inline: bool = False) -> FileResponse:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "completed" or not job.filename:
        raise HTTPException(status_code=409, detail="The file is not ready yet")
    path = Path(job.preview_filename if preview and job.preview_filename else job.filename)
    if not path.exists():
        raise HTTPException(status_code=410, detail="The output file is no longer available")
    return FileResponse(path=path, filename=path.name, media_type=(mimetypes.guess_type(path.name)[0] or "application/octet-stream"),
                        content_disposition_type="inline" if preview or inline else "attachment")


@app.websocket("/api/jobs/{job_id}/events")
async def job_events(websocket: WebSocket, job_id: str) -> None:
    await websocket.accept()
    try:
        while True:
            job = jobs.get(job_id)
            if not job:
                await websocket.send_json({"error": "Job not found"})
                await websocket.close(code=4404)
                return
            await websocket.send_json(job.public())
            if job.status in {"completed", "failed", "cancelled"}:
                await websocket.close()
                return
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        return


from . import workspace
workspace.configure(sys.modules[__name__])
app.include_router(workspace.router)
from . import subscriptions
subscriptions.context=sys.modules[__name__]
app.include_router(subscriptions.router)
from . import browser_link
browser_link.context=sys.modules[__name__]
app.include_router(browser_link.router)

from . import support
support.context=sys.modules[__name__]
app.include_router(support.router)

@app.get('/api/engine-update')
def engine_update_status():
    from .engine_update import status
    return status()

@app.post('/api/engine-update/check',status_code=202)
def engine_update_check():
    from .engine_update import request_check,status
    request_check()
    return status()

# Production/web build: if frontend/dist exists, serve the SPA from FastAPI.
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
