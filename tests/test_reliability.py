import io,json,sys,zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.jobs import JobStore
from app.native import NativeAPI

def make(store,tmp_path,**options):
    return store.create(url='https://example.com/media',kind='video',container='mp4',quality='best',directory=str(tmp_path/'partial'),**options)

def test_corrupt_checkpoint_recovers_backup_and_skips_bad_record(tmp_path):
    path=tmp_path/'queue.json';store=JobStore();store.enable_persistence(path)
    job=make(store,tmp_path)
    with patch('app.jobs.time',return_value=job.created_at+2):store.update(job.id,status='downloading',percent=31,downloaded_bytes=310,total_bytes=1000)
    store.update(job.id,status='queued') # force checkpoint containing previous progress into backup
    backup=json.loads(path.with_suffix('.bak').read_text());backup.insert(0,{'invalid':'record'})
    path.with_suffix('.bak').write_text(json.dumps(backup));path.write_text('{incomplete')
    restored=JobStore();restored.enable_persistence(path)
    record=restored.get(job.id)
    assert restored.restored_from_backup and restored.recovered_count==1
    assert record.status=='paused' and record.interrupted and record.percent==31
    assert record.directory==job.directory and len(restored.list())==1
    assert json.loads(path.read_text())[0]['id']==job.id

def test_restart_preserves_pause_cancel_and_completion_intent(tmp_path):
    path=tmp_path/'queue.json';store=JobStore();store.enable_persistence(path)
    states=['paused','cancelling','pausing','completed','failed','cancelled','downloading','queued']
    records=[make(store,tmp_path,status=state) for state in states]
    restored=JobStore();restored.enable_persistence(path)
    for previous,status in zip(records,states):
        item=restored.get(previous.id)
        if status in ('downloading','queued'):assert item.status=='paused' and item.interrupted
        else:assert item.status=={'cancelling':'cancelled','pausing':'paused'}.get(status,status) and not item.interrupted

def test_graceful_checkpoint_is_resumable_and_keeps_partial_files(tmp_path):
    path=tmp_path/'queue.json';store=JobStore();store.enable_persistence(path)
    job=make(store,tmp_path,status='downloading',percent=42,downloaded_bytes=420)
    partial=Path(job.directory)/'media.mp4.part';partial.parent.mkdir();partial.write_bytes(b'partial')
    store.checkpoint_for_shutdown();store.update_attempt(job,status='paused')
    restored=JobStore();restored.enable_persistence(path);job2=restored.get(job.id)
    assert job2.interrupted and job2.status=='paused'
    retry=restored.retry(job.id)
    assert retry.id==job.id and not retry.interrupted and retry.downloaded_bytes==420
    assert partial.read_bytes()==b'partial'

def test_persistence_failure_is_visible_without_killing_download(tmp_path):
    store=JobStore();store.enable_persistence(tmp_path/'queue.json')
    with patch('app.jobs.os.fsync',side_effect=OSError('disk full')):
        job=make(store,tmp_path)
        assert store.get(job.id) is job and store.persistence_error=='disk full'
    store.update(job.id,status='paused')
    assert store.persistence_error is None

@pytest.mark.parametrize('error,code',[('HTTP Error 503','network'),('No space left on device','disk_space'),('Sign in to view','authentication'),('Unsupported URL','unsupported'),('Media worker stopped unexpectedly','worker_crash')])
def test_actionable_error_categories(error,code,tmp_path):
    store=JobStore();assert make(store,tmp_path,error=error).public()['error_code']==code

def test_native_detached_player_validates_identity_and_docks(tmp_path):
    class Event:
        def __iadd__(self,callback):self.callback=callback;return self
    source=tmp_path/'movie.mp4';source.write_bytes(b'media')
    created=[];scripts=[]
    class Window:
        def __init__(self):self.events=SimpleNamespace(shown=Event(),closed=Event());self.functions=[];self.closed=False;self.shows=0
        def expose(self,*functions):self.functions=list(functions)
        def destroy(self):self.closed=True;self.events.closed.callback()
        def show(self):self.shows+=1
    def create(title,url,**options):
        child=Window();created.append((title,url,options,child));return child
    bridge=NativeAPI(SimpleNamespace(),lambda identity:{'status':'completed','output_path':str(source)})
    bridge._window=SimpleNamespace(get_current_url=lambda:'http://127.0.0.1:17321/',evaluate_js=scripts.append)
    with patch.dict('sys.modules',{'webview':SimpleNamespace(create_window=create)}):
        with pytest.raises(ValueError):bridge.open_player('job:../../other')
        with pytest.raises(ValueError):bridge.open_player('job:test','en',float('nan'))
        assert bridge.open_player('job:test','ar',12,1.5)
        assert bridge.open_player('job:test','ar',12,1.5) and len(created)==1
        title,url,options,child=created[0]
        assert 'player=job%3Atest' in url and 'lang=ar' in url and 'time=12' in url
        assert options['min_size']==(420,320)
        dock=next(fn for fn in child.functions if fn.__name__=='dock_player')
        assert dock(24,1.25) and child.closed
        assert 'dropdl-player-docked' in scripts[0] and '24' in scripts[0]
        assert not bridge._players

