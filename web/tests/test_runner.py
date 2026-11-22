import dataclasses
import json
import subprocess
import sys
from pathlib import Path

import pytest

from server import runner
from server.errors import ApiError
from tests.conftest import spec

DANGEROUS_FLAGS = {"--exec", "--exec-before-download", "--cookies", "--cookies-from-browser", "--config-locations", "--load-info-json",
                   "-a", "--batch-file", "--plugin-dirs", "--netrc", "--netrc-cmd", "--download-archive", "--external-downloader",
                   "--ffmpeg-location", "--proxy-from-env", "--enable-file-urls"}


# --------------------------------------------------------------------------- what the browser may ask for
def test_defaults_and_clamping(settings):
    s = runner.normalise_spec("https://v.com/x", None, None, None, None, None, settings)
    assert (s.kind, s.fmt, s.height) == ("video", "mp4", settings.default_height)
    assert runner.normalise_spec("https://v.com/x", "video", 4000, "mp4", None, None, settings).height == settings.max_height
    assert runner.normalise_spec("https://v.com/x", "video", 50, "mp4", None, None, settings).height == 144
    audio = runner.normalise_spec("https://v.com/x", "AUDIO", 720, None, None, None, settings)
    assert (audio.kind, audio.fmt, audio.height) == ("audio", "mp3", None)


@pytest.mark.parametrize("kind,fmt,code", [("gif", "mp4", "bad_request"), ("video", "exe", "bad_format"), ("video", "mp3", "bad_format"),
                                           ("audio", "mp4", "bad_format"), ("video", "mp4; rm -rf /", "bad_format")])
def test_bad_choices(settings, kind, fmt, code):
    with pytest.raises(ApiError) as caught:
        runner.normalise_spec("https://v.com/x", kind, 720, fmt, None, None, settings)
    assert caught.value.code == code


@pytest.mark.parametrize("start,end", [(10, None), (None, 10), (10, 5), (10, 10), (-1, 5), (float("nan"), 5), (0, float("inf")),
                                       (0, 601), (1_000_000, 1_000_030)])
def test_bad_clips(settings, start, end):
    with pytest.raises(ApiError) as caught:
        runner.normalise_spec("https://v.com/x", "video", 720, "mp4", start, end, settings)
    assert caught.value.code == "bad_clip"


def test_good_clip(settings):
    s = runner.normalise_spec("https://v.com/x", "video", 720, "mp4", 30, 42.5, settings)
    assert (s.start, s.end) == (30, 42.5)


# --------------------------------------------------------------------------- the command line
def args_for(settings, **kw):
    return runner.build_download_args(spec(**kw), settings, Path("/work/job"))


def value_after(args, flag):
    return args[args.index(flag) + 1]


def test_url_is_always_last_and_after_double_dash(settings):
    for url in ("https://vimeo.com/1", "https://vimeo.com/?--exec=touch", "https://vimeo.com/a b"):
        a = args_for(settings, url=url)
        assert a[-2:] == ["--", url]
        assert sum(1 for x in a if x == url) == 1


def test_only_known_flags_no_dangerous_ones(settings):
    for kw in (dict(), dict(kind="audio", fmt="mp3", height=None), dict(start=1.0, end=9.0), dict(fmt="webm"), dict(fmt="mkv")):
        a = args_for(settings, **kw)
        assert not DANGEROUS_FLAGS & set(a)
        assert all(isinstance(x, str) for x in a)
        assert a[:4] == [sys.executable, "-P", "-m", "yt_dlp"]
        assert "--ignore-config" in a
        assert value_after(a, "--use-extractors") == "default,-generic"      # the "fetch any URL" extractor stays off
        assert "--no-playlist" in a and value_after(a, "--max-downloads") == "1"


def test_video_mp4_selector(settings):
    a = args_for(settings)
    fmt = value_after(a, "-f")
    assert "height<=?720" in fmt and f"filesize<?{settings.max_filesize_mb}M" in fmt
    assert value_after(a, "-S") == "res,vcodec:h264,acodec:aac"
    assert value_after(a, "--merge-output-format") == "mp4" and value_after(a, "--remux-video") == "mp4"
    assert value_after(a, "--max-filesize") == f"{settings.max_filesize_mb}M"
    assert value_after(a, "--match-filters") == f"!is_live & duration<=?{settings.max_duration_min * 60}"


def test_other_containers(settings):
    assert "--remux-video" not in args_for(settings, fmt="webm")
    assert value_after(args_for(settings, fmt="webm"), "-S") == "res,vcodec:vp9,acodec:opus"
    assert value_after(args_for(settings, fmt="mkv"), "--remux-video") == "mkv"


