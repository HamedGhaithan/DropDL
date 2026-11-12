import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from fastapi.testclient import TestClient
from app.main import app
from app.jobs import jobs
from app.downloader import run_download, _format_selector

client = TestClient(app)

def test_health():
    r = client.get('/api/health')
    assert r.status_code == 200
    assert isinstance(r.json()['ffmpeg'], bool)

def test_invalid_urls():
    for url in ['file:///etc/passwd', 'http://127.0.0.1/test', 'http://192.168.1.1/test']:
        assert client.post('/api/info', json={'url': url}).status_code == 400

def test_format_validation():
    with patch('app.main.checked_url', return_value='https://example.com/video'):
        r = client.post('/api/download', json={'url': 'https://example.com/video', 'kind': 'audio', 'container': 'mp4'})
        assert r.status_code == 400

def test_inspection_contract():
    with patch('app.main.checked_url', return_value='https://example.com/video'), patch('app.main.inspect_url', return_value={'title': 'Test', 'heights': [1080], 'suggested_qualities': ['1080p']}):
        r = client.post('/api/info', json={'url': 'https://example.com/video'})
        assert r.status_code == 200 and r.json()['heights'] == [1080]

def test_cancelled_queued_job_does_not_download(tmp_path):
    job = jobs.create(url='https://example.com', kind='video', container='mp4', quality='1080p', directory=str(tmp_path))
    assert client.post(f'/api/jobs/{job.id}/cancel').status_code == 200
    with patch('app.downloader.YoutubeDL') as downloader:
        run_download(job)
        downloader.assert_not_called()
    assert job.status == 'cancelled'

def test_missing_ffmpeg_is_actionable(tmp_path):
    job = jobs.create(url='https://example.com', kind='audio', container='mp3', quality='best', directory=str(tmp_path))
    with patch('app.downloader._ffmpeg_location', return_value=None):
        run_download(job)
    assert job.status == 'failed' and 'FFmpeg' in job.error

def test_file_response_and_not_ready(tmp_path):
    job = jobs.create(url='https://example.com', kind='video', container='mp4', quality='720p', directory=str(tmp_path))
    assert client.get(f'/api/jobs/{job.id}/file').status_code == 409
    output = tmp_path / 'clip.mp4'
    output.write_bytes(b'test-media')
    jobs.update(job.id, status='completed', filename=str(output))
    r = client.get(f'/api/jobs/{job.id}/file')
    assert r.content == b'test-media' and 'clip.mp4' in r.headers['content-disposition']

def test_quality_ceiling():
    assert '[height<=720]' in _format_selector('video', '720p')
    assert _format_selector('audio', 'best') == 'bestaudio/best'

import io
import json
import subprocess
import time
import zipfile
import pytest
from app.downloader import inspect_playlist, trim_file


def test_batch_both_creates_two_independent_jobs_per_unique_url(tmp_path):
    with patch('app.main.checked_batch_urls', side_effect=lambda urls:list(dict.fromkeys(u.strip() for u in urls))), patch('app.main.executor.submit') as submit, patch('app.main.DOWNLOAD_ROOT', tmp_path):
        response = client.post('/api/batch', json={'urls':['https://example.com/a','https://example.com/b','https://example.com/a'], 'mode':'both', 'clip_start':1, 'clip_end':2.5})
    assert response.status_code == 202
    items = response.json()['jobs']
    assert [j['kind'] for j in items] == ['video','audio','video','audio']
    assert submit.call_count == 4 and len({j['id'] for j in items}) == 4
    assert all(j['clip_start'] == 1 and j['clip_end'] == 2.5 for j in items)
    assert len({j['batch_id'] for j in items}) == 1


def test_batch_invalid_destination_is_atomic():
    def check(u):
        if 'bad' in u:
            from fastapi import HTTPException
            raise HTTPException(400, 'Bad destination')
        return u
    with patch('app.main.checked_batch_urls', side_effect=lambda urls:[check(u) for u in urls]), patch('app.main.executor.submit') as submit:
        response = client.post('/api/batch', json={'urls':['https://example.com/a','https://bad.example/a']})
    assert response.status_code == 400
    submit.assert_not_called()


