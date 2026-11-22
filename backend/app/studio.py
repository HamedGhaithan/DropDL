"""Clip Studio projects and smart tools (DropDL 3.0).

Projects made from the Studio home need no source clip: they can start empty and gather media later. Their timeline
uses the same recovery history as quick edits (editor-projects/<hash>.json); this module keeps the catalogue around
it (name, frame shape, the files it uses, a poster) and re-links files whose temporary task records were cleared.

The smart tools (silence removal, scene splits, transcripts) work on the files behind a project's clips.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field, field_validator

from . import analysis, transcripts
from .jobs import jobs
from .settings import CONFIG_ROOT

router = APIRouter(prefix='/api/studio')
PROJECT_ID = re.compile(r'p[0-9a-f]{20}')
ASPECT_PATTERN = r'^(16:9|9:16|1:1|4:5|4:3|original)$'
_lock = threading.RLock()


def is_project(identity: str) -> bool:
    return bool(PROJECT_ID.fullmatch(identity or ''))


def _catalogue() -> Path:
    return CONFIG_ROOT / 'studio-projects.json'


def _load() -> list[dict]:
    try:
        data = json.loads(_catalogue().read_text(encoding='utf-8'))
        return [item for item in data if isinstance(item, dict) and is_project(item.get('id', ''))] if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _store(items: list[dict]) -> None:
    path = _catalogue()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding='utf-8')
    os.replace(temporary, path)


def _record(identity: str) -> dict:
    if not is_project(identity):
        raise HTTPException(404, 'Project not found.')
    record = next((item for item in _load() if item['id'] == identity), None)
    if not record:
        raise HTTPException(404, 'Project not found.')
    return record


def _clean_name(value: str) -> str:
    name = ' '.join(''.join(ch for ch in value if ch.isprintable()).split())[:80]
    if not name:
        raise HTTPException(422, 'Give the project a name.')
    return name


# Starter templates: a shape plus the settings that suit what is being made.
TEMPLATES = {
    'podcast': {'name': 'Podcast clip', 'aspect': '9:16', 'settings': {'fit': 'blur', 'height': 1920, 'caption_style': 'pop', 'loudness': -14, 'duck': True, 'export_preset': 'shorts'}},
    'short': {'name': 'Captioned short', 'aspect': '9:16', 'settings': {'fit': 'blur', 'height': 1920, 'caption_style': 'karaoke', 'loudness': -14, 'export_preset': 'shorts'}},
    'music': {'name': 'Music video', 'aspect': '16:9', 'settings': {'fit': 'crop', 'height': 1080, 'loudness': -14, 'export_preset': 'youtube'}},
    'tutorial': {'name': 'Tutorial', 'aspect': '16:9', 'settings': {'fit': 'fit', 'height': 1080, 'caption_style': 'boxed', 'loudness': -16, 'duck': True, 'export_preset': 'youtube'}},
}


def blank_project(aspect: str = '16:9') -> dict:
    return {'segments': [], 'ratio': aspect, 'rotate': 0, 'flip': False, 'brightness': 0, 'contrast': 1, 'saturation': 1,
            'volume': 1, 'fadeIn': 0, 'fadeOut': 0}


def _referenced(project: dict) -> list[str]:
    ids = [part.get('source_job_id') for part in project.get('segments', [])]
    if project.get('soundtrack'):
        ids.append(project['soundtrack'].get('source_job_id'))
    return list(dict.fromkeys(i for i in ids if i))


def _usable(identity: str):
    job = jobs.get(identity)
    return job if job and job.status == 'completed' and job.filename and Path(job.filename).is_file() else None


def register_file(path: str, title: str = '') -> str | None:
    """A completed task id for a local file (reused when one exists), adding the file to the media library."""
    from .converter import probe_media
    from .media_library import library
    file = Path(path)
    if not file.is_file():
        return None
    for item in jobs.list():
        cached = jobs.get(item['id'])
        if cached and cached.status == 'completed' and cached.filename == str(file):
            return cached.id
    try:
        metadata = probe_media(file)
        record = library.add(file, title=title or file.stem, kind=metadata['kind'], metadata={k: v for k, v in metadata.items() if k != 'streams'})
    except (ValueError, OSError, RuntimeError):
        return None
    job = jobs.create(url=record['url'] or 'local://' + record['id'], kind=record['kind'], container=file.suffix.lstrip('.'), quality='best',
                      directory=str(CONFIG_ROOT / 'work' / uuid4().hex), source_filename=str(file), purpose='preview', title=record['title'],
                      status='completed', percent=100, filename=str(file), preview_filename=str(file))
    return job.id


def relink(project: dict, media: dict) -> tuple[dict, int]:
    """Point clips whose task record was cleared at a fresh record for the same file."""
    mapping = {}
    for identity in _referenced(project):
        if _usable(identity):
            continue
        known = media.get(identity) or {}
        replacement = register_file(known.get('path', ''), known.get('title', '')) if known.get('path') else None
        if replacement and replacement != identity:
            mapping[identity] = replacement
    if not mapping:
        return project, 0
    project = json.loads(json.dumps(project))
    for part in project.get('segments', []):
        if part.get('source_job_id') in mapping:
            part['source_job_id'] = mapping[part['source_job_id']]
    if project.get('soundtrack', {}).get('source_job_id') in mapping:
        project['soundtrack']['source_job_id'] = mapping[project['soundtrack']['source_job_id']]
    return project, len(mapping)


def touch(identity: str, project: dict) -> None:
    """Refresh a project's card after its timeline was saved (called by the editor's save route)."""
    if not is_project(identity):
        return
    from .editor import timeline_duration
    with _lock:
        items = _load()
        record = next((item for item in items if item['id'] == identity), None)
        if not record:
            return
        ids = _referenced(project)
        media = {key: value for key, value in (record.get('media') or {}).items() if key in ids}
        for key in ids:
            job = jobs.get(key)
            if job and job.filename:
                media[key] = {'path': job.filename, 'title': job.title or Path(job.filename).stem}
        segments = project.get('segments', [])
        first = min(segments, key=lambda s: (s.get('offset') or 0, s.get('track') or 0), default=None)
        record.update(modified=time.time(), media=media, clips=len(segments), ratio=project.get('ratio', 'original'),
                      duration=round(timeline_duration(segments), 3) if segments else 0,
                      poster={'job': first['source_job_id'], 'at': round(first['start'] + min(1.5, (first['end'] - first['start']) / 3), 3)}
                      if first and first.get('source_job_id') else None)
        _store(items)


def _snapshot(identity: str) -> dict | None:
    from .workspace import _project_lock, project_history
    with _project_lock:
        history = project_history(identity)
    return history[0]['project'] if history else None


def _save_snapshot(identity: str, project: dict) -> dict:
    from .workspace import store_project
    return store_project(identity, project)


# ---------------------------------------------------------------- projects
class NewProject(BaseModel):
    name: str = Field(default='', max_length=200)
    aspect: str = Field(default='16:9', pattern=ASPECT_PATTERN)
    media: list[str] = Field(default_factory=list, max_length=50)
    template: str | None = Field(default=None, pattern='^(podcast|short|music|tutorial)$')


class ProjectName(BaseModel):
    name: str = Field(max_length=200)


@router.get('/projects')
def list_projects():
    items = sorted(_load(), key=lambda item: item.get('modified', 0), reverse=True)
    for item in items:
        item['missing'] = sum(1 for value in (item.get('media') or {}).values() if not Path(value.get('path', '')).is_file())
    return {'projects': items}


@router.post('/projects', status_code=201)
def create_project(payload: NewProject):
    from .converter import probe_media
    template = TEMPLATES.get(payload.template or '')
    aspect = template['aspect'] if template else payload.aspect
    project, cursor = {**blank_project(aspect), **(template['settings'] if template else {})}, 0.0
    titles = []
    for identity in dict.fromkeys(payload.media):
        job = _usable(identity)
        if not job:
            raise HTTPException(409, 'A chosen file is not ready or was moved.')
        try:
            info = probe_media(job.filename)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if info['duration'] < .05:
            raise HTTPException(422, 'A chosen file has no usable duration.')
        project['segments'].append({'source_job_id': job.id, 'start': 0, 'end': round(info['duration'], 3), 'speed': 1, 'gain': 1,
                                    'offset': round(cursor, 3), 'track': 0})
        cursor += info['duration']
        titles.append(job.title or Path(job.filename).stem)
    with _lock:
        items = _load()
        if len(items) >= 500:
            raise HTTPException(409, 'You have 500 projects. Delete some before creating more.')
        if payload.name.strip():
            name = _clean_name(payload.name)
        elif titles:
            name = _clean_name(titles[0])
        else:
            taken = {item['name'] for item in items}
            stem = template['name'] if template else 'Untitled project'
            number = 1
            while f'{stem} {number}' in taken:
                number += 1
            name = f'{stem} {number}'
        now = time.time()
        record = {'id': 'p' + uuid4().hex[:20], 'name': name, 'created': now, 'modified': now, 'aspect': aspect,
                  'ratio': aspect, 'duration': 0, 'clips': 0, 'media': {}, 'poster': None}
        items.append(record)
        _store(items)
    _save_snapshot(record['id'], project)
    touch(record['id'], project)
    return _record(record['id'])


@router.get('/projects/{identity}')
def open_project(identity: str):
    record = _record(identity)
    project = _snapshot(identity) or blank_project(record.get('aspect', '16:9'))
    project, relinked = relink(project, record.get('media') or {})
    if relinked:
        _save_snapshot(identity, project)
        touch(identity, project)
        record = _record(identity)
    missing = [identity for identity in _referenced(project) if not _usable(identity)]
    return {'record': record, 'project': project, 'relinked': relinked, 'missing': missing}


@router.post('/projects/{identity}/rename')
def rename_project(identity: str, payload: ProjectName):
    name = _clean_name(payload.name)
    with _lock:
        items = _load()
        record = next((item for item in items if item['id'] == identity), None)
        if not record:
            raise HTTPException(404, 'Project not found.')
        record.update(name=name, modified=time.time())
        _store(items)
    return record


@router.post('/projects/{identity}/duplicate', status_code=201)
def duplicate_project(identity: str):
    source = _record(identity)
    project = _snapshot(identity) or blank_project(source.get('aspect', '16:9'))
    with _lock:
        items = _load()
        now = time.time()
        copy = {**source, 'id': 'p' + uuid4().hex[:20], 'name': _clean_name(source['name'][:72] + ' (copy)'), 'created': now, 'modified': now}
        copy.pop('missing', None)
        items.append(copy)
        _store(items)
    _save_snapshot(copy['id'], project)
    return copy


@router.post('/projects/{identity}/remove')
def remove_project(identity: str):
    from .workspace import project_path
    with _lock:
        items = _load()
        if not any(item['id'] == identity for item in items):
            raise HTTPException(404, 'Project not found.')
        _store([item for item in items if item['id'] != identity])
    path = project_path(identity)
    for candidate in (path, path.with_suffix('.backup.json')):
        candidate.unlink(missing_ok=True)
    for poster in (CONFIG_ROOT / 'thumbnails').glob(f'studio-{identity}-*.jpg'):
        poster.unlink(missing_ok=True)
    return {'ok': True}


@router.get('/projects/{identity}/poster')
def project_poster(identity: str):
    from .downloader import _tool
    record = _record(identity)
    poster = record.get('poster') or {}
    job = _usable(poster.get('job', '')) if poster else None
    if not job or job.kind == 'audio':
        raise HTTPException(404, 'This project has no picture yet.')
    folder = CONFIG_ROOT / 'thumbnails'
    folder.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(f"{job.filename}|{poster.get('at', 0)}".encode()).hexdigest()[:16]
    target = folder / f'studio-{identity}-{key}.jpg'
    if not target.exists():
        for stale in folder.glob(f'studio-{identity}-*.jpg'):
            stale.unlink(missing_ok=True)
        process = subprocess.run([_tool('ffmpeg'), '-nostdin', '-v', 'error', '-y', '-ss', str(max(0, poster.get('at', 0))), '-i', job.filename,
                                  '-frames:v', '1', '-vf', 'scale=640:-2', '-q:v', '4', str(target)],
                                 capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        if process.returncode or not target.exists():
            raise HTTPException(404, 'This project has no picture yet.')
    return FileResponse(target, media_type='image/jpeg', headers={'Cache-Control': 'no-cache'})


# ---------------------------------------------------------------- smart tools
def _source(identity: str):
    job = _usable(identity)
    if not job:
        raise HTTPException(409, 'This clip\'s file is not available.')
    return job


class Range(BaseModel):
    source_job_id: str = Field(max_length=100)
    start: float = Field(default=0, ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)


class SilenceRequest(Range):
    threshold: float = Field(default=-35, ge=-70, le=-10, allow_inf_nan=False)
    minimum: float = Field(default=.6, ge=.2, le=5, allow_inf_nan=False)
    padding: float = Field(default=.12, ge=0, le=1, allow_inf_nan=False)


class SceneRequest(Range):
    sensitivity: float = Field(default=.35, ge=.05, le=.9, allow_inf_nan=False)


@router.post('/analyze/silence')
def analyze_silence(payload: SilenceRequest):
    from .converter import probe_media
    job = _source(payload.source_job_id)
    info = probe_media(job.filename)
    if not info['audio_codec']:
        raise HTTPException(422, 'This clip has no sound to analyse.')
    end = min(payload.end, info['duration'])
    if end - payload.start < .2:
        raise HTTPException(422, 'Select a longer clip.')
    try:
        quiet = analysis.silences(job.filename, payload.threshold, payload.minimum, info['duration'])
    except RuntimeError as exc:
        raise HTTPException(422, str(exc)) from exc
    inside = [[max(a, payload.start), min(b, end)] for a, b in quiet if b > payload.start and a < end]
    keep = analysis.keep_ranges(quiet, payload.start, end, payload.padding)
    return {'silences': inside, 'keep': keep, 'removed': round((end - payload.start) - sum(b - a for a, b in keep), 3)}


@router.post('/analyze/scenes')
def analyze_scenes(payload: SceneRequest):
    from .converter import probe_media
    job = _source(payload.source_job_id)
    if not probe_media(job.filename)['video_codec']:
        raise HTTPException(422, 'This clip has no picture to analyse.')
    try:
        cuts = analysis.scenes(job.filename, payload.sensitivity)
    except RuntimeError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {'cuts': [moment for moment in cuts if payload.start + .2 < moment < payload.end - .2]}


@router.post('/analyze/beats')
def analyze_beats(payload: Range):
    from .converter import probe_media
    job = _source(payload.source_job_id)
    if not probe_media(job.filename)['audio_codec']:
        raise HTTPException(422, 'This file has no sound to find beats in.')
    try:
        return analysis.beats(job.filename, payload.start, payload.end)
    except RuntimeError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post('/analyze/loudness')
def analyze_loudness(payload: Range):
    job = _source(payload.source_job_id)
    try:
        return analysis.loudness(job.filename, payload.start, payload.end)
    except (RuntimeError, ValueError, KeyError) as exc:
        raise HTTPException(422, 'Loudness could not be measured for this clip.') from exc


# ---------------------------------------------------------------- transcripts
def _transcript_key(job) -> str:
    return hashlib.sha1(str(Path(job.filename).resolve()).lower().encode()).hexdigest()[:32]


def _transcript_view(job, record: dict | None) -> dict:
    remote = job.url.startswith(('http://', 'https://'))
    if not record:
        return {'segments': [], 'source': None, 'language': '', 'can_fetch': remote}
    return {**record, 'can_fetch': remote}


def _save_transcript(job, segments: list[dict], language: str, source: str) -> dict:
    if not segments:
        raise HTTPException(422, 'No timed lines were found.')
    return transcripts.save('media', _transcript_key(job), segments[:20000], language=language, source=source,
                            title=job.title or Path(job.filename).stem, extra={'job_id': job.id, 'path': job.filename})


@router.get('/transcript/{identity}')
def get_transcript(identity: str):
    job = _source(identity)
    record = transcripts.load('media', _transcript_key(job))
    if not record:
        found = transcripts.from_sidecar(Path(job.filename))
        if found:
            record = _save_transcript(job, found[0], found[1], 'file')
    return _transcript_view(job, record)


@router.post('/transcript/{identity}/fetch')
def fetch_transcript(identity: str):
    job = _source(identity)
    if not job.url.startswith(('http://', 'https://')):
        raise HTTPException(422, 'This file did not come from a link, so there are no online captions. Import an .srt or .vtt file instead.')
    try:
        found = transcripts.fetch_captions(job.url)
    except Exception as exc:  # yt-dlp raises many types; the message is what the user needs
        raise HTTPException(422, 'Captions could not be fetched: ' + str(exc)[-300:]) from exc
    if not found:
        raise HTTPException(404, 'This video has no captions or automatic captions.')
    segments, language, kind = found
    return _transcript_view(job, _save_transcript(job, segments, language, kind))


class TranscriptText(BaseModel):
    text: str = Field(max_length=4_000_000)

    @field_validator('text')
    @classmethod
    def not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('The subtitle file is empty.')
        return value


@router.post('/transcript/{identity}/import')
def import_transcript(identity: str, payload: TranscriptText):
    job = _source(identity)
    return _transcript_view(job, _save_transcript(job, transcripts.parse(payload.text), '', 'import'))


@router.post('/transcript/{identity}/remove')
def remove_transcript(identity: str):
    job = _source(identity)
    transcripts.remove('media', _transcript_key(job))
    return _transcript_view(job, None)


@router.get('/transcript/{identity}/export')
def export_transcript(identity: str, format: str = 'srt'):
    job = _source(identity)
    record = transcripts.load('media', _transcript_key(job))
    if not record:
        raise HTTPException(404, 'There is no transcript for this clip yet.')
    if format not in ('srt', 'txt'):
        raise HTTPException(400, 'Choose srt or txt.')
    body = transcripts.to_srt(record['segments']) if format == 'srt' else transcripts.to_text(record['segments'])
    name = re.sub(r'[^\w\- .]+', '', record.get('title') or 'transcript')[:80].strip() or 'transcript'
    return Response(body, media_type='text/plain; charset=utf-8',
                    headers={'Content-Disposition': f'attachment; filename="{name}.{format}"'})


@router.get('/transcripts/search')
def search_transcripts(q: str = ''):
    if len(q) > 200:
        raise HTTPException(422, 'Search for fewer words.')
    return {'results': transcripts.search(q)}
