"""Everything that touches yt-dlp.

Each download is a separate subprocess with OS resource limits (Linux) and a watchdog thread that can kill it for
timeout, size, or cancellation. The command line is built here from validated values only; visitor input never becomes
a flag (the link goes after `--`).
"""
from __future__ import annotations

import collections
import json
import math
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import Settings
from .errors import ApiError, RunError

VIDEO_FORMATS = ("mp4", "webm", "mkv")
AUDIO_FORMATS = ("mp3", "m4a", "opus", "flac", "wav")
OUTPUT_EXT = frozenset(VIDEO_FORMATS + AUDIO_FORMATS)
MIME = {"mp4": "video/mp4", "webm": "video/webm", "mkv": "video/x-matroska", "mp3": "audio/mpeg", "m4a": "audio/mp4",
        "opus": "audio/ogg", "flac": "audio/flac", "wav": "audio/wav"}
MIB = 1024 * 1024
PROGRESS_TEMPLATE = ("download:__P__%(progress.status)s|%(progress.downloaded_bytes)s|%(progress.total_bytes)s|"
                     "%(progress.total_bytes_estimate)s|%(progress.speed)s|%(progress.eta)s")
_P = re.compile(r"__P__(\w+)\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|(.*)$")
_POST_TAGS = ("[Merger]", "[ExtractAudio]", "[VideoRemuxer]", "[VideoConvertor]", "[Metadata]", "[EmbedThumbnail]",
              "[ThumbnailsConvertor]", "[FixupM4a]", "[FixupM3u8]", "[FixupTimestamp]")
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


@dataclass(frozen=True)
class Spec:
    url: str
    kind: str            # "video" | "audio"
    height: int | None   # video only
    fmt: str
    start: float | None = None
    end: float | None = None


def _num(x: float) -> str:
    return f"{x:.3f}".rstrip("0").rstrip(".")


def normalise_spec(url: str, kind: str | None, height: int | None, fmt: str | None,
                   start: float | None, end: float | None, settings: Settings) -> Spec:
    """Turn what the browser asked for into something safe. Anything out of range is clamped or rejected."""
    kind = (kind or "video").lower()
    if kind not in ("video", "audio"):
        raise ApiError(400, "bad_request", "Choose video or audio.")
    fmt = (fmt or ("mp4" if kind == "video" else "mp3")).lower()
    if fmt not in (VIDEO_FORMATS if kind == "video" else AUDIO_FORMATS):
        raise ApiError(400, "bad_format", "That format isn't available.")
    h = None
    if kind == "video":
        h = int(height) if height else settings.default_height
        h = max(144, min(settings.max_height, h))
    if (start is None) != (end is None):
        raise ApiError(400, "bad_clip", "Set both a start and an end time, or neither.")
    if start is not None:
        if not (math.isfinite(start) and math.isfinite(end)) or start < 0 or end <= start:
            raise ApiError(400, "bad_clip", "The end time must be after the start time.")
        if end - start > settings.max_clip_min * 60:
            raise ApiError(400, "bad_clip", f"You can trim up to {settings.max_clip_min} minutes.")
        if end > 48 * 3600:
            raise ApiError(400, "bad_clip", "That time is too far into the video.")
    return Spec(url=url, kind=kind, height=h, fmt=fmt, start=start, end=end)


# ----------------------------------------------------------------------------- command lines
def _js_runtime_args() -> list[str]:
    """YouTube's checks need a JavaScript runtime. yt-dlp only enables Deno by default, so switch Node on when it exists."""
    return ["--js-runtimes", "node"] if shutil.which("node") else []


def _copy_cookies(settings: Settings, destination: Path) -> str | None:
    """yt-dlp rewrites the cookie file it is given, so every run gets its own private copy and the original is never touched."""
    if not settings.cookies_file:
        return None
    try:
        shutil.copyfile(settings.cookies_file, destination)
        if os.name == "posix":
            os.chmod(destination, 0o600)
    except OSError:
        raise RunError("cookies_missing", "The saved cookies file can't be read.") from None
    return str(destination)


