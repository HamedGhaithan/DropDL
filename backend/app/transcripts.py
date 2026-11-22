"""Transcripts: turn subtitles (downloaded, auto-generated or imported) into timed, searchable text.

Sources, in order: subtitle files saved next to a download, a fresh fetch of the site's captions through
yt-dlp (no audio processing, no model), or an .srt/.vtt the user imports. Results are cached as JSON under
CONFIG_ROOT/transcripts and power the transcript panel in Clip Studio and the library-wide search.
"""
from __future__ import annotations

import html
import json
import logging
import re
import threading
import time
from pathlib import Path

from .settings import CONFIG_ROOT

log = logging.getLogger('dropdl.transcripts')
TIME = re.compile(r'(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})')
ARROW = re.compile(r'^\s*(\S+)\s*-->\s*(\S+)')
TAG = re.compile(r'<[^>]+>')
STAMP = re.compile(r'<((?:\d+:)?\d{1,2}:\d{2}[.,]\d{1,3})>')
_lock = threading.Lock()


def _seconds(stamp: str) -> float:
    match = TIME.fullmatch(stamp.strip())
    if not match:
        raise ValueError(stamp)
    hours, minutes, seconds, fraction = match.groups()
    return int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds) + int(fraction.ljust(3, '0')[:3]) / 1000


def _clean(text: str) -> str:
    text = TAG.sub('', text)
    text = html.unescape(text).replace('​', '')
    return ' '.join(text.split())


def _timed_words(line: str, start: float) -> list[list] | None:
    """Word start times from YouTube's inline timing tags (`word<00:00:01.120><c> next</c>`), when present."""
    if not STAMP.search(line):
        return None
    words, moment = [], start
    for index, part in enumerate(STAMP.split(line)):
        if index % 2:
            try:
                moment = _seconds(part)
            except ValueError:
                return None
            continue
        words += [[round(moment, 3), word] for word in _clean(part).split()]
    return words


def parse(text: str) -> list[dict]:
    """Parse SRT or WebVTT into [{'start', 'end', 'text'}], merging YouTube's rolling auto-captions.

    Auto-captions repeat the previous line at the top of every cue and add the new words below it, so a naive
    parse doubles every sentence. Each cue keeps only the text that is new compared with the cue before.
    """
    text = text.replace('\r\n', '\n').replace('\r', '\n').lstrip('﻿')
    # Line by line: a cue runs from its timing line to the next empty line. YouTube puts a line holding a single
    # space inside its cues, so whitespace-only lines must not end a cue the way an empty line does.
    cues: list[dict] = []
    current: dict | None = None
    for line in text.split('\n'):
        match = ARROW.match(line)
        if match:
            if current and current['raw'] and current['raw'][-1].strip().isdigit():
                current['raw'].pop()                      # an SRT counter that followed a whitespace-only separator
            try:
                current = {'start': round(_seconds(match.group(1)), 3), 'end': round(_seconds(match.group(2)), 3), 'raw': []}
            except ValueError:
                current = None
                continue
            cues.append(current)
        elif current is not None:
            if line == '' and current['raw']:
                current = None
            elif line:                                    # an empty line straight after the timing is not an end
                current['raw'].append(line)
    for cue in cues:
        raw = cue.pop('raw')
        cleaned = [(_clean(line), line) for line in raw]
        cue['lines'] = [item for item, _ in cleaned if item]
        cue['timed'] = {item: _timed_words(line, cue['start']) for item, line in cleaned if item}
    cues = [cue for cue in cues if cue['lines'] and cue['end'] > cue['start']]
    segments: list[dict] = []
    previous_lines: list[str] = []
    for cue in cues:
        lines = cue['lines']
        fresh = [line for line in lines if line not in previous_lines]
        previous_lines = lines
        if not fresh:
            continue
        sentence = ' '.join(fresh)
        if segments and segments[-1]['text'] == sentence:
            segments[-1]['end'] = max(segments[-1]['end'], cue['end'])
            continue
        if segments and cue['end'] - cue['start'] < 0.05:    # zero-length "settle" cues add nothing
            continue
        segment = {'start': cue['start'], 'end': cue['end'], 'text': sentence}
        timed = [cue['timed'].get(line) for line in fresh]
        if all(timed):                                  # every new line carries word timings: keep them
            words = [word for line in timed for word in line]
            if len(words) == len(sentence.split()):
                segment['words'] = [max(cue['start'], min(cue['end'], t)) for t, _ in words]
        segments.append(segment)
    for current, following in zip(segments, segments[1:]):  # rolling cues overlap: end where the next one starts
        if current['end'] > following['start']:
            current['end'] = max(current['start'] + .2, following['start'])
    return segments


def to_srt(segments: list[dict]) -> str:
    def stamp(value: float) -> str:
        ms = int(round(value * 1000))
        return f'{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}'
    return '\n'.join(f"{i}\n{stamp(s['start'])} --> {stamp(s['end'])}\n{s['text']}\n" for i, s in enumerate(segments, 1))


