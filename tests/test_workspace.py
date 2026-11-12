import sys
from pathlib import Path
from unittest.mock import patch
import json
import subprocess
import time
from threading import Event
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.jobs import JobStore,jobs
from app.main import app
import app.main as main
import app.workspace as workspace
from app.media_library import MediaLibrary
from app.converter import PRESETS,probe_media,run_conversion
from fastapi.testclient import TestClient
client=TestClient(app)

@pytest.fixture
def sample(tmp_path):
    source=tmp_path/'original.mp4'
    result=subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=30','-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','2','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-y',str(source)],capture_output=True)
    assert result.returncode==0,result.stderr
    return source

@pytest.fixture
def catalogue(tmp_path,monkeypatch):
    library=MediaLibrary(tmp_path/'library.sqlite3')
    import app.media_library as module
    monkeypatch.setattr(module,'library',library)
    monkeypatch.setattr(workspace,'library',library)
    monkeypatch.setattr(workspace,'CONFIG_ROOT',tmp_path/'state')
    monkeypatch.setattr(main.executor,'paused',True)
    return library

@pytest.mark.parametrize('preset',['device','compact','webm','mp3','m4a','wav','flac','prores','dnxhr','remux'])
def test_real_conversion_preserves_original(sample,tmp_path,catalogue,preset):
    original=sample.read_bytes();p=PRESETS[preset]
    job=jobs.create(url='local://sample',kind=p['kind'],container=p['container'],quality='best',directory=str(tmp_path/preset),destination=str(tmp_path/'outputs'),source_filename=str(sample),purpose='conversion',conversion_options={'preset':preset},title='Test source')
    run_conversion(job)
    assert job.status=='completed',job.error
    output=Path(job.filename);assert output.exists() and output!=sample
    data=probe_media(output);assert data['duration']==pytest.approx(2,abs=.15)
    assert sample.read_bytes()==original
    assert any(record['path']==str(output) for record in catalogue.list())

def test_real_trim_resize_rotation_and_sample(sample,tmp_path,catalogue):
    job=jobs.create(url='local://sample',kind='video',container='mp4',quality='best',directory=str(tmp_path/'work'),destination=str(tmp_path/'outputs'),source_filename=str(sample),purpose='conversion_sample',conversion_options={'preset':'device','start':.25,'finish':1.25,'height':144,'fps':24,'rotate':90,'sample':True})
    run_conversion(job);assert job.status=='completed',job.error
    data=probe_media(job.filename)
    assert data['duration']==pytest.approx(1,abs=.12) and data['height']==144 and data['fps']==24
    assert catalogue.list()==[]

def test_conversion_cancel_preserves_original(sample,tmp_path,catalogue):
    job=jobs.create(url='local://sample',kind='audio',container='wav',quality='best',directory=str(tmp_path/'work'),source_filename=str(sample),purpose='conversion',conversion_options={'preset':'wav'})
    job.cancel_event.set();run_conversion(job)
    assert job.status=='cancelled' and sample.exists() and not job.filename

def test_library_survives_queue_clear_and_original_deletion_rejected(sample,catalogue,tmp_path):
    record=catalogue.add(sample,owned=False)
    assert client.post(f'/api/library/{record["id"]}/remove',json={'delete_file':True}).status_code==400
    assert sample.exists()
    client.post('/api/queue/clear',json={'include_active':False})
    assert client.get('/api/library').json()['files'][0]['id']==record['id']
    catalogue.remove(record['id']);assert sample.exists() and catalogue.list()==[]
    assert MediaLibrary(tmp_path/'library.sqlite3').list()==[]

def test_library_byte_range(sample,catalogue):
    record=catalogue.add(sample)
    r=client.get(f'/api/library/{record["id"]}/file',headers={'Range':'bytes=0-15'})
    assert r.status_code==206 and r.content==sample.read_bytes()[:16]

def test_converter_batch_atomic_and_validation(sample,catalogue):
    record=catalogue.add(sample)
    with patch.object(main.executor,'submit') as submit:
        assert client.post('/api/convert',json={'media_ids':[record['id'],'missing'],'preset':'wav'}).status_code==404
        submit.assert_not_called()
        r=client.post('/api/convert',json={'media_ids':[record['id'],record['id']],'preset':'wav'})
        assert r.status_code==202 and len(r.json()['jobs'])==1 and submit.call_count==1
    for options in [{'preset':'unknown'},{'preset':'wav','rotate':45},{'preset':'device','fps':0},{'preset':'device','start':3,'finish':1},{'preset':'device','container':'mp3'},{'preset':'remux','container':'../../bad'}]:
        assert client.post('/api/convert',json={'media_ids':[record['id']],**options}).status_code==422