@pytest.mark.parametrize('extra', [{'clip_start':5,'clip_end':2}, {'clip_start':2}, {'clip_start':-1,'clip_end':5}, {'clip_start':0,'clip_end':0}])
def test_invalid_clip_ranges_rejected(extra):
    assert client.post('/api/batch', json={'urls':['https://example.com/a'],**extra}).status_code == 422


def test_playlist_flat_expansion_and_pagination():
    fake = {'title':'A playlist','playlist_count':3,'entries':[{'id':'abc','url':'abc','ie_key':'Youtube','title':'One'}, None]}
    with patch('app.downloader.YoutubeDL') as ydl:
        instance = ydl.return_value.__enter__.return_value
        instance.extract_info.return_value = fake
        instance.sanitize_info.side_effect = lambda info:info
        result = inspect_playlist('https://example.com/list',1,2)
        options = ydl.call_args.args[0]
    assert result['entries'][0]['url'] == 'https://www.youtube.com/watch?v=abc'
    assert result['entries'][1]['url'] is None
    assert result['has_more'] and result['next_start'] == 3
    assert options['playlistend'] == 2 and options['noplaylist'] is False


@pytest.fixture(scope='module')
def sample_media(tmp_path_factory):
    directory = tmp_path_factory.mktemp('ffmpeg-media')
    source = directory / 'sample.mp4'
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','lavfi','-i','testsrc2=size=160x90:rate=25','-f','lavfi','-i','sine=frequency=440:sample_rate=44100','-t','4','-c:v','libx264','-c:a','aac',str(source)],check=True)
    return source


def duration_of(path):
    result = subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','json',str(path)],capture_output=True,text=True,check=True)
    return float(json.loads(result.stdout)['format']['duration'])


def test_real_ffmpeg_exact_clip_and_source_preservation(tmp_path, sample_media):
    job = jobs.create(url='https://example.com/a',kind='video',container='mp4',quality='best',directory=str(tmp_path),source_filename=str(sample_media),clip_start=1,clip_end=2.2)
    run_download(job)
    assert job.status == 'completed',job.error
    assert abs(duration_of(job.filename) - 1.2) < .15
    assert sample_media.exists()
    assert not list(tmp_path.glob('*.tmp.*'))


def test_real_dual_clip_tasks_and_zip(tmp_path, sample_media):
    source = jobs.create(url='https://example.com/a',kind='video',container='mp4',quality='best',directory=str(sample_media.parent))
    jobs.update(source.id,status='completed',filename=str(sample_media),title='Test clip source')
    with patch('app.main.DOWNLOAD_ROOT',tmp_path):
        response=client.post(f'/api/jobs/{source.id}/clip',json={'mode':'both','clip_start':.5,'clip_end':2,'audio_container':'mp3'})
        assert response.status_code == 202,response.text
        items=response.json()['jobs']
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            actual=[jobs.get(j['id']) for j in items]
            if all(j.status in {'completed','failed','cancelled'} for j in actual):break
            time.sleep(.1)
        assert all(j.status=='completed' for j in actual),[(j.status,j.error) for j in actual]
        assert {Path(j.filename).suffix for j in actual} == {'.mp4','.mp3'}
        assert all(abs(duration_of(j.filename)-1.5)<.15 for j in actual)
        archive=client.get(f'/api/batches/{response.json()["batch_id"]}/archive')
        assert archive.status_code==200
        with zipfile.ZipFile(io.BytesIO(archive.content)) as zipped:
            assert len(zipped.namelist())==2 and any(n.endswith('.mp3') for n in zipped.namelist())
        assert not list((tmp_path/'_archives').glob('*.zip'))
    assert sample_media.exists()


def test_clip_beyond_duration_fails_without_destroying_source(tmp_path,sample_media):
    job=jobs.create(url='https://example.com/a',kind='audio',container='m4a',quality='best',directory=str(tmp_path),source_filename=str(sample_media),clip_start=3,clip_end=8)
    run_download(job)
    assert job.status=='failed' and 'duration' in job.error
    assert sample_media.exists()


