"""3.0 desktop features that live in the window process: YouTube sign-in, the copied-link catcher, notifications.

This module runs in the GUI process (pywebview: WinForms on Windows, Cocoa on macOS) and never imports yt-dlp or
FastAPI. The macOS versions live in mac_native; anything without a counterpart degrades to a no-op.
"""
from __future__ import annotations

import ctypes
import email.utils
import json
import logging
import os
import re
import sys
import threading
import time
from urllib.parse import urlparse

log = logging.getLogger('dropdl.connect')


def run_js(window, script: str, what: str = 'update the interface') -> None:
    """Run a script in the page without blocking the caller.

    pywebview's evaluate_js marshals the script onto the window's UI thread and then waits for the result there.
    Called from a UI-thread event (a notification click, a window event) that wait can never finish and the whole
    window stops responding, so the call always happens on a short-lived worker thread."""
    def go():
        try:
            window.evaluate_js(script)
        except Exception:                              # noqa: BLE001 - the window may be closing
            log.exception('Could not %s', what)
    threading.Thread(target=go, daemon=True, name='run-js').start()
YOUTUBE_URI = 'https://www.youtube.com/'
GOOGLE_URIS = ('https://accounts.google.com/', 'https://www.google.com/')
AUTH_NAMES = {'LOGIN_INFO', 'SAPISID', '__Secure-1PAPISID', '__Secure-3PAPISID', '__Secure-1PSID', '__Secure-3PSID', 'SID'}
SIGN_IN_URL = ('https://accounts.google.com/ServiceLogin?service=youtube&uilel=3&passive=true'
               '&continue=https%3A%2F%2Fwww.youtube.com%2Fsignin%3Faction_handle_signin%3Dtrue%26app%3Ddesktop%26next%3Dhttps%253A%252F%252Fwww.youtube.com%252F')
# Links worth a notification while DropDL is in the background (inside the app any link is offered).
MEDIA_HOSTS = ('youtube.com', 'youtu.be', 'vimeo.com', 'soundcloud.com', 'tiktok.com', 'instagram.com', 'twitter.com', 'x.com',
               'facebook.com', 'fb.watch', 'twitch.tv', 'dailymotion.com', 'dai.ly', 'reddit.com', 'archive.org', 'bandcamp.com',
               'bilibili.com', 'rumble.com', 'odysee.com', 'mixcloud.com', 'streamable.com', 'kick.com', 'ted.com', 'nicovideo.jp')
URL_PATTERN = re.compile(r'^\s*(https?://[^\s<>"\']{4,2000})\s*$', re.IGNORECASE)


def media_link(text: str | None) -> str | None:
    """The link if the clipboard holds just one web address, else None."""
    if not text or len(text) > 2100:
        return None
    match = URL_PATTERN.match(text)
    if not match:
        return None
    url = match.group(1).rstrip('.,);')
    host = (urlparse(url).hostname or '').lower()
    if not host or host in {'localhost', '127.0.0.1'}:
        return None
    return url


def is_media_host(url: str) -> bool:
    host = (urlparse(url).hostname or '').lower()
    return any(host == h or host.endswith('.' + h) for h in MEDIA_HOSTS)


# ---------------------------------------------------------------- WebView2 cookie access
def _edge(window):
    from webview.platforms.winforms import BrowserView
    form = BrowserView.instances.get(window.uid)
    browser = getattr(form, 'browser', None) if form else None
    if not browser or not getattr(browser, 'webview', None):
        return None, None
    return form, browser