def test_converter_preset_persistence(catalogue):
    r=client.post('/api/convert/presets',json={'name':'My WAV','options':{'preset':'wav','normalize':True}})
    assert r.status_code==200
    assert client.get('/api/convert/presets').json()['custom'][0]['options']['normalize'] is True

def test_native_import_requires_token(sample,catalogue):
    payload={'paths':[str(sample)]}
    assert client.post('/api/native/import',json=payload).status_code==403
    with patch.dict('os.environ',{'DROPDL_NATIVE_TOKEN':'private'}):
        r=client.post('/api/native/import',json=payload,headers={'X-DropDL-Native-Token':'private'})
    assert r.status_code==200 and r.json()['files'][0]['owned'] is False

def test_paused_tasks_survive_clear_and_resume(tmp_path):
    store=JobStore();store.enable_persistence(tmp_path/'queue.json')
    job=store.create(url='https://example.com',kind='video',container='mp4',quality='720p',directory=str(tmp_path));store.update(job.id,status='paused');store.clear()
    assert store.get(job.id) is job
    new=store.retry(job.id);assert new.id==job.id and new.attempt==2 and not new.cancel_event.is_set()

def test_priority_scheduler_and_future_start(tmp_path,monkeypatch):
    import app.scheduler as module
    store=JobStore();monkeypatch.setattr(module,'jobs',store)
    release=Event();finished=Event();order=[]
    def execute(job):
        order.append(job.title)
        if job.title=='first':release.wait(3)
        store.update(job.id,status='completed')
        if job.title=='high':finished.set()
    scheduler=module.Scheduler(1,lambda:{'global_speed_limit_kbps':256},execute)
    try:
        def make(title,priority=0,scheduled_at=0):return store.create(url='https://example.com',kind='video',container='mp4',quality='720p',directory=str(tmp_path),title=title,priority=priority,scheduled_at=scheduled_at)
        first=make('first');scheduler.submit(None,first)
        deadline=time.time()+2
        while not order and time.time()<deadline:time.sleep(.02)
        scheduler.submit(None,make('low',-1));scheduler.submit(None,make('future',500,time.time()+3600));scheduler.submit(None,make('high',100));release.set()
        assert finished.wait(2);assert order[:2]==['first','high'] and 'future' not in order
        assert first.speed_limit_kbps==256
    finally:release.set();scheduler.close()

def test_duplicate_identity_and_output_distinction(sample,catalogue):
    from app.duplicates import existing_keys,output_key
    catalogue.add(sample,url='https://youtu.be/abc?si=one',owned=True,kind='video',metadata={'purpose':'download','container':'mp4','quality':'720p'})
    keys=existing_keys()
    assert output_key('https://www.youtube.com/watch?v=abc&list=xyz','video','mp4','720p') in keys
    assert output_key('https://youtube.com/watch?v=abc','audio','mp3','best') not in keys
    assert output_key('https://youtube.com/watch?v=abc','video','mp4','1080p') not in keys

def test_real_isolated_download_from_local_source(sample,tmp_path,catalogue):
    from app.media_worker import run_isolated
    job=jobs.create(url='https://example.com/video',kind='video',container='mp4',quality='best',directory=str(tmp_path/'worker'),destination=str(tmp_path/'output'),source_filename=str(sample),clip_start=.25,clip_end=1.25)
    run_isolated(job)
    assert job.status=='completed',job.error
    assert probe_media(job.filename)['duration']==pytest.approx(1,abs=.15) and sample.exists()
    assert catalogue.list()

def test_worker_crash_keeps_api_healthy(tmp_path,catalogue):
    from app.media_worker import run_isolated
    job=jobs.create(url='https://example.com/video',kind='video',container='mp4',quality='best',directory=str(tmp_path/'worker'))
    with patch('app.media_worker.subprocess.Popen') as popen:
        popen.return_value.poll.return_value=-11;popen.return_value.returncode=-11
        run_isolated(job)
    assert job.status=='failed' and 'worker stopped' in job.error
    assert client.get('/api/health').status_code==200

