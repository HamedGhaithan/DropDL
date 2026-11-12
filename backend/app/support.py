"""Local health report and bounded, redacted diagnostic exports."""
import io
import json
import os
import platform
import re
import shutil
import tempfile
import zipfile
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from .settings import CONFIG_ROOT
from .version import VERSION

router = APIRouter(prefix='/api/support')
context = None
from .diagnostic_report import LOGS,redact

def log_tail(name, limit=160*1024):
    try:
        with (CONFIG_ROOT/name).open('rb') as stream:
            stream.seek(0,2);size=stream.tell();stream.seek(max(0,size-limit))
            return redact(stream.read(limit).decode('utf-8',errors='replace'))
    except OSError:return ''

def package_version(name):
    try:return version(name)
    except PackageNotFoundError:return None

@router.get('/status')
def status():
    checks=[]
    checks.append({'id':'backend','ok':True,'detail':VERSION})
    checks.append({'id':'python','ok':True,'detail':platform.python_version()})
    for name in ('yt-dlp','pywebview'):
        installed=package_version(name)
        checks.append({'id':name,'ok':bool(installed),'detail':installed or 'Missing'})
    for name in ('ffmpeg','ffprobe'):
        path=context._tool(name) if context else shutil.which(name)
        checks.append({'id':name,'ok':bool(path),'detail':'Available' if path else 'Missing'})
    try:
        CONFIG_ROOT.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryFile(dir=CONFIG_ROOT):pass
        checks.append({'id':'profile','ok':True,'detail':'Writable'})
    except OSError:checks.append({'id':'profile','ok':False,'detail':'Not writable'})
    try:
        free=shutil.disk_usage(context.settings.get()['download_directory']).free
        checks.append({'id':'storage','ok':free>=100*1024**2,'detail':f'{free//1024**2} MB free'})
    except OSError:checks.append({'id':'storage','ok':False,'detail':'Directory unavailable'})
    diagnostics=log_tail('diagnostics.log')[-6000:]
    findings=[]
    for marker,code in [('10048','port_in_use'),('WebView2','webview'),('ModuleNotFoundError','dependency'),('PermissionError','permissions'),('startup timed out','timeout')]:
        if marker.lower() in diagnostics.lower():findings.append(code)
    failures=[]
    if context:
        for job in context.jobs.list():
            if job['status']=='failed' and job.get('error'):
                failures.append({'id':job['id'],'error':redact(job['error'])[:800]})
            if len(failures)>=5:break
    from .diagnostics import session_state
    session=session_state()
    if context:
        checks.append({'id':'queue','ok':not context.jobs.persistence_error,'detail':'Checkpoint failed' if context.jobs.persistence_error else 'Checkpoint writable'})
    return {'session':{'previous_unclean_exit':session.get('previous_unclean_exit',False)},'recovery':{'interrupted':sum(bool(j.get('interrupted')) for j in context.jobs.list()) if context else 0,'restored_from_backup':bool(context and context.jobs.restored_from_backup)},'version':VERSION,'checks':checks,'findings':findings,'failures':failures,
            'repair_available':os.name=='nt' and (CONFIG_ROOT/'installer/DropDL-Setup.exe').is_file()}

@router.get('/bundle')
def bundle():
    data=io.BytesIO()
    with zipfile.ZipFile(data,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('health.json',json.dumps(status(),ensure_ascii=False,indent=2))
        for name in LOGS:
            archive.writestr(name,log_tail(name))
        if context:
            # Include worker evidence for at most three recent failed tasks.
            # No queue URLs, filenames, settings or cookies are exported.
            for index, record in enumerate([j for j in context.jobs.list() if j['status']=='failed'][:3]):
                job=context.jobs.get(record['id'])
                for relative in ('worker.log','worker-state/diagnostics.log','worker-state/crash.log'):
                    try:
                        with (Path(job.directory)/relative).open('rb') as stream:
                            stream.seek(0,2);stream.seek(max(0,stream.tell()-160*1024))
                            tail=redact(stream.read(160*1024).decode('utf-8',errors='replace'))
                        archive.writestr(f'workers/{index+1}/'+relative,tail)
                    except OSError:pass
        archive.writestr('README.txt','Local diagnostic export. URLs, recognized credential values and the current home path are redacted. Review before sharing. Cookies, settings, queue history and media are not included. Logs are limited to the last 160 KiB each.\n')
    data.seek(0)
    return StreamingResponse(data,media_type='application/zip',headers={'Content-Disposition':'attachment; filename="DropDL-diagnostics.zip"','Cache-Control':'no-store'})
