"""Backend child lifecycle. The native GUI never imports yt-dlp or FastAPI."""
import json
import logging
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time
from threading import Thread
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from .settings import CONFIG_ROOT
from .version import VERSION


class BackendProcess:
    def __init__(self,port):
        self._port=port
        self._token=secrets.token_hex(32)
        self._process=None
        self._console=None
        self._closing=False
        self.url=f'http://127.0.0.1:{port}'

    def request(self,path,data=None,timeout=2):
        headers={'X-DropDL-Native-Token':self._token}
        if data is not None:headers['Content-Type']='application/json'
        request=Request(self.url+path,data=json.dumps(data).encode() if data is not None else None,headers=headers)
        try:
            with urlopen(request,timeout=timeout) as response:return json.load(response)
        except HTTPError as exc:
            try:
                detail=json.loads(exc.read(16384)).get('detail')
            except (ValueError,TypeError):detail=None
            # Native pickers should show the backend's useful validation message.
            raise ValueError(str(detail)[:2000] if detail else f'The desktop request failed ({exc.code}).') from exc

    def start(self):
        import socket
        with socket.socket() as probe:
            try:probe.bind(('127.0.0.1',self._port))
            except OSError as exc:raise RuntimeError('DropDL is already running, or its port is in use. Close the other instance first.') from exc
        CONFIG_ROOT.mkdir(parents=True,exist_ok=True)
        self._console=(CONFIG_ROOT/'backend-console.log').open('ab',buffering=0)
        command=[sys.executable,'--backend-worker'] if getattr(sys,'frozen',False) else [sys.executable,'-u',str(Path(__file__).resolve().parents[1]/'desktop.py'),'--backend-worker']
        env=dict(os.environ,DROPDL_NATIVE_TOKEN=self._token,PORT=str(self._port),PYTHONUNBUFFERED='1')
        self._process=subprocess.Popen(command,env=env,stdin=subprocess.DEVNULL,stdout=self._console,stderr=self._console,
            creationflags=(subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP) if os.name=='nt' else 0,start_new_session=os.name!='nt')
        logging.getLogger('dropdl').info('Backend child started: pid=%s',self._process.pid)
        for _ in range(150):
            if self._process.poll() is not None:
                raise RuntimeError(f'Backend stopped during startup (code {self._process.returncode}). See backend-console.log.')
            try:
                health=self.request('/api/health')
                if health.get('ok'):
                    if health.get('version')!=VERSION:
                        raise RuntimeError('The running download engine does not match this desktop release. Close DropDL and reinstall the latest desktop package.')
                    Thread(target=self._watch_exit,daemon=True,name='backend-monitor').start()
                    return
            except (OSError,ValueError):pass
            time.sleep(.1)
        raise RuntimeError('Backend startup timed out. See diagnostics.log and backend-console.log.')

    def _watch_exit(self):
        code=self._process.wait()
        if not self._closing:logging.getLogger('dropdl').error('Backend child exited unexpectedly: pid=%s code=%s',self._process.pid,code)

    def close(self):
        self._closing=True
        process=self._process
        if process and process.poll() is None:
            try:self.request('/api/native/shutdown',{})
            except (OSError,ValueError):pass
            try:process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                if os.name=='nt':
                    subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5,creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    try:os.killpg(process.pid,signal.SIGTERM)
                    except ProcessLookupError:pass
                try:process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    if os.name!='nt':
                        try:os.killpg(process.pid,signal.SIGKILL)
                        except ProcessLookupError:pass
                    else:process.kill()
                    process.wait()
        if self._console:self._console.close()


class RemoteSettings:
    def __init__(self,backend):self._backend=backend
    def get_media(self,identity):return self._backend.request(f'/api/library/{identity}')
    def relink_media(self,identity,path):return self._backend.request(f"/api/native/library/{identity}/relink",{"path":path},timeout=120)
    def get(self):return self._backend.request('/api/settings')
    def import_cookies(self,path):return self._backend.request("/api/native/cookies",{"path":path})
    def import_files(self,paths):return self._backend.request("/api/native/import",{"paths":paths},timeout=120)
    def change(self,**changes):return self._backend.request('/api/native/export-destination' if 'export_directory' in changes else '/api/native/destination',changes)


def serve_backend():
    from .diagnostics import configure_diagnostics
    configure_diagnostics()
    import uvicorn
    from .main import app
    app.state.desktop=True
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=int(os.getenv('PORT','17321')),log_level='warning',log_config=None))
    app.state.server=server
    logging.getLogger('dropdl').info('Separate backend starting')
    server.run()
