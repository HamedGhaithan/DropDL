"""Native host with extraction and downloads in a separate backend."""
import os
import sys
from pathlib import Path
os.environ.setdefault('DOWNLOAD_ROOT',str(Path.home()/'Downloads'/'DropDL'))
# Finder does not inherit an interactive shell's PATH. Prefer bundled tools;
# source launches also support Homebrew's Apple Silicon and Intel prefixes.
if sys.platform == 'darwin':
    bundle_root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))
    os.environ['PATH']=os.pathsep.join([str(bundle_root/'bin'),'/opt/homebrew/bin','/usr/local/bin',os.environ.get('PATH','/usr/bin:/bin')])

from app.engine_update import activate
activate()

# Dispatch worker modes before importing the native webview.
if '--media-worker' in sys.argv:
    from app.media_worker import worker_main
    worker_main()
    raise SystemExit(0)
if '--playlist-worker' in sys.argv:
    from app.playlist_process import worker_main
    worker_main()
    raise SystemExit(0)
if '--backend-worker' in sys.argv:
    from app.server_process import serve_backend
    serve_backend()
    raise SystemExit(0)

if __name__=='__main__':
    from app.diagnostics import configure_diagnostics,start_session,finish_session
    configure_diagnostics("desktop")
    start_session()
    import logging
    import webview
    from app.version import VERSION
    from app.desktop_host import create_desktop_window,desktop_icon,set_windows_app_id
    from app.server_process import BackendProcess,RemoteSettings
    from app.settings import CONFIG_ROOT
    logging.getLogger('dropdl').info('Desktop starting: version=%s', VERSION)
    import json
    app_root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))
    manifest=app_root/'frontend'/'dist'/'build.json'
    if not manifest.is_file() or json.loads(manifest.read_text()).get('version')!=VERSION:
        raise RuntimeError('The desktop interface is missing or belongs to a different release. Reinstall the latest desktop package.')
    set_windows_app_id()
    backend=BackendProcess(int(os.getenv('PORT','17321')))
    try:
        backend.start()
        settings=RemoteSettings(backend)
        window,bridge=create_desktop_window(webview,settings,f"{backend.url}/?desktop_build={VERSION}",job_lookup=lambda job_id:backend.request(f'/api/jobs/{job_id}'))
        webview.settings['ALLOW_DOWNLOADS']=True
        webview.start(gui='edgechromium' if os.name=='nt' else None,private_mode=False,storage_path=str(CONFIG_ROOT/'webview'),icon=str(desktop_icon()))
    except Exception:
        logging.getLogger("dropdl").exception("Desktop failed")
        raise
    else:
        finish_session()
    finally:
        backend.close()
