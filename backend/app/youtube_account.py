"""Your YouTube sign-in, kept as the cookies.txt that downloads already use.

The desktop window captures the session from DropDL's own sign-in window (never from your
everyday browser) and sends it here through the native-token API. Only youtube.com cookies
are stored; cookies for other sites that you imported yourself are kept untouched.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from .settings import CONFIG_ROOT

router = APIRouter(prefix='/api')
context = None
AUTH_NAMES = {'LOGIN_INFO', 'SAPISID', '__Secure-1PAPISID', '__Secure-3PAPISID', '__Secure-1PSID', '__Secure-3PSID', 'SID'}
HEADER = '# Netscape HTTP Cookie File\n# Written by DropDL Studio from its own YouTube sign-in window.\n\n'


def cookie_file() -> Path:
    return CONFIG_ROOT / 'cookies.txt'


def _meta_file() -> Path:
    return CONFIG_ROOT / 'youtube.json'


def _is_youtube(domain: str) -> bool:
    domain = domain.lower().lstrip('.')
    return domain == 'youtube.com' or domain.endswith('.youtube.com')


def _parse(text: str):
    """Yield (domain, name, expires, line) for every cookie line in a Netscape file."""
    for line in text.splitlines():
        raw = line
        if line.startswith('#HttpOnly_'):
            line = line[len('#HttpOnly_'):]
        elif not line.strip() or line.startswith('#'):
            continue
        parts = line.split('\t')
        if len(parts) != 7:
            continue
        try:
            expires = int(float(parts[4] or 0))
        except ValueError:
            expires = 0
        yield parts[0], parts[5], expires, raw


def status() -> dict:
    path = cookie_file()
    try:
        meta = json.loads(_meta_file().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        meta = {}
    if not path.is_file():
        return {'configured': False, 'signed_in': False, 'youtube_cookies': 0, 'source': None, 'updated_at': None, 'expires_at': None}
    try:
        rows = list(_parse(path.read_text(encoding='utf-8', errors='replace')))
    except OSError:
        rows = []
    youtube = [r for r in rows if _is_youtube(r[0])]
    auth = [r for r in youtube if r[1] in AUTH_NAMES]
    expiries = [r[2] for r in auth if r[2] > 0]
    return {'configured': True, 'signed_in': bool(auth), 'youtube_cookies': len(youtube), 'other_cookies': len(rows) - len(youtube),
            'source': meta.get('source') or 'file', 'updated_at': meta.get('updated_at') or path.stat().st_mtime,
            'expires_at': min(expiries) if expiries else None}


def _write(lines_youtube: list[str], source: str | None):
    path = cookie_file()
    kept = []
    if path.is_file():
        kept = [raw for domain, _, _, raw in _parse(path.read_text(encoding='utf-8', errors='replace')) if not _is_youtube(domain)]
    lines = kept + lines_youtube
    CONFIG_ROOT.mkdir(parents=True, exist_ok=True)
    if not lines:
        path.unlink(missing_ok=True)
        _meta_file().unlink(missing_ok=True)
        return
    temporary = path.with_suffix('.tmp')
    temporary.write_text(HEADER + '\n'.join(lines) + '\n', encoding='utf-8')
    try:
        temporary.chmod(0o600)
    except OSError:
        pass
    temporary.replace(path)
    if source:
        _meta_file().write_text(json.dumps({'source': source, 'updated_at': time.time()}), encoding='utf-8')


class Cookie(BaseModel):
    domain: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=256)
    value: str = Field(max_length=8192)
    path: str = Field(default='/', max_length=1024)
    secure: bool = True
    httponly: bool = False
    expires: float = 0


class CookieUpload(BaseModel):
    cookies: list[Cookie] = Field(max_length=400)


def _line(cookie: Cookie) -> str | None:
    if not _is_youtube(cookie.domain):
        return None
    if any(ch in cookie.value + cookie.name + cookie.domain + cookie.path for ch in '\t\r\n'):
        return None
    domain = cookie.domain if cookie.domain.startswith('.') else cookie.domain
    flag = 'TRUE' if domain.startswith('.') else 'FALSE'
    expires = int(cookie.expires) if cookie.expires and cookie.expires > 0 else 0
    line = '\t'.join([domain, flag, cookie.path or '/', 'TRUE' if cookie.secure else 'FALSE', str(expires), cookie.name, cookie.value])
    return ('#HttpOnly_' + line) if cookie.httponly else line


@router.post('/native/youtube/cookies')
def native_youtube_cookies(payload: CookieUpload, x_dropdl_native_token: str | None = Header(default=None)):
    context.require_native_token(x_dropdl_native_token)
    lines = [line for line in (_line(c) for c in payload.cookies) if line]
    if not any(c.name in AUTH_NAMES and _is_youtube(c.domain) for c in payload.cookies):
        raise HTTPException(409, 'You are not signed in to YouTube in the sign-in window yet.')
    _write(lines, 'signin')
    return status()


def _local_only(request: Request):
    host = (request.headers.get('host') or '').lower()
    name = host[1:host.find(']')] if host.startswith('[') else host.rsplit(':', 1)[0]
    if name not in {'127.0.0.1', 'localhost', '::1'}:
        raise HTTPException(403, 'This request must come from DropDL on this PC.')


@router.get('/youtube/status')
def youtube_status(request: Request):
    _local_only(request)
    return status()


@router.post('/youtube/disconnect')
def youtube_disconnect(request: Request):
    _local_only(request)
    _write([], None)
    _meta_file().unlink(missing_ok=True)
    return status()