def test_storage_cleanup_keeps_paused_partials_and_registered_media(tmp_path,catalogue):
    work=tmp_path/'state'/'work';paused=work/'paused';stale=work/'stale';owned=work/'owned'
    for path in [paused,stale,owned]:path.mkdir(parents=True);(path/'file.mp4').write_bytes(b'media')
    job=jobs.create(url='https://example.com',kind='video',container='mp4',quality='best',directory=str(paused));jobs.update(job.id,status='paused')
    catalogue.add(owned/'file.mp4',owned=True)
    r=client.post('/api/storage/cleanup')
    assert r.status_code==200 and paused.exists() and owned.exists() and not stale.exists()

def test_browser_pairing_expiry_and_link_authorization(tmp_path,monkeypatch):
    import app.browser_link as module
    monkeypatch.setattr(module,'CONFIG_ROOT',tmp_path)
    monkeypatch.setattr(module,'failures',[])
    code=client.post('/api/browser/pair-code').json()['code']
    assert client.post('/api/browser/pair',json={'code':'badbad'}).status_code==403
    result=client.post('/api/browser/pair',json={'code':code});assert result.status_code==200
    assert client.post('/api/browser/inbox',json={'url':'https://example.com/video'}).status_code==403
    with patch('app.main.checked_url',side_effect=lambda u:u):
        r=client.post('/api/browser/inbox',json={'url':'https://example.com/video','title':'Example'},headers={'Authorization':'Bearer '+result.json()['token']})
    assert r.status_code==200 and client.get('/api/browser/inbox').json()['links'][0]['title']=='Example'
    client.post('/api/browser/unpair')
    assert client.post('/api/browser/inbox',json={'url':'https://example.com/video'},headers={'Authorization':'Bearer '+result.json()['token']}).status_code==403

def test_subscription_filters_and_duplicate_options(tmp_path,monkeypatch):
    import app.subscriptions as module
    monkeypatch.setattr(module,'CONFIG_ROOT',tmp_path)
    with patch('app.main.checked_url',side_effect=lambda u:u):
        r=client.post('/api/subscriptions',json={'name':'Editing lessons','url':'https://example.com/playlist','title_contains':'edit','max_duration':60})
    assert r.status_code==200
    row=r.json()
    data={'entries':[{'url':'https://example.com/a','title':'Edit in Premiere','duration':30},{'url':'https://example.com/b','title':'Edit long film','duration':90},{'url':'https://example.com/c','title':'Other topic','duration':30}]}
    with patch('app.main.checked_url',side_effect=lambda u:u),patch('app.main.inspect_playlist',return_value=data),patch('app.main.batch') as batch:
        assert module.check(row)==1
        payload=batch.call_args.args[0]
        assert payload.urls==['https://example.com/a'] and payload.skip_duplicates
    assert client.post(f'/api/subscriptions/{row["id"]}/toggle',json={'enabled':False}).json()['enabled'] is False
    assert client.post(f'/api/subscriptions/{row["id"]}/remove').status_code==200
    assert client.get('/api/subscriptions').json()['subscriptions']==[]

def test_real_waveform_and_timeline_frame(sample,tmp_path,catalogue):
    job=jobs.create(url='local://sample',kind='video',container='mp4',quality='best',directory=str(tmp_path))
    jobs.update(job.id,status='completed',filename=str(sample))
    frame=client.get(f'/api/jobs/{job.id}/frame/4');assert frame.status_code==200 and frame.content[:2]==b'\xff\xd8'
    wave=client.get(f'/api/jobs/{job.id}/waveform');assert wave.status_code==200 and wave.content[:8]==b'\x89PNG\r\n\x1a\n'
    assert client.get(f'/api/jobs/{job.id}/frame/8').status_code==400
    assert client.get(f'/api/jobs/{job.id}/media-info').json()['fps']==30

def test_disk_full_rejects_batch_before_queue_commit(tmp_path):
    from collections import namedtuple
    usage=namedtuple('Usage','total used free')(100000000,99999999,1)
    with patch('app.main.checked_batch_urls',return_value=['https://example.com/a']),patch('shutil.disk_usage',return_value=usage),patch.object(main.executor,'submit') as submit:
        assert client.post('/api/batch',json={'urls':['https://example.com/a']}).status_code==507
        submit.assert_not_called()

