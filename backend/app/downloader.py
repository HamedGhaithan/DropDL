from __future__ import annotations

import os
import shutil
import sys
import subprocess
import json
import math
from itertools import islice
from pathlib import Path
from typing import Any

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from .jobs import Job, jobs


class DownloadCancelled(Exception):
    pass


AUDIO_CONTAINERS = ("mp3", "m4a", "opus", "flac", "wav")
VIDEO_CONTAINERS = ("mp4", "webm", "mkv")
SPONSOR_CATEGORIES = ["sponsor", "intro", "outro", "selfpromo", "preview", "filler", "interaction", "music_offtopic"]
SPONSOR_REMOVE = {"sponsor", "selfpromo", "interaction"}
BROWSERS = ("firefox", "chrome", "edge", "brave", "opera", "vivaldi", "chromium")
MEDIA_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mp3", ".m4a", ".mov", ".ogg", ".opus", ".wav", ".flac"}


def _ffmpeg_location() -> str | None:
    configured = os.getenv("FFMPEG_LOCATION")
    if configured:
        return configured

    roots = [Path(__file__).resolve().parents[2]]
    if getattr(sys, "frozen", False):
        roots.insert(0, Path(sys.executable).resolve().parent)
    for root in roots:
        for candidate in (root / "bin" / "ffmpeg.exe", root / "ffmpeg.exe", root / "bin" / "ffmpeg"):
            if candidate.exists():
                return str(candidate.parent)

    executable = shutil.which("ffmpeg")
    return str(Path(executable).parent) if executable else None


# --------------------------------------------------------------------------- formats

def _height(quality: str) -> int | None:
    if quality == "best":
        return None
    try:
        return int(str(quality).rstrip("p"))
    except ValueError:
        return 1080


def format_plan(kind: str, container: str, quality: str, codec: str | None = None) -> tuple[str, list[str]]:
    """Return ``(format, format_sort)`` that always resolves to *something*.

    1.x used hard filters such as ``bestvideo[ext=mp4][height<=720]`` that fail
    with "Requested format is not available" on many sites. 2.0 orders the
    candidates with yt-dlp's format sorting instead, while ``bv*+ba/b`` still
    matches whatever the site offers.
    """
    if kind == "audio":
        preferred = {"m4a": ["acodec:aac"], "opus": ["acodec:opus"]}.get(container, [])
        return "ba/b", preferred + ["abr", "asr"]
    height = _height(quality)
    resolution = [f"res:{height}"] if height else ["res"]
    if codec is None:
        codec = "compatible" if container == "mp4" else "any"
    if codec == "compatible":
        # H.264/AAC plays in every player, phone and editor; AV1/VP9 often do not.
        # Some sites (archive.org, generic pages) publish no codec metadata, so
        # the MP4 container is the next-best signal before resolution.
        sort = ["vcodec:h264", "ext:mp4:m4a", *resolution, "fps", "acodec:aac"]
    elif container == "webm":
        sort = [*resolution, "fps", "vcodec:vp9", "acodec:opus", "ext:webm:webm"]
    elif container == "mp4":
        sort = [*resolution, "fps", "ext:mp4:m4a"]
    else:
        sort = [*resolution, "fps"]
    return "bv*+ba/b", sort


def _format_selector(kind: str, quality: str) -> str:
    """Legacy hard-filter selector kept for 1.x tooling; downloads use format_plan."""
    if kind == "audio":
        return "bestaudio/best"
    if quality == "best":
        return "bestvideo+bestaudio/best"
    height = _height(quality) or 1080
    return f"bestvideo[height<={height}]+bestaudio/best[height<={height}]/bv*+ba/b"


# --------------------------------------------------------------------------- network

def _impersonate_target():
    try:
        from yt_dlp.networking.impersonate import ImpersonateTarget
        import curl_cffi  # noqa: F401  (impersonation requires curl-cffi)
        return ImpersonateTarget.from_str("chrome")
    except Exception:
        return None