def test_preview_response_supports_range(tmp_path):
    output=tmp_path/'preview.mp4';output.write_bytes(b'0123456789')
    job=jobs.create(url='https://example.com/a',kind='video',container='mp4',quality='best',directory=str(tmp_path))
    jobs.update(job.id,status='completed',filename=str(output))
    response=client.get(f'/api/jobs/{job.id}/file?preview=true',headers={'Range':'bytes=2-5'})
    assert response.status_code==206 and response.content==b'2345'
    assert response.headers['content-type']=='video/mp4' and 'inline' in response.headers['content-disposition']


def test_retry_local_clip_preserves_source_and_range(tmp_path,sample_media):
    old=jobs.create(url='https://example.com/a',kind='video',container='mp4',quality='best',directory=str(tmp_path),source_filename=str(sample_media),clip_start=.2,clip_end=1.2)
    jobs.update(old.id,status='cancelled')
    with patch('app.main.executor.submit'),patch('app.main.DOWNLOAD_ROOT',tmp_path):
        response=client.post(f'/api/jobs/{old.id}/retry')
    assert response.status_code==202
    new=jobs.get(response.json()['id'])
    assert new.source_filename==old.source_filename and new.clip_start==.2 and new.clip_end==1.2
    assert new.id == old.id
    assert new.attempt == 2
    assert old.cancel_event.is_set() and not new.cancel_event.is_set()


def test_preview_request_requires_one_source():
    assert client.post('/api/preview',json={}).status_code==422
    assert client.post('/api/preview',json={'url':'https://example.com/a','source_job_id':'anything'}).status_code==422
    assert client.post('/api/preview',json={'source_job_id':'missing'}).status_code==409


def test_url_preview_queues_unclipped_original_at_chosen_quality(tmp_path):
    with patch('app.main.checked_url',return_value='https://example.com/a'),patch('app.main.executor.submit'),patch('app.main.DOWNLOAD_ROOT',tmp_path):
        response=client.post('/api/preview',json={'url':'https://example.com/a','quality':'2160p'})
    assert response.status_code==202
    job=jobs.get(response.json()['id'])
    assert job.purpose=='preview' and job.quality=='2160p'
    assert job.clip_start is None and job.clip_end is None and job.source_filename is None


def test_real_preview_playback_copy_original_export_and_cache(tmp_path,sample_media):
    original=sample_media.read_bytes()
    source=jobs.create(url='https://example.com/preview',kind='video',container='mp4',quality='1080p',directory=str(sample_media.parent))
    jobs.update(source.id,status='completed',filename=str(sample_media))
    with patch('app.main.DOWNLOAD_ROOT',tmp_path),patch('app.main.executor.submit'),patch('app.main.editor.submit'):
        response=client.post('/api/preview',json={'source_job_id':source.id,'force_transcode':True})
        assert response.status_code==202
        preview=jobs.get(response.json()['id'])
        run_download(preview)
        assert preview.status=='completed',preview.error
        assert preview.filename==str(sample_media) and preview.preview_filename != preview.filename
        assert preview.public()['preview_ready'] is True
        result=subprocess.run(['ffprobe','-v','error','-show_entries','stream=codec_name,width,pix_fmt','-of','json',preview.preview_filename],capture_output=True,text=True,check=True)
        streams=json.loads(result.stdout)['streams']
        assert streams[0]['codec_name']=='h264' and streams[0]['width']<=960 and streams[0]['pix_fmt']=='yuv420p'
        assert any(s['codec_name']=='aac' for s in streams)
        assert abs(duration_of(preview.preview_filename)-duration_of(sample_media))<.1
        playback=client.get(f'/api/jobs/{preview.id}/file?preview=true')
        full=client.get(f'/api/jobs/{preview.id}/file')
        assert playback.content==Path(preview.preview_filename).read_bytes()
        assert full.content==original
        reused=client.post('/api/preview',json={'source_job_id':source.id,'force_transcode':True})
        assert reused.json()['id']==preview.id
        clip_result=client.post(f'/api/jobs/{preview.id}/clip',json={'clip_start':1,'clip_end':2,'mode':'video'})
        exported=jobs.get(clip_result.json()['jobs'][0]['id'])
        assert exported.source_filename==str(sample_media)
        run_download(exported)
        assert exported.status=='completed',exported.error
        assert abs(duration_of(exported.filename)-1)<.1
    assert sample_media.read_bytes()==original


