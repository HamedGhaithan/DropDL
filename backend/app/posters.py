"""Representative images for media cards, queue rows and timeline clips (2.1).

1.x always grabbed the very first frame, which is black for most films,
trailers and fade-ins. Video now uses FFmpeg's ``thumbnail`` filter over a
window ~10% into the file (it picks the frame closest to the average, which
skips black and transition frames). Audio uses its embedded cover art.
"""
import os
import subprocess
from pathlib import Path

from .converter import probe_media

FLAGS = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0


def _run(command, timeout):
    return subprocess.run(command, capture_output=True, timeout=timeout, creationflags=FLAGS)


def make_poster(source: str, target: Path, width: int = 320) -> bool:
    """Write a JPEG poster for ``source``; False when it has no picture."""
    from .downloader import _tool
    try:
        info = probe_media(source)
    except Exception:
        info = {}
    duration = float(info.get('duration') or 0)
    has_video = bool(info.get('video_codec'))
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.stem + '.tmp' + target.suffix)
    scale = f'scale={width}:-2'
    attempts = []
    if has_video and duration > 2:
        offset = min(duration * 0.1, 45.0)
        attempts.append(['-ss', f'{offset:.2f}', '-i', source, '-map', '0:v:0', '-vf', f'thumbnail=48,{scale}'])
    # Short clips, audio cover art (an attached picture is a video stream), and
    # the fallback when the analysed window can't be decoded.
    attempts.append(['-i', source, '-map', '0:v:0', '-vf', scale])
    try:
        for arguments in attempts:
            result = _run([_tool('ffmpeg'), '-nostdin', '-v', 'error', '-y', '-threads', '2', *arguments,
                           '-frames:v', '1', '-q:v', '4', str(temporary)], timeout=25)
            if result.returncode == 0 and temporary.is_file() and temporary.stat().st_size > 0:
                temporary.replace(target)
                return True
        return False
    except (OSError, subprocess.TimeoutExpired):
        return False
    finally:
        temporary.unlink(missing_ok=True)