def network_options(network: dict | None) -> dict[str, Any]:
    """Translate a Preferences network snapshot into yt-dlp options."""
    network = network or {}
    options: dict[str, Any] = {}
    proxy = str(network.get("proxy") or "").strip()
    if proxy:
        options["proxy"] = proxy
    if network.get("force_ipv4"):
        options["source_address"] = "0.0.0.0"
    browser = str(network.get("cookies_browser") or "").lower()
    if browser in BROWSERS:
        options["cookiesfrombrowser"] = (browser, None, None, None)
    try:
        fragments = int(network.get("concurrent_fragments") or 4)
    except (TypeError, ValueError):
        fragments = 4
    options["concurrent_fragment_downloads"] = max(1, min(16, fragments))
    if network.get("impersonate") == "always":
        target = _impersonate_target()
        if target is not None:
            options["impersonate"] = target
    return options


def current_network() -> dict[str, Any]:
    """Network preferences for in-process inspection (workers get a snapshot)."""
    from .settings import CONFIG_ROOT
    try:
        saved = json.loads((CONFIG_ROOT / "settings.json").read_text(encoding="utf-8"))
        return saved if isinstance(saved, dict) else {}
    except (OSError, ValueError):
        return {}


# --------------------------------------------------------------------------- inspection

def _size_estimates(formats: list[dict], duration: float | None) -> tuple[dict[str, int], int | None]:
    def size(f):
        value = f.get("filesize") or f.get("filesize_approx")
        if not value and isinstance(f.get("tbr"), (int, float)) and duration:
            value = f["tbr"] * 1000 / 8 * duration
        return int(value) if value else None

    audio_size = max((size(f) or 0 for f in formats if f.get("vcodec") == "none" and f.get("acodec") not in (None, "none")), default=0) or None
    sizes: dict[str, int] = {}
    for f in formats:
        height = f.get("height")
        if not isinstance(height, (int, float)) or f.get("vcodec") in (None, "none"):
            continue
        value = size(f)
        if not value:
            continue
        if f.get("acodec") in (None, "none") and audio_size:
            value += audio_size
        key = f"{int(height)}p"
        sizes[key] = max(sizes.get(key, 0), value)
    return sizes, audio_size


def _extract(options: dict[str, Any], url: str) -> dict[str, Any]:
    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)
        if not info or "entries" in info:
            raise ValueError("This is a playlist. Select Playlist and load its entries instead.")
        return ydl.sanitize_info(info)


def inspect_url(url: str) -> dict[str, Any]:
    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "socket_timeout": 30,
        "noplaylist": True,
        # A pure playlist URL can still produce entries with noplaylist=True.
        # Never fully extract its videos through the single-video inspector.
        "extract_flat": "in_playlist",
        "lazy_playlist": True,
        "playlistend": 1,
        "extractor_retries": 2,
    }
    from .settings import CONFIG_ROOT
    if (CONFIG_ROOT/"cookies.txt").is_file():options["cookiefile"]=str(CONFIG_ROOT/"cookies.txt")
    if shutil.which("node"):
        options["js_runtimes"] = {"node": {}}
    options.update(network_options(current_network()))
    try:
        info = _extract(options, url)
    except DownloadError as exc:
        # Same self-healing as downloads: a 403 is often a browser check.
        target = _impersonate_target()
        if not ("http error 403" in str(exc).lower() and target is not None and "impersonate" not in options):
            raise
        info = _extract(dict(options, impersonate=target), url)

    formats = info.get("formats") or []
    heights = sorted(
        {int(f["height"]) for f in formats if isinstance(f.get("height"), (int, float))},
        reverse=True,
    )
    sizes, audio_size = _size_estimates(formats, info.get("duration"))
    vcodecs = {str(f.get("vcodec") or "").split(".")[0] for f in formats if f.get("vcodec") not in (None, "none")}

    return {
        "id": info.get("id"),
        "title": info.get("title") or "Untitled media",
        "uploader": info.get("uploader") or info.get("channel") or info.get("extractor_key"),
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "webpage_url": info.get("webpage_url") or url,
        "extractor": info.get("extractor_key") or info.get("extractor"),
        "heights": heights,
        "suggested_qualities": [f"{h}p" for h in heights[:10]],
        "sizes": sizes,
        "audio_size": audio_size,
        "is_live": bool(info.get("is_live")),
        "live_status": info.get("live_status"),
        "has_h264": any(codec in {"avc1", "h264"} for codec in vcodecs),
        "chapters": len(info.get("chapters") or []),
        "subtitles": sorted((info.get("subtitles") or {}).keys())[:40],
    }