def read_cookies(window, uri: str, delete: bool = False, timeout: float = 10) -> list[dict] | None:
    """All cookies the shared browser profile would send to `uri` (optionally deleting them). Must not run on the UI thread."""
    if sys.platform == 'darwin':
        from .mac_native import read_cookies as read_webkit_cookies
        return read_webkit_cookies(window, uri, delete, timeout)
    if os.name != 'nt':
        return None
    form, browser = _edge(window)
    if not form:
        return None
    from System import Action, Func, Type
    from System.Collections.Generic import List
    from System.Globalization import CultureInfo
    from System.Threading.Tasks import Task
    from Microsoft.Web.WebView2.Core import CoreWebView2Cookie
    result: list[dict] = []
    done = threading.Event()

    def callback(task):
        try:
            manager = browser.webview.CoreWebView2.CookieManager
            for c in task.Result:
                try:
                    expires = 0.0
                    if not c.IsSession:
                        parsed = email.utils.parsedate_to_datetime(c.Expires.ToUniversalTime().ToString('r', CultureInfo.GetCultureInfo('en-US')))
                        expires = parsed.timestamp()
                    result.append({'domain': c.Domain, 'name': c.Name, 'value': c.Value, 'path': c.Path or '/',
                                   'secure': bool(c.IsSecure), 'httponly': bool(c.IsHttpOnly), 'expires': expires})
                    if delete:
                        manager.DeleteCookie(c)
                except Exception:                      # noqa: BLE001 - skip one odd cookie, keep the rest
                    log.exception('Could not read a cookie')
        finally:
            done.set()

    def start():
        browser.webview.CoreWebView2.CookieManager.GetCookiesAsync(uri).ContinueWith(
            Action[Task[List[CoreWebView2Cookie]]](callback), browser.syncContextTaskScheduler)

    try:
        form.Invoke(Func[Type](start))
    except Exception:                                  # noqa: BLE001
        log.exception('Cookie request failed')
        return None
    return result if done.wait(timeout) else None


def signed_in(cookies: list[dict] | None) -> bool:
    return bool(cookies) and any(c['name'] in AUTH_NAMES and c['domain'].lstrip('.').endswith('youtube.com') for c in cookies)


# ---------------------------------------------------------------- the YouTube sign-in window
class YouTubeAccount:
    def __init__(self, webview, main_window, backend):
        self.webview, self.main, self.backend = webview, main_window, backend
        self.window = None
        self.lock = threading.Lock()

    def _tell_interface(self, payload: dict):
        run_js(self.main, f"window.dispatchEvent(new CustomEvent('dropdl:youtube',{{detail:{json.dumps(payload)}}}))")

    def _upload(self, cookies: list[dict]) -> dict:
        youtube = [c for c in cookies if c['domain'].lstrip('.').endswith('youtube.com')]
        return self.backend.request('/api/native/youtube/cookies', {'cookies': youtube}, timeout=15)

    def sign_in(self, language: str = 'en') -> bool:
        with self.lock:
            if self.window is not None:
                try:
                    self.window.restore(); self.window.show()
                except Exception:                      # noqa: BLE001
                    pass
                return True
            title = 'تسجيل الدخول إلى يوتيوب — DropDL' if language == 'ar' else 'Sign in to YouTube — DropDL'
            self.window = self.webview.create_window(title, SIGN_IN_URL, width=520, height=760, min_size=(420, 560))
            self.window.events.closed += self._closed
        threading.Thread(target=self._watch, args=(self.window,), daemon=True, name='youtube-sign-in').start()
        return True

    def _closed(self):
        with self.lock:
            self.window = None

    def _watch(self, window):
        deadline = time.time() + 30 * 60
        while time.time() < deadline:
            time.sleep(1.5)
            with self.lock:
                if self.window is not window:
                    return                             # closed by the user
            cookies = read_cookies(window, YOUTUBE_URI)
            if signed_in(cookies):
                try:
                    status = self._upload(cookies)
                    self._tell_interface({'ok': True, 'status': status})
                except Exception as exc:               # noqa: BLE001
                    log.exception('Saving the YouTube sign-in failed')
                    self._tell_interface({'ok': False, 'error': str(exc)[:300]})
                time.sleep(1.2)
                try:
                    window.destroy()
                except Exception:                      # noqa: BLE001
                    pass
                return

    def refresh(self) -> dict:
        cookies = read_cookies(self.main, YOUTUBE_URI)
        if cookies is None:
            return {'refreshed': False, 'error': 'Not available on this system.'}
        if not signed_in(cookies):
            return {'refreshed': False, 'signed_in': False}
        status = self._upload(cookies)
        return {'refreshed': True, **status}

    def disconnect(self) -> dict:
        for uri in (YOUTUBE_URI,) + GOOGLE_URIS:
            read_cookies(self.main, uri, delete=True)
        return self.backend.request('/api/youtube/disconnect', {}, timeout=10)