def _classify(text: str, code: int | None, settings: Settings) -> tuple[str, str]:
    error_code, message = classify_error(text, code)
    if error_code == "youtube_blocked" and settings.cookies_file:
        return "youtube_cookies", "YouTube rejected the saved cookies. Export a fresh cookies.txt from a signed-in browser and restart."
    return error_code, message


def _common(settings: Settings, cookies: str | None = None) -> list[str]:
    args = [sys.executable, "-P", "-m", "yt_dlp", "--ignore-config",
            "--use-extractors", "default,-generic",          # only sites with a dedicated extractor: no "fetch any URL"
            "--no-playlist", "--playlist-items", "1",
            "--socket-timeout", "20", "--extractor-retries", "2",
            "--cache-dir", str(settings.data_dir / "cache"), "--no-mtime"]
    args += _js_runtime_args()
    if cookies:
        args += ["--cookies", cookies]
    if settings.proxy:
        args += ["--proxy", settings.proxy]
    return args


def build_info_args(url: str, settings: Settings, cookies: str | None = None) -> list[str]:
    return _common(settings, cookies) + ["--lazy-playlist", "--skip-download", "--dump-single-json", "--no-warnings", "--", url]


def build_download_args(spec: Spec, settings: Settings, outdir: Path, cookies: str | None = None) -> list[str]:
    # A trimmed download only fetches the section, so the source may be much longer than a full download may be.
    source_cap = (6 * 3600) if spec.start is not None else settings.max_duration_min * 60
    clip = spec.start is not None
    args = _common(settings, cookies) + [
        "--retries", "5", "--fragment-retries", "5", "--concurrent-fragments", "2", "--max-downloads", "1",
        "--match-filters", f"!is_live & duration<=?{source_cap}",
        "--newline", "--progress", "--progress-template", PROGRESS_TEMPLATE,
        "--write-info-json", "-P", str(outdir), "-o", "media.%(ext)s", "--embed-metadata",
    ]
    if spec.kind == "video":
        h, fits = spec.height, ("" if clip else f"[filesize<?{settings.max_filesize_mb}M][filesize_approx<?{settings.max_filesize_mb}M]")
        sort = {"mp4": "res,vcodec:h264,acodec:aac", "webm": "res,vcodec:vp9,acodec:opus"}.get(spec.fmt, "res")
        args += ["-f", f"bv*[height<=?{h}]{fits}+ba/b[height<=?{h}]{fits}", "-S", sort, "--merge-output-format", spec.fmt]
        if spec.fmt in ("mp4", "mkv"):
            args += ["--remux-video", spec.fmt]
    else:
        args += ["-f", "ba/b", "-x", "--audio-format", spec.fmt]
        if spec.fmt == "mp3":
            args += ["--audio-quality", "192K"]
        if spec.fmt in ("mp3", "m4a"):
            args += ["--embed-thumbnail", "--convert-thumbnails", "jpg"]
    if clip:
        args += ["--download-sections", f"*{_num(spec.start)}-{_num(spec.end)}", "--force-keyframes-at-cuts"]
    else:
        args += ["--max-filesize", f"{settings.max_filesize_mb}M"]
    return args + ["--", spec.url]


# ----------------------------------------------------------------------------- errors
# Order matters: the specific reasons come first, because "not available" also appears in many of them.
_RULES: list[tuple[tuple[str, ...], str, str]] = [
    (("not a bot", "sign in to confirm", "po token", "this helps protect our community"), "youtube_blocked",
     "YouTube blocks most free web servers. Try the desktop app, or another site."),
    (("larger than max-filesize", "max-filesize"), "too_large", "That file is larger than this server allows."),
    (("does not pass filter",), "too_long", "That video is live or longer than this server allows."),
    (("unsupported url", "no suitable extractor"), "unsupported", "This site isn't supported by the web version."),
    (("drm",), "drm", "That content is DRM-protected and can't be downloaded."),
    (("geo restrict", "geo-restrict", "in your country", "from your location", "your region"), "geo",
     "That content isn't available in this server's region."),
    (("requested format is not available", "no video formats found"), "no_format",
     "That quality isn't available. Try another."),
    (("private video", "video is private", "is private", "video unavailable", "this video is unavailable", "has been removed",
      "members-only", "login required", "requires authentication", "account is private", "not available"), "private",
     "That video is private or unavailable."),
    (("http error 429", "too many requests"), "site_rate_limited", "The site is limiting this server. Try again later."),
    (("timed out", "connection reset", "name or service not known", "temporary failure in name resolution", "urlopen error",
      "network is unreachable", "unable to download"), "network", "Couldn't reach the site. Try again."),
]


