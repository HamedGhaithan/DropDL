"""Safe output organization using fixed rules, never arbitrary path templates."""
import re
from pathlib import Path
from time import localtime, strftime

FOLDER_RULES = {'none', 'creator', 'playlist', 'date', 'media_type'}
NAME_RULES = {'original', 'title', 'date_title'}

def component(value, fallback='Unknown'):
    text = re.sub(r'[\x00-\x1f<>:"/\\|?*]', '_', str(value or '')).strip(' .')[:100].rstrip(' .')
    if not text or text in {'.', '..'}: text = fallback
    if re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?', text): text = '_' + text
    return text

def output_location(job, metadata, result):
    rules = job.organization or {}
    destination = Path(job.destination)
    date = strftime('%Y-%m-%d', localtime(job.created_at))
    folder = rules.get('folder_rule', 'none')
    label = {
        'creator': metadata.get('uploader') or metadata.get('channel') or 'Unknown creator',
        'playlist': job.collection or metadata.get('playlist_title') or 'Unsorted',
        'date': date,
        'media_type': 'Audio' if job.kind == 'audio' else 'Video',
    }.get(folder)
    if label is not None: destination /= component(label)
    name_rule = rules.get('name_rule', 'original')
    stem = result.stem[:160]
    if name_rule in {'title', 'date_title'}:
        stem = component(job.title or metadata.get('title') or result.stem, 'Media')
        if name_rule == 'date_title': stem = date + ' ' + stem
    return destination, stem