def test_removed_reference_is_not_resurrected_by_queue_migration(sample,catalogue,tmp_path):
    from app.media_library import remember_job
    store=JobStore();job=store.create(url='https://example.com/a',kind='video',container='mp4',quality='best',directory=str(tmp_path))
    job.filename=str(sample);job.status='completed';remember_job(job)
    record=catalogue.list()[0];catalogue.remove(record['id']);remember_job(job)
    assert catalogue.list()==[] and sample.exists()
    catalogue.add(sample);assert catalogue.list()

def test_private_cookie_import_is_native_only(tmp_path,monkeypatch):
    monkeypatch.setattr(workspace,'CONFIG_ROOT',tmp_path/'state')
    source=tmp_path/'cookies.txt';source.write_text('# Netscape HTTP Cookie File\n')
    assert client.post('/api/native/cookies',json={'path':str(source)}).status_code==403
    with patch.dict('os.environ',{'DROPDL_NATIVE_TOKEN':'private'}):
        assert client.post('/api/native/cookies',json={'path':str(source)},headers={'X-DropDL-Native-Token':'private'}).status_code==200
    assert client.get('/api/cookies').json()['configured']
    assert client.post('/api/cookies/remove').status_code==200
    assert not (tmp_path/'state'/'cookies.txt').exists()

def test_transient_failure_schedules_same_row_retry(tmp_path,monkeypatch):
    import app.scheduler as module
    store=JobStore();monkeypatch.setattr(module,'jobs',store)
    original=store.create(url='https://example.com/video',kind='video',container='mp4',quality='best',directory=str(tmp_path))
    def execute(job):store.update(job.id,status='failed',error='Connection reset by peer')
    scheduler=module.Scheduler(1,lambda:{},execute)
    try:
        scheduler.submit(None,original);deadline=time.time()+2
        while store.get(original.id).attempt==1 and time.time()<deadline:time.sleep(.02)
        replacement=store.get(original.id)
        assert replacement.id==original.id and replacement.attempt==2 and replacement.status=='queued'
        assert replacement.scheduled_at>time.time() and replacement.auto_retries==1
        assert len(store.list())==1
    finally:scheduler.close()

def test_progress_snapshot_survives_windows_file_lock(tmp_path):
    from app.media_worker import publish_snapshot
    job=jobs.create(url='https://example.com/video',kind='video',container='mp4',quality='best',directory=str(tmp_path))
    status=tmp_path/'worker-status.json'
    original=Path.replace
    attempts=[]
    def replace(path,target):
        if path==status.with_suffix('.tmp'):
            attempts.append(path)
            if len(attempts)==1:raise PermissionError('Windows sharing violation')
        return original(path,target)
    with patch.object(Path,'replace',replace):
        jobs.update(job.id,status='downloading',percent=10,downloaded_bytes=100,total_bytes=1000)
        assert publish_snapshot(job,status) is False
        jobs.update(job.id,percent=35,downloaded_bytes=350)
        assert publish_snapshot(job,status) is True
    assert json.loads(status.read_text())['percent']==35

def test_open_downloaded_uses_registered_media_path_only(tmp_path):
    from app.native import NativeAPI
    media=tmp_path/'video.mp4';media.write_bytes(b'media')
    record={'status':'completed','output_path':str(media)}
    api=NativeAPI(None,lambda identity:record if identity=='job-id' else None)
    with patch('app.native.sys.platform','win32'),patch('app.native.os.startfile',create=True) as start:
        assert api.open_downloaded('job-id') is True
        start.assert_called_once_with(str(media))
        with pytest.raises(ValueError):api.open_downloaded(str(media))
        record['status']='downloading'
        with pytest.raises(ValueError):api.open_downloaded('job-id')
        record['status']='completed';record['output_path']=str(tmp_path/'launcher.exe')
        (tmp_path/'launcher.exe').write_bytes(b'not-media')
        with pytest.raises(ValueError):api.open_downloaded('job-id')

def test_icon_has_classic_windows_bitmap_frames():
    import struct
    data=(Path(__file__).resolve().parents[1]/'installer'/'dropdl.ico').read_bytes()
    assert struct.unpack_from('<HH',data,0)==(0,1)
    count=struct.unpack_from('<H',data,4)[0];assert count>=6
    for index in range(count):
        offset=struct.unpack_from('<I',data,6+16*index+12)[0]
        assert struct.unpack_from('<I',data,offset)[0]==40