def _detail(text: str) -> str:
    """The last error line with links, paths and colour codes removed, short enough to show."""
    lines = [_ANSI.sub("", ln).strip() for ln in text.splitlines() if ln.strip()]
    pick = next((ln for ln in reversed(lines) if ln.startswith("ERROR:")), lines[-1] if lines else "")
    pick = re.sub(r"^ERROR:\s*(\[[^\]]+\]\s*[\w\-]*:?\s*)?", "", pick)
    pick = re.sub(r"https?://\S+", "<link>", pick)
    pick = re.sub(r"[A-Za-z]:\\\S+|(?:/[\w.\-@+]+){2,}", "<path>", pick)
    return pick[:180]


def classify_error(text: str, returncode: int | None = None) -> tuple[str, str]:
    low = text.lower()
    for needles, code, message in _RULES:
        if any(n in low for n in needles):
            return code, message
    if returncode in (-25, 153):                               # killed by SIGXFSZ: wrote past the file size limit
        return "too_large", "That file is larger than this server allows."
    detail = _detail(text)
    return "failed", f"The download failed. {detail}".strip()


# ----------------------------------------------------------------------------- progress
def _f(value: str) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


class Tracker:
    """Turns yt-dlp's output lines into one steady 0-to-1 progress value.

    A video is usually two downloads (picture, then sound) followed by a merge, so each stream gets a slice of the bar and
    the value never moves backwards.
    """
    WEIGHTS = {"video": (0.80, 0.15), "audio": (0.90, 0.05)}

    def __init__(self, kind: str):
        self.kind = kind if kind in self.WEIGHTS else "video"
        self.stream = 0
        self.stage = "preparing"
        self.progress = 0.0
        self.speed: float | None = None
        self.eta: int | None = None

    def feed(self, line: str) -> bool:
        match = _P.search(line)
        if match and self.stage == "processing":
            return False
        if match:
            status, done, total, estimate, speed, eta = match.groups()
            first, second = self.WEIGHTS[self.kind]
            low, span = (0.0, first) if self.stream == 0 else (first, second)
            d, t = _f(done), _f(total) or _f(estimate)
            if status == "finished":
                self.progress = max(self.progress, low + span)
                self.stream += 1
            elif d is not None and t:
                self.progress = max(self.progress, low + span * min(1.0, d / t))
            self.stage = "downloading"
            self.speed = _f(speed)
            e = _f(eta)
            self.eta = int(e) if e is not None else None
            return True
        if line.lstrip().startswith(_POST_TAGS):
            self.stage, self.progress, self.speed, self.eta = "processing", max(self.progress, 0.95), None, None
            return True
        return False

    def snapshot(self) -> dict:
        return {"stage": self.stage, "progress": round(self.progress, 4), "speed": self.speed, "eta": self.eta}


# ----------------------------------------------------------------------------- subprocess helpers
def dir_size(path: Path) -> int:
    total = 0
    try:
        for entry in os.scandir(path):
            try:
                total += entry.stat().st_size if entry.is_file() else dir_size(Path(entry.path))
            except OSError:
                pass
    except OSError:
        pass
    return total


def _limits(settings: Settings) -> Callable[[], None]:
    import resource                                             # POSIX only; imported lazily so tests run anywhere
    fsize = int(settings.max_filesize_bytes * 2.5) + 64 * MIB
    cpu = settings.job_timeout_sec + 30

    def apply() -> None:
        resource.setrlimit(resource.RLIMIT_FSIZE, (fsize, fsize))   # the OS stops any write past this size
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        os.umask(0o077)
    return apply


