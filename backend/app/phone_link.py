"""Phone Link: pair a phone on the same network and use it as a remote for DropDL.

The phone talks to a separate, minimal web server on its own port that runs only while
Phone Link is switched on. Downloads started from the phone run on this PC (with this PC's
YouTube sign-in, tools and folders) and can be saved back to the phone.

Safety rules, all enforced here:
  * off until the user switches it on;
  * requests are accepted only from private networks (home Wi-Fi, Tailscale), never the internet;
  * the Host header must be an address, which blocks DNS-rebinding pages;
  * a phone must pair with a one-time code shown on the PC (10 minutes, rate limited);
  * every request then carries a per-device token (an HttpOnly cookie); the PC stores only its hash,
    and any device can be removed from the PC.
The desktop interface manages all of this through the local API under /api/phone.
"""
from __future__ import annotations

import collections
import hashlib
import hmac
import ipaddress
import json
import logging
import mimetypes
import os
import secrets
import socket
import threading
import time
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from . import qr
from .settings import CONFIG_ROOT
from .version import VERSION

log = logging.getLogger('dropdl.phone')
router = APIRouter(prefix='/api/phone')
context = None                                   # the main module: enqueue, checked_url, jobs, ...

DEFAULT_PORT = int(os.getenv('DROPDL_PHONE_PORT', '17330'))
BIND_HOST = os.getenv('DROPDL_PHONE_HOST', '0.0.0.0')
STATIC = Path(__file__).resolve().parent / 'phone'
COOKIE = 'dropdl_phone'
CODE_ALPHABET = 'ABCDEFGHJKMNPQRSTVWXYZ23456789'  # no 0/O, 1/I/L or U: easy to read aloud and type
CODE_TTL = 600
MAX_DEVICES = 12
MAX_INBOX = 40
STATIC_FILES = {'index.html', 'app.js', 'style.css', 'manifest.webmanifest', 'sw.js', 'icon-192.png', 'icon-512.png',
                'logo.svg', 'inter.woff2', 'plex-arabic.woff2'}


def _now() -> float:
    return time.time()


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _state_file() -> Path:
    return CONFIG_ROOT / 'phone.json'


# ---------------------------------------------------------------- persistent state
class State:
    def __init__(self):
        self.lock = threading.RLock()
        self.data = {'enabled': False, 'port': DEFAULT_PORT, 'devices': [], 'inbox': [], 'firewall_hint_shown': False}
        try:
            saved = json.loads(_state_file().read_text(encoding='utf-8'))
            if isinstance(saved, dict):
                self.data['enabled'] = saved.get('enabled') is True
                port = saved.get('port')
                if type(port) is int and 1024 <= port <= 65535:
                    self.data['port'] = port
                self.data['devices'] = [d for d in saved.get('devices', []) if isinstance(d, dict) and isinstance(d.get('token'), str)][:MAX_DEVICES]
                self.data['inbox'] = [i for i in saved.get('inbox', []) if isinstance(i, dict)][:MAX_INBOX]
                self.data['firewall_hint_shown'] = saved.get('firewall_hint_shown') is True
        except (OSError, ValueError, TypeError):
            pass
        self._last_seen_save = 0.0

    def save(self):
        with self.lock:
            path = _state_file()
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix('.tmp')
            temporary.write_text(json.dumps(self.data, indent=2), encoding='utf-8')
            try:
                temporary.chmod(0o600)
            except OSError:
                pass
            temporary.replace(path)

    def device_for(self, token: str | None):
        if not token or len(token) > 200:
            return None
        digest = _hash(token)
        with self.lock:
            for device in self.data['devices']:
                if hmac.compare_digest(device['token'], digest):
                    return device
        return None

    def touch(self, device, ip):
        with self.lock:
            device['last_seen'] = _now()
            device['ip'] = ip
            if _now() - self._last_seen_save > 60:
                self._last_seen_save = _now()
                self.save()


state = State()