def test_live_download_progress_reaches_parent(sample,tmp_path,catalogue):
    from app.media_worker import run_isolated
    from http.server import HTTPServer,BaseHTTPRequestHandler
    from threading import Thread
    data=sample.read_bytes()
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200);self.send_header('Content-Type','video/mp4');self.send_header('Content-Length',str(len(data)));self.end_headers()
            try:
                for offset in range(0,len(data),1024):self.wfile.write(data[offset:offset+1024]);self.wfile.flush();time.sleep(.025)
            except (BrokenPipeError,ConnectionResetError):pass
        def log_message(self,*args):pass
    server=HTTPServer(('127.0.0.1',0),Handler);Thread(target=server.serve_forever,daemon=True).start()
    job=jobs.create(url=f'http://127.0.0.1:{server.server_port}/test.mp4',kind='video',container='mp4',quality='best',directory=str(tmp_path/'worker'),destination=str(tmp_path/'output'))
    observed=[]
    worker=Thread(target=run_isolated,args=(job,));worker.start();deadline=time.time()+25
    try:
        while worker.is_alive() and time.time()<deadline:
            observed.append((job.status,job.percent,job.downloaded_bytes));time.sleep(.05)
        worker.join(timeout=1)
        assert not worker.is_alive(),'Download worker did not finish'
        assert job.status=='completed',job.error
        assert any(status=='downloading' and 0<percent<100 and downloaded for status,percent,downloaded in observed),observed
        assert Path(job.filename).is_file()
    finally:
        job.cancel_event.set();server.shutdown();server.server_close();worker.join(timeout=5)

def test_icon_is_applied_to_native_form_after_creation(monkeypatch):
    import app.desktop_host as host
    import types
    monkeypatch.setattr(host,'os',types.SimpleNamespace(name='nt'))
    monkeypatch.setitem(sys.modules,'System',types.SimpleNamespace(Action=lambda callback:callback))
    monkeypatch.setitem(sys.modules,'System.Drawing',types.SimpleNamespace(Icon=lambda path:('native-icon',path)))
    invoked=[]
    form=types.SimpleNamespace(InvokeRequired=True,Icon=None,ShowIcon=False)
    def invoke(callback):invoked.append(True);callback()
    form.Invoke=invoke;window=types.SimpleNamespace(native=form)
    host.apply_windows_icon(window)
    assert invoked==[True] and form.ShowIcon
    assert form.Icon==window._dropdl_native_icon
    assert form.Icon[1].endswith('dropdl.ico')


def test_imported_clip_preview_does_not_queue_or_modify_original(sample,catalogue):
    record=catalogue.add(sample);original=sample.read_bytes()
    with patch.object(main.executor,'submit') as downloads,patch.object(main.editor,'submit') as edits:
        result=client.post(f'/api/library/{record["id"]}/preview')
        assert result.status_code==202 and result.json()['preview_ready']
        job=jobs.get(result.json()['id'])
        assert job.status=='completed' and job.filename==str(sample)
        assert client.get(f'/api/jobs/{job.id}/file?preview=true').content==original
        again=client.post(f'/api/library/{record["id"]}/preview')
        assert again.json()['id']==job.id
        downloads.assert_not_called();edits.assert_not_called()
    assert sample.read_bytes()==original


