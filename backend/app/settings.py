from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from threading import Lock
from urllib.parse import urlparse

_DEFAULT_CONFIG = Path.home() / 'Library' / 'Application Support' / 'DropDL' if sys.platform == 'darwin' else Path(os.getenv('LOCALAPPDATA', str(Path.home()))) / 'DropDL'
CONFIG_ROOT = Path(os.getenv('DROPDL_DATA_ROOT', str(_DEFAULT_CONFIG)))


def site_folder(url: str) -> str:
    host = (urlparse(url).hostname or 'Other').lower().removeprefix('www.')
    known = {'youtu.be': 'YouTube', 'youtube.com': 'YouTube', 'dai.ly': 'Dailymotion', 'dailymotion.com': 'Dailymotion', 'vimeo.com': 'Vimeo', 'tiktok.com': 'TikTok', 'instagram.com': 'Instagram', 'facebook.com': 'Facebook', 'fb.watch': 'Facebook', 'twitter.com': 'X', 'x.com': 'X'}
    for domain, label in known.items():
        if host == domain or host.endswith('.' + domain):
            return label
    return re.sub(r'[^a-zA-Z0-9._-]', '_', host)[:100].strip('.') or 'Other'


BROWSERS = ('', 'firefox', 'chrome', 'edge', 'brave', 'opera', 'vivaldi', 'chromium')
PROXY_PATTERN = re.compile(r'^(https?|socks4a?|socks5h?)://([^\s/?#@]+@)?[^\s/?#@]+(:\d{1,5})?/?$', re.IGNORECASE)

# 2.0 reliability and network preferences. Workers receive a snapshot when a
# task starts, so changes apply to tasks started afterwards.
NETWORK_DEFAULTS = {
    'max_concurrent_downloads': 2,
    'max_auto_retries': 4,
    'stall_timeout': 90,
    'concurrent_fragments': 4,
    'proxy': '',
    'force_ipv4': False,
    'impersonate': 'auto',
    'cookies_browser': '',
}


def valid_network_value(key, value):
    if key == 'force_ipv4':
        return isinstance(value, bool)
    if key == 'max_concurrent_downloads':
        return type(value) is int and 1 <= value <= 8
    if key == 'max_auto_retries':
        return type(value) is int and 0 <= value <= 10
    if key == 'stall_timeout':
        return type(value) is int and (value == 0 or 30 <= value <= 900)
    if key == 'concurrent_fragments':
        return type(value) is int and 1 <= value <= 16
    if key == 'proxy':
        return isinstance(value, str) and len(value) <= 300 and (value == '' or bool(PROXY_PATTERN.match(value.strip())))
    if key == 'impersonate':
        return value in {'auto', 'always'}
    if key == 'cookies_browser':
        return value in BROWSERS
    return False


def network_snapshot(values):
    return {key: values.get(key, default) for key, default in NETWORK_DEFAULTS.items()}


class Settings:
    def __init__(self, path: Path, default_directory: Path):
        self.path = path
        self.lock = Lock()
        self.values = {'download_directory': str(default_directory.resolve()), 'group_by_site': True, 'speed_limit_kbps': 0, 'global_speed_limit_kbps':0, 'auto_recover':True, 'keep_in_tray':False, 'auto_cleanup':True, 'skip_duplicates':False, 'duplicate_naming_version':1, 'folder_rule':'none', 'name_rule':'original'}
        self.values['export_directory'] = str((default_directory / 'Exports').resolve())
        self.values.update(NETWORK_DEFAULTS)
        try:
            self.values['max_concurrent_downloads'] = max(1, min(8, int(os.getenv('MAX_CONCURRENT_DOWNLOADS', '2') or 2)))
        except ValueError:
            pass
        try:
            saved = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(saved, dict): saved = {}
            from .organization import FOLDER_RULES, NAME_RULES
            for key, allowed in (('folder_rule', FOLDER_RULES), ('name_rule', NAME_RULES)):
                if saved.get(key) in allowed: self.values[key] = saved[key]
            if isinstance(saved.get('download_directory'), str) and Path(saved['download_directory']).is_absolute():
                self.values['download_directory'] = saved['download_directory']
                self.values['export_directory'] = str(Path(saved['download_directory']) / 'Exports')
            if isinstance(saved.get('export_directory'), str) and Path(saved['export_directory']).is_absolute():
                self.values['export_directory'] = saved['export_directory']
            if isinstance(saved.get('group_by_site'), bool): self.values['group_by_site'] = saved['group_by_site']
            if type(saved.get('speed_limit_kbps')) is int and 0 <= saved['speed_limit_kbps'] <= 1000000:
                self.values['speed_limit_kbps'] = saved['speed_limit_kbps']
            for key in ("auto_recover","skip_duplicates","auto_cleanup","keep_in_tray"):
                if isinstance(saved.get(key),bool) and (key!="skip_duplicates" or saved.get("duplicate_naming_version")==1):self.values[key]=saved[key]
            if type(saved.get("global_speed_limit_kbps")) is int and 0<=saved["global_speed_limit_kbps"]<=1000000:self.values["global_speed_limit_kbps"]=saved["global_speed_limit_kbps"]
            for key, value in saved.items():
                if key in NETWORK_DEFAULTS and valid_network_value(key, value):
                    self.values[key] = value
        except (OSError, ValueError, TypeError):
            pass

    def get(self):
        with self.lock:
            return dict(self.values)

    def change(self, **changes):
        with self.lock:
            values = dict(self.values, **changes)
            directory = Path(values['export_directory'] if 'export_directory' in changes else values['download_directory'])
            directory.mkdir(parents=True, exist_ok=True)
            # Test permission before saving or queueing anything to this location.
            from tempfile import TemporaryFile
            with TemporaryFile(dir=directory): pass
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix('.tmp')
            temporary.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding='utf-8')
            temporary.replace(self.path)
            self.values = values
            return dict(values)
