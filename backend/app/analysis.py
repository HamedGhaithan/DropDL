"""Smart edit analysis for Clip Studio: silences, scene cuts and loudness, measured with FFmpeg.

Every result is cached per file (path, size and modification time) and per setting, so asking again is instant.
Nothing leaves the PC and no model is involved: these are signal measurements FFmpeg already knows how to make.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import threading
from pathlib import Path

from .settings import CONFIG_ROOT

SILENCE_START = re.compile(r'silence_start:\s*(-?[\d.]+)')
SILENCE_END = re.compile(r'silence_end:\s*(-?[\d.]+)')
SCENE_TIME = re.compile(r'pts_time:\s*([\d.]+)')
_slots = threading.BoundedSemaphore(2)


def _ffmpeg() -> str:
    from .downloader import _tool
    return _tool('ffmpeg')


def _cache_path(path: Path, kind: str, settings: dict) -> Path:
    stat = path.stat()
    key = json.dumps([str(path.resolve()), stat.st_size, int(stat.st_mtime), kind, settings], sort_keys=True)
    folder = CONFIG_ROOT / 'analysis'
    folder.mkdir(parents=True, exist_ok=True)
    return folder / (hashlib.sha256(key.encode()).hexdigest()[:32] + '.json')


def _cached(path: Path, kind: str, settings: dict, work):
    target = _cache_path(path, kind, settings)
    try:
        return json.loads(target.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        pass
    with _slots:
        result = work()
    try:
        target.write_text(json.dumps(result), encoding='utf-8')
    except OSError:
        pass
    return result


def _run(command: list[str], timeout: float) -> str:
    try:
        process = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout,
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError('The analysis took too long for this file.') from exc
    if process.returncode:
        raise RuntimeError('FFmpeg could not analyse this file: ' + (process.stderr or '')[-400:])
    return process.stderr or ''


def silences(path: str | Path, threshold_db: float = -35, minimum: float = .6, duration: float | None = None) -> list[list[float]]:
    """Quiet stretches as [[start, end], ...] in source seconds."""
    path = Path(path)
    settings = {'threshold': round(float(threshold_db), 1), 'minimum': round(float(minimum), 2)}

    def work():
        log = _run([_ffmpeg(), '-nostdin', '-hide_banner', '-v', 'info', '-i', str(path), '-map', '0:a:0', '-vn', '-sn', '-dn',
                    '-af', f"silencedetect=noise={settings['threshold']}dB:d={settings['minimum']}", '-f', 'null', '-'], 1800)
        found, start = [], None
        for line in log.splitlines():
            if (match := SILENCE_START.search(line)):
                start = max(0.0, float(match.group(1)))
            elif (match := SILENCE_END.search(line)) and start is not None:
                found.append([round(start, 3), round(float(match.group(1)), 3)])
                start = None
        if start is not None:                       # silent until the end of the file
            found.append([round(start, 3), None])
        return found

    found = []
    for a, b in _cached(path, 'silence', settings, work):
        b = duration if b is None else b             # silence that runs to the end of the file
        if b is not None and b > a:
            found.append([a, b])
    return found


def scenes(path: str | Path, sensitivity: float = .35, minimum_gap: float = .8) -> list[float]:
    """Times (source seconds) where the picture cuts to a new shot."""
    path = Path(path)
    settings = {'sensitivity': round(min(.9, max(.05, float(sensitivity))), 2)}

    def work():
        log = _run([_ffmpeg(), '-nostdin', '-hide_banner', '-v', 'info', '-i', str(path), '-map', '0:v:0', '-an', '-sn', '-dn',
                    '-vf', f"scale=320:-2,select='gt(scene,{settings['sensitivity']})',showinfo", '-f', 'null', '-'], 3600)
        return [round(float(match.group(1)), 3) for line in log.splitlines() if 'showinfo' in line and (match := SCENE_TIME.search(line))]

    cuts, last = [], -1e9
    for moment in _cached(path, 'scenes', settings, work):
        if moment - last >= minimum_gap:
            cuts.append(moment)
            last = moment
    return cuts


def loudness(path: str | Path, start: float = 0, end: float | None = None) -> dict:
    """Integrated loudness (LUFS), true peak (dBTP) and loudness range (LU) of a stretch of a file."""
    path = Path(path)
    settings = {'start': round(start, 2), 'end': round(end, 2) if end else None}

    def work():
        command = [_ffmpeg(), '-nostdin', '-hide_banner', '-v', 'info']
        if start:
            command += ['-ss', str(start)]
        command += ['-i', str(path)]
        if end:
            command += ['-t', str(max(.1, end - start))]
        log = _run(command + ['-map', '0:a:0', '-vn', '-af', 'loudnorm=print_format=json', '-f', 'null', '-'], 1800)
        block = log[log.rfind('{'):log.rfind('}') + 1]
        data = json.loads(block)
        return {'integrated': float(data['input_i']), 'true_peak': float(data['input_tp']), 'range': float(data['input_lra'])}

    return _cached(path, 'loudness', settings, work)


def keep_ranges(quiet: list[list[float]], start: float, end: float, padding: float = .12, minimum_keep: float = .2) -> list[list[float]]:
    """The parts of [start, end] that are not silent, each widened by `padding` so words are not clipped."""
    keep, cursor = [], start
    for a, b in sorted(quiet):
        a, b = max(start, a + padding), min(end, b - padding)
        if b <= a:                                   # too short once padded: not worth a cut
            continue
        if a > cursor:
            keep.append([cursor, a])
        cursor = max(cursor, b)
    if end > cursor:
        keep.append([cursor, end])
    # A blip shorter than `minimum_keep` (a click between two pauses) is treated as part of the silence.
    return [[round(a, 3), round(b, 3)] for a, b in keep if b - a >= max(.05, minimum_keep)]


# ---------------------------------------------------------------- music beats
ENVELOPE_RATE = 100        # envelope frames per second (10 ms)


def _envelopes(path: Path, start: float, end: float | None) -> tuple[list[float], list[float]]:
    """Low (kick) and high (snare, hats) band energy envelopes, computed by FFmpeg at 100 frames a second."""
    import array
    command = [_ffmpeg(), '-nostdin', '-hide_banner', '-v', 'error']
    if start:
        command += ['-ss', str(start)]
    command += ['-i', str(path)]
    if end:
        command += ['-t', str(max(.5, end - start))]
    command += ['-filter_complex', "[0:a:0]aformat=channel_layouts=mono,aresample=22050,asplit[a][b];"
                "[a]lowpass=f=150,aeval=val(0)*val(0)[l];[b]highpass=f=2500,aeval=val(0)*val(0)[h];"
                f"[l][h]amerge=inputs=2,aresample={ENVELOPE_RATE}:filter_size=64[out]", '-map', '[out]', '-f', 'f32le', '-']
    try:
        process = subprocess.run(command, capture_output=True, timeout=900, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError('The analysis took too long for this file.') from exc
    if process.returncode:
        raise RuntimeError('FFmpeg could not read the music: ' + process.stderr.decode(errors='replace')[-300:])
    values = array.array('f')
    values.frombytes(process.stdout[:len(process.stdout) // 8 * 8])
    return [max(0.0, v) for v in values[0::2]], [max(0.0, v) for v in values[1::2]]


def onset_strength(low: list[float], high: list[float]) -> list[float]:
    """How suddenly the music gets louder in each 10 ms frame (positive log-energy change, both bands)."""
    import math
    result = [0.0] * len(low)
    for band in (low, high):
        peak = max(band, default=0) or 1.0
        logs = [math.log1p(1000 * v / peak) for v in band]
        flux = [0.0] + [max(0.0, logs[i] - logs[i - 1]) for i in range(1, len(logs))]
        mean = sum(flux) / max(1, len(flux))
        spread = (sum((f - mean) ** 2 for f in flux) / max(1, len(flux))) ** .5 or 1.0
        for i, f in enumerate(flux):
            result[i] += f / spread
    return result


def tempo_and_beats(onset: list[float], rate: int = ENVELOPE_RATE) -> tuple[float, list[float]]:
    """Tempo by autocorrelation (60-200 BPM, gently preferring ~120), then beats tracked along the onsets."""
    import math
    n = len(onset)
    if n < rate * 3:
        return 0.0, []
    mean = sum(onset) / n
    centred = [v - mean for v in onset]
    best, best_lag = -1e18, 0
    scores = {}
    for lag in range(int(rate * 60 / 200), int(rate * 60 / 60) + 1):
        score = sum(centred[i] * centred[i + lag] for i in range(0, n - lag)) / (n - lag)
        bpm = 60 * rate / lag
        score *= math.exp(-.5 * (math.log2(bpm / 120) / .9) ** 2)       # prefer the felt tempo over halves/doubles
        scores[lag] = score
        if score > best:
            best, best_lag = score, lag
    if best <= 0:
        return 0.0, []
    # Sub-frame precision from the neighbouring lags (parabolic peak).
    a, b, c = scores.get(best_lag - 1, best), best, scores.get(best_lag + 1, best)
    shift = .5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) != 0 else 0
    period = best_lag + max(-.5, min(.5, shift))
    return track_beats(onset, period, rate)


def track_beats(onset: list[float], period: float, rate: int = ENVELOPE_RATE, tightness: float = 120) -> tuple[float, list[float]]:
    """The beat sequence that best balances landing on onsets against keeping a steady tempo.

    Dynamic programming (Ellis, 2007): each frame's score is its onset strength plus the best score of a previous
    beat between half and twice a period earlier, minus a penalty for straying from the period. Backtracking from
    the best final beat gives a globally consistent sequence, so early beats and tempo drift are handled well.
    """
    import math
    n = len(onset)
    mean = sum(onset) / max(1, n)
    spread = (sum((v - mean) ** 2 for v in onset) / max(1, n)) ** .5 or 1.0
    strength = [v / spread for v in onset]
    low, high = max(1, int(round(period / 2))), max(2, int(round(period * 2)))
    penalty = {gap: -tightness * math.log(gap / period) ** 2 for gap in range(low, high + 1)}
    gaps = list(penalty.items())
    score, back = [0.0] * n, [-1] * n
    for t in range(n):
        best, arg = 0.0, -1
        for gap, cost in gaps:
            prev = t - gap
            if prev < 0:
                break
            value = score[prev] + cost
            if value > best:
                best, arg = value, prev
        score[t], back[t] = strength[t] + best, arg
    tail = range(max(0, n - int(period * 1.5)), n)
    t = max(tail, key=lambda i: score[i])
    found = []
    while t >= 0:
        found.append(t)
        t = back[t]
    found.reverse()
    # Beats before the first strong one (a soft intro) are filled in on the same grid.
    while found and found[0] - period >= -period * .25:
        found.insert(0, max(0, int(round(found[0] - period))))
        if found[0] == found[1]:
            found.pop(0)
            break
    if len(found) < 2:
        return 0.0, []
    intervals = sorted(b - a for a, b in zip(found, found[1:]))
    median = intervals[len(intervals) // 2]
    steady = [i for i in intervals if abs(i - median) <= median * .25] or [median]   # ignore gaps and doubled beats
    return round(60 * rate / (sum(steady) / len(steady)), 1), [round(i / rate, 3) for i in found]


def beats(path: str | Path, start: float = 0, end: float | None = None) -> dict:
    """{'bpm': tempo, 'beats': [seconds from `start`]} for the music in a file."""
    path = Path(path)
    settings = {'start': round(start, 2), 'end': round(end, 2) if end else None, 'version': 3}

    def work():
        low, high = _envelopes(path, start, min(end, start + 1200) if end else start + 1200)
        bpm, found = tempo_and_beats(onset_strength(low, high))
        return {'bpm': bpm, 'beats': found}

    return _cached(path, 'beats', settings, work)