def test_audio_options(settings):
    mp3 = args_for(settings, kind="audio", fmt="mp3", height=None)
    assert "-x" in mp3 and value_after(mp3, "--audio-format") == "mp3" and value_after(mp3, "--audio-quality") == "192K"
    assert "--embed-thumbnail" in mp3 and "-S" not in mp3
    wav = args_for(settings, kind="audio", fmt="wav", height=None)
    assert "--embed-thumbnail" not in wav and "--audio-quality" not in wav


def test_trim_downloads_only_the_section(settings):
    a = args_for(settings, start=30.0, end=42.5)
    assert value_after(a, "--download-sections") == "*30-42.5" and "--force-keyframes-at-cuts" in a
    assert "--max-filesize" not in a                                         # whole-file size doesn't apply to a clip
    assert "filesize" not in value_after(a, "-f")
    assert value_after(a, "--match-filters") == "!is_live & duration<=?21600"


def test_proxy_is_passed_only_when_configured(settings):
    assert "--proxy" not in args_for(settings)
    with_proxy = dataclasses.replace(settings, proxy="socks5://127.0.0.1:9050")
    assert value_after(runner.build_download_args(spec(), with_proxy, Path("/w")), "--proxy") == "socks5://127.0.0.1:9050"


def test_info_command(settings):
    a = runner.build_info_args("https://vimeo.com/1", settings)
    assert a[-2:] == ["--", "https://vimeo.com/1"] and "--dump-single-json" in a and "--skip-download" in a
    assert value_after(a, "--use-extractors") == "default,-generic" and not DANGEROUS_FLAGS & set(a)


# --------------------------------------------------------------------------- progress
def test_video_progress_is_steady_and_never_goes_back():
    t = runner.Tracker("video")
    seen = []
    for line in ["__P__downloading|500|1000|NA|1000.0|5", "__P__downloading|1000|1000|NA|1000.0|0", "__P__finished|1000|1000|NA|NA|NA",
                 "__P__downloading|50|100|NA|10|1", "__P__downloading|10|100|NA|10|1", "__P__finished|100|100|NA|NA|NA"]:
        assert t.feed(line)
        seen.append(t.progress)
    assert seen == sorted(seen)
    assert seen[0] == pytest.approx(0.4) and seen[2] == pytest.approx(0.8) and seen[-1] == pytest.approx(0.95)


def test_processing_stage_is_sticky():
    t = runner.Tracker("audio")
    t.feed("__P__downloading|100|100|NA|1|1")
    assert t.feed('[ExtractAudio] Destination: x.mp3') and t.stage == "processing" and t.progress >= 0.95
    assert t.feed("__P__downloading|1|100|NA|1|1") is False             # the cover-art download must not look like a regression
    assert t.stage == "processing" and t.progress >= 0.95


def test_unknown_values_and_estimates():
    t = runner.Tracker("audio")
    t.feed("__P__downloading|1000|NA|2000|NA|NA")
    assert t.progress == pytest.approx(0.45) and t.speed is None and t.eta is None
    t.feed("__P__downloading|NA|NA|NA|NA|NA")
    assert t.progress == pytest.approx(0.45)
    assert not t.feed("[info] something unrelated")


# --------------------------------------------------------------------------- error messages
@pytest.mark.parametrize("text,code", [
    ("ERROR: [youtube] x: Sign in to confirm you're not a bot", "youtube_blocked"),
    ("ERROR: Unsupported URL: https://example.com/x", "unsupported"),
    ("ERROR: [generic] No suitable extractor found for URL https://example.com/x", "unsupported"),
    ("[download] File is larger than max-filesize (400000000 bytes > 300000000 bytes). Aborting.", "too_large"),
    ("[download] A title does not pass filter (!is_live & duration<=?3600), skipping ..", "too_long"),
    ("ERROR: HTTP Error 429: Too Many Requests", "site_rate_limited"),
    ("ERROR: This video is DRM protected", "drm"),
    ("ERROR: [vimeo] 1: This video is private", "private"),
    ("ERROR: Video unavailable", "private"),
    ("ERROR: The uploader has not made this video available in your country (geo restricted)", "geo"),
    ("ERROR: Requested format is not available", "no_format"),
    ("ERROR: Unable to download webpage: <urlopen error timed out>", "network"),
    ("ERROR: This video is not available in your country", "geo"),
    ("ERROR: [site] 1: The requested format is not available", "no_format"),
    ("ERROR: This video is not available", "private"),
])
def test_known_errors(text, code):
    assert runner.classify_error(text)[0] == code


def test_unknown_error_message_leaks_no_links_or_paths():
    code, message = runner.classify_error("ERROR: [vimeo] 12: boom https://secret.example/a?token=1 C:\\Users\\bob\\x.mp4 /home/app/jobs/x/media.mp4\x1b[0m")
    assert code == "failed"
    for leaked in ("secret.example", "token=1", "bob", "/home/app", "\x1b"):
        assert leaked not in message
    assert "<link>" in message and len(message) < 260


def test_killed_by_file_size_limit():
    assert runner.classify_error("", -25)[0] == "too_large"