def test_clear_finished_keeps_active_and_files(tmp_path):
    from app.jobs import JobStore
    store = JobStore()
    output = tmp_path / 'saved.mp4'
    output.write_bytes(b'saved video')
    finished = store.create(url='https://example.com', kind='video', container='mp4', quality='best', directory=str(tmp_path))
    store.update(finished.id, status='completed', filename=str(output))
    active = store.create(url='https://example.com', kind='audio', container='mp3', quality='best', directory=str(tmp_path))
    with patch('app.main.jobs', store):
        response = client.post('/api/queue/clear', json={})
    assert response.json() == {'removed': 1, 'stopped': 0, 'remaining': 1}
    assert store.get(finished.id) is None and store.get(active.id) is active
    assert not active.cancel_event.is_set()
    assert output.read_bytes() == b'saved video'


def test_clear_all_cancels_workers_and_empties_queue(tmp_path):
    from app.jobs import JobStore
    store = JobStore()
    queued = store.create(url='https://example.com', kind='video', container='mp4', quality='best', directory=str(tmp_path))
    running = store.create(url='https://example.com', kind='audio', container='mp3', quality='best', directory=str(tmp_path))
    store.update(running.id, status='downloading')
    with patch('app.main.jobs', store):
        response = client.post('/api/queue/clear', json={'include_active': True})
        again = client.post('/api/queue/clear', json={'include_active': True})
    assert response.json() == {'removed': 2, 'stopped': 2, 'remaining': 0}
    assert again.json()['removed'] == 0
    assert queued.cancel_event.is_set() and running.cancel_event.is_set()
    with patch('app.downloader.YoutubeDL') as downloader:
        run_download(queued)
        downloader.assert_not_called()
    assert store.list() == []


def test_same_row_retry_ignores_previous_worker_updates(tmp_path):
    from app.jobs import JobStore
    store=JobStore()
    old=store.create(url='https://example.com',kind='video',container='mp4',quality='best',directory=str(tmp_path),batch_id='batch-original')
    store.update(old.id,status='cancelled')
    new=store.retry(old.id)
    assert new.id==old.id and new.directory==old.directory and new.batch_id=='batch-original'
    assert len(store.list())==1 and new.attempt==2
    assert store.update_attempt(old,status='failed',error='Late old-worker result') is None
    assert new.status=='queued' and new.error is None
    assert store.retry(new.id) is None


def test_persistent_queue_recovers_interrupted_tasks(tmp_path):
    from app.jobs import JobStore
    path=tmp_path/'queue.json'
    store=JobStore();store.enable_persistence(path)
    job=store.create(url='https://example.com',kind='video',container='mp4',quality='best',directory=str(tmp_path))
    store.update(job.id,status='downloading')
    other=JobStore();other.enable_persistence(path)
    loaded=other.get(job.id)
    assert loaded.status=='paused' and loaded.interrupted and loaded.phase=='interrupted'
    assert loaded.directory==job.directory
    other.retry(job.id)
    assert len(other.list())==1
    other.clear(True)
    third=JobStore();third.enable_persistence(path)
    assert third.list()==[]


