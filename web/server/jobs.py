"""The download queue: who is waiting, what is running, and what to delete when."""
from __future__ import annotations

import logging
import queue
import re
import secrets
import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import runner
from .config import Settings
from .errors import ApiError, RunError
from .safety import safe_stem

log = logging.getLogger("dropdl.web")
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{16,40}$")
FINAL = ("done", "error", "cancelled")


@dataclass
class Job:
    id: str
    spec: runner.Spec
    owner: str
    dir: Path
    status: str = "queued"          # queued | running | done | error | cancelled
    stage: str = "queued"           # queued | preparing | downloading | processing | done
    progress: float = 0.0
    speed: float | None = None
    eta: int | None = None
    title: str = ""
    ext: str = ""
    size: int = 0
    path: Path | None = None
    error_code: str = ""
    error: str = ""
    created: float = field(default_factory=time.time)
    started: float | None = None
    finished: float | None = None
    cancel: threading.Event = field(default_factory=threading.Event)

    @property
    def filename(self) -> str:
        return f"{safe_stem(self.title or 'download')}.{self.ext}" if self.ext else ""


RunFn = Callable[[runner.Spec, Path, Settings, dict, threading.Event, Callable[[dict], None]], runner.Result]


class JobManager:
    def __init__(self, settings: Settings, engine, run_fn: RunFn | None = None):
        self.s = settings
        self.engine = engine
        self.run = run_fn or runner.run_download
        self.jobs: dict[str, Job] = {}
        self._waiting: list[str] = []
        self._queue: queue.Queue[str] = queue.Queue()
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self.completed = 0

    # -- lifecycle -------------------------------------------------------------
    def start(self) -> None:
        shutil.rmtree(self.s.jobs_dir, ignore_errors=True)       # anything left from a previous run is garbage
        self.s.jobs_dir.mkdir(parents=True, exist_ok=True)
        for n in range(self.s.max_active):
            t = threading.Thread(target=self._worker, name=f"worker-{n}", daemon=True)
            t.start()
            self._threads.append(t)
        t = threading.Thread(target=self._janitor, name="janitor", daemon=True)
        t.start()
        self._threads.append(t)

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            for job in self.jobs.values():
                job.cancel.set()
        for t in self._threads:
            t.join(timeout=3)

    # -- visitor-facing operations ---------------------------------------------
    def submit(self, spec: runner.Spec, owner: str) -> Job:
        with self._lock:
            mine = sum(1 for j in self.jobs.values() if j.owner == owner and j.status in ("queued", "running"))
            if mine >= self.s.per_ip_active:
                raise ApiError(429, "too_many_active", "You already have downloads in progress. Wait for one to finish.", 15)
            if len(self._waiting) >= self.s.max_queue:
                raise ApiError(503, "busy", "The server is busy right now. Try again in a minute.", 30)
            if self._disk_used() > self.s.disk_quota_bytes * 0.9:
                raise ApiError(503, "storage_full", "The server's storage is full for the moment. Try again in a few minutes.", 60)
            job_id = secrets.token_urlsafe(18)
            job = Job(id=job_id, spec=spec, owner=owner, dir=self.s.jobs_dir / job_id)
            job.dir.mkdir(parents=True, exist_ok=True)
            self.jobs[job_id] = job
            self._waiting.append(job_id)
            self._queue.put(job_id)
            return job

    def get(self, job_id: str) -> Job | None:
        if not _ID_RE.match(job_id or ""):
            return None
        with self._lock:
            return self.jobs.get(job_id)

    def cancel(self, job: Job) -> None:
        with self._lock:
            job.cancel.set()
            if job.status == "queued":
                if job.id in self._waiting:
                    self._waiting.remove(job.id)
                self._finish(job, "cancelled", "cancelled", "Cancelled.")

    def delete(self, job: Job) -> None:
        self.cancel(job)
        with self._lock:
            self.jobs.pop(job.id, None)
            if job.id in self._waiting:
                self._waiting.remove(job.id)
        shutil.rmtree(job.dir, ignore_errors=True)

    def view(self, job: Job) -> dict:
        with self._lock:
            position = self._waiting.index(job.id) + 1 if job.id in self._waiting else 0
            expires_in = None
            if job.status == "done" and job.finished:
                expires_in = max(0, int(job.finished + self.s.job_ttl_min * 60 - time.time()))
            return {
                "id": job.id, "status": job.status, "stage": job.stage, "progress": round(job.progress, 4),
                "speed": job.speed, "eta": job.eta, "title": job.title, "filename": job.filename, "ext": job.ext,
                "size": job.size, "kind": job.spec.kind, "queue_position": position, "expires_in": expires_in,
                "error": {"code": job.error_code, "message": job.error} if job.status in ("error", "cancelled") else None,
            }

    def stats(self) -> dict:
        with self._lock:
            return {"queued": len(self._waiting), "active": sum(1 for j in self.jobs.values() if j.status == "running"),
                    "completed": self.completed}

    # -- internals -------------------------------------------------------------
    def _finish(self, job: Job, status: str, code: str = "", message: str = "") -> None:
        with self._lock:
            job.finished = time.time()
            job.speed = job.eta = None
            if status == "done":
                job.stage, job.progress = "done", 1.0
                self.completed += 1
            else:
                job.error_code, job.error = code, message
                shutil.rmtree(job.dir, ignore_errors=True)       # nothing worth keeping from a failed job
            # Publish the final state last: readers poll `status` without the lock, so everything
            # it implies (files removed, result fields set) must already be true when it changes.
            job.status = status

    def _update(self, job: Job, fields: dict) -> None:
        job.stage = fields.get("stage", job.stage)
        job.progress = max(job.progress, float(fields.get("progress", job.progress)))
        job.speed = fields.get("speed")
        job.eta = fields.get("eta")

    def _worker(self) -> None:
        while not self._stop.is_set():
            try:
                job_id = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            with self._lock:
                job = self.jobs.get(job_id)
                if job_id in self._waiting:
                    self._waiting.remove(job_id)
                if job is None or job.status != "queued":
                    continue
                if job.cancel.is_set():
                    self._finish(job, "cancelled", "cancelled", "Cancelled.")
                    continue
                job.status, job.stage, job.started = "running", "preparing", time.time()
            try:
                result = self.run(job.spec, job.dir, self.s, self.engine.env(), job.cancel, lambda f, j=job: self._update(j, f))
            except RunError as exc:
                self._finish(job, "cancelled" if exc.code == "cancelled" else "error", exc.code, exc.message)
            except Exception:                                    # noqa: BLE001 - a bug must not kill the worker thread
                log.exception("job %s crashed", job.id[:6])
                self._finish(job, "error", "failed", "The download failed unexpectedly.")
            else:
                with self._lock:
                    job.title, job.ext, job.size, job.path = result.title, result.ext, result.size, result.path
                    self._finish(job, "done")

    def _disk_used(self) -> int:
        return runner.dir_size(self.s.jobs_dir)

    def _janitor(self) -> None:
        while not self._stop.wait(20):
            try:
                self.sweep()
            except Exception:                                    # noqa: BLE001
                log.exception("sweep failed")

    def sweep(self, now: float | None = None) -> None:
        """Delete expired files, stop stuck jobs, enforce the disk quota, remove stray folders."""
        now = time.time() if now is None else now
        ttl = self.s.job_ttl_min * 60
        with self._lock:
            for job in list(self.jobs.values()):
                if job.status in FINAL:
                    if now - (job.finished or job.created) > ttl:
                        self.jobs.pop(job.id, None)
                        shutil.rmtree(job.dir, ignore_errors=True)
                elif job.status == "running" and job.started and now - job.started > self.s.job_timeout_sec + 60:
                    job.cancel.set()
                elif job.status == "queued" and now - job.created > 3600:
                    self.cancel(job)
            if self._disk_used() > self.s.disk_quota_bytes:
                finished = sorted((j for j in self.jobs.values() if j.status == "done"), key=lambda j: j.finished or 0)
                for job in finished:
                    if self._disk_used() <= self.s.disk_quota_bytes * 0.8:
                        break
                    self.jobs.pop(job.id, None)
                    shutil.rmtree(job.dir, ignore_errors=True)
            known = set(self.jobs)
            try:
                for folder in self.s.jobs_dir.iterdir():
                    if folder.is_dir() and folder.name not in known:
                        shutil.rmtree(folder, ignore_errors=True)
            except OSError:
                pass
