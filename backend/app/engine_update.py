"""Official stable yt-dlp releases, installed in immutable runtime slots.
Never replace packages underneath running downloads; activate on the next launch.
"""
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from threading import Event,Lock,Thread
import time
from urllib.request import Request,urlopen
from .settings import CONFIG_ROOT

ROOT=Path(os.getenv('DROPDL_ENGINE_ROOT',str(CONFIG_ROOT/'engine')));stop=Event();lock=Lock();state={'checking':False,'error':None,'available':None,'pending':None,'last_check':None}

def activate():
    if getattr(sys,'frozen',False):return
    try:
        version=(ROOT/'active.json').read_text(encoding='utf-8');slot=json.loads(version)['slot']
        if not re.fullmatch(r'[0-9.]+-[a-f0-9]{8}',slot):return
        path=ROOT/slot
        if (path/'yt_dlp'/'version.py').is_file():sys.path.insert(0,str(path))
    except (OSError,ValueError,KeyError,TypeError):pass

def status():
    from yt_dlp.version import __version__
    with lock:return dict(state,current=__version__,auto=True,supported=not getattr(sys,'frozen',False),channel='stable',interval_hours=1)

def fetch(url,limit=4*1024*1024):
    with urlopen(Request(url,headers={'User-Agent':'DropDL-Studio-updater','Accept':'application/vnd.github+json'}),timeout=30) as response:
        data=response.read(limit+1)
    if len(data)>limit:raise ValueError('Update response exceeded the size limit.')
    return data

def check():
    with lock:
        if state['checking']:return
        state.update(checking=True,error=None)
    stage=None
    try:
        if getattr(sys,'frozen',False):raise ValueError('This packaged runtime requires an application update; use the online desktop installer for engine updates.')
        from yt_dlp.version import __version__
        release=json.loads(fetch('https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest'))
        tag=release['tag_name'].removeprefix('v')
        if not re.fullmatch(r'\d{4}\.\d{1,2}\.\d{1,2}(?:\.\d+)?',tag):raise ValueError('Unexpected release version.')
        key=lambda v:tuple(int(n) for n in v.split('.'))
        with lock:state.update(last_check=time.time(),available=tag)
        if key(tag)<=key(__version__):return
        ROOT.mkdir(parents=True,exist_ok=True)
        try:
            active=json.loads((ROOT/'active.json').read_text())
            if active.get('version')==tag and (ROOT/active['slot']/'yt_dlp/version.py').is_file():
                with lock:state['pending']=tag
                return
        except (OSError,ValueError,KeyError):pass
        assets=release.get('assets',[])
        wheel=next((a for a in assets if a['name'].startswith('yt_dlp-') and a['name'].endswith('-py3-none-any.whl')),None)
        if not wheel:wheel=next((a for a in assets if a['name']=='yt-dlp.tar.gz'),None)
        if not wheel:raise ValueError('The official Python release package is unavailable.')
        base=f'https://github.com/yt-dlp/yt-dlp/releases/download/{release["tag_name"]}/'
        if not wheel['browser_download_url'].startswith(base):raise ValueError('Unexpected release download origin.')
        digest=wheel.get('digest') or ''
        if not re.fullmatch(r'sha256:[a-f0-9]{64}',digest):
            sums=next((a for a in assets if a['name']=='SHA2-256SUMS'),None)
            if not sums or not sums['browser_download_url'].startswith(base):raise ValueError('Release checksums unavailable.')
            expected=next((line.split()[0] for line in fetch(sums['browser_download_url']).decode().splitlines() if line.split()[-1].lstrip('*')==wheel['name']),None)
        else:expected=digest.split(':')[1]
        if not expected or not re.fullmatch(r'[a-f0-9]{64}',expected):raise ValueError('No valid package checksum.')
        content=fetch(wheel['browser_download_url'],32*1024*1024)
        if hashlib.sha256(content).hexdigest()!=expected:raise ValueError('Update checksum verification failed; existing engine retained.')
        with tempfile.TemporaryDirectory(prefix='dropdl-engine-') as temp:
            package=Path(temp)/wheel['name'];package.write_bytes(content)
            stage=ROOT/('staging-'+str(time.time_ns()));stage.mkdir()
            flags={'creationflags':subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0}
            result=subprocess.run([sys.executable,'-m','pip','install','--disable-pip-version-check','--no-warn-script-location','--target',str(stage),str(package)+'[default]'],capture_output=True,text=True,timeout=300,**flags)
            if result.returncode:raise ValueError('Engine installation failed. Existing engine retained. '+result.stderr[-800:])
            code='import sys; sys.path.insert(0,sys.argv[1]); from yt_dlp.version import __version__; from yt_dlp import YoutubeDL; assert __version__ == sys.argv[2]'
            result=subprocess.run([sys.executable,'-c',code,str(stage),tag],capture_output=True,text=True,timeout=30,**flags)
            if result.returncode:raise ValueError('Engine validation failed. Existing engine retained.')
        slot=tag+'-'+expected[:8];destination=ROOT/slot
        if destination.exists():shutil.rmtree(stage)
        else:stage.rename(destination)
        stage=None;pointer=ROOT/'active.tmp';pointer.write_text(json.dumps({'slot':slot,'version':tag}),encoding='utf-8');pointer.replace(ROOT/'active.json')
        with lock:state['pending']=tag
    except Exception as exc:
        logging.getLogger('dropdl.updater').warning('yt-dlp update: %s',exc)
        with lock:state.update(error=str(exc),last_check=time.time())
    finally:
        if stage:shutil.rmtree(stage,ignore_errors=True)
        with lock:state['checking']=False

def request_check():
    Thread(target=check,daemon=True,name='yt-dlp-update-check').start()

def start():
    stop.clear()
    def loop():
        while not stop.is_set():
            check()
            if stop.wait(3600):break
    Thread(target=loop,daemon=True,name='yt-dlp-updater').start()