def to_text(segments: list[dict]) -> str:
    return '\n'.join(s['text'] for s in segments)


# ---------------------------------------------------------------- storage
def _folder() -> Path:
    folder = CONFIG_ROOT / 'transcripts'
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _key(kind: str, identity: str) -> Path:
    if kind not in ('job', 'media') or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', identity):
        raise ValueError('Invalid transcript reference.')
    return _folder() / f'{kind}-{identity}.json'


def load(kind: str, identity: str) -> dict | None:
    try:
        return json.loads(_key(kind, identity).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def save(kind: str, identity: str, segments: list[dict], *, language: str = '', source: str = '', title: str = '', extra: dict | None = None) -> dict:
    record = {**(extra or {}), 'kind': kind, 'id': identity, 'language': language, 'source': source, 'title': title,
              'segments': segments, 'words': sum(len(s['text'].split()) for s in segments), 'created_at': time.time()}
    path = _key(kind, identity)
    temporary = path.with_suffix('.tmp')
    with _lock:
        temporary.write_text(json.dumps(record, ensure_ascii=False), encoding='utf-8')
        temporary.replace(path)
    return record


def remove(kind: str, identity: str) -> None:
    _key(kind, identity).unlink(missing_ok=True)


def sidecars(media: Path) -> list[Path]:
    """Subtitle files saved next to a media file (title.en.vtt, title.en-orig.srt, title.srt...)."""
    folder, stem = media.parent, media.stem
    try:
        return sorted((p for p in folder.iterdir() if p.suffix.lower() in {'.vtt', '.srt'} and p.name.startswith(stem)),
                      key=lambda p: (0 if '.en' in p.name.lower() else 1, len(p.name)))
    except OSError:
        return []


def from_sidecar(media: Path) -> tuple[list[dict], str] | None:
    for path in sidecars(media):
        try:
            segments = parse(path.read_text(encoding='utf-8', errors='replace'))
        except OSError:
            continue
        if segments:
            language = path.name[len(media.stem):].strip('.').rsplit('.', 1)[0]
            return segments, language
    return None


def _pick(table: dict, language: str) -> str | None:
    if not language:
        return None
    if language in table:
        return language
    return next((key for key in table if key.split('-')[0] == language and not key.endswith('-orig')), None)


def fetch_captions(url: str, preferred: str = '') -> tuple[list[dict], str, str] | None:
    """The best caption track a site offers for `url`: (segments, language, 'subtitles' | 'auto'), or None.

    Prefers human subtitles in the video's own language, then the site's automatic captions in that language
    (YouTube marks the untranslated track "-orig"), then English or Arabic. Only the caption file is fetched.
    """
    import shutil
    from yt_dlp import YoutubeDL
    from .downloader import current_network, network_options
    options = {'quiet': True, 'no_warnings': True, 'skip_download': True, 'noplaylist': True, 'socket_timeout': 30}
    if (CONFIG_ROOT / 'cookies.txt').is_file():
        options['cookiefile'] = str(CONFIG_ROOT / 'cookies.txt')
    if shutil.which('node'):
        options['js_runtimes'] = {'node': {}}
    options.update(network_options(current_network()))
    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)
        manual = {k: v for k, v in (info.get('subtitles') or {}).items() if k != 'live_chat'}
        automatic = info.get('automatic_captions') or {}
        spoken = (info.get('language') or '').split('-')[0]
        order: list[tuple[str, str | None]] = []
        for language in dict.fromkeys([preferred, spoken, 'en', 'ar']):
            if language:
                order += [('subtitles', _pick(manual, language)), ('auto', f'{language}-orig' if f'{language}-orig' in automatic else None),
                          ('auto', _pick(automatic, language))]
        order += [('subtitles', key) for key in manual] + [('auto', key) for key in automatic if key.endswith('-orig')]
        for kind, key in order:
            tracks = (manual if kind == 'subtitles' else automatic).get(key or '') or []
            chosen = next((t for t in tracks if t.get('ext') == 'vtt'), None) or next((t for t in tracks if t.get('ext') == 'srt'), None)
            if not chosen or not chosen.get('url'):
                continue
            text = ydl.urlopen(chosen['url']).read().decode('utf-8', errors='replace')
            segments = parse(text)
            if segments:
                return segments, key.removesuffix('-orig'), kind
    return None


# ---------------------------------------------------------------- search
def search(query: str, limit: int = 60) -> list[dict]:
    """Find `query` (all words, any order within a line) across every saved transcript."""
    words = [w for w in query.lower().split() if w]
    if not words:
        return []
    results = []
    for path in sorted(_folder().glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            record = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        for segment in record.get('segments', []):
            line = segment['text'].lower()
            if all(word in line for word in words):
                results.append({'kind': record['kind'], 'id': record['id'], 'title': record.get('title') or '',
                                'job_id': record.get('job_id', ''), 'path': record.get('path', ''),
                                'start': segment['start'], 'end': segment['end'], 'text': segment['text']})
                if len(results) >= limit:
                    return results
    return results