def test_session_marker_distinguishes_clean_shutdown(tmp_path,monkeypatch):
    import app.diagnostics as diagnostics
    monkeypatch.setattr(diagnostics,'CONFIG_ROOT',tmp_path)
    diagnostics.start_session();assert diagnostics.session_state()['clean_exit'] is False
    diagnostics.start_session();assert diagnostics.session_state()['previous_unclean_exit']
    diagnostics.finish_session();diagnostics.start_session()
    assert not diagnostics.session_state()['previous_unclean_exit']

def test_postprocessor_stages_cross_worker_snapshot(tmp_path):
    from app.jobs import jobs
    import app.downloader as downloader
    from app.media_worker import publish_snapshot
    phases=[]
    job=make(jobs,tmp_path)
    class Downloader:
        def __init__(self,options):self.options=options
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def add_progress_hook(self,hook):pass
        def download(self,urls):
            for pp in ('Merger','ExtractAudio','VideoRemuxer','Metadata'):
                self.options['postprocessor_hooks'][0]({'status':'started','postprocessor':pp});phases.append(job.phase)
            Path(job.directory).joinpath('video.mp4').write_bytes(b'video')
    with patch.object(downloader,'YoutubeDL',Downloader):downloader.run_download(job)
    assert phases==['merging','converting','remuxing','metadata']
    assert publish_snapshot(job,tmp_path/'status.json')
    assert json.loads((tmp_path/'status.json').read_text())['phase']=='completed'

def test_native_diagnostics_export_survives_backend_failure(tmp_path,monkeypatch):
    import app.settings as settings
    monkeypatch.setattr(settings,'CONFIG_ROOT',tmp_path)
    (tmp_path/'desktop-diagnostics.log').write_text('Startup failed https://example.com/?token=private\npassword=secret\n')
    (tmp_path/'queue.json').write_text('private queue')
    target=tmp_path/'saved-report.zip'
    bridge=NativeAPI(SimpleNamespace(_backend=SimpleNamespace(url='http://127.0.0.1:1',_token='local')))
    bridge._window=SimpleNamespace(create_file_dialog=lambda *a,**k:(str(target),))
    with patch.dict('sys.modules',{'webview':SimpleNamespace(FileDialog=SimpleNamespace(SAVE=30))}):assert bridge.export_diagnostics()
    with zipfile.ZipFile(target) as archive:
        assert json.loads(archive.read('health.json'))['backend_reachable'] is False
        text=archive.read('desktop-diagnostics.log').decode()
        assert 'Startup failed' in text and 'secret' not in text and 'example.com' not in text
        assert 'queue.json' not in archive.namelist()

def test_auto_recovery_respects_setting_and_export_and_user_pause(tmp_path):
    store=JobStore();path=tmp_path/'queue.json';store.enable_persistence(path)
    download=make(store,tmp_path,status='paused',interrupted=True)
    manual=make(store,tmp_path,status='paused')
    export=make(store,tmp_path,status='paused',interrupted=True,purpose='clip')
    assert store.recover_interrupted(False)==[]
    recovered=store.recover_interrupted(True)
    assert [j.id for j in recovered]==[download.id] and recovered[0].status=='queued'
    assert store.get(manual.id).status=='paused' and store.get(export.id).status=='paused'
    assert store.recover_interrupted(True)==[]

def test_diagnostics_include_bounded_redacted_failed_worker(tmp_path,monkeypatch):
    import app.support as support
    store=JobStore();job=make(store,tmp_path,status='failed',error='worker stopped unexpectedly')
    work=Path(job.directory);work.mkdir();(work/'worker.log').write_text('x'*200000+'\nhttps://example.com/private?token=secret\npassword=secret\n')
    context=SimpleNamespace(jobs=store,settings=SimpleNamespace(get=lambda:{'download_directory':str(tmp_path)}),_tool=lambda name:'available')
    monkeypatch.setattr(support,'context',context);monkeypatch.setattr(support,'CONFIG_ROOT',tmp_path)
    # Consume the StreamingResponse body without an HTTP server.
    import asyncio
    async def collect():return b''.join([chunk async for chunk in support.bundle().body_iterator])
    with zipfile.ZipFile(io.BytesIO(asyncio.run(collect()))) as archive:
        text=archive.read('workers/1/worker.log').decode()
        assert len(text)<170000 and 'secret' not in text and 'example.com' not in text
        assert not any('queue' in name or 'cookie' in name for name in archive.namelist())