# ---------------------------------------------------------------- Windows clipboard
class _Clipboard:
    def __init__(self):
        self.ok = os.name == 'nt'
        if not self.ok:
            return
        self.user32, self.kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        self.user32.GetClipboardSequenceNumber.restype = ctypes.c_uint32
        self.user32.GetClipboardData.restype = ctypes.c_void_p
        self.user32.GetClipboardData.argtypes = [ctypes.c_uint]
        self.user32.OpenClipboard.argtypes = [ctypes.c_void_p]
        self.kernel32.GlobalLock.restype = ctypes.c_void_p
        self.kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        self.kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        self.kernel32.GlobalSize.restype = ctypes.c_size_t
        self.kernel32.GlobalSize.argtypes = [ctypes.c_void_p]
        self.user32.GetForegroundWindow.restype = ctypes.c_void_p

    def sequence(self) -> int:
        return self.user32.GetClipboardSequenceNumber() if self.ok else 0

    def text(self) -> str | None:
        if not self.ok:
            return None
        for _ in range(3):                             # another app may hold the clipboard for a moment
            if self.user32.OpenClipboard(None):
                break
            time.sleep(.05)
        else:
            return None
        try:
            handle = self.user32.GetClipboardData(13)  # CF_UNICODETEXT
            if not handle or self.kernel32.GlobalSize(handle) > 16384:
                return None
            pointer = self.kernel32.GlobalLock(handle)
            if not pointer:
                return None
            try:
                return ctypes.wstring_at(pointer)
            finally:
                self.kernel32.GlobalUnlock(handle)
        finally:
            self.user32.CloseClipboard()

    def foreground(self) -> int:
        if not self.ok:
            return 0
        return self.user32.GetForegroundWindow() or 0


class LinkCatcher:
    """Offers a copied link: a banner inside DropDL when it is in front, a notification when it is not."""

    def __init__(self, main_window, notifier):
        self.main, self.notifier = main_window, notifier
        if sys.platform == 'darwin':
            from .mac_native import Pasteboard
            self.clipboard = Pasteboard()
        else:
            self.clipboard = _Clipboard()
        self.enabled = False
        self.language = 'en'
        self.thread = None
        self.stop = threading.Event()
        self.last_url = None

    def configure(self, enabled: bool, language: str = 'en') -> bool:
        if type(enabled) is not bool or language not in ('en', 'ar'):
            raise ValueError('Invalid clipboard preference.')
        self.language = language
        if enabled and not self.clipboard.ok:
            return False
        if enabled and not (self.thread and self.thread.is_alive()):
            self.stop.clear()
            self.thread = threading.Thread(target=self._run, daemon=True, name='link-catcher')
            self.thread.start()
        elif not enabled:
            self.stop.set()
        self.enabled = enabled
        return enabled

    def _front(self) -> bool:
        if sys.platform == 'darwin':
            return self.clipboard.app_is_front()
        try:
            native = self.main.native
            return bool(native.Visible) and self.clipboard.foreground() == int(native.Handle.ToInt64())
        except Exception:                              # noqa: BLE001
            return False

    def _run(self):
        seen = self.clipboard.sequence()               # never offer what was already copied before this started
        while not self.stop.wait(.7):
            current = self.clipboard.sequence()
            if current == seen:
                continue
            seen = current
            url = media_link(self.clipboard.text())
            if not url or url == self.last_url:
                continue
            self.last_url = url
            script = f"window.dropdlClipboard&&window.dropdlClipboard({json.dumps(url)})"
            if self._front():
                self._eval(script)
            elif is_media_host(url):
                host = (urlparse(url).hostname or '').removeprefix('www.')
                ar = self.language == 'ar'
                self.notifier.show('رابط منسوخ — تنزيل؟' if ar else 'Link copied — download it?',
                                   (f'{host}: انقر لتنزيله باستخدام DropDL.' if ar else f'{host} · Click to download it with DropDL.'), script)

    def _eval(self, script):
        run_js(self.main, script, 'reach the interface')