# ---------------------------------------------------------------- pairing codes and rate limits
class Pairing:
    def __init__(self):
        self.lock = threading.Lock()
        self.code = ''
        self.expires = 0.0
        self.attempts: dict[str, collections.deque] = {}
        self.global_attempts: collections.deque = collections.deque()

    def current(self, renew=False):
        with self.lock:
            if renew or not self.code or _now() >= self.expires:
                self.code = ''.join(secrets.choice(CODE_ALPHABET) for _ in range(8))
                self.expires = _now() + CODE_TTL
            return self.code, self.expires

    def allow_attempt(self, ip: str) -> bool:
        now = _now()
        with self.lock:
            per_ip = self.attempts.setdefault(ip, collections.deque())
            for queue, window in ((per_ip, 3600), (self.global_attempts, 3600)):
                while queue and now - queue[0] > window:
                    queue.popleft()
            recent = sum(1 for t in per_ip if now - t < 60)
            if recent >= 6 or len(per_ip) >= 20 or len(self.global_attempts) >= 60:
                return False
            per_ip.append(now)
            self.global_attempts.append(now)
            return True

    def check(self, candidate: str) -> bool:
        cleaned = ''.join(ch for ch in candidate.upper() if ch.isalnum())
        with self.lock:
            if not self.code or _now() >= self.expires or len(cleaned) != len(self.code):
                return False
            if hmac.compare_digest(cleaned, self.code):
                self.code = ''                       # one use only: a new code appears on the PC
                return True
            return False


pairing = Pairing()


# ---------------------------------------------------------------- network helpers
def _private(ip: str) -> bool:
    try:
        address = ipaddress.ip_address(ip.split('%')[0])
    except ValueError:
        return False
    if address.version == 6 and address.ipv4_mapped:
        address = address.ipv4_mapped
    if address.is_loopback or address.is_link_local:
        return True
    if address.version == 4 and address in ipaddress.ip_network('100.64.0.0/10'):   # Tailscale / carrier-grade NAT
        return True
    return address.is_private and not address.is_unspecified


VIRTUAL = ('vethernet', 'wsl', 'virtualbox', 'vmware', 'hyper-v', 'docker', 'loopback', 'bluetooth', 'npcap', 'isatap', 'teredo', 'pseudo')
VPN = ('wt0', 'wg', 'wireguard', 'zerotier', 'netbird', 'openvpn', 'proton', 'nordlynx', 'tun', 'tap', 'vpn', 'hamachi')
_adapter_cache: tuple[float, list[dict]] = (0.0, [])


def _windows_adapters() -> list[dict]:
    """IPv4 addresses with adapter name, type and gateway, from Windows' GetAdaptersAddresses (cached for a minute)."""
    global _adapter_cache
    if time.time() - _adapter_cache[0] < 60:
        return _adapter_cache[1]
    import ctypes
    from ctypes import wintypes

    class SocketAddress(ctypes.Structure):
        _fields_ = [('lpSockaddr', ctypes.c_void_p), ('iSockaddrLength', ctypes.c_int)]

    class Unicast(ctypes.Structure):
        pass
    Unicast._fields_ = [('Length', wintypes.ULONG), ('Flags', wintypes.DWORD), ('Next', ctypes.POINTER(Unicast)), ('Address', SocketAddress)]

    class Adapter(ctypes.Structure):
        pass
    Adapter._fields_ = [('Length', wintypes.ULONG), ('IfIndex', wintypes.DWORD), ('Next', ctypes.POINTER(Adapter)),
                        ('AdapterName', ctypes.c_char_p), ('FirstUnicastAddress', ctypes.POINTER(Unicast)),
                        ('FirstAnycastAddress', ctypes.c_void_p), ('FirstMulticastAddress', ctypes.c_void_p),
                        ('FirstDnsServerAddress', ctypes.c_void_p), ('DnsSuffix', ctypes.c_wchar_p), ('Description', ctypes.c_wchar_p),
                        ('FriendlyName', ctypes.c_wchar_p), ('PhysicalAddress', ctypes.c_ubyte * 8), ('PhysicalAddressLength', wintypes.ULONG),
                        ('Flags', wintypes.ULONG), ('Mtu', wintypes.ULONG), ('IfType', wintypes.ULONG), ('OperStatus', ctypes.c_int),
                        ('Ipv6IfIndex', wintypes.DWORD), ('ZoneIndices', wintypes.ULONG * 16), ('FirstPrefix', ctypes.c_void_p),
                        ('TransmitLinkSpeed', ctypes.c_uint64), ('ReceiveLinkSpeed', ctypes.c_uint64),
                        ('FirstWinsServerAddress', ctypes.c_void_p), ('FirstGatewayAddress', ctypes.c_void_p)]
    result = []
    try:
        api = ctypes.windll.iphlpapi.GetAdaptersAddresses
        api.argtypes = [wintypes.ULONG, wintypes.ULONG, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(wintypes.ULONG)]
        api.restype = wintypes.ULONG
        flags = 0x80 | 0x2 | 0x4 | 0x8                        # include gateways; skip anycast, multicast, DNS
        size = wintypes.ULONG(16384)
        for _ in range(4):
            buffer = ctypes.create_string_buffer(size.value)
            code = api(2, flags, None, buffer, ctypes.byref(size))  # AF_INET
            if code != 111:                                   # ERROR_BUFFER_OVERFLOW: try again with the size Windows asked for
                break
        if code == 0:
            node = ctypes.cast(buffer, ctypes.POINTER(Adapter))
            while node:
                adapter = node.contents
                if adapter.OperStatus == 1:                   # up
                    unicast = adapter.FirstUnicastAddress
                    while unicast:
                        address = unicast.contents.Address
                        if address.lpSockaddr and address.iSockaddrLength >= 8:
                            raw = ctypes.string_at(address.lpSockaddr + 4, 4)
                            result.append({'ip': socket.inet_ntoa(raw), 'alias': adapter.FriendlyName or '', 'gw': bool(adapter.FirstGatewayAddress),
                                           'wireless': adapter.IfType == 71})
                        unicast = unicast.contents.Next
                node = adapter.Next
    except (OSError, AttributeError, ValueError):
        log.exception('Could not list network adapters')
        result = []
    _adapter_cache = (time.time(), result)
    return result