def _find_result_file(directory: Path) -> Path | None:
    candidates = [p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in MEDIA_EXTENSIONS and ".clip.tmp." not in p.name]
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


def inspect_playlist(url: str, start: int = 1, limit: int = 100) -> dict[str, Any]:
    options = {"quiet": True, "skip_download": True, "extract_flat": "in_playlist",
               "noplaylist": False, "playliststart": start, "playlistend": start + limit - 1,
               "socket_timeout": 15, "ignoreerrors": True, "lazy_playlist": True,
               "extractor_retries": 2, "retries": 2}
    from .settings import CONFIG_ROOT
    if (CONFIG_ROOT/"cookies.txt").is_file():options["cookiefile"]=str(CONFIG_ROOT/"cookies.txt")
    if shutil.which("node"):
        options["js_runtimes"] = {"node": {}}
    options.update(network_options(current_network()))
    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)
        if not isinstance(info, dict) or "entries" not in info:
            raise ValueError("This URL did not return a playlist. Use Single URL or Batch URLs instead.")
        # Do not serialize the whole extractor result: lazy entry collections
        # and nested metadata can otherwise be expanded unnecessarily.
        raw_entries = list(islice(info.get("entries") or [], limit))
    if not info or "entries" not in info:
        raise ValueError("This URL did not return a playlist. Use Single URL or Batch URLs instead.")
    entries = []
    for index, item in enumerate(raw_entries, start):
        if not isinstance(item, dict):
            entries.append({"index": index, "title": "Unavailable item", "url": None, "duration": None})
            continue
        item_url = item.get("webpage_url") or item.get("url")
        if not isinstance(item_url, str):
            item_url = None
        if item_url and not item_url.startswith(("https://", "http://")):
            item_url = f"https://www.youtube.com/watch?v={item['id']}" if str(item.get("ie_key", "")).lower() == "youtube" and item.get("id") else None
        entry_index = item.get("playlist_index")
        duration = item.get("duration")
        entries.append({"index": entry_index if isinstance(entry_index, int) and entry_index > 0 else index,
                        "title": str(item.get("title") or item.get("id") or "Untitled"),
                        "url": item_url, "duration": duration if isinstance(duration, (int, float)) and math.isfinite(duration) and duration >= 0 else None})
    total = info.get("playlist_count")
    more = start + len(entries) - 1 < total if isinstance(total, int) else len(entries) == limit
    return {"title": str(info.get("title") or "Playlist"), "entries": entries, "total": total if isinstance(total, int) else None,
            "has_more": bool(entries) and more, "next_start": start + len(entries)}


def _tool(name: str) -> str:
    location = _ffmpeg_location()
    if location:
        base = Path(location)
        if base.is_file():
            base = base.parent
        for filename in (name + ".exe", name):
            candidate = base / filename
            if candidate.exists():
                return str(candidate)
    executable = shutil.which(name)
    if not executable:
        raise RuntimeError(f"{name} is missing. Install FFmpeg and ffprobe together.")
    return executable