# ---------------------------------------------------------------- notifications
class Notifier:
    """Windows notifications through a notification-area icon (shown as toasts on Windows 10/11)."""

    def __init__(self, main_window, tray=None):
        self.main, self.tray = main_window, tray
        self.helper = None
        self.helper_icon = None
        self.pending = None
        self.mac = None

    def _mac_clicked(self, script):
        from .mac_native import bring_to_front
        bring_to_front(self.main)
        if script:
            run_js(self.main, script, 'run the notification action')

    def _ui(self, fn):
        from System import Action
        native = self.main.native
        if native.InvokeRequired:
            native.BeginInvoke(Action(fn))
        else:
            fn()

    def _clicked(self, *_):
        script, self.pending = self.pending, None
        try:
            if self.tray:
                self.tray.restore()
            else:
                from System.Windows.Forms import FormWindowState
                native = self.main.native
                native.Show()
                if native.WindowState == FormWindowState.Minimized:
                    native.WindowState = FormWindowState.Normal
                native.Activate()
        except Exception:                              # noqa: BLE001
            log.exception('Could not bring DropDL to the front')
        if script:                                     # this handler runs on the UI thread: never wait here
            run_js(self.main, script, 'run the notification action')

    def _hide_helper(self, *_):
        if self.helper is not None and not (self.tray and self.tray.icon is self.helper):
            self.helper.Visible = False

    def show(self, title: str, text: str, script: str | None = None) -> bool:
        if sys.platform == 'darwin':
            try:
                if self.mac is None:
                    from .mac_native import MacNotifier
                    self.mac = MacNotifier(self._mac_clicked)
                return self.mac.show(title, text, script)
            except Exception:                          # noqa: BLE001
                log.exception('Notification failed')
                return False
        if os.name != 'nt':
            return False
        self.pending = script

        def show_now():
            try:
                from System.Windows.Forms import NotifyIcon, ToolTipIcon
                icon = self.tray.icon if self.tray and self.tray.icon is not None and self.tray.icon.Visible else None
                if icon is None:
                    if self.helper is None:
                        from System.Drawing import Icon
                        from .desktop_host import desktop_icon
                        self.helper_icon = Icon(str(desktop_icon()))
                        self.helper = NotifyIcon()
                        self.helper.Icon = self.helper_icon
                        self.helper.Text = 'DropDL Studio'
                        self.helper.BalloonTipClicked += self._clicked
                        self.helper.BalloonTipClosed += self._hide_helper
                    self.helper.Visible = True
                    icon = self.helper
                elif not getattr(self, '_tray_hooked', False):
                    icon.BalloonTipClicked += self._clicked
                    self._tray_hooked = True
                icon.BalloonTipTitle = title[:63]
                icon.BalloonTipText = text[:255]
                icon.BalloonTipIcon = getattr(ToolTipIcon, 'None')   # 'None' is a Python keyword
                icon.ShowBalloonTip(6000)
            except Exception:                          # noqa: BLE001
                log.exception('Notification failed')

        try:
            self._ui(show_now)
            return True
        except Exception:                              # noqa: BLE001
            log.exception('Notification failed')
            return False

    def dispose(self):
        def clean():
            if self.helper is not None:
                self.helper.Visible = False
                self.helper.Dispose()
                self.helper = None
            if self.helper_icon is not None:
                self.helper_icon.Dispose()
                self.helper_icon = None
        try:
            self._ui(clean)
        except Exception:                              # noqa: BLE001
            pass
