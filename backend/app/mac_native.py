"""macOS versions of the 3.0 window-process features: WebKit cookies, the pasteboard and notifications.

Imported only on macOS (by connect_native). Everything here talks to Cocoa through PyObjC, which pywebview already
uses for its Cocoa backend, and degrades to a quiet no-op when a framework is unavailable.
"""
from __future__ import annotations

import logging
import subprocess
import sys
import threading
import uuid
from urllib.parse import urlparse

log = logging.getLogger('dropdl.connect.mac')


# ---------------------------------------------------------------- WebKit cookies (YouTube sign-in)
def _matches(host: str, domain: str) -> bool:
    domain = domain.lstrip('.').lower()
    return bool(domain) and (host == domain or host.endswith('.' + domain))


def read_cookies(window, uri: str, delete: bool = False, timeout: float = 10) -> list[dict] | None:
    """Cookies WebKit would send to `uri`, from the store every DropDL window shares. Must not run on the main thread."""
    try:
        from PyObjCTools import AppHelper
        from webview.platforms.cocoa import BrowserView
    except Exception:                                  # noqa: BLE001
        log.exception('Cocoa is unavailable')
        return None
    view = BrowserView.instances.get(window.uid)
    store_owner = getattr(view, 'datastore', None) if view else None
    if store_owner is None:
        return None
    store = store_owner.httpCookieStore()
    host = (urlparse(uri).hostname or '').lower()
    result: list[dict] = []
    done = threading.Event()

    def handler(cookies):
        try:
            for c in cookies or []:
                try:
                    domain = str(c.domain())
                    if not _matches(host, domain):
                        continue
                    expires = 0.0
                    date = c.expiresDate()
                    if date is not None and not c.isSessionOnly():
                        expires = float(date.timeIntervalSince1970())
                    result.append({'domain': domain, 'name': str(c.name()), 'value': str(c.value()), 'path': str(c.path() or '/'),
                                   'secure': bool(c.isSecure()), 'httponly': bool(c.isHTTPOnly()), 'expires': expires})
                    if delete:
                        store.deleteCookie_completionHandler_(c, None)
                except Exception:                      # noqa: BLE001 - skip one odd cookie, keep the rest
                    log.exception('Could not read a cookie')
        finally:
            done.set()

    try:
        AppHelper.callAfter(store.getAllCookies_, handler)
    except Exception:                                  # noqa: BLE001
        log.exception('Cookie request failed')
        return None
    return result if done.wait(timeout) else None


# ---------------------------------------------------------------- the general pasteboard (copied-link catcher)
class Pasteboard:
    def __init__(self):
        try:
            import AppKit
            self.appkit = AppKit
            self.board = AppKit.NSPasteboard.generalPasteboard()
            self.ok = True
        except Exception:                              # noqa: BLE001
            self.ok = False

    def sequence(self) -> int:
        return int(self.board.changeCount()) if self.ok else 0

    def text(self) -> str | None:
        if not self.ok:
            return None
        value = self.board.stringForType_(self.appkit.NSPasteboardTypeString)
        if value is None:
            return None
        value = str(value)
        return value if len(value) <= 16384 else None

    def app_is_front(self) -> bool:
        if not self.ok:
            return False
        try:
            return bool(self.appkit.NSApplication.sharedApplication().isActive())
        except Exception:                              # noqa: BLE001
            return False


def bring_to_front(window) -> None:
    try:
        from PyObjCTools import AppHelper
        import AppKit

        def go():
            AppKit.NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        window.restore()
        window.show()
        AppHelper.callAfter(go)
    except Exception:                                  # noqa: BLE001
        log.exception('Could not bring DropDL to the front')


# ---------------------------------------------------------------- notifications
class MacNotifier:
    """Notification Center banners. Clicking one brings DropDL forward and runs its action.

    The UserNotifications framework only works inside an app bundle with an identifier (the packaged DropDLStudio.app).
    Run from source, banners fall back to `osascript`, which shows the text but cannot report clicks.
    """

    def __init__(self, on_click):
        self.on_click = on_click                         # on_click(script) runs on a worker, never the main thread
        self.actions: dict[str, str | None] = {}
        self.center = None
        self.delegate = None
        try:
            import Foundation
            bundle_id = Foundation.NSBundle.mainBundle().bundleIdentifier()
            if not bundle_id or not getattr(sys, 'frozen', False):
                return
            import UserNotifications as UN
            self.UN = UN
            self.center = UN.UNUserNotificationCenter.currentNotificationCenter()
            self.delegate = _make_delegate(self)
            self.center.setDelegate_(self.delegate)
            self.center.requestAuthorizationWithOptions_completionHandler_(
                UN.UNAuthorizationOptionAlert | UN.UNAuthorizationOptionSound, lambda granted, error: None)
        except Exception:                                # noqa: BLE001
            log.exception('Notification Center is unavailable; using osascript banners')
            self.center = None

    def clicked(self, key: str) -> None:
        script = self.actions.pop(key, None)
        threading.Thread(target=self.on_click, args=(script,), daemon=True, name='notification-click').start()

    def show(self, title: str, text: str, script: str | None = None) -> bool:
        if self.center is not None:
            try:
                UN = self.UN
                key = uuid.uuid4().hex
                self.actions[key] = script
                content = UN.UNMutableNotificationContent.alloc().init()
                content.setTitle_(title[:120])
                content.setBody_(text[:240])
                content.setUserInfo_({'dropdl': key})
                request = UN.UNNotificationRequest.requestWithIdentifier_content_trigger_(key, content, None)
                self.center.addNotificationRequest_withCompletionHandler_(request, None)
                return True
            except Exception:                            # noqa: BLE001
                log.exception('Notification failed')
        try:
            quote = lambda s: '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'
            subprocess.Popen(['osascript', '-e', f'display notification {quote(text[:240])} with title {quote(title[:120])}'],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except OSError:
            return False


_DELEGATE_CLASS = None


def _make_delegate(owner: MacNotifier):
    global _DELEGATE_CLASS
    import objc
    from Foundation import NSObject
    UN = owner.UN
    if _DELEGATE_CLASS is not None:
        delegate = _DELEGATE_CLASS.alloc().init(); delegate.owner = owner
        return delegate
    protocol = objc.protocolNamed('UNUserNotificationCenterDelegate')

    class DropDLNotificationDelegate(NSObject, protocols=[protocol]):
        def userNotificationCenter_willPresentNotification_withCompletionHandler_(self, center, notification, handler):
            # show the banner even while DropDL is the active app
            handler(UN.UNNotificationPresentationOptionBanner | UN.UNNotificationPresentationOptionList)

        def userNotificationCenter_didReceiveNotificationResponse_withCompletionHandler_(self, center, response, handler):
            try:
                info = response.notification().request().content().userInfo()
                key = info.get('dropdl') if info else None
                if key:
                    owner.clicked(str(key))
            finally:
                handler()

    _DELEGATE_CLASS = _DELEGATE_CLASS or DropDLNotificationDelegate
    return _DELEGATE_CLASS.alloc().init()