def test_destination_grouping_and_speed_snapshot(tmp_path):
    from app.settings import Settings,site_folder
    preferences=Settings(tmp_path/'settings.json',tmp_path/'outputs')
    preferences.change(group_by_site=True,speed_limit_kbps=256)
    with patch('app.main.settings',preferences),patch('app.main.checked_batch_urls',side_effect=lambda urls:urls),patch('app.main.executor.submit'):
        response=client.post('/api/batch',json={'urls':['https://www.youtube.com/watch?v=sample'],'mode':'both'})
    created=[jobs.get(item['id']) for item in response.json()['jobs']]
    assert all(j.destination==str(tmp_path/'outputs'/'YouTube') and j.speed_limit_kbps==256 for j in created)
    preferences.change(group_by_site=False)
    with patch('app.main.settings',preferences),patch('app.main.checked_url',side_effect=lambda u:u),patch('app.main.executor.submit'):
        flat=client.post('/api/download',json={'url':'https://dai.ly/sample'}).json()
    assert flat['destination']==str(tmp_path/'outputs')
    assert created[0].destination.endswith('YouTube')
    assert site_folder('https://sub.dailymotion.com/video/test')=='Dailymotion'
    assert site_folder('https://another.example.com/video')=='another.example.com'
    saved=Settings(tmp_path/'settings.json',tmp_path/'elsewhere')
    assert saved.get()['group_by_site'] is False and saved.get()['speed_limit_kbps']==256


def test_export_publishes_to_destination_without_changing_source(tmp_path,sample_media):
    destination=tmp_path/'chosen'/'Vimeo'
    job=jobs.create(url='https://vimeo.com/sample',kind='video',container='mp4',quality='best',directory=str(tmp_path/'work'),source_filename=str(sample_media),clip_start=.2,clip_end=1.2,destination=str(destination))
    run_download(job)
    assert job.status=='completed' and Path(job.filename).parent==destination
    assert sample_media.exists() and abs(duration_of(job.filename)-1)<.15


def test_native_folder_picker_cancel_and_selection(tmp_path):
    import types
    from app.native import NativeAPI
    from app.settings import Settings
    from unittest.mock import MagicMock
    preferences=Settings(tmp_path/'settings.json',tmp_path/'old')
    bridge=NativeAPI(preferences);bridge._window=MagicMock()
    bridge._window.create_file_dialog.return_value=None
    with patch.dict(sys.modules,{'webview':types.SimpleNamespace(FileDialog=types.SimpleNamespace(FOLDER=10))}):
        assert bridge.choose_folder() is None
        bridge._window.create_file_dialog.return_value=(str(tmp_path/'chosen'),)
        result=bridge.choose_folder()
    assert result['download_directory']==str(tmp_path/'chosen')
    assert result['native_folder_picker'] is True
    assert (tmp_path/'chosen').is_dir()


def test_settings_validation(tmp_path):
    from app.settings import Settings
    preferences=Settings(tmp_path/'settings.json',tmp_path/'outputs')
    with patch('app.main.settings',preferences):
        assert client.post('/api/settings',json={'group_by_site':True,'speed_limit_kbps':-1}).status_code==422
        assert client.post('/api/settings',json={'group_by_site':False,'speed_limit_kbps':512}).status_code==200
        assert client.get('/api/settings').json()['speed_limit_kbps']==512


def test_desktop_bridge_exposes_only_explicit_functions(tmp_path):
    from app.desktop_host import create_desktop_window, desktop_icon
    from app.settings import Settings
    from unittest.mock import MagicMock
    host=MagicMock()
    preferences=Settings(tmp_path/'settings.json',tmp_path/'downloads')
    window,bridge=create_desktop_window(host,preferences,'http://127.0.0.1:17321')
    assert 'js_api' not in host.create_window.call_args.kwargs
    functions=window.expose.call_args.args
    assert {f.__name__ for f in functions}=={'choose_folder','open_folder','choose_media_files','choose_cookies','open_downloaded','open_library','locate_media','reveal_library','launch_repair','open_editor','open_player','export_diagnostics','configure_tray'}
    assert [name for name in vars(bridge) if not name.startswith('_')]==[]
    assert bridge._window is window
    assert desktop_icon().is_file()