def lan_addresses() -> list[dict]:
    """IPv4 addresses a phone can use, most likely first: the Wi-Fi/Ethernet adapter that has the default gateway."""
    rows = _windows_adapters() if os.name == 'nt' else []
    if not rows:
        found = []
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.connect(('192.0.2.1', 9))           # no packet is sent; this only picks the default route
                found.append(probe.getsockname()[0])
        except OSError:
            pass
        try:
            found += [info[4][0] for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)]
        except OSError:
            pass
        rows = [{'ip': ip, 'alias': '', 'gw': i == 0} for i, ip in enumerate(found)]
    result, seen = [], set()
    for row in rows:
        ip, alias, name = row['ip'], row['alias'], row['alias'].lower()
        if ip in seen or ip.startswith(('127.', '169.254.')) or not _private(ip) or any(v in name for v in VIRTUAL):
            continue
        seen.add(ip)
        tailscale = 'tailscale' in name or ipaddress.ip_address(ip) in ipaddress.ip_network('100.64.0.0/10')
        vpn = not tailscale and any(name == v or name.startswith(v) or v in name.split() for v in VPN)
        wireless = row.get('wireless') or any(w in name for w in ('wi-fi', 'wifi', 'wlan', 'wireless'))
        kind = 'tailscale' if tailscale else 'vpn' if vpn else 'lan'
        rank = 4 if tailscale else 3 if vpn else (0 if row['gw'] and wireless else 1 if row['gw'] else 2)
        result.append({'ip': ip, 'kind': kind, 'label': alias, 'rank': rank})
    result.sort(key=lambda a: a['rank'])
    return result


def _host_allowed(host_header: str | None) -> bool:
    if not host_header:
        return False
    host = host_header.strip().lower()
    if host.startswith('['):
        host = host[1:host.find(']')] if ']' in host else host
    elif host.count(':') == 1:
        host = host.rsplit(':', 1)[0]
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    name = socket.gethostname().lower()
    return host in {'localhost', name, f'{name}.local'} or host.endswith('.ts.net')


