"""The yt-dlp "engine": sites break every few weeks, so the server keeps its own up-to-date copy.

Updates are installed into a fresh, timestamped folder (never over a running copy), checked, and only then made current.
A bad release can never take the server down: if the new copy doesn't start, it is thrown away.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from .config import Settings

log = logging.getLogger("dropdl.web")
_PASS_ENV = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP", "TMPDIR",
             "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "LD_LIBRARY_PATH")
_VERSION_RE = re.compile(r"^\d{4}\.\d{2}\.\d{2}(\.\d+)?$")


class Engine:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.root = settings.data_dir / "engine"
        self._pointer = self.root / "current"
        self._version: str | None = None
        self._lock = threading.Lock()

    # -- which copy is current -------------------------------------------------
    def path(self) -> Path | None:
        try:
            name = self._pointer.read_text().strip()
        except OSError:
            return None
        folder = self.root / name
        return folder if re.fullmatch(r"\d{10}", name) and folder.is_dir() else None

    def env(self) -> dict[str, str]:
        """A minimal environment for yt-dlp subprocesses: no secrets from the server's own environment leak into them."""
        env = {k: os.environ[k] for k in _PASS_ENV if k in os.environ}
        home = self.settings.data_dir / "home"
        home.mkdir(parents=True, exist_ok=True)
        env.update(HOME=str(home), USERPROFILE=str(home), PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        current = self.path()
        if current:
            env["PYTHONPATH"] = str(current)
        return env

    def version(self) -> str | None:
        return self._version

    def refresh_version(self) -> str | None:
        try:
            out = subprocess.run([sys.executable, "-P", "-m", "yt_dlp", "--version"], env=self.env(), capture_output=True,
                                 text=True, timeout=30, cwd=str(self._workdir()))
            value = out.stdout.strip()
            self._version = value if out.returncode == 0 and _VERSION_RE.match(value) else None
        except (OSError, subprocess.SubprocessError):
            self._version = None
        return self._version

    def _workdir(self) -> Path:
        work = self.settings.data_dir / "work"
        work.mkdir(parents=True, exist_ok=True)
        return work

    # -- updating --------------------------------------------------------------
    def update(self) -> str | None:
        """Install the newest yt-dlp. Returns the new version, or None if nothing changed. Raises RuntimeError on failure."""
        with self._lock:
            self.root.mkdir(parents=True, exist_ok=True)
            taken = [int(p.name) for p in self.root.iterdir() if p.is_dir() and re.fullmatch(r"\d{10}", p.name)]
            name = str(max(int(time.time()), max(taken, default=0) + 1)).zfill(10)   # never reuse a folder that may be in use
            target = self.root / name
            shutil.rmtree(target, ignore_errors=True)
            run = subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "--no-deps",
                                  "--upgrade", "--target", str(target), "yt-dlp"], capture_output=True, text=True, timeout=240,
                                 cwd=str(self._workdir()))
            if run.returncode != 0:
                shutil.rmtree(target, ignore_errors=True)
                raise RuntimeError("pip could not install yt-dlp")
            env = self.env()
            env["PYTHONPATH"] = str(target)
            check = subprocess.run([sys.executable, "-P", "-m", "yt_dlp", "--version"], env=env, capture_output=True, text=True,
                                   timeout=30, cwd=str(self._workdir()))
            version = check.stdout.strip()
            if check.returncode != 0 or not _VERSION_RE.match(version):
                shutil.rmtree(target, ignore_errors=True)
                raise RuntimeError("the new yt-dlp did not start")
            if version == self._version:
                shutil.rmtree(target, ignore_errors=True)
                return None
            tmp = self._pointer.with_suffix(".tmp")
            tmp.write_text(name)
            os.replace(tmp, self._pointer)
            self._version = version
            self._prune(keep=name)
            return version

    def _prune(self, keep: str) -> None:
        folders = sorted(p for p in self.root.iterdir() if p.is_dir() and re.fullmatch(r"\d{10}", p.name))
        for old in folders[:-2]:
            if old.name != keep and time.time() - old.stat().st_mtime > 3600:   # a running job may still be using it
                shutil.rmtree(old, ignore_errors=True)

    def run_forever(self, stop: threading.Event) -> None:
        hours = self.settings.engine_update_hours
        self.refresh_version()
        if hours <= 0:
            return
        stop.wait(20)                                         # let the server come up first
        while not stop.is_set():
            try:
                new = self.update()
                log.info("engine: %s", f"updated to {new}" if new else "already current")
            except Exception as exc:                          # noqa: BLE001 - never let the updater crash the thread
                log.warning("engine update failed: %s", exc)
            stop.wait(hours * 3600)