def test_real_webview_bridge_finishes_startup(tmp_path):
    import json
    import types
    from threading import Event, Lock
    from webview.util import inject_pywebview
    from app.native import NativeAPI
    from app.settings import Settings
    bridge=NativeAPI(Settings(tmp_path/'settings.json',tmp_path/'downloads'))
    scripts=[]
    window=types.SimpleNamespace(
        _js_api=None,
        _functions={name:getattr(bridge,name) for name in ('choose_folder','open_folder','choose_media_files','choose_cookies','open_downloaded','open_library','locate_media','reveal_library','launch_repair','open_editor','open_player','export_diagnostics','configure_tray')},
        _expose_lock=Lock(),
        events=types.SimpleNamespace(before_load=Event(),loaded=Event(),_pywebviewready=Event()),
        run_js=scripts.append)
    bridge._window=window
    with patch('webview.util.load_js_files',return_value=('start','%(functions)s')):
        inject_pywebview('edgechromium',window)
        assert window.events.loaded.wait(2), 'Native bridge stalled during startup'
    assert window.events._pywebviewready.is_set()
    assert {f['func'] for f in json.loads(scripts[-1])}=={'choose_folder','open_folder','choose_media_files','choose_cookies','open_downloaded','open_library','locate_media','reveal_library','launch_repair','open_editor','open_player','export_diagnostics','configure_tray'}


def test_single_inspection_never_expands_playlist():
    from app.downloader import inspect_url
    def forbidden_entries():
        raise AssertionError('Single inspection expanded playlist entries')
        yield
    with patch('app.downloader.YoutubeDL') as ydl:
        instance=ydl.return_value.__enter__.return_value
        instance.extract_info.return_value={'_type':'playlist','entries':forbidden_entries()}
        with pytest.raises(ValueError,match='Select Playlist'):
            inspect_url('https://www.youtube.com/playlist?list=PLsample')
        instance.sanitize_info.assert_not_called()
        options=ydl.call_args.args[0]
        assert options['extract_flat']=='in_playlist' and options['playlistend']==1
        assert options['lazy_playlist'] is True


def test_playlist_extraction_consumes_only_requested_page():
    def entries():
        for i in range(100):
            yield {'id':str(i),'url':str(i),'ie_key':'Youtube','title':f'Video {i}'}
        raise AssertionError('Extraction consumed beyond requested page')
    with patch('app.downloader.YoutubeDL') as ydl:
        instance=ydl.return_value.__enter__.return_value
        instance.extract_info.return_value={'title':'Large playlist','playlist_count':100000,'entries':entries()}
        result=inspect_playlist('https://youtube.com/playlist?list=PLsample')
        instance.sanitize_info.assert_not_called()
        assert ydl.call_args.args[0]['lazy_playlist'] is True
    assert len(result['entries'])==100 and result['has_more']
    assert result['next_start']==101


def test_playlist_unavailable_and_malformed_metadata():
    with patch('app.downloader.YoutubeDL') as ydl:
        instance=ydl.return_value.__enter__.return_value
        instance.extract_info.return_value={'title':{'unexpected':'value'},'entries':[None,42,{'title':{'name':'Title'},'url':{},'duration':float('nan'),'playlist_index':'bad'}]}
        result=inspect_playlist('https://example.com/list')
    assert [item['index'] for item in result['entries']]==[1,2,3]
    assert all(item['url'] is None and item['duration'] is None for item in result['entries'])
    assert isinstance(result['title'],str) and isinstance(result['entries'][2]['title'],str)


def test_playlist_error_keeps_api_healthy():
    with patch('app.main.checked_url',return_value='https://youtube.com/playlist?list=PLsample'),patch('app.main.inspect_playlist',side_effect=RuntimeError('Playlist unavailable')):
        response=client.post('/api/playlist',json={'url':'https://youtube.com/playlist?list=PLsample'})
    assert response.status_code==422
    assert client.get('/api/health').status_code==200


def test_isolated_playlist_result_and_worker_command():
    from app.playlist_process import inspect_playlist_isolated
    import types
    def fake_run(command,**kwargs):
        request=json.loads(Path(command[-2]).read_text())
        assert request['limit']==100 and request['start']==1
        assert request['url']=='https://youtube.com/playlist?list=PLsample'
        assert request['url'] not in command
        assert kwargs['timeout']==50
        Path(command[-1]).write_text(json.dumps({'ok':True,'data':{'title':'Playlist','entries':[],'has_more':False}}))
        return types.SimpleNamespace(returncode=0)
    with patch('app.playlist_process.subprocess.run',side_effect=fake_run):
        assert inspect_playlist_isolated('https://youtube.com/playlist?list=PLsample')['entries']==[]