def test_real_editor_montage_speed_color_crop_fades(sample,tmp_path):
    from app.editor import build_edit_command
    original=sample.read_bytes();metadata=probe_media(sample)
    project={'segments':[{'start':0,'end':.8,'speed':.5},{'start':1,'end':1.8,'speed':2}], 'ratio':'1:1','rotate':90,'flip':True,'brightness':.1,'contrast':1.1,'saturation':.8,'volume':.5,'fadeIn':.2,'fadeOut':.2}
    target=tmp_path/'edited.mp4'
    result=subprocess.run(build_edit_command(sample,target,project,metadata),capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr
    output=probe_media(target)
    assert output['width']==output['height'] and output['video_codec']=='h264' and output['audio_codec']=='aac'
    assert output['duration']==pytest.approx(2,abs=.15)
    assert sample.read_bytes()==original


def test_editor_export_validation_and_edit_worker(sample,catalogue):
    from app.editor import build_edit_command
    source=jobs.create(url='local://editor-source',kind='video',container='mp4',quality='best',directory=str(sample.parent),status='completed',filename=str(sample),title='Local edit')
    project={'segments':[{'start':0,'end':1,'speed':1}]}
    with patch.object(main.editor,'submit') as edit,patch.object(main.executor,'submit') as download:
        result=client.post('/api/editor/export',json={'source_job_id':source.id,'project':project})
        assert result.status_code==202
        item=jobs.get(result.json()['id']);assert item.purpose=='clip' and all(item.conversion_options['edit']['segments'][0][k]==v for k,v in project['segments'][0].items())
        edit.assert_called_once();download.assert_not_called()
        client.post(f'/api/jobs/{item.id}/cancel')
        for bad in [{**project,'rotate':45},{**project,'ratio':'invalid'},{'segments':[{'start':0,'end':20,'speed':1}]},{'segments':[{'start':0,'end':1,'speed':0}]},{'segments':[{'start':1,'end':0,'speed':1}]}]:
            assert client.post('/api/editor/export',json={'source_job_id':source.id,'project':bad}).status_code==422


def test_native_editor_is_separate_validated_and_reused(tmp_path):
    from app.native import NativeAPI
    from app.settings import Settings
    from unittest.mock import MagicMock
    import webview
    source=tmp_path/'source.mp4';source.write_bytes(b'local media')
    record={'id':'source-id','status':'completed','output_path':str(source)}
    bridge=NativeAPI(Settings(tmp_path/'preferences.json',tmp_path/'downloads'),lambda identity:record if identity=='source-id' else None)
    bridge._window=MagicMock();bridge._window.get_current_url.return_value='http://127.0.0.1:17321/'
    with patch.object(webview,'create_window') as create:
        assert bridge.open_editor('source-id','ar')
        assert create.call_args.args[1]=='http://127.0.0.1:17321/?editor=source-id&lang=ar'
        assert create.call_args.kwargs['width']==1440 and create.call_args.kwargs['min_size']==(1000,720)
        assert {f.__name__ for f in create.return_value.expose.call_args.args}=={'open_downloaded','open_library','open_folder','close_editor','choose_media_files','export_diagnostics','choose_export_folder'}
        assert bridge.open_editor('source-id','ar');assert create.call_count==1
        with pytest.raises(ValueError):bridge.open_editor(str(source),'en')
        with pytest.raises(ValueError):bridge.open_editor('source-id','xx')

# 0.15 catalogue migration and durable organization.
def test_library_015_migrates_without_replacing_existing_records(sample,tmp_path):
    import sqlite3
    path=tmp_path/'old.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE media (id TEXT PRIMARY KEY,path TEXT UNIQUE,title TEXT,kind TEXT,site TEXT,url TEXT,owned INTEGER,created REAL,metadata TEXT)')
        db.execute('INSERT INTO media VALUES (?,?,?,?,?,?,?,?,?)',('legacy',str(sample),'Old title','video','Local','',0,123,'{}'))
    lib=MediaLibrary(path);record=lib.list()[0];assert record['id']=='legacy' and not record['favorite'] and record['collection_id'] is None
    group=lib.save_collection('مشروع');lib.organize(['legacy'],favorite=True,collection_id=group['id'],change_collection=True,title='My title')
    reopened=MediaLibrary(path);assert reopened.get('legacy')['title']=='My title' and reopened.get('legacy')['favorite']
    reopened.add(sample,title='Automatic task title');assert reopened.get('legacy')['title']=='My title'

def test_collections_batch_atomicity_and_removal(sample,catalogue):
    record=catalogue.add(sample);group=client.post('/api/collections',json={'name':'Project'}).json()
    assert client.post('/api/collections',json={'name':' project '}).status_code==400
    assert client.post('/api/collections',json={'name':'   '}).status_code==400
    result=client.post('/api/library/selection/organize',json={'ids':[record['id'],record['id']],'collection_id':group['id'],'favorite':True});assert result.status_code==200 and len(result.json()['files'])==1
    assert client.get('/api/collections').json()['collections'][0]['count']==1
    assert client.post('/api/library/selection/organize',json={'ids':[record['id'],'missing'],'favorite':False}).status_code==400
    assert catalogue.get(record['id'])['favorite']
    assert client.post('/api/library/selection/organize',json={'ids':[record['id']],'collection_id':'missing'}).status_code==400
    assert catalogue.get(record['id'])['collection_id']==group['id']
    assert client.post('/api/collections/'+group['id']+'/rename',json={'name':'Renamed'}).status_code==200
    assert catalogue.get(record['id'])['collection_name']=='Renamed'
    assert client.post('/api/collections/'+group['id']+'/remove').status_code==200
    assert catalogue.get(record['id'])['collection_id'] is None and catalogue.get(record['id'])['favorite'] and sample.exists()
    catalogue.remove(record['id']);assert sample.exists()
    with catalogue.connection() as db:assert db.execute('SELECT COUNT(*) FROM media_notes').fetchone()[0]==0

