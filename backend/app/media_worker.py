"""Downloads run in disposable processes, isolating native/extractor crashes."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import logging
from dataclasses import fields
from threading import Thread
from .jobs import Job,jobs


def command(request,status,control):
    if getattr(sys,'frozen',False):return [sys.executable,'--media-worker',str(request),str(status),str(control)]
    return [sys.executable,'-u',str(Path(__file__).resolve().parents[1]/'desktop.py'),'--media-worker',str(request),str(status),str(control)]

FIELDS={'status','percent','downloaded_bytes','total_bytes','speed','eta','title','filename','preview_filename','error','phase','thumbnail'}
# Statuses where bytes are expected to move; FFmpeg phases may legitimately be quiet.
TRANSFER_STATES={'downloading'}


def _read_status(path):
    for _ in range(20):
        try:return json.loads(path.read_text(encoding='utf-8'))
        except FileNotFoundError:return None
        except (OSError,ValueError):time.sleep(.05)  # Antivirus/indexers can briefly lock the file.
    return None


def run_isolated(job):
    directory=Path(job.directory);directory.mkdir(parents=True,exist_ok=True)
    request=directory/'worker-request.json';status=directory/'worker-status.json';control=directory/'worker-stop'
    status.unlink(missing_ok=True);control.unlink(missing_ok=True)
    request.write_text(json.dumps({f.name:getattr(job,f.name) for f in fields(Job) if f.name!='cancel_event'}),encoding='utf-8')
    from .engine_update import ROOT as engine_root
    env=dict(os.environ,DROPDL_ENGINE_ROOT=str(engine_root),DROPDL_DATA_ROOT=str(directory/'worker-state'),PYTHONFAULTHANDLER='1',DROPDL_PARENT_PID=str(os.getpid()))
    stall_limit=float((job.network or {}).get('stall_timeout',90) or 0)
    process=None;last=None;stalled=False
    try:
        with (directory/'worker.log').open('ab',buffering=0) as log:
            process=subprocess.Popen(command(request,status,control),env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            stopped=None
            progress_mark=(None,time.monotonic())
            while process.poll() is None:
                if job.cancel_event.is_set():
                    if stopped is None:control.touch();stopped=time.monotonic()
                    if time.monotonic()-stopped>7:process.kill()
                try:
                    data=json.loads(status.read_text(encoding='utf-8'))
                    if data!=last:
                        updates={k:v for k,v in data.items() if k in FIELDS}
                        # Do not announce completion until the worker exits successfully,
                        # and never let a stopping worker overwrite pause/shutdown intent.
                        if updates.get('status')=='completed' or (job.cancel_event.is_set() or stalled) and updates.get('status') in {'cancelled','failed'}:updates.pop('status')
                        jobs.update_attempt(job,**updates);last=data
                except (OSError,ValueError):pass
                # Stall watchdog: a transfer with no new bytes for stall_limit seconds
                # is restarted from its partial data instead of hanging forever.
                if stall_limit and stopped is None and job.status in TRANSFER_STATES:
                    if job.downloaded_bytes!=progress_mark[0]:progress_mark=(job.downloaded_bytes,time.monotonic())
                    elif time.monotonic()-progress_mark[1]>stall_limit:
                        logging.getLogger('dropdl.worker').warning('Task %s stalled for %ss; restarting worker',job.id[:8],int(stall_limit))
                        stalled=True;control.touch();stopped=time.monotonic()
                else:progress_mark=(job.downloaded_bytes,time.monotonic())
                time.sleep(.15)
            if stalled and not job.cancel_event.is_set():
                jobs.update_attempt(job,status='failed',phase='stalled',stalls=job.stalls+1,speed=None,eta=None,
                    error=f'Download stalled: no data received for {int(stall_limit)} seconds. Partial data is kept for resuming.')
            elif job.cancel_event.is_set():jobs.update_attempt(job,status='paused' if job.pause_requested else 'cancelled',error=None,speed=None,eta=None)
            elif process.returncode:
                jobs.update_attempt(job,status='failed',error=f"Media worker stopped unexpectedly (code {process.returncode}). The app is still running. Retry this task; see {directory / 'worker.log'}.")
            else:
                data=_read_status(status)
                if data is None:
                    jobs.update_attempt(job,status='failed',error=f"The media worker finished without reporting a result. See {directory / 'worker.log'}.")
                else:
                    updates={k:v for k,v in data.items() if k in FIELDS}
                    if updates.get('status') not in {'completed','failed','cancelled','paused'}:
                        updates['status']='failed';updates['error']=updates.get('error') or 'The media worker exited before finishing this task.'
                    jobs.update_attempt(job,**updates)
    except Exception as exc:jobs.update_attempt(job,status='failed',error=str(exc))
    finally:
        if process and process.poll() is None:process.kill();process.wait()
        request.unlink(missing_ok=True);control.unlink(missing_ok=True)

class ParentWatch:
    """Detect the death of the backend that started this worker. On Windows a
    process handle is held, so a recycled PID can never be mistaken for it."""
    def __init__(self,pid):
        self.pid=int(pid) if str(pid or '').isdigit() else 0
        self.handle=None;self.checked=0.0;self.dead=False
        if self.pid and os.name=='nt':
            try:
                import ctypes
                self.handle=ctypes.windll.kernel32.OpenProcess(0x00100000,False,self.pid)  # SYNCHRONIZE
            except Exception:self.handle=None
    def gone(self):
        if not self.pid or self.dead:return self.dead
        now=time.monotonic()
        if now-self.checked<1:return False
        self.checked=now
        try:
            if os.name=='nt':
                import ctypes
                if not self.handle:return False
                self.dead=ctypes.windll.kernel32.WaitForSingleObject(self.handle,0)==0  # WAIT_OBJECT_0: exited
            else:
                self.dead=os.getppid()!=self.pid
        except Exception:return False
        return self.dead


def worker_main():
    offset=sys.argv.index('--media-worker')
    request,status,control=map(Path,sys.argv[offset+1:offset+4])
    from .diagnostics import configure_diagnostics
    configure_diagnostics()
    job=Job(**json.loads(request.read_text(encoding='utf-8')))
    jobs._jobs[job.id]=job
    def publish():
        return publish_snapshot(job,status)
    done=False
    parent=ParentWatch(os.environ.get('DROPDL_PARENT_PID'))
    def watch():
        while not done:
            if control.exists():job.cancel_event.set()
            if parent.gone() and not job.cancel_event.is_set():
                # The backend died (crash, Task Manager). Stop cleanly and keep
                # the partial file, so the restarted app can resume it without
                # an orphaned worker writing the same file concurrently.
                logging.getLogger('dropdl.worker').warning('Backend process ended; pausing task %s',job.id[:8])
                job.pause_requested=True;job.cancel_event.set()
            # Windows readers and antivirus can briefly lock the status file.
            # A failed replace must never kill the progress publisher thread.
            try:publish()
            except Exception:logging.getLogger('dropdl.worker').exception('Progress publication failed; will retry')
            time.sleep(.15)
    watcher=Thread(target=watch,daemon=True);watcher.start()
    from .downloader import run_download
    try:run_download(job)
    finally:
        done=True
        watcher.join(timeout=2)
        for _ in range(40):
            if publish():break
            time.sleep(.05)
        else:raise RuntimeError('Could not publish final media status. See worker diagnostics.')


def publish_snapshot(job,status):
    # Snapshot under the same lock used by hooks to avoid half-applied updates.
    with jobs._lock:
        data={f.name:getattr(job,f.name) for f in fields(Job) if f.name!='cancel_event'}
    # Normalize non-finite optional measurements to JSON null.
    import math
    for key,value in list(data.items()):
        if isinstance(value,float) and not math.isfinite(value):data[key]=None
    temporary=status.with_suffix('.tmp')
    try:
        temporary.write_text(json.dumps(data,ensure_ascii=False,allow_nan=False),encoding='utf-8')
        temporary.replace(status)
        return True
    except OSError:
        return False
