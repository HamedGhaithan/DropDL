from __future__ import annotations

from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from threading import Event, Lock
import json
import os
import logging
import math
from time import time
from typing import Any
from uuid import uuid4


@dataclass
class Job:
    id: str
    url: str
    kind: str
    container: str
    quality: str
    directory: str
    organization: dict = field(default_factory=dict)
    collection: str = ""
    destination: str | None = None
    site: str = ""
    speed_limit_kbps: int = 0
    auto_retries: int = 0
    priority: int = 0
    scheduled_at: float = 0
    pause_requested: bool = False
    conversion_options: dict = field(default_factory=dict)
    subtitle_languages: list = field(default_factory=list)
    embed_metadata: bool = False
    # 2.0: per-task download extras (codec preference, SponsorBlock, cover art,
    # audio bitrate) and a network snapshot taken when the task starts.
    download_options: dict = field(default_factory=dict)
    network: dict = field(default_factory=dict)
    retry_at: float = 0
    stalls: int = 0
    cookie_file: str | None = None
    attempt: int = 1
    purpose: str = "download"
    preview_filename: str | None = None
    thumbnail: str | None = None
    title: str = ""
    batch_id: str | None = None
    clip_start: float | None = None
    clip_end: float | None = None
    source_filename: str | None = None
    interrupted: bool = False
    phase: str = ""
    status: str = "queued"
    percent: float = 0.0
    downloaded_bytes: int | None = None
    total_bytes: int | None = None
    speed: float | None = None
    eta: int | None = None
    filename: str | None = None
    error: str | None = None
    created_at: float = field(default_factory=time)
    updated_at: float = field(default_factory=time)
    cancel_event: Event = field(default_factory=Event, repr=False)

    def public(self) -> dict[str, Any]:
        from .task_errors import classify
        return {
            "id": self.id,
            "site": self.site,
            "destination": self.destination,
            "output_path": self.filename,
            "priority": self.priority,
            "scheduled_at": self.scheduled_at,
            "conversion_options": self.conversion_options,
            "subtitle_languages": self.subtitle_languages,
            "embed_metadata": self.embed_metadata,
            "download_options": self.download_options,
            "retry_at": self.retry_at,
            "auto_retries": self.auto_retries,
            "attempt": self.attempt,
            "speed_limit_kbps": self.speed_limit_kbps,
            "url": self.url,
            "kind": self.kind,
            "container": self.container,
            "quality": self.quality,
            "purpose": self.purpose,
            "preview_ready": bool(self.preview_filename),
            "title": self.title,
            "thumbnail": self.thumbnail,
            "batch_id": self.batch_id,
            "clip_start": self.clip_start,
            "clip_end": self.clip_end,
            "status": self.status,
            "phase": self.phase,
            "interrupted": self.interrupted,
            "percent": self.percent,
            "downloaded_bytes": self.downloaded_bytes,
            "total_bytes": self.total_bytes,
            "speed": self.speed,
            "eta": self.eta,
            "filename": Path(self.filename).name if self.filename else None,
            "error": self.error,
            "error_code": classify(self.error),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = Lock()
        self._path: Path | None = None
        self._last_save = 0.0
        self.persistence_error = None
        self.restored_from_backup = False
        self.recovered_count = 0
        # Monotonic change counter: clients skip re-rendering an unchanged queue.
        self.revision = 0

    def create(self, *, url: str, kind: str, container: str, quality: str, directory: str, **options: Any) -> Job:
        job = Job(
            id=uuid4().hex,
            url=url,
            kind=kind,
            container=container,
            quality=quality,
            directory=directory,
            **options,
        )
        with self._lock:
            self._jobs[job.id] = job
            self.revision += 1
            self._save_locked(force=True)
        return job

    def create_many(self, specifications: list[dict[str, Any]]) -> list[Job]:
        # Construct everything before changing the queue; persist a batch once.
        created = [Job(id=uuid4().hex, **specification) for specification in specifications]
        with self._lock:
            self._jobs.update({job.id: job for job in created})
            self.revision += 1
            self._save_locked(force=True)
        return created

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [job.public() for job in reversed(list(self._jobs.values()))]

    def snapshot(self) -> tuple[int, list[dict[str, Any]]]:
        """Return the revision and the public queue atomically."""
        with self._lock:
            return self.revision, [job.public() for job in reversed(list(self._jobs.values()))]

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **changes: Any) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            previous_status=job.status
            for key, value in changes.items():
                setattr(job, key, value)
            job.updated_at = time()
            self.revision += 1
            self._save_locked(force=job.status!=previous_status or job.status in {"completed", "failed", "cancelled", "paused", "queued"})
            return job

    def clear(self, include_active: bool = False) -> dict[str, int]:
        with self._lock:
            ids = [key for key, job in self._jobs.items()
                   if include_active or job.status in {"completed", "failed", "cancelled"}]
            stopped = 0
            for key in ids:
                job = self._jobs.pop(key)
                if job.status not in {"completed", "failed", "cancelled", "paused"}:
                    job.cancel_event.set()
                    stopped += 1
            self.revision += 1
            self._save_locked(force=True)
            return {"removed": len(ids), "stopped": stopped, "remaining": len(self._jobs)}

    def remove_selected(self, identities):
        with self._lock:
            removed, missing = [], []
            stopped = 0
            for identity in dict.fromkeys(identities):
                job = self._jobs.pop(identity, None)
                if job is None:
                    missing.append(identity)
                    continue
                job.cancel_event.set()
                if job.status not in {"completed", "failed", "cancelled", "paused"}:
                    stopped += 1
                removed.append(identity)
            self.revision += 1
            self._save_locked(force=True)
            return {"removed": removed, "missing": missing, "stopped": stopped}

    def update_attempt(self, attempt: Job, **changes):
        with self._lock:
            if self._jobs.get(attempt.id) is not attempt: return None
            for key, value in changes.items(): setattr(attempt, key, value)
            attempt.updated_at = time()
            self.revision += 1
            self._save_locked(force=attempt.status in {"completed", "failed", "cancelled", "paused"})
            if changes.get("status") == "completed":
                from .media_library import remember_job
                remember_job(attempt)
            return attempt

    def retry(self, job_id: str):
        with self._lock:
            previous = self._jobs.get(job_id)
            if not previous or previous.status not in {"failed", "cancelled", "paused"}: return None
            # Keep the old worker's cancellation event set and ignore its late updates.
            previous.cancel_event.set()
            job = replace(previous, status="queued", error=None, speed=None, eta=None,
                          filename=None, preview_filename=None,
                          pause_requested=False, interrupted=False, auto_retries=0, retry_at=0, phase="resuming", attempt=previous.attempt + 1, updated_at=time(), cancel_event=Event())
            self._jobs[job_id] = job
            self.revision += 1
            self._save_locked(force=True)
            return job

    def recover_interrupted(self, enabled=True):
        if not enabled:return []
        recovered=[]
        for record in self.list():
            if record.get('interrupted') and record['status']=='paused' and record['purpose']=='download':
                replacement=self.retry(record['id'])
                if replacement:recovered.append(replacement)
        return recovered

    def checkpoint_for_shutdown(self):
        """Record restart intent before workers are asked to stop."""
        with self._lock:
            for job in self._jobs.values():
                if job.status not in {"completed", "failed", "cancelled", "paused", "cancelling", "pausing"}:
                    job.interrupted = True
                    job.pause_requested = True
                    job.cancel_event.set()
            self.revision += 1
            self._save_locked(force=True)

    def enable_persistence(self, path: Path):
        with self._lock:
            self._path = path
            valid = {item.name for item in fields(Job)} - {"cancel_event"}
            records = None
            for candidate in (path, path.with_suffix(".bak")):
                try:
                    value = json.loads(candidate.read_text(encoding="utf-8"))
                    if not isinstance(value, list): raise ValueError("Queue must be a list")
                    records = value
                    self.restored_from_backup = candidate != path
                    break
                except FileNotFoundError: continue
                except (OSError, ValueError, TypeError):
                    logging.getLogger('dropdl.queue').exception('Could not read queue checkpoint: %s', candidate.name)
            if records is not None:
                for record in records:
                    try:
                        if not isinstance(record, dict): raise ValueError('Invalid queue record')
                        job = Job(**{k: v for k, v in record.items() if k in valid})
                        if not all(isinstance(getattr(job,key),str) for key in ('id','url','kind','container','quality','directory','purpose','status','title')) or not job.id:raise ValueError('Invalid task fields')
                        if not isinstance(job.conversion_options,dict) or not isinstance(job.organization,dict):raise ValueError('Invalid task options')
                        if not isinstance(job.percent,(int,float)) or not math.isfinite(job.percent):job.percent=0
                        if job.error is not None and not isinstance(job.error,str):raise ValueError('Invalid error')
                        if job.filename is not None and not isinstance(job.filename,str):raise ValueError('Invalid file path')
                        if job.status == "cancelling":
                            job.status = "cancelled";job.interrupted = False
                        elif job.status == "pausing":
                            job.status = "paused";job.interrupted = False
                        elif job.status not in {"completed", "failed", "cancelled", "paused"}:
                            job.status = "paused";job.interrupted = True
                        # Migrate older releases without confusing user cancellation.
                        if job.status == "cancelled" and (job.interrupted or job.error and 'Interrupted by an app restart' in job.error):
                            job.status = "paused";job.interrupted = True
                        if not isinstance(job.download_options,dict):job.download_options={}
                        if not isinstance(job.network,dict):job.network={}
                        if job.interrupted:
                            self.recovered_count += 1
                            job.phase = "interrupted";job.speed = None;job.eta = None
                            job.error = None
                        self._jobs[job.id] = job
                        if job.status == "completed":
                            from .media_library import remember_job
                            remember_job(job)
                    except (ValueError, TypeError, KeyError, OSError):
                        logging.getLogger('dropdl.queue').exception('Skipped an invalid task record')
            self._save_locked(force=True)

    def _save_locked(self, force=False):
        if not self._path or not force and time() - self._last_save < 1: return
        temporary = self._path.with_suffix(".tmp")
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            records = [{item.name: getattr(job, item.name) for item in fields(Job) if item.name != "cancel_event"}
                       for job in self._jobs.values()]
            data = json.dumps(records, ensure_ascii=False, allow_nan=False)
            with temporary.open('w', encoding='utf-8') as stream:
                stream.write(data);stream.flush();os.fsync(stream.fileno())
            # Keep the last readable checkpoint; never back up a corrupt primary.
            try:
                previous = self._path.read_text(encoding='utf-8')
                if isinstance(json.loads(previous), list):
                    backup = self._path.with_suffix('.bak.tmp')
                    with backup.open('w', encoding='utf-8') as stream:
                        stream.write(previous);stream.flush();os.fsync(stream.fileno())
                    backup.replace(self._path.with_suffix('.bak'))
            except (FileNotFoundError, ValueError, TypeError): pass
            temporary.replace(self._path)
            self._last_save = time()
            self.persistence_error = None
        except (OSError, ValueError, TypeError) as exc:
            message = str(exc)
            if message != self.persistence_error:
                logging.getLogger('dropdl.queue').exception('Queue checkpoint failed; active downloads remain running')
            self.persistence_error = message
        finally:
            try: temporary.unlink(missing_ok=True)
            except OSError: pass


jobs = JobStore()