def _spawn(cmd: list[str], cwd: Path, env: dict[str, str], settings: Settings) -> subprocess.Popen:
    kwargs: dict = dict(cwd=str(cwd), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                        text=True, encoding="utf-8", errors="replace", bufsize=1)
    if os.name == "posix":
        kwargs.update(start_new_session=True, preexec_fn=_limits(settings))
    else:
        kwargs.update(creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    return subprocess.Popen(cmd, **kwargs)


def _kill(proc: subprocess.Popen) -> None:
    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGKILL)                  # yt-dlp and any ffmpeg it started
        else:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        try:
            proc.kill()
        except OSError:
            pass


@dataclass
class Result:
    path: Path
    title: str
    ext: str
    size: int


def _find_output(folder: Path) -> Path | None:
    files = [p for p in folder.iterdir()
             if p.is_file() and p.name.startswith("media.") and p.suffix.lower().lstrip(".") in OUTPUT_EXT]
    return max(files, key=lambda p: p.stat().st_size, default=None)


def run_download(spec: Spec, outdir: Path, settings: Settings, env: dict[str, str], cancel: threading.Event,
                 on_update: Callable[[dict], None]) -> Result:
    outdir.mkdir(parents=True, exist_ok=True)
    cookies = _copy_cookies(settings, outdir / "cookies.txt")
    proc = _spawn(build_download_args(spec, settings, outdir, cookies), outdir, env, settings)
    reason: dict[str, str] = {}
    stop = threading.Event()
    size_limit = int(settings.max_filesize_bytes * 2.3) + 16 * MIB

    def watchdog() -> None:
        started = time.monotonic()
        while not stop.wait(0.5):
            if proc.poll() is not None:
                return
            if cancel.is_set():
                reason["why"] = "cancelled"
            elif time.monotonic() - started > settings.job_timeout_sec:
                reason["why"] = "timeout"
            elif dir_size(outdir) > size_limit:
                reason["why"] = "too_large"
            else:
                continue
            _kill(proc)
            return

    threading.Thread(target=watchdog, daemon=True).start()
    tail: collections.deque[str] = collections.deque(maxlen=60)
    tracker = Tracker(spec.kind)
    try:
        for raw in proc.stdout:                                  # type: ignore[union-attr]
            line = raw.rstrip()
            tail.append(line)
            if tracker.feed(line):
                on_update(tracker.snapshot())
        code = proc.wait()
    finally:
        stop.set()
        if proc.poll() is None:
            _kill(proc)
        try:
            proc.stdout.close()                                  # type: ignore[union-attr]
        except OSError:
            pass
    why = reason.get("why")
    if why == "cancelled":
        raise RunError("cancelled", "Cancelled.")
    if why == "timeout":
        raise RunError("timeout", "That took too long and was stopped.")
    if why == "too_large":
        raise RunError("too_large", "That file is larger than this server allows.")
    output = _find_output(outdir)
    if output and output.stat().st_size > settings.max_filesize_bytes:   # e.g. a long recording converted to WAV
        raise RunError("too_large", "That file is larger than this server allows.")
    if code in (0, 101) and output:
        title = ""
        try:
            title = str(json.loads((outdir / "media.info.json").read_text("utf-8")).get("title") or "")[:300]
        except (OSError, ValueError):
            pass
        for item in outdir.iterdir():                            # keep only the finished file
            if item != output:
                try:
                    item.unlink() if item.is_file() else None
                except OSError:
                    pass
        return Result(path=output, title=title, ext=output.suffix.lower().lstrip("."), size=output.stat().st_size)
    error_code, message = _classify("\n".join(tail), code, settings)
    raise RunError(error_code, message)


# ----------------------------------------------------------------------------- link lookup
def _fsize(f: dict, duration: float | None) -> int | None:
    n = f.get("filesize") or f.get("filesize_approx")
    if not n and f.get("tbr") and duration:
        n = f["tbr"] * 1000 / 8 * duration
    return int(n) if n else None