def trim_file(job: Job, source: Path) -> Path:
    if job.clip_start is None or job.clip_end is None:
        return source
    probe = subprocess.run([_tool("ffprobe"), "-v", "error", "-show_entries", "format=duration",
                            "-of", "json", str(source)], capture_output=True, text=True, timeout=30)
    if probe.returncode:
        raise RuntimeError("Could not read this file's duration for clipping.")
    duration = float(json.loads(probe.stdout)["format"]["duration"])
    if job.clip_start >= duration or job.clip_end > duration + 0.1:
        raise ValueError(f"Clip range exceeds this media's duration ({duration:.2f}s).")
    target = Path(job.directory) / f"{source.stem} [clip {job.clip_start:g}-{job.clip_end:g}].{job.container}"
    temporary = target.with_name(target.stem + ".clip.tmp." + job.container)
    command = [_tool("ffmpeg"), "-nostdin", "-y", "-i", str(source), "-ss", str(job.clip_start),
               "-t", str(job.clip_end - job.clip_start)]
    if job.kind == "audio":
        codec = {"mp3": "libmp3lame", "m4a": "aac", "opus": "libopus", "flac": "flac", "wav": "pcm_s16le"}.get(job.container, "aac")
        command += ["-vn", "-c:a", codec] + (["-b:a", "192k"] if job.container in {"mp3", "m4a", "opus"} else [])
    elif job.container == "webm":
        command += ["-map", "0:v:0", "-map", "0:a:0?", "-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0", "-c:a", "libopus"]
    else:
        command += ["-map", "0:v:0", "-map", "0:a:0?", "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-c:a", "aac"]
        if job.container == "mp4":
            command += ["-movflags", "+faststart"]
    command.append(str(temporary))
    jobs.update_attempt(job, status="clipping", phase="clipping", percent=0, eta=None, speed=None)
    log = Path(job.directory) / "clip.log"
    try:
        with log.open("w+b") as errors:
            process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=errors)
            try:
                while process.poll() is None:
                    if job.cancel_event.wait(0.2):
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                        raise DownloadCancelled()
                if process.returncode:
                    errors.seek(0)
                    raise RuntimeError("Clip export failed: " + errors.read().decode(errors="replace")[-2000:])
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
        if job.cancel_event.is_set():
            raise DownloadCancelled()
        check=subprocess.run([_tool("ffprobe"),"-v","error","-show_entries","format=duration","-of","json",str(temporary)],capture_output=True,text=True,timeout=30)
        actual=float(json.loads(check.stdout).get('format',{}).get('duration',0)) if check.returncode==0 else 0
        expected=job.clip_end-job.clip_start
        if actual<=0 or abs(actual-expected)>max(.25,expected*.01):
            raise RuntimeError("The clip duration does not match the selected range. The full source was not saved as a completed clip.")
        temporary.replace(target)
        return target
    finally:
        temporary.unlink(missing_ok=True)
        log.unlink(missing_ok=True)


def prepare_preview(job: Job, source: Path) -> Path:
    directory = Path(job.directory)
    output = directory / ("playback-preview.mp4" if job.kind == "video" else "playback-preview.m4a")
    temporary = output.with_name("playback-preview.tmp" + output.suffix)
    command = [_tool("ffmpeg"), "-nostdin", "-y", "-i", str(source)]
    if job.kind == "video":
        maximum=640 if job.conversion_options.get("proxy") else 960
        command += ["-map", "0:v:0", "-map", "0:a:0?", "-vf", f"scale=w='max(2,trunc(min({maximum},iw)/2)*2)':h=-2",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "25", "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart"]
    else:
        command += ["-vn", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart"]
    command.append(str(temporary))
    jobs.update_attempt(job, status="preparing_preview", percent=0, speed=None, eta=None)
    log = directory / "preview.log"
    try:
        with log.open("w+b") as errors:
            process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=errors)
            try:
                while process.poll() is None:
                    if job.cancel_event.wait(0.2):
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill(); process.wait()
                        raise DownloadCancelled()
                if process.returncode:
                    errors.seek(0)
                    raise RuntimeError("Preview preparation failed: " + errors.read().decode(errors="replace")[-1500:])
            finally:
                if process.poll() is None:
                    process.kill(); process.wait()
        if job.cancel_event.is_set():
            raise DownloadCancelled()
        temporary.replace(output)
        return output
    finally:
        temporary.unlink(missing_ok=True)
        log.unlink(missing_ok=True)


# --------------------------------------------------------------------------- download