# ---------------------------------------------------------------- the phone server
class Server:
    def __init__(self):
        self.lock = threading.Lock()
        self.server = None
        self.thread = None
        self.port = None
        self.error = ''

    @property
    def running(self) -> bool:
        return bool(self.thread and self.thread.is_alive() and self.server and self.server.started)

    def start(self, port: int) -> bool:
        with self.lock:
            self._stop_locked()
            import uvicorn
            try:
                with socket.socket() as probe:
                    probe.bind((BIND_HOST, port))
            except OSError:
                self.error = f'Port {port} is already in use on this PC.'
                log.warning('Phone Link port %s unavailable', port)
                return False
            config = uvicorn.Config(phone_app, host=BIND_HOST, port=port, log_level='warning', log_config=None, access_log=False,
                                    lifespan='off', proxy_headers=False, server_header=False, timeout_keep_alive=5, limit_concurrency=64)
            self.server = uvicorn.Server(config)
            self.thread = threading.Thread(target=self.server.run, name='phone-link', daemon=True)
            self.thread.start()
            deadline = time.time() + 6
            while time.time() < deadline and self.thread.is_alive() and not self.server.started:
                time.sleep(.05)
            if not self.server.started:
                self.error = 'Phone Link could not start on this PC.'
                self._stop_locked()
                return False
            self.port, self.error = port, ''
            log.info('Phone Link listening on %s:%s', BIND_HOST, port)
            return True

    def _stop_locked(self):
        if self.server:
            self.server.should_exit = True
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(5)
        self.server = self.thread = None
        self.port = None

    def stop(self):
        with self.lock:
            self._stop_locked()


server = Server()


def start_if_enabled():
    if state.data['enabled']:
        server.start(state.data['port'])


def shutdown():
    server.stop()


# ---------------------------------------------------------------- shared views
def _signed_in_to_youtube() -> bool:
    try:
        from .youtube_account import status
        return bool(status().get('signed_in'))
    except Exception:                                  # noqa: BLE001 - informational only
        return False


def _job_view(job, device_id: str | None = None) -> dict:
    public = job.public()
    size = public.get('total_bytes')
    if job.status == 'completed' and job.filename:
        try:
            size = Path(job.filename).stat().st_size
        except OSError:
            size = None
    return {key: public.get(key) for key in ('id', 'title', 'url', 'site', 'kind', 'container', 'quality', 'status', 'phase', 'percent',
                                             'downloaded_bytes', 'total_bytes', 'speed', 'eta', 'filename', 'error', 'error_code',
                                             'created_at', 'updated_at', 'thumbnail')} | {
        'size': size, 'mine': bool(device_id) and job.origin == f'phone:{device_id}', 'from_phone': job.origin.startswith('phone:')}


def _media_view(record: dict) -> dict:
    return {'id': record['id'], 'title': record.get('title') or record.get('filename'), 'kind': record.get('kind'),
            'size': record.get('size'), 'filename': record.get('filename'), 'site': record.get('site'),
            'added': record.get('created_at') or record.get('added_at')}


def _inbox_view() -> list[dict]:
    with state.lock:
        return [dict(item) for item in state.data['inbox']]


# ---------------------------------------------------------------- local API (desktop interface only)
def _local_only(request: Request):
    host = (request.headers.get('host') or '').lower()
    name = host[1:host.find(']')] if host.startswith('[') else host.rsplit(':', 1)[0]
    if name not in {'127.0.0.1', 'localhost', '::1'}:
        raise HTTPException(403, 'This request must come from DropDL on this PC.')


def status_payload(address: str | None = None) -> dict:
    port = state.data['port']
    addresses = lan_addresses()
    ips = [a['ip'] for a in addresses]
    primary = address if address in ips else (ips[0] if ips else None)
    code, expires = pairing.current()
    pair_url = f'http://{primary}:{port}/#pair={code}' if primary else None
    with state.lock:
        devices = [{'id': d['id'], 'name': d.get('name') or 'Phone', 'created': d.get('created'), 'last_seen': d.get('last_seen'),
                    'online': bool(d.get('last_seen')) and _now() - d['last_seen'] < 120} for d in state.data['devices']]
    return {
        'enabled': state.data['enabled'], 'running': server.running, 'error': server.error, 'port': port,
        'addresses': [{'kind': a['kind'], 'label': a['label'], 'ip': a['ip'], 'url': f"http://{a['ip']}:{port}"} for a in addresses],
        'chosen': primary,
        'pairing': {'code': f'{code[:4]}-{code[4:]}', 'url': pair_url, 'qr': qr.svg(pair_url) if pair_url else None,
                    'expires_in': max(0, int(expires - _now()))},
        'devices': devices, 'inbox': len(state.data['inbox']),
        'firewall_hint': state.data['enabled'] and not state.data['firewall_hint_shown'],
        'youtube': _signed_in_to_youtube(),
    }


class EnableRequest(BaseModel):
    enabled: bool


class SendRequest(BaseModel):
    job_id: str | None = Field(default=None, max_length=64)
    media_id: str | None = Field(default=None, max_length=64)


