"""Shared fixtures for the web version's tests. Nothing here touches the network or a real yt-dlp."""
import dataclasses
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import config, runner  # noqa: E402

PUBLIC_IP = "93.184.216.34"


@pytest.fixture
def settings(tmp_path):
    """Settings that write to a temp folder, never update yt-dlp, and ignore proxy headers."""
    return dataclasses.replace(config.load(), data_dir=tmp_path / "data", engine_update_hours=0, trusted_proxy_hops=0,
                               youtube="off", proxy="", allowed_sites=(), blocked_sites=())


@pytest.fixture(autouse=True)
def no_dns(monkeypatch):
    """Every hostname resolves to a public address unless a test says otherwise."""
    from server import safety
    monkeypatch.setattr(safety, "_resolve", lambda host, port: {PUBLIC_IP})


class FakeEngine:
    def env(self):
        return {}

    def version(self):
        return "2026.01.01"


def spec(**kw):
    base = dict(url="https://vimeo.com/123", kind="video", height=720, fmt="mp4", start=None, end=None)
    base.update(kw)
    return runner.Spec(**base)


def fake_run(sp, outdir, settings, env, cancel, on_update):
    """Pretends to download: reports progress, writes a 1000-byte file, returns it."""
    outdir.mkdir(parents=True, exist_ok=True)
    on_update({"stage": "downloading", "progress": 0.4, "speed": 1000.0, "eta": 3})
    path = outdir / f"media.{sp.fmt}"
    path.write_bytes(b"0123456789" * 100)
    on_update({"stage": "processing", "progress": 0.95, "speed": None, "eta": None})
    return runner.Result(path=path, title='A "weird" / title: ok?', ext=sp.fmt, size=path.stat().st_size)


def fake_info(url, settings, env):
    return {"url": url, "title": "Demo", "uploader": "Someone", "site": "Vimeo", "duration": 100.0, "thumbnail": None,
            "heights": [360, 720], "sizes": {"360": 1000, "720": 2000}, "audio_size": 500, "has_video": True,
            "has_audio": True, "too_long": False}


def wait_for(condition, timeout=5.0, step=0.02):
    end = time.time() + timeout
    while time.time() < end:
        value = condition()
        if value:
            return value
        time.sleep(step)
    raise AssertionError("condition not met in time")


class Gate:
    """A run function that blocks until released (or cancelled), to test queues and cancellation."""

    def __init__(self):
        self.release = threading.Event()
        self.started = 0

    def __call__(self, sp, outdir, settings, env, cancel, on_update):
        self.started += 1
        while not self.release.wait(0.02):
            if cancel.is_set():
                raise runner.RunError("cancelled", "Cancelled.")
        return fake_run(sp, outdir, settings, env, cancel, on_update)
