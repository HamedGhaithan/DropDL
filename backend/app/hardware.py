"""Hardware video encoding: find the GPU encoders that actually work on this PC and build their FFmpeg flags.

FFmpeg lists encoders it was built with, not ones the machine can run (an RTX 30 card lists av1_nvenc but
cannot use it; a PC without Intel graphics lists h264_qsv). So each candidate is proven with a short test
encode, the result is cached per FFmpeg build, and callers always have the CPU encoder to fall back to.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time
from pathlib import Path

from .settings import CONFIG_ROOT

log = logging.getLogger('dropdl.hardware')
# Fastest first. MediaFoundation (h264_mf) works almost everywhere on Windows but its quality control is
# weak, so it is never chosen automatically.
# On a Mac the GPU encoder is Apple's VideoToolbox (Apple Silicon media engine or Intel Quick Sync underneath).
CANDIDATES = {
    'h264': ['h264_videotoolbox', 'h264_nvenc', 'h264_amf', 'h264_qsv'],
    'hevc': ['hevc_videotoolbox', 'hevc_nvenc', 'hevc_amf', 'hevc_qsv'],
    'av1': ['av1_nvenc', 'av1_amf', 'av1_qsv'],
}
SOFTWARE = {'h264': 'libx264', 'hevc': 'libx265', 'av1': 'libsvtav1'}
VENDOR = {'nvenc': 'NVIDIA', 'amf': 'AMD', 'qsv': 'Intel', 'videotoolbox': 'Apple'}
PROBE_VERSION = 3          # bump when the probe flags change, so saved results are measured again
_lock = threading.Lock()
_cache: dict | None = None


def _cache_file() -> Path:
    return CONFIG_ROOT / 'hardware.json'


def _run(command: list[str], timeout: float = 25) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout,
                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def _ffmpeg() -> str:
    from .downloader import _tool
    return _tool('ffmpeg')


def _signature(ffmpeg: str) -> str:
    try:
        stat = Path(ffmpeg).stat()
        return f'{PROBE_VERSION}|{Path(ffmpeg).resolve()}|{stat.st_size}|{int(stat.st_mtime)}'
    except OSError:
        return ffmpeg


def probe_encoder(ffmpeg: str, encoder: str) -> bool:
    """True when a one-second 720p test encode with `encoder`, using the exact flags exports use, succeeds."""
    try:
        result = _run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=1280x720:rate=30',
                       '-t', '1', *video_flags(encoder, 20), '-f', 'null', '-'], timeout=20)
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def detect(force: bool = False) -> dict:
    """{'encoders': {codec: [working hardware encoders]}, 'gpu': name or None, 'checked_at': t}. Cached."""
    global _cache
    with _lock:
        try:
            ffmpeg = _ffmpeg()
        except RuntimeError:
            return {'encoders': {}, 'gpu': None, 'checked_at': None, 'error': 'FFmpeg is missing.'}
        signature = _signature(ffmpeg)
        if not force:
            if _cache and _cache.get('signature') == signature:
                return _cache
            try:
                saved = json.loads(_cache_file().read_text(encoding='utf-8'))
                if saved.get('signature') == signature and time.time() - saved.get('checked_at', 0) < 30 * 86400:
                    _cache = saved
                    return saved
            except (OSError, ValueError):
                pass
        try:
            listed = _run([ffmpeg, '-hide_banner', '-encoders'], timeout=15).stdout
        except (OSError, subprocess.SubprocessError):
            listed = ''
        working: dict[str, list[str]] = {}
        for codec, names in CANDIDATES.items():
            working[codec] = [name for name in names if f' {name} ' in listed and probe_encoder(ffmpeg, name)]
        first = next((name for names in working.values() for name in names), None)
        gpu = VENDOR.get(first.split('_')[-1]) if first else None
        _cache = {'signature': signature, 'encoders': working, 'gpu': gpu, 'checked_at': time.time()}
        try:
            CONFIG_ROOT.mkdir(parents=True, exist_ok=True)
            _cache_file().write_text(json.dumps(_cache), encoding='utf-8')
        except OSError:
            pass
        log.info('Hardware encoders: %s', working)
        return _cache


def detect_in_background():
    threading.Thread(target=lambda: detect(), name='hardware-probe', daemon=True).start()


def choose(codec: str = 'h264', prefer_hardware: bool = True) -> str:
    """The encoder to use for `codec`: the first working GPU encoder, else the CPU encoder."""
    if prefer_hardware:
        found = (detect().get('encoders') or {}).get(codec) or []
        if found:
            return found[0]
    return SOFTWARE.get(codec, 'libx264')


def video_flags(encoder: str, quality: int = 20, speed: str = 'balanced', bitrate: int | None = None) -> list[str]:
    """FFmpeg flags for `encoder` at a quality comparable to x264 CRF `quality` (lower is better), or at `bitrate`.

    The GPU settings were matched to x264 with VMAF on 1080p footage: NVENC at CQ = CRF + 7 with adaptive
    quantization and look-ahead gives the same score and file size about three times faster; AMF at QP = CRF
    matches x264 at about half the time.
    """
    q = max(0, min(51, int(quality)))
    rate = ['-b:v', str(bitrate), '-maxrate', str(int(bitrate * 1.4)), '-bufsize', str(int(bitrate * 2))] if bitrate else []
    if encoder in ('libx264', 'libx265'):
        preset = {'fast': 'veryfast', 'balanced': 'medium', 'best': 'slow'}.get(speed, 'medium')
        if encoder == 'libx265':
            preset = {'fast': 'superfast', 'balanced': 'fast', 'best': 'medium'}.get(speed, 'fast')
        quality_flags = rate or ['-crf', str(min(51, q + (5 if encoder == 'libx265' else 0)))]
        return ['-c:v', encoder, '-preset', preset, *quality_flags, '-pix_fmt', 'yuv420p']
    if encoder == 'libsvtav1':
        preset = {'fast': '10', 'balanced': '7', 'best': '4'}.get(speed, '7')
        return ['-c:v', encoder, '-preset', preset, *(rate or ['-crf', str(min(63, q + 10))]), '-pix_fmt', 'yuv420p']
    if encoder.endswith('_nvenc'):
        preset = {'fast': 'p3', 'balanced': 'p5', 'best': 'p7'}.get(speed, 'p5')
        quality_flags = rate or ['-cq', str(min(51, q + 7)), '-b:v', '0']
        return ['-c:v', encoder, '-preset', preset, '-tune', 'hq', '-rc', 'vbr', *quality_flags, '-spatial-aq', '1',
                '-temporal-aq', '1', '-rc-lookahead', '20', '-bf', '3', '-pix_fmt', 'yuv420p']
    if encoder.endswith('_amf'):
        quality_mode = {'fast': 'speed', 'balanced': 'balanced', 'best': 'quality'}.get(speed, 'balanced')
        quality_flags = ['-rc', 'vbr_peak', *rate] if rate else ['-rc', 'cqp', '-qp_i', str(q), '-qp_p', str(q + 2), '-qp_b', str(q + 4)]
        return ['-c:v', encoder, '-quality', quality_mode, *quality_flags, '-pix_fmt', 'nv12']
    if encoder.endswith('_videotoolbox'):
        # VideoToolbox constant quality (-q:v 1-100, higher is better) runs on Apple Silicon; Intel Macs only take a
        # bitrate, so their probe fails here and exports fall back to x264 unless a bitrate target is set.
        quality_flags = rate or ['-q:v', str(max(1, min(100, round(118 - 2.6 * q))))]
        return ['-c:v', encoder, '-allow_sw', '0', '-realtime', '0', *quality_flags, '-pix_fmt', 'yuv420p']
    if encoder.endswith('_qsv'):
        preset = {'fast': 'veryfast', 'balanced': 'medium', 'best': 'slow'}.get(speed, 'medium')
        return ['-c:v', encoder, '-preset', preset, *(rate or ['-global_quality', str(q + 2)]), '-pix_fmt', 'nv12']
    return ['-c:v', encoder]


def is_hardware(encoder: str) -> bool:
    return encoder.endswith(('_nvenc', '_amf', '_qsv', '_videotoolbox'))


def summary() -> dict:
    found = detect()
    encoders = found.get('encoders') or {}
    return {'gpu': found.get('gpu'), 'h264': (encoders.get('h264') or [None])[0], 'hevc': (encoders.get('hevc') or [None])[0],
            'av1': (encoders.get('av1') or [None])[0], 'checked_at': found.get('checked_at'), 'error': found.get('error')}