@router.get('/status')
def local_status(request: Request, address: str | None = None):
    _local_only(request)
    return status_payload(address)


@router.post('/enable')
def local_enable(payload: EnableRequest, request: Request):
    _local_only(request)
    with state.lock:
        state.data['enabled'] = payload.enabled
        state.save()
    if payload.enabled:
        server.start(state.data['port'])
    else:
        server.stop()
        server.error = ''
    return status_payload()


@router.post('/firewall-hint/dismiss')
def local_dismiss_hint(request: Request):
    _local_only(request)
    with state.lock:
        state.data['firewall_hint_shown'] = True
        state.save()
    return status_payload()


@router.post('/pairing/renew')
def local_renew(request: Request):
    _local_only(request)
    pairing.current(renew=True)
    return status_payload()


@router.post('/devices/{identity}/remove')
def local_remove_device(identity: str, request: Request):
    _local_only(request)
    with state.lock:
        state.data['devices'] = [d for d in state.data['devices'] if d['id'] != identity]
        state.save()
    return status_payload()


@router.post('/send')
def local_send(payload: SendRequest, request: Request):
    _local_only(request)
    if bool(payload.job_id) == bool(payload.media_id):
        raise HTTPException(400, 'Choose one download or one library item.')
    if payload.job_id:
        job = context.jobs.get(payload.job_id)
        if not job or job.status != 'completed' or not job.filename or not Path(job.filename).is_file():
            raise HTTPException(409, 'Only finished downloads whose file still exists can be sent.')
        item = {'kind': 'job', 'ref': job.id, 'title': job.title or Path(job.filename).name, 'size': Path(job.filename).stat().st_size}
    else:
        from .media_library import library
        record = library.get(payload.media_id)
        if not record or not record['exists']:
            raise HTTPException(404, 'That file is no longer in the library.')
        item = {'kind': 'media', 'ref': record['id'], 'title': record.get('title') or record['filename'], 'size': record['size']}
    with state.lock:
        inbox = [i for i in state.data['inbox'] if not (i['kind'] == item['kind'] and i['ref'] == item['ref'])]
        inbox.insert(0, dict(item, id=secrets.token_hex(8), added=_now()))
        state.data['inbox'] = inbox[:MAX_INBOX]
        state.save()
    return {'sent': True, 'inbox': len(state.data['inbox']), 'devices': len(state.data['devices'])}


# ---------------------------------------------------------------- the phone web app and its API
phone_app = FastAPI(title='DropDL Phone Link', docs_url=None, redoc_url=None, openapi_url=None)

CSP = ("default-src 'self'; img-src 'self' https: data: blob:; media-src 'self' blob:; style-src 'self'; script-src 'self'; "
       "font-src 'self'; connect-src 'self'; manifest-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")


@phone_app.middleware('http')
async def guard(request: Request, call_next):
    ip = request.client.host if request.client else ''
    if os.getenv('DROPDL_PHONE_TEST_CLIENT') and ip == 'testclient':
        ip = os.getenv('DROPDL_PHONE_TEST_CLIENT')
    if not _private(ip):
        return JSONResponse({'detail': 'Phone Link only answers devices on your own network.'}, status_code=403)
    if not _host_allowed(request.headers.get('host')):
        return JSONResponse({'detail': 'Open DropDL with the address shown on your PC.'}, status_code=400)
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        origin = request.headers.get('origin')
        if origin and origin.split('://', 1)[-1].rstrip('/').lower() != (request.headers.get('host') or '').lower():
            return JSONResponse({'detail': 'Cross-site request refused.'}, status_code=403)
        try:
            if int(request.headers.get('content-length') or 0) > 64 * 1024:
                return JSONResponse({'detail': 'Request too large.'}, status_code=413)
        except ValueError:
            return JSONResponse({'detail': 'Bad request.'}, status_code=400)
    request.state.ip = ip
    response = await call_next(request)
    response.headers['Content-Security-Policy'] = CSP
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    if request.url.path.startswith('/api/') or request.url.path in ('/', '/share', '/index.html', '/sw.js'):
        response.headers['Cache-Control'] = 'no-store'
    return response


def _device(request: Request) -> dict:
    device = state.device_for(request.cookies.get(COOKIE))
    if not device:
        raise HTTPException(401, 'This phone is not paired with DropDL. Scan the code on your PC.')
    state.touch(device, getattr(request.state, 'ip', ''))
    return device


