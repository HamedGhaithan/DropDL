"""The window-process helpers: copied-link detection, the catcher's routing, notifications and the new settings."""
import json
import time

import pytest

from app import connect_native as cn
from app.native import NativeAPI
from app.settings import Settings


@pytest.mark.parametrize('text,expected', [
    ('https://youtu.be/dQw4w9WgXcQ', 'https://youtu.be/dQw4w9WgXcQ'),
    ('  https://www.youtube.com/watch?v=abc  \n', 'https://www.youtube.com/watch?v=abc'),
    ('https://vimeo.com/1.', 'https://vimeo.com/1'),
    ('look at https://youtu.be/x', None),                 # a sentence, not a link
    ('ftp://example.com/file', None),
    ('http://localhost:5173/', None),
    ('https://' + 'a' * 2200 + '.com', None),
    ('', None), (None, None),
])
def test_only_a_single_web_link_counts(text, expected):
    assert cn.media_link(text) == expected


def test_background_offers_are_limited_to_media_sites():
    assert cn.is_media_host('https://m.youtube.com/watch?v=1') and cn.is_media_host('https://www.tiktok.com/@a/video/1')
    assert not cn.is_media_host('https://example.com/watch') and not cn.is_media_host('https://notyoutube.com/x')


class FakeClipboard:
    ok = True
    def __init__(self): self.seq, self.value, self.front_window = 1, '', 0
    def sequence(self): return self.seq
    def text(self): return self.value
    def foreground(self): return self.front_window
    def copy(self, value): self.value, self.seq = value, self.seq + 1


class FakeHandle:
    def ToInt64(self): return 42


class FakeNative:
    Visible = True
    Handle = FakeHandle()


class FakeWindow:
    def __init__(self): self.native, self.scripts = FakeNative(), []
    def evaluate_js(self, script): self.scripts.append(script)


class FakeNotifier:
    def __init__(self): self.shown = []
    def show(self, title, text, script=None): self.shown.append((title, text, script)); return True


def wait(condition, timeout=4):
    end = time.time() + timeout
    while time.time() < end:
        if condition():
            return True
        time.sleep(.05)
    return False


def test_the_catcher_offers_in_app_when_dropdl_is_in_front_and_notifies_otherwise():
    window, notifier = FakeWindow(), FakeNotifier()
    catcher = cn.LinkCatcher(window, notifier)
    catcher.clipboard = clip = FakeClipboard()
    clip.value = 'https://youtu.be/already-there'                # copied before DropDL started: never offered
    assert catcher.configure(True, 'en') is True
    try:
        time.sleep(.9)
        assert window.scripts == [] and notifier.shown == []
        clip.front_window = 42                                    # DropDL is the foreground window
        clip.copy('https://youtu.be/one')
        assert wait(lambda: window.scripts)
        assert json.dumps('https://youtu.be/one') in window.scripts[0]
        clip.front_window = 7                                     # another app is in front
        clip.copy('https://www.youtube.com/watch?v=two')
        assert wait(lambda: notifier.shown)
        title, text, script = notifier.shown[0]
        assert 'download' in title.lower() and 'youtube.com' in text and 'watch?v=two' in script
        clip.copy('https://example.com/page')                     # not a media site: no notification in the background
        clip.copy('just some text')
        time.sleep(1.6)
        assert len(notifier.shown) == 1
    finally:
        catcher.configure(False)
    assert wait(lambda: not catcher.thread.is_alive())


def test_the_catcher_rejects_bad_preferences():
    catcher = cn.LinkCatcher(FakeWindow(), FakeNotifier())
    with pytest.raises(ValueError):
        catcher.configure('yes')
    with pytest.raises(ValueError):
        catcher.configure(True, 'fr')


def test_bridge_notifications_validate_their_input():
    bridge = NativeAPI(settings=None)
    notifier = FakeNotifier()
    bridge._connect_parts = {'notifier': notifier, 'catcher': None, 'youtube': None}
    assert bridge.notify('Download complete', 'Song.mp3', 'abc123')
    assert 'dropdlFocusJob' in notifier.shown[0][2]
    with pytest.raises(ValueError):
        bridge.notify('x', 'y', 'bad id;alert(1)')
    with pytest.raises(RuntimeError):
        NativeAPI(settings=None).youtube_sign_in('en')          # only inside the desktop window


def test_new_settings_default_on_and_persist(tmp_path):
    settings = Settings(tmp_path / 'settings.json', tmp_path / 'downloads')
    assert settings.get()['clipboard_watch'] is True and settings.get()['notify_done'] is True
    settings.change(clipboard_watch=False, notify_done=False)
    reloaded = Settings(tmp_path / 'settings.json', tmp_path / 'downloads')
    assert reloaded.get()['clipboard_watch'] is False and reloaded.get()['notify_done'] is False


def test_a_notification_click_never_waits_on_the_ui_thread():
    """Clicking 'Link copied - download it?' froze the app: the click runs on the UI thread, and pywebview's
    evaluate_js waits for that same thread. The action must be handed to a worker so the click returns first."""
    import threading
    returned, ran = threading.Event(), []

    class UIWindow(FakeWindow):
        def evaluate_js(self, script):
            assert returned.wait(2), 'evaluate_js ran on the clicking thread and would deadlock'
            ran.append(script)

    notifier = cn.Notifier(UIWindow())
    notifier.pending = "window.dropdlClipboard('https://youtu.be/one')"
    notifier._clicked()
    returned.set()
    assert wait(lambda: ran) and ran == ["window.dropdlClipboard('https://youtu.be/one')"]