def build_options(job: Job, directory: Path, progress_hook=None, postprocessor_hook=None) -> dict[str, Any]:
    """All yt-dlp options for one task (pure; exercised directly by tests)."""
    extras = job.download_options or {}
    selected_format, format_sort = format_plan(job.kind, job.container, job.quality, extras.get("codec"))
    options: dict[str, Any] = {
        "nocolor": True,
        "ratelimit": job.speed_limit_kbps * 1024 or None,
        "format": selected_format,
        "format_sort": format_sort,
        "outtmpl": str(directory / "%(title).180B [%(id)s].%(ext)s"),
        "progress_hooks": [progress_hook] if progress_hook else [],
        "postprocessor_hooks": [postprocessor_hook] if postprocessor_hook else [],
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "restrictfilenames": False,
        "windowsfilenames": True,
        "continuedl": True,
        "socket_timeout": 30,
        "retries": 15,
        "fragment_retries": 15,
        "extractor_retries": 3,
        "file_access_retries": 10,
        "http_chunk_size": 10 * 1024 * 1024,
        "nopart": False,
        "skip_unavailable_fragments": False,
        "retry_sleep_functions": {"http": lambda n: min(20, 2 ** min(n, 4)), "fragment": lambda n: min(10, n + 1),
                                  "extractor": lambda n: min(10, 2 * n + 1)},
        "overwrites": False,
    }
    options.update(network_options(job.network))
    if job.cookie_file and Path(job.cookie_file).is_file():
        options["cookiefile"] = job.cookie_file
    if shutil.which("node"):
        options["js_runtimes"] = {"node": {}}
    ffmpeg = _ffmpeg_location()
    if ffmpeg:
        options["ffmpeg_location"] = ffmpeg

    postprocessors: list[dict[str, Any]] = []
    sponsorblock = extras.get("sponsorblock") if extras.get("sponsorblock") in {"mark", "remove"} else None
    if sponsorblock == "remove" and job.clip_start is not None:
        sponsorblock = "mark"  # Removing segments would shift the selected clip range.
    if sponsorblock and job.kind == "audio" and job.container == "wav":
        sponsorblock = None if sponsorblock == "mark" else sponsorblock  # WAV cannot hold chapters.
    if sponsorblock:
        postprocessors.append({"key": "SponsorBlock", "categories": SPONSOR_CATEGORIES,
                               "api": "https://sponsor.ajay.app", "when": "after_filter"})
    if job.subtitle_languages:
        options.update(writesubtitles=True, writeautomaticsub=True, subtitleslangs=job.subtitle_languages,
                       subtitlesformat="srt/vtt/best")

    if job.kind == "audio":
        quality = str(extras.get("audio_quality") or "best").rstrip("k")
        postprocessors.append({
            "key": "FFmpegExtractAudio",
            "preferredcodec": job.container if job.container in AUDIO_CONTAINERS else "mp3",
            "preferredquality": "0" if quality == "best" or job.container in {"flac", "wav"} else quality,
        })
    else:
        options["merge_output_format"] = job.container
        postprocessors.append({"key": "FFmpegVideoRemuxer", "preferedformat": job.container})
        if extras.get("embed_subtitles") and job.subtitle_languages:
            postprocessors.append({"key": "FFmpegEmbedSubtitle", "already_have_subtitle": False})

    if sponsorblock:
        postprocessors.append({"key": "ModifyChapters", "remove_chapters_patterns": [], "remove_ranges": [],
                               "remove_sponsor_segments": set(SPONSOR_REMOVE) if sponsorblock == "remove" else set(),
                               "sponsorblock_chapter_title": "[SponsorBlock]: %(category_names)l",
                               "force_keyframes": False})
    if job.embed_metadata or sponsorblock == "mark":
        postprocessors.append({"key": "FFmpegMetadata", "add_metadata": bool(job.embed_metadata), "add_chapters": True})
    if extras.get("embed_thumbnail") and job.container not in {"webm", "wav"}:
        options["writethumbnail"] = True
        postprocessors.append({"key": "EmbedThumbnail", "already_have_thumbnail": False})
    options["postprocessors"] = postprocessors
    return options


def _without(options: dict[str, Any], *keys: str) -> None:
    options["postprocessors"] = [pp for pp in options.get("postprocessors", []) if pp["key"] not in keys]


