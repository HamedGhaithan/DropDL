"""Small, explicit native host setup; never expose the Window object to JS."""
from pathlib import Path
import ctypes
import logging
import os
import sys
from .native import NativeAPI
from .version import VERSION


def desktop_icon():
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2]))
    return root / 'installer' / 'dropdl.ico'


def set_windows_app_id():
    if os.name != 'nt': return
    try:
        set_id = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
        set_id.argtypes = [ctypes.c_wchar_p]
        set_id.restype = ctypes.c_long
        result = set_id('DropDL.Studio')
        if result != 0: logging.warning('Could not set Windows app identity: %s', result)
    except (OSError, AttributeError):
        logging.exception('Could not set Windows app identity')


def create_desktop_window(webview, settings, url, job_lookup=None):
    bridge = NativeAPI(settings, job_lookup)
    # js_api recursively walks public attributes. Explicit function exposure avoids
    # discovery of the Window, GUI objects, settings and locks during startup.
    window = webview.create_window(f'DropDL Studio {VERSION}', url, width=1320, height=900, min_size=(800, 620))
    bridge._window = window
    window.expose(bridge.choose_folder, bridge.open_folder, bridge.choose_media_files, bridge.choose_cookies, bridge.open_downloaded, bridge.open_library,bridge.locate_media,bridge.reveal_library, bridge.launch_repair,bridge.open_editor,bridge.open_player,bridge.export_diagnostics,bridge.configure_tray)
    window.events.shown += lambda: apply_windows_icon(window)
    if os.name=='nt':
        from .windows_tray import WindowsTray
        tray=WindowsTray(window,webview,settings);bridge._tray=tray
        window.events.shown += tray.install
    return window, bridge


def apply_windows_icon(window):
    """Apply the icon to the actual WinForms HWND after it exists."""
    if os.name!='nt':return
    try:
        from System import Action
        from System.Drawing import Icon
        native=window.native
        def assign():
            # Hold the managed icon for the lifetime of the native window.
            window._dropdl_native_icon=Icon(str(desktop_icon()))
            native.Icon=window._dropdl_native_icon
            native.ShowIcon=True
        if native.InvokeRequired:native.Invoke(Action(assign))
        else:assign()
    except Exception:logging.getLogger('dropdl').exception('Could not apply native window icon')
