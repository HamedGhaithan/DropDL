import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from fastapi.testclient import TestClient
from app.main import app
from app.jobs import jobs
from app.media_worker import run_isolated
from app.settings import Settings
from app.windows_tray import TrayPolicy

client=TestClient(app)

def test_clip_enabled_cannot_silently_queue_whole_video():
    with patch('app.main.executor.submit') as submit:
        r=client.post('/api/batch',json={'urls':['https://example.com/video'],'clip_enabled':True})
    assert r.status_code==422;submit.assert_not_called()

@pytest.mark.parametrize('preview',[False,True])
def test_sidebar_api_to_real_isolated_worker_clips_both_outputs(tmp_path,preview):
    source=tmp_path/'source.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=size=160x90:rate=25','-f','lavfi','-i','sine=frequency=500','-t','4','-c:v','libx264','-c:a','aac',str(source)],check=True)
    options={'mode':'both','clip_enabled':True,'clip_start':.5,'clip_end':1.7}
    pref=Settings(tmp_path/'settings.json',tmp_path/'exports');pref.change(group_by_site=False)
    with patch('app.main.settings',pref),patch('app.main.CONFIG_ROOT',tmp_path/'config'),patch('app.main.checked_batch_urls',side_effect=lambda urls:urls),patch('app.main.executor.submit'),patch('app.main.editor.submit'):
        if preview:
            parent=jobs.create(url='https://example.com/a',kind='video',container='mp4',quality='best',directory=str(tmp_path))
            jobs.update(parent.id,status='completed',filename=str(source),purpose='preview')
            r=client.post(f'/api/jobs/{parent.id}/clip',json=dict(options,show_in_downloads=True))
        else:
            r=client.post('/api/batch',json=dict(options,urls=['https://example.com/a']))
    assert r.status_code==202,r.text
    for record in r.json()['jobs']:
        job=jobs.get(record['id']);assert job.clip_start==.5 and job.clip_end==1.7 and job.purpose=='download'
        # Isolate/exercise the exact native worker serialization and clipping
        # path; only replace network acquisition with an existing real source.
        job.source_filename=str(source)
        run_isolated(job)
        assert job.status=='completed',job.error
        output=Path(job.filename);assert output.exists() and output!=source
        info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','json',str(output)]))
        assert abs(float(info['format']['duration'])-1.2)<.15
    assert source.exists() and len(list((tmp_path/'exports').glob('*')))==2

def test_tray_preference_persists_default_off(tmp_path):
    settings=Settings(tmp_path/'settings.json',tmp_path/'out')
    assert settings.get()['keep_in_tray'] is False
    settings.change(keep_in_tray=True)
    assert Settings(settings.path,tmp_path/'out').get()['keep_in_tray'] is True

def test_tray_close_exit_and_unavailable_policy():
    policy=TrayPolicy()
    assert not policy.intercept()
    policy.enabled=True;assert not policy.intercept()
    policy.ready=True;assert policy.intercept()
    assert not policy.intercept(user_close=False)
    policy.exiting=True;assert not policy.intercept()

def test_native_tray_restore_exit_and_shutdown(monkeypatch,tmp_path):
    from types import SimpleNamespace
    from unittest.mock import Mock
    import app.windows_tray as module
    class Event:
        def __init__(self):self.handlers=[]
        def __iadd__(self,fn):self.handlers.append(fn);return self
        def fire(self,*args):
            for fn in self.handlers:fn(*args)
    class Disposable:
        def __init__(self,*args):self.Dispose=Mock();self.Click=Event();self.DoubleClick=Event();self.Visible=False
    class Menu(Disposable):
        def __init__(self):super().__init__();self.Items=SimpleNamespace(Add=Mock())
    native=SimpleNamespace(InvokeRequired=False,Visible=True,WindowState='minimized',Hide=Mock(),Show=Mock(),Activate=Mock(),BringToFront=Mock(),FormClosing=Event(),FormClosed=Event())
    window=SimpleNamespace(native=native,destroy=Mock());child=SimpleNamespace(destroy=Mock())
    forms=SimpleNamespace(NotifyIcon=Disposable,ContextMenuStrip=Menu,ToolStripMenuItem=Disposable,CloseReason=SimpleNamespace(UserClosing='user'),RightToLeft=SimpleNamespace(Yes='rtl',No='ltr'),FormWindowState=SimpleNamespace(Minimized='minimized',Normal='normal'))
    monkeypatch.setattr(module,'os',SimpleNamespace(name='nt'))
    monkeypatch.setitem(sys.modules,'System',SimpleNamespace(Action=lambda fn:fn))
    monkeypatch.setitem(sys.modules,'System.Drawing',SimpleNamespace(Icon=Disposable))
    monkeypatch.setitem(sys.modules,'System.Windows.Forms',forms)
    tray=module.WindowsTray(window,SimpleNamespace(windows=[window,child]),SimpleNamespace(get=lambda:{'keep_in_tray':True}))
    tray.install();assert tray.policy.ready and tray.icon.Visible
    close=SimpleNamespace(CloseReason='user',Cancel=False);native.FormClosing.fire(None,close)
    assert close.Cancel;native.Hide.assert_called_once()
    shutdown=SimpleNamespace(CloseReason='shutdown',Cancel=False);native.FormClosing.fire(None,shutdown);assert not shutdown.Cancel
    tray.configure(True,'ar');assert tray.open_item.Text=='فتح DropDL' and tray.menu.RightToLeft=='rtl'
    tray.icon.DoubleClick.fire(None,None);native.Show.assert_called_once();assert native.WindowState=='normal'
    tray.exit_item.Click.fire(None,None);window.destroy.assert_called_once();child.destroy.assert_called_once();assert not tray.icon.Visible
    icon=tray.icon;native.FormClosed.fire(None,None);icon.Dispose.assert_called_once();assert not tray.policy.ready

def test_network_source_is_trimmed_before_publishing(tmp_path):
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    from threading import Thread
    source=tmp_path/'network.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=size=160x90:rate=25','-f','lavfi','-i','sine=frequency=400','-t','4','-c:v','libx264','-c:a','aac',str(source)],check=True)
    data=source.read_bytes()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            self.send_response(200);self.send_header('Content-Type','video/mp4');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        job=jobs.create(url=f'http://127.0.0.1:{server.server_port}/network.mp4',kind='video',container='mp4',quality='best',directory=str(tmp_path/'work'),destination=str(tmp_path/'output'),clip_start=.8,clip_end=2)
        run_isolated(job);assert job.status=='completed',job.error
        info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','json',job.filename]))
        assert abs(float(info['format']['duration'])-1.2)<.15
        assert len(list((tmp_path/'output').glob('*.mp4')))==1
    finally:server.shutdown();server.server_close();thread.join(timeout=3)