def fallback_for(error: str, options: dict[str, Any], used: set[str]) -> str | None:
    """Apply one corrective change for a failed attempt; None means give up."""
    text = error.lower()
    if "requested format is not available" in text and "format" not in used:
        options["format"] = "bv*+ba/b" if options.get("merge_output_format") else "ba/b"
        options.pop("format_sort", None)
        return "format"
    keys = {pp["key"] for pp in options.get("postprocessors", [])}
    if "conversion failed" in text or "postprocessing" in text:
        # Post-processing ladder: the media itself is already downloaded, so
        # each step is cheap. Re-encode instead of remuxing incompatible codecs
        # (e.g. Theora into MP4), then shed optional extras one at a time.
        # yt-dlp's message rarely names the step, but our hook records the
        # running post-processor as "[phase: ...]"; fix that step first.
        phase = text.rsplit("[phase: ", 1)[-1].rstrip("]") if "[phase: " in text else ""
        first = {"remuxing": "convert", "thumbnail": "thumbnail", "sponsorblock": "sponsorblock", "subtitles": "subtitles"}.get(phase)
        for step in dict.fromkeys([first, "convert", "thumbnail", "sponsorblock", "subtitles"]):
            if not step or step in used:
                continue
            if step == "convert" and "FFmpegVideoRemuxer" in keys:
                options["postprocessors"] = [
                    {"key": "FFmpegVideoConvertor", "preferedformat": pp["preferedformat"]} if pp["key"] == "FFmpegVideoRemuxer" else pp
                    for pp in options["postprocessors"]]
                return step
            if step == "thumbnail" and options.get("writethumbnail"):
                _without(options, "EmbedThumbnail")
                options.pop("writethumbnail", None)
                return step
            if step == "sponsorblock" and "SponsorBlock" in keys:
                _without(options, "SponsorBlock", "ModifyChapters")
                return step
            if step == "subtitles" and "FFmpegEmbedSubtitle" in keys:
                _without(options, "FFmpegEmbedSubtitle")
                return step
    if "sponsorblock" in text and "sponsorblock" not in used and "SponsorBlock" in keys:
        _without(options, "SponsorBlock", "ModifyChapters")
        return "sponsorblock"
    if "thumbnail" in text and "thumbnail" not in used and options.get("writethumbnail"):
        _without(options, "EmbedThumbnail")
        options.pop("writethumbnail", None)
        return "thumbnail"
    if "subtitle" in text and "subtitles" not in used and options.get("writesubtitles"):
        for key in ("writesubtitles", "writeautomaticsub", "subtitleslangs"):
            options.pop(key, None)
        _without(options, "FFmpegEmbedSubtitle")
        return "subtitles"
    if "cookie" in text and "cookies" not in used and options.get("cookiesfrombrowser"):
        # Chromium cookie databases are often locked or app-bound encrypted.
        options.pop("cookiesfrombrowser", None)
        return "cookies"
    if ("http error 403" in text or "forbidden" in text) and "forbidden" not in used:
        target = _impersonate_target()
        if target is not None and "impersonate" not in options:
            options["impersonate"] = target
        options["_clear_cache"] = True
        return "forbidden"
    return None


def _reported_file(reported: list[str], directory: Path) -> Path | None:
    """The final file yt-dlp reports (post_hooks) after post-processing."""
    for path in reversed(reported):
        if isinstance(path, str) and Path(path).is_file() and Path(path).suffix.lower() in MEDIA_EXTENSIONS:
            try:
                if Path(path).resolve().parent == directory.resolve():
                    return Path(path)
            except OSError:
                continue
    return None


def remove_empty_outputs(directory: Path) -> None:
    """A failed FFmpeg step can leave an empty target file. yt-dlp would treat
    it as "already downloaded" on the next attempt and post-process nothing."""
    try:
        entries = list(directory.iterdir())
    except OSError:
        return
    for leftover in entries:
        try:
            if leftover.is_file() and leftover.suffix.lower() in MEDIA_EXTENSIONS and leftover.stat().st_size == 0:
                leftover.unlink()
        except OSError:
            pass


POSTPROCESSING_STATES = {"processing"}