def _call(fn, *args):
    """Run one of the main API handlers and pass its HTTP errors through."""
    return fn(*args)


class PairRequest(BaseModel):
    code: str = Field(min_length=4, max_length=20)
    name: str = Field(default='', max_length=60)


class LinkRequest(BaseModel):
    url: str = Field(min_length=8, max_length=4096)


class PhoneDownload(LinkRequest):
    kind: str = Field(default='video', pattern='^(video|audio)$')
    quality: str = Field(default='best', pattern='^(best|[0-9]{3,4}p)$')
    container: str = Field(default='mp4', pattern='^(mp4|webm|mkv|mp3|m4a|opus|flac|wav)$')
    title: str = Field(default='', max_length=300)              # from the preview, so the card has a name at once
    thumbnail: str = Field(default='', max_length=2000)


def _device_name(given: str, agent: str) -> str:
    name = ' '.join(given.split())[:60]
    if name:
        return name
    agent = agent or ''
    for marker, label in (('iPhone', 'iPhone'), ('iPad', 'iPad'), ('Android', 'Android phone'), ('Mac OS', 'Mac'), ('Windows', 'Windows PC')):
        if marker in agent:
            return label
    return 'Phone'


@phone_app.post('/api/pair')
def phone_pair(payload: PairRequest, request: Request):
    ip = getattr(request.state, 'ip', '')
    if not pairing.allow_attempt(ip):
        raise HTTPException(429, 'Too many tries. Wait a minute, then use the code shown on your PC.')
    if not pairing.check(payload.code):
        time.sleep(.4)
        raise HTTPException(403, 'That code is not right, or it has expired. Check the code on your PC.')
    token = secrets.token_urlsafe(32)
    device = {'id': secrets.token_hex(8), 'name': _device_name(payload.name, request.headers.get('user-agent', '')), 'token': _hash(token),
              'created': _now(), 'last_seen': _now(), 'ip': ip}
    with state.lock:
        state.data['devices'] = ([device] + state.data['devices'])[:MAX_DEVICES]
        state.save()
    response = JSONResponse({'paired': True, 'device': {'id': device['id'], 'name': device['name']}})
    response.set_cookie(COOKIE, token, max_age=400 * 86400, httponly=True, samesite='strict', path='/')
    return response


@phone_app.get('/api/session')
def phone_session(request: Request):
    device = state.device_for(request.cookies.get(COOKIE))
    base = {'pc': socket.gethostname(), 'version': VERSION}
    if not device:
        return base | {'paired': False}
    state.touch(device, getattr(request.state, 'ip', ''))
    return base | {'paired': True, 'device': {'id': device['id'], 'name': device.get('name')}, 'youtube': _signed_in_to_youtube()}


@phone_app.post('/api/unpair')
def phone_unpair(request: Request):
    device = _device(request)
    with state.lock:
        state.data['devices'] = [d for d in state.data['devices'] if d['id'] != device['id']]
        state.save()
    response = JSONResponse({'paired': False})
    response.delete_cookie(COOKIE, path='/')
    return response


@phone_app.post('/api/info')
def phone_info(payload: LinkRequest, request: Request):
    _device(request)
    return _call(context.info, context.UrlRequest(url=payload.url))


@phone_app.post('/api/download', status_code=202)
def phone_download(payload: PhoneDownload, request: Request):
    device = _device(request)
    url = context.checked_url(payload.url)
    audio = payload.kind == 'audio'
    if audio and payload.container not in context.AUDIO_FORMATS:
        raise HTTPException(400, 'Audio can be MP3, M4A, Opus, FLAC or WAV.')
    if not audio and payload.container not in {'mp4', 'webm', 'mkv'}:
        raise HTTPException(400, 'Video can be MP4, WebM or MKV.')
    extras = {'title': ' '.join(payload.title.split())[:300]} if payload.title.strip() else {}
    if payload.thumbnail.startswith('https://'):
        extras['thumbnail'] = payload.thumbnail
    public = context.enqueue(url, payload.kind, payload.container, payload.quality, origin=f"phone:{device['id']}", **extras)
    job = context.jobs.get(public['id'])
    return _job_view(job, device['id'])