def test_library_info_is_lazy_and_cached(sample,catalogue):
    record=catalogue.add(sample)
    with patch.object(workspace,'probe_media',wraps=probe_media) as probe:
        client.get('/api/library');assert probe.call_count==0
        response=client.get('/api/library/'+record['id']+'/info');assert response.status_code==200 and probe.call_count==1
    assert response.json()['info']['duration']==pytest.approx(2,abs=.1)
    assert catalogue.get(record['id'])['metadata']['video_codec']=='h264'
    sample.unlink();assert client.get('/api/library/'+record['id']+'/info').status_code==410

def test_native_relink_preserves_identity_and_protects_external_original(sample,catalogue,tmp_path):
    record=catalogue.add(sample,owned=True,metadata={'job_id':'old-job','purpose':'download'});group=catalogue.save_collection('Favorite collection')
    catalogue.organize([record['id']],favorite=True,collection_id=group['id'],change_collection=True,title='Custom title')
    moved=tmp_path/'moved.mp4';sample.rename(moved)
    url='/api/native/library/'+record['id']+'/relink'
    assert client.post(url,json={'path':str(moved)}).status_code==403
    with patch.dict('os.environ',{'DROPDL_NATIVE_TOKEN':'private'}):
        response=client.post(url,json={'path':str(moved)},headers={'X-DropDL-Native-Token':'private'})
        assert response.status_code==200
        data=response.json();assert data['id']==record['id'] and data['title']=='Custom title' and data['favorite'] and data['collection_id']==group['id']
        assert not data['owned'] and 'job_id' not in data['metadata'] and data['exists']
        assert client.post(url,json={'path':str(moved)},headers={'X-DropDL-Native-Token':'private'}).status_code==400
    assert client.post('/api/library/'+record['id']+'/remove',json={'delete_file':True}).status_code==400 and moved.exists()
    assert client.post('/api/library/'+record['id']+'/preview').status_code==202

def test_relink_rejects_non_media_and_duplicate_entry(sample,catalogue,tmp_path):
    record=catalogue.add(sample);duplicate=tmp_path/'another.mp4';duplicate.write_bytes(sample.read_bytes());catalogue.add(duplicate);sample.unlink()
    fake=tmp_path/'fake.mp4';fake.write_text('not media')
    with patch.dict('os.environ',{'DROPDL_NATIVE_TOKEN':'private'}):
        for path in (fake,duplicate):
            assert client.post('/api/native/library/'+record['id']+'/relink',json={'path':str(path)},headers={'X-DropDL-Native-Token':'private'}).status_code==400
    assert not catalogue.get(record['id'])['exists'] and duplicate.exists()

def test_native_locate_cancel_and_reveal_registered_file(sample):
    from app.native import NativeAPI
    from unittest.mock import MagicMock
    import types
    settings=MagicMock();settings.get_media.return_value={'exists':False,'path':str(sample)}
    bridge=NativeAPI(settings);bridge._window=MagicMock();bridge._window.create_file_dialog.return_value=None
    module=types.SimpleNamespace(FileDialog=types.SimpleNamespace(OPEN=1))
    with patch.dict(sys.modules,{'webview':module}):assert bridge.locate_media('id') is None
    settings.relink_media.assert_not_called()
    bridge._window.create_file_dialog.return_value=[str(sample)]
    with patch.dict(sys.modules,{'webview':module}):bridge.locate_media('id')
    settings.relink_media.assert_called_once_with('id',str(sample.resolve()))
    settings.get_media.return_value={'exists':True,'path':str(sample)}
    with patch('app.native.sys.platform','win32'),patch('app.native.subprocess.Popen') as launch:
        assert bridge.reveal_library('id');assert launch.call_args.args[0]==['explorer.exe','/select,',str(sample)]