def test_worker_crash_does_not_stop_api():
    real_run=subprocess.run
    def crash_worker(command,**kwargs):
        return real_run([sys.executable,'-c','import os; os._exit(17)'],**kwargs)
    with patch('app.main.checked_url',return_value='https://youtube.com/playlist?list=PLsample'),patch('app.playlist_process.subprocess.run',side_effect=crash_worker):
        response=client.post('/api/playlist',json={'url':'https://youtube.com/playlist?list=PLsample'})
    assert response.status_code==422 and 'stopped unexpectedly' in response.json()['detail']
    assert client.get('/api/health').status_code==200


def test_worker_timeout_does_not_stop_api():
    real_run=subprocess.run
    def stalled_worker(command,**kwargs):
        kwargs['timeout']=.02
        return real_run([sys.executable,'-c','import time; time.sleep(10)'],**kwargs)
    with patch('app.main.checked_url',return_value='https://youtube.com/playlist?list=PLsample'),patch('app.playlist_process.subprocess.run',side_effect=stalled_worker):
        response=client.post('/api/playlist',json={'url':'https://youtube.com/playlist?list=PLsample'})
    assert response.status_code==422 and 'timed out' in response.json()['detail']
    assert client.get('/api/health').status_code==200


def test_real_worker_entry_point_reports_failure(tmp_path):
    import os
    request=tmp_path/'request.json';result=tmp_path/'result.json'
    request.write_text(json.dumps({'unexpected_argument':True}))
    env=dict(os.environ,DROPDL_DATA_ROOT=str(tmp_path/'diagnostics'))
    process=subprocess.run([sys.executable,'-u','-m','app.playlist_process','--worker',str(request),str(result)],cwd=Path(__file__).resolve().parents[1]/'backend',env=env,capture_output=True,timeout=15)
    assert process.returncode==0,process.stderr
    data=json.loads(result.read_text())
    assert data['ok'] is False and 'unexpected_argument' in data['error']
    assert (tmp_path/'diagnostics'/'playlist-worker-crash.log').read_text().startswith('Playlist worker started')


def test_diagnostics_flush_immediately(tmp_path):
    import os
    env=dict(os.environ,DROPDL_DATA_ROOT=str(tmp_path))
    code="from app.diagnostics import configure_diagnostics; import logging; configure_diagnostics(); logging.getLogger('dropdl').info('Flush test'); from app.settings import CONFIG_ROOT; assert 'Flush test' in (CONFIG_ROOT/'diagnostics.log').read_text()"
    result=subprocess.run([sys.executable,'-c',code],cwd=Path(__file__).resolve().parents[1]/'backend',env=env,capture_output=True,timeout=10)
    assert result.returncode==0,result.stderr


def test_interface_diagnostic_limits():
    assert client.post('/api/diagnostics',json={'event':'load-playlist-click'}).status_code==200
    assert client.post('/api/diagnostics',json={'event':'error','message':'x'*6001}).status_code==422


def test_bulk_queue_persists_once_and_only_then_starts_workers(tmp_path):
    from app.jobs import JobStore
    store=JobStore();store.enable_persistence(tmp_path/'queue.json')
    submitted=[]
    def submit(function,job):
        records=json.loads((tmp_path/'queue.json').read_text())
        assert len(records)==200
        submitted.append(job.id)
    with patch('app.main.jobs',store),patch('app.main.checked_batch_urls',side_effect=lambda urls:urls),patch('app.main.executor.submit',side_effect=submit),patch.object(store,'_save_locked',wraps=store._save_locked) as save:
        response=client.post('/api/batch',json={'urls':[f'https://youtube.com/watch?v=video{i}' for i in range(100)],'mode':'both'})
    assert response.status_code==202
    assert len(response.json()['jobs'])==200 and len(set(submitted))==200
    assert save.call_count==1