def _download_with_fallbacks(job: Job, options: dict[str, Any], capture_title, directory: Path) -> Path | None:
    used: set[str] = set()
    reported: list[str] = []
    options["post_hooks"] = [reported.append]
    while True:
        try:
            remove_empty_outputs(directory)
            clear_cache = options.pop("_clear_cache", False)
            with YoutubeDL(options) as ydl:
                if clear_cache:
                    ydl.cache.remove()
                ydl.add_progress_hook(capture_title)
                ydl.download([job.url])
            return _reported_file(reported, directory) or _find_result_file(directory)
        except DownloadCancelled:
            raise
        except Exception as exc:
            if job.cancel_event.is_set():
                raise DownloadCancelled() from exc
            text = str(exc)
            if not isinstance(exc, DownloadError):
                # yt-dlp lets some post-processor bugs escape raw (e.g. KeyError
                # from an unreadable file). Treat those like a failed PP step.
                if job.status not in POSTPROCESSING_STATES:
                    raise
                text = f"Postprocessing: {type(exc).__name__}: {text}"
            if job.status in POSTPROCESSING_STATES and job.phase:
                text += f" [phase: {job.phase}]"
            change = fallback_for(text, options, used)
            if not change:
                raise
            used.add(change)
            jobs.update_attempt(job, status="starting", phase="fallback_" + change, speed=None, eta=None)


class ProgressTracker:
    """Combine the separate video and audio transfers of a merged download
    into one monotonic progress value instead of two 0-100% passes."""

    def __init__(self) -> None:
        self.files: dict[str, tuple[float, float]] = {}
        self.expected: list[float] = []

    def update(self, data: dict[str, Any], finished: bool = False) -> tuple[int | None, int | None, int | None]:
        info = data.get("info_dict") or {}
        requested = info.get("requested_formats") or []
        if len(requested) > 1 and not self.expected:
            sizes = [f.get("filesize") or f.get("filesize_approx") or 0 for f in requested]
            if all(sizes):
                self.expected = [float(size) for size in sizes]
        name = str(data.get("filename") or data.get("tmpfilename") or info.get("format_id") or "media")
        downloaded = data.get("downloaded_bytes") or 0
        total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
        if finished:
            downloaded = total = max(downloaded, total, self.files.get(name, (0, 0))[0])
        self.files[name] = (float(downloaded), float(total))
        done = sum(item[0] for item in self.files.values())
        if not self.expected:
            return (int(downloaded) or None, int(total) or None, data.get("eta"))
        # Finished parts count at their real size; unfinished parts use the larger
        # of the live total and the extractor's estimate.
        known = sum(item[1] for item in self.files.values())
        grand = max(sum(self.expected), known, done)
        speed = data.get("speed")
        eta = int((grand - done) / speed) if speed and speed > 0 else data.get("eta")
        return int(done), int(grand), eta

    def pending(self) -> bool:
        return bool(self.expected) and len(self.files) < len(self.expected)