def _is_video(f: dict) -> bool:
    """Some sites (archive.org) leave the codec blank but still give a height: blank means "probably", "none" means no."""
    return f.get("vcodec") != "none" and bool(f.get("height") or f.get("vcodec"))


def _has_audio(f: dict) -> bool:
    return f.get("acodec") != "none"


def _estimates(formats: list[dict], duration: float | None, max_height: int) -> tuple[dict[str, int | None], int | None]:
    videos = [f for f in formats if _is_video(f) and f.get("height")]
    audios = [f for f in formats if f.get("vcodec") == "none" and _has_audio(f)]
    best_audio = max(audios, key=lambda f: f.get("abr") or f.get("tbr") or 0, default=None)
    audio_size = _fsize(best_audio, duration) if best_audio else None
    sizes: dict[str, int | None] = {}
    for h in sorted({int(f["height"]) for f in videos if int(f["height"]) <= max_height}):
        pick = max((f for f in videos if int(f["height"]) == h),
                   key=lambda f: (str(f.get("vcodec") or "").startswith("avc"), f.get("tbr") or 0, f.get("filesize") or 0))
        size = _fsize(pick, duration)
        sizes[str(h)] = None if size is None else size + (0 if _has_audio(pick) else (audio_size or 0))
    return sizes, audio_size


_EMAIL = re.compile(r"\S+@\S+\.\S+")


def _person(name: object) -> str:
    """Uploader names are shown on the page; some sites expose an email address there, which isn't ours to display."""
    text = str(name or "").strip()
    return "" if _EMAIL.search(text) else text[:120]


def fetch_info(url: str, settings: Settings, env: dict[str, str], timeout: int = 45) -> dict:
    work = settings.data_dir / "work"
    work.mkdir(parents=True, exist_ok=True)
    cookie_copy = work / f"info-{secrets.token_hex(6)}.txt"
    try:
        try:
            cookies = _copy_cookies(settings, cookie_copy)
        except RunError as exc:
            raise ApiError(500, exc.code, exc.message) from None
        done = subprocess.run(build_info_args(url, settings, cookies), env=env, cwd=str(work), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise ApiError(504, "timeout", "The site took too long to answer.") from None
    except OSError:
        raise ApiError(500, "failed", "The server could not start the downloader.") from None
    finally:
        cookie_copy.unlink(missing_ok=True)
    if done.returncode != 0:
        code, message = _classify(done.stderr or done.stdout, done.returncode, settings)
        raise ApiError(422, code, message)
    try:
        info = json.loads((done.stdout.strip().splitlines() or [""])[-1])
    except ValueError:
        raise ApiError(502, "failed", "The site's answer couldn't be read.") from None
    if info.get("_type") in ("playlist", "multi_video"):
        raise ApiError(422, "playlist", "Playlists aren't supported in the web version yet.")
    if info.get("is_live"):
        raise ApiError(422, "live", "Live streams aren't supported.")
    formats = [f for f in (info.get("formats") or []) if isinstance(f, dict)] or [info]
    duration = info.get("duration") if isinstance(info.get("duration"), (int, float)) else None
    heights = sorted({int(f["height"]) for f in formats if _is_video(f) and f.get("height") and int(f["height"]) <= settings.max_height})
    has_video = any(_is_video(f) for f in formats)
    has_audio = any(_has_audio(f) for f in formats)
    sizes, audio_size = _estimates(formats, duration, settings.max_height)
    thumb = info.get("thumbnail") if isinstance(info.get("thumbnail"), str) and info["thumbnail"].startswith("https://") else None
    return {
        "url": url,
        "title": str(info.get("title") or "")[:300],
        "uploader": _person(info.get("uploader") or info.get("channel")),
        "site": str(info.get("extractor_key") or info.get("extractor") or "")[:40],
        "duration": duration,
        "thumbnail": thumb,
        "heights": heights,
        "sizes": sizes,
        "audio_size": audio_size,
        "has_video": has_video,
        "has_audio": has_audio,
        "too_long": bool(duration and duration > settings.max_duration_min * 60),
    }