# --------------------------------------------------------------------------- link lookup (yt-dlp stubbed out)
def stub(monkeypatch, payload=None, returncode=0, stderr="", exc=None):
    def fake(cmd, **kw):
        if exc:
            raise exc
        out = payload if isinstance(payload, str) else json.dumps(payload)
        return subprocess.CompletedProcess(cmd, returncode, stdout=out, stderr=stderr)
    monkeypatch.setattr(runner.subprocess, "run", fake)


ARCHIVE = {"title": "Big Buck Bunny", "uploader": "jake@archive.org", "duration": 596.46, "extractor_key": "ArchiveOrg",
           "thumbnail": "https://archive.org/t.jpg", "ext": "avi", "vcodec": None, "acodec": None, "height": 720,
           "formats": [{"format_id": "0", "ext": "ogv", "vcodec": None, "acodec": None, "height": 300, "filesize": 46_935_223},
                       {"format_id": "1", "ext": "mp4", "vcodec": None, "acodec": None, "height": 360, "filesize": 61_878_609},
                       {"format_id": "2", "ext": "avi", "vcodec": None, "acodec": None, "height": 720, "filesize": 332_243_668}]}


def test_info_for_a_site_that_leaves_codecs_blank(settings, monkeypatch):
    stub(monkeypatch, ARCHIVE)
    info = runner.fetch_info("https://archive.org/details/x", settings, {})
    assert info["heights"] == [300, 360, 720] and info["has_video"] and info["has_audio"]
    assert info["sizes"] == {"300": 46_935_223, "360": 61_878_609, "720": 332_243_668}
    assert info["uploader"] == "" and info["thumbnail"] == "https://archive.org/t.jpg" and not info["too_long"]


def test_info_for_audio_only_site(settings, monkeypatch):
    stub(monkeypatch, {"title": "Flickermood", "uploader": "Forss", "duration": 213.9, "extractor_key": "Soundcloud",
                       "thumbnail": "http://insecure.example/t.jpg",
                       "formats": [{"vcodec": "none", "acodec": "mp4a.40.2", "abr": 96, "filesize_approx": 2_566_632},
                                   {"vcodec": "none", "acodec": "mp4a.40.2", "abr": 160, "filesize_approx": 4_277_720}]})
    info = runner.fetch_info("https://soundcloud.com/forss/flickermood", settings, {})
    assert info["heights"] == [] and not info["has_video"] and info["has_audio"]
    assert info["audio_size"] == 4_277_720 and info["uploader"] == "Forss"
    assert info["thumbnail"] is None                                        # only https pictures are shown


def test_info_adds_the_audio_stream_to_video_only_formats(settings, monkeypatch):
    stub(monkeypatch, {"title": "T", "duration": 7200, "formats": [
        {"vcodec": "avc1.64001F", "acodec": "none", "height": 720, "filesize": 10_000_000, "tbr": 1500},
        {"vcodec": "vp09", "acodec": "none", "height": 720, "filesize": 8_000_000, "tbr": 1200},
        {"vcodec": "avc1", "acodec": "none", "height": 1440, "filesize": 50_000_000},
        {"vcodec": "none", "acodec": "mp4a", "abr": 128, "filesize": 3_000_000}]})
    info = runner.fetch_info("https://vimeo.com/1", settings, {})
    assert info["heights"] == [720]                                         # 1440p is above the server's cap
    assert info["sizes"] == {"720": 13_000_000}                              # the H.264 stream (preferred) plus audio
    assert info["too_long"]


@pytest.mark.parametrize("payload,code,status", [({"_type": "playlist", "entries": []}, "playlist", 422), ({"is_live": True, "formats": []}, "live", 422)])
def test_info_refuses_playlists_and_live(settings, monkeypatch, payload, code, status):
    stub(monkeypatch, payload)
    with pytest.raises(ApiError) as caught:
        runner.fetch_info("https://vimeo.com/1", settings, {})
    assert (caught.value.code, caught.value.status) == (code, status)


def test_info_failures(settings, monkeypatch):
    for kwargs, code, status in [(dict(payload="", returncode=1, stderr="ERROR: Sign in to confirm you're not a bot"), "youtube_blocked", 422),
                                 (dict(exc=subprocess.TimeoutExpired("x", 1)), "timeout", 504),
                                 (dict(payload="not json at all"), "failed", 502),
                                 (dict(exc=FileNotFoundError()), "failed", 500)]:
        stub(monkeypatch, **kwargs)
        with pytest.raises(ApiError) as caught:
            runner.fetch_info("https://vimeo.com/1", settings, {})
        assert (caught.value.code, caught.value.status) == (code, status)


def test_dir_size(tmp_path):
    (tmp_path / "a").write_bytes(b"x" * 10)
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b").write_bytes(b"x" * 5)
    assert runner.dir_size(tmp_path) == 15
    assert runner.dir_size(tmp_path / "missing") == 0