@phone_app.get('/api/jobs')
def phone_jobs(request: Request):
    device = _device(request)
    revision, _ = context.jobs.snapshot()
    rows = [job for job in context.jobs.objects() if job.purpose == 'download'][:40]
    return {'revision': revision, 'jobs': [_job_view(job, device['id']) for job in rows], 'inbox': _inbox_view()}


def _completed_file(job_id: str) -> Path:
    job = context.jobs.get(job_id)
    if not job or job.purpose != 'download':
        raise HTTPException(404, 'Download not found.')
    if job.status != 'completed' or not job.filename:
        raise HTTPException(409, 'This download has not finished yet.')
    path = Path(job.filename)
    if not path.is_file():
        raise HTTPException(410, 'The file was moved or deleted on the PC.')
    return path


def _send_file(path: Path, inline: bool) -> FileResponse:
    return FileResponse(path, filename=path.name, media_type=mimetypes.guess_type(path.name)[0] or 'application/octet-stream',
                        content_disposition_type='inline' if inline else 'attachment')


@phone_app.get('/api/jobs/{job_id}/file')
def phone_job_file(job_id: str, request: Request, inline: bool = False):
    _device(request)
    return _send_file(_completed_file(job_id), inline)


@phone_app.post('/api/jobs/{job_id}/cancel')
def phone_cancel(job_id: str, request: Request):
    device = _device(request)
    context.cancel_job(job_id)
    return _job_view(context.jobs.get(job_id), device['id'])


@phone_app.post('/api/jobs/{job_id}/retry', status_code=202)
def phone_retry(job_id: str, request: Request):
    device = _device(request)
    public = context.retry_job(job_id)
    return _job_view(context.jobs.get(public['id']), device['id'])


@phone_app.get('/api/library')
def phone_library(request: Request, q: str = '', offset: int = 0, limit: int = 30):
    _device(request)
    from .media_library import library
    words = q.lower().split()
    rows = [r for r in library.list() if r.get('exists')]
    if words:
        rows = [r for r in rows if all(w in f"{r.get('title') or ''} {r.get('filename') or ''} {r.get('site') or ''}".lower() for w in words)]
    offset, limit = max(0, offset), max(1, min(60, limit))
    return {'total': len(rows), 'items': [_media_view(r) for r in rows[offset:offset + limit]]}


def _media(identity: str) -> dict:
    from .media_library import library
    record = library.get(identity)
    if not record or not record['exists']:
        raise HTTPException(404, 'That file is no longer on the PC.')
    return record


@phone_app.get('/api/library/{identity}/file')
def phone_media_file(identity: str, request: Request, inline: bool = False):
    _device(request)
    return _send_file(Path(_media(identity)['path']), inline)


@phone_app.get('/api/library/{identity}/thumbnail')
def phone_media_thumbnail(identity: str, request: Request):
    _device(request)
    _media(identity)
    from .workspace import thumbnail
    return thumbnail(identity)


@phone_app.get('/api/inbox/{identity}/file')
def phone_inbox_file(identity: str, request: Request, inline: bool = False):
    _device(request)
    with state.lock:
        item = next((i for i in state.data['inbox'] if i['id'] == identity), None)
    if not item:
        raise HTTPException(404, 'That item was removed.')
    path = _completed_file(item['ref']) if item['kind'] == 'job' else Path(_media(item['ref'])['path'])
    return _send_file(path, inline)


@phone_app.post('/api/inbox/{identity}/done')
def phone_inbox_done(identity: str, request: Request):
    _device(request)
    with state.lock:
        state.data['inbox'] = [i for i in state.data['inbox'] if i['id'] != identity]
        state.save()
    return {'inbox': _inbox_view()}


def _static(name: str) -> Response:
    path = STATIC / name
    if name not in STATIC_FILES or not path.is_file():
        raise HTTPException(404, 'Not found.')
    media = {'.webmanifest': 'application/manifest+json', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
             '.woff2': 'font/woff2', '.svg': 'image/svg+xml'}.get(path.suffix) or mimetypes.guess_type(name)[0] or 'application/octet-stream'
    response = FileResponse(path, media_type=media)
    if path.suffix in {'.woff2', '.png', '.svg'}:
        response.headers['Cache-Control'] = 'public, max-age=604800'
    return response


@phone_app.get('/')
@phone_app.get('/share')
def phone_index():
    return _static('index.html')


@phone_app.get('/{name}')
def phone_static(name: str):
    return _static(name)