def run_download(job: Job) -> None:
    directory = Path(job.directory)
    if job.cancel_event.is_set():
        jobs.update_attempt(job, status="cancelled")
        return
    if not _ffmpeg_location():
        jobs.update_attempt(job, status="failed", error="FFmpeg is missing. Install FFmpeg and restart DropDL to enable video merging and audio conversion.")
        return
    directory.mkdir(parents=True, exist_ok=True)

    tracker = ProgressTracker()

    def progress_hook(data: dict[str, Any]) -> None:
        if job.cancel_event.is_set():
            raise DownloadCancelled("Download cancelled by user")

        status = data.get("status")
        if status == "downloading":
            downloaded, total, eta = tracker.update(data)
            percent = (downloaded / total * 100) if downloaded and total else job.percent
            jobs.update_attempt(
                job,
                status="downloading",
                phase="downloading",
                percent=round(float(min(100.0, percent)), 2),
                downloaded_bytes=downloaded,
                total_bytes=total,
                speed=data.get("speed"),
                eta=eta,
            )
        elif status == "finished":
            downloaded, total, _ = tracker.update(data, finished=True)
            if tracker.pending():
                jobs.update_attempt(job, downloaded_bytes=downloaded, total_bytes=total,
                                    percent=round(downloaded / total * 100, 2) if total else job.percent)
            else:
                jobs.update_attempt(job, status="processing", phase="processing", percent=100.0, speed=None, eta=None)

    def postprocessor_hook(data):
        if job.cancel_event.is_set(): raise DownloadCancelled('Download cancelled by user')
        if data.get('status') == 'started':
            name = str(data.get('postprocessor', '')).lower()
            phase = ('merging' if 'merger' in name else 'converting' if 'extractaudio' in name else 'remuxing' if 'remux' in name
                     else 'sponsorblock' if 'sponsorblock' in name or 'modifychapters' in name else 'thumbnail' if 'thumbnail' in name
                     else 'subtitles' if 'subtitle' in name else 'metadata' if 'metadata' in name else 'processing')
            jobs.update_attempt(job, status='processing', phase=phase, speed=None, eta=None)

    options = build_options(job, directory, progress_hook, postprocessor_hook)
    jobs.update_attempt(job, status="starting", phase="resuming" if job.attempt>1 else "connecting")
    metadata = {}
    try:
        if job.source_filename:
            result = Path(job.source_filename)
        else:
            def capture_title(data: dict[str, Any]) -> None:
                info = data.get("info_dict", {})
                metadata.update({key: info.get(key) for key in ("title","uploader","channel","playlist_title") if info.get(key)})
                if info.get("title") and info["title"] != job.title:
                    jobs.update_attempt(job, title=info["title"], thumbnail=info.get("thumbnail") or job.thumbnail)
            result = _download_with_fallbacks(job, options, capture_title, directory)
        if job.cancel_event.is_set():
            raise DownloadCancelled("Download cancelled by user")
        if not result:
            raise RuntimeError("The download completed but no output file was found.")
        if job.purpose == "preview":
            preview = prepare_preview(job, result)
            jobs.update_attempt(job, status="completed", phase="completed", percent=100.0, filename=str(result), preview_filename=str(preview), eta=0)
            return
        original = result
        result = trim_file(job, result)
        if result != original and not job.source_filename:
            original.unlink(missing_ok=True)
        if job.cancel_event.is_set(): raise DownloadCancelled("Download cancelled by user")
        if job.destination:
            from .organization import output_location
            destination, output_stem = output_location(job, metadata, result)
            destination.mkdir(parents=True, exist_ok=True)
            from .output_files import publish_download
            final,copy_number=publish_download(result,destination,output_stem)
            if copy_number:jobs.update_attempt(job,title=(job.title or output_stem)+f' (+{copy_number})')
            for sidecar in directory.iterdir():
                if sidecar.is_file() and sidecar.suffix.lower() in {'.srt','.vtt','.ass','.lrc'}:
                    suffix=sidecar.name[len(result.stem):] if sidecar.name.startswith(result.stem) else '.'+sidecar.name
                    shutil.move(str(sidecar),str(final.with_name(final.stem+suffix)))
            result = final
        try:
            size = result.stat().st_size
        except OSError:
            size = job.total_bytes
        jobs.update_attempt(job, status="completed", phase="completed", percent=100.0, filename=str(result), eta=0,
                            total_bytes=size or job.total_bytes, downloaded_bytes=size or job.downloaded_bytes)
    except DownloadCancelled:
        jobs.update_attempt(job, status="cancelled", error=None)
    except DownloadError as exc:
        if job.cancel_event.is_set():
            jobs.update_attempt(job, status="cancelled", error=None)
        else:
            jobs.update_attempt(job, status="failed", error=str(exc))
    except Exception as exc:  # Keep worker failures visible to the GUI.
        import logging
        import traceback
        logging.getLogger("dropdl.worker").error("Task %s failed:\n%s", job.id[:8], traceback.format_exc())
        readable = isinstance(exc, (RuntimeError, ValueError, OSError)) and str(exc)
        jobs.update_attempt(job, status="failed", error=str(exc) if readable else f"Unexpected {type(exc).__name__}: {exc}")