def test_batch_dns_validation_resolves_shared_host_once():
    from app.main import checked_batch_urls
    public=[(2,1,6,'',('93.184.216.34',0))]
    urls=[f'https://example.com/video/{i}' for i in range(100)]
    with patch('app.security.socket.getaddrinfo',return_value=public) as lookup:
        assert checked_batch_urls(urls)==urls
    assert lookup.call_count==1
    with patch('app.security.socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',0))]):
        with pytest.raises(Exception):checked_batch_urls(urls)


def test_native_destination_requires_private_token(tmp_path):
    import os
    from app.settings import Settings
    preferences=Settings(tmp_path/'settings.json',tmp_path/'old')
    with patch.dict(os.environ,{'DROPDL_NATIVE_TOKEN':'private-test-token'}),patch('app.main.settings',preferences):
        payload={'download_directory':str(tmp_path/'chosen')}
        assert client.post('/api/native/destination',json=payload).status_code==403
        response=client.post('/api/native/destination',json=payload,headers={'X-DropDL-Native-Token':'private-test-token'})
        assert response.status_code==200 and response.json()['download_directory']==str(tmp_path/'chosen')


def test_real_backend_runs_separately_and_remote_folder_settings_work(tmp_path):
    import os,socket
    from app.server_process import BackendProcess,RemoteSettings
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
    with patch('app.server_process.CONFIG_ROOT',tmp_path),patch.dict(os.environ,{'DROPDL_DATA_ROOT':str(tmp_path),'DOWNLOAD_ROOT':str(tmp_path/'outputs')}):
        backend=BackendProcess(port)
        try:
            backend.start()
            assert backend._process.pid!=os.getpid()
            assert backend.request('/api/health')['ok']
            remote=RemoteSettings(backend)
            assert remote.get()['native_folder_picker'] is True
            assert remote.change(download_directory=str(tmp_path/'chosen'))['download_directory']==str(tmp_path/'chosen')
            assert remote.get()['download_directory']==str(tmp_path/'chosen')
            # A dead child cannot terminate its parent; calls fail normally.
            backend._process.terminate();backend._process.wait(timeout=5)
            with pytest.raises(OSError):backend.request('/api/health')
        finally:backend.close()


def test_gui_worker_dispatch_does_not_import_webview_or_downloader(tmp_path):
    import os
    backend_dir=Path(__file__).resolve().parents[1]/'backend'
    code="import sys,runpy; from app import server_process; server_process.serve_backend=lambda: (None if 'webview' not in sys.modules and 'yt_dlp' not in sys.modules else (_ for _ in ()).throw(AssertionError('Native/yt imports crossed process boundary'))); sys.argv=['desktop.py','--backend-worker']; runpy.run_path('desktop.py',run_name='__main__')"
    result=subprocess.run([sys.executable,'-c',code],cwd=backend_dir,env=dict(os.environ,DROPDL_DATA_ROOT=str(tmp_path)),capture_output=True,timeout=10)
    assert result.returncode==0,result.stderr


def test_local_clipping_preview_is_direct_and_export_uses_editor(tmp_path):
    source_file=tmp_path/'local.mp4';source_file.write_bytes(b'local media bytes')
    source=jobs.create(url='https://example.com/local',kind='video',container='mp4',quality='1080p',directory=str(tmp_path),status='completed',filename=str(source_file))
    before=len(jobs.list())
    with patch('app.main.executor.submit') as downloader,patch('app.main.editor.submit') as editor:
        preview=client.post('/api/preview',json={'source_job_id':source.id})
        assert preview.status_code==202 and preview.json()['id']==source.id and preview.json()['preview_ready']
        assert len(jobs.list())==before
        downloader.assert_not_called();editor.assert_not_called()
        assert client.get(f'/api/jobs/{source.id}/file?preview=true').content==source_file.read_bytes()
        clip=client.post(f'/api/jobs/{source.id}/clip',json={'clip_start':0,'clip_end':1,'mode':'video'})
        assert clip.status_code==202
        exported=jobs.get(clip.json()['jobs'][0]['id'])
        assert exported.purpose=='clip' and exported.source_filename==str(source_file)
        downloader.assert_not_called();editor.assert_called_once()
        client.post(f'/api/jobs/{exported.id}/cancel')
