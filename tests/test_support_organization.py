import io
import sys
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import zipfile
import pytest
from fastapi.testclient import TestClient
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.main import app
from app.settings import Settings
from app.jobs import Job,JobStore
from app.organization import component,output_location
import app.main as main
import app.support as support

client=TestClient(app)

@pytest.mark.parametrize('name',['../bad/name','CON','NUL.mp4','  .  ','a\\b:c*?','اسم القناة'])
def test_safe_folder_components(name,tmp_path):
    value=component(name)
    assert '/' not in value and '\\' not in value and value not in {'.','..'}
    assert value.strip(' .')==value
    assert component('CON')=='_CON'
    assert component('اسم القناة')=='اسم القناة'

# Date folders use local time; compute the expected label in the runner's zone.
@pytest.mark.parametrize('rule,label',[('creator','Creator'),('playlist','Playlist'),('date',__import__('time').strftime('%Y-%m-%d',__import__('time').localtime(1700000000))),('media_type','Video'),('none',None)])
def test_output_rules_stay_inside_destination(tmp_path,rule,label):
    job=Job(id='abc',url='https://example.com',kind='video',container='mp4',quality='best',directory=str(tmp_path),destination=str(tmp_path/'outputs'),created_at=1700000000,title='My clip',collection='Playlist',organization={'folder_rule':rule,'name_rule':'title'})
    folder,stem=output_location(job,{'uploader':'Creator'},Path('original.mp4'))
    assert folder.is_relative_to(tmp_path/'outputs') and stem=='My clip'
    if label:assert folder.name==label


def test_settings_roundtrip_and_queue_rule_snapshot(tmp_path):
    preferences=Settings(tmp_path/'settings.json',tmp_path/'outputs')
    with patch.object(main,'settings',preferences),patch.object(main,'checked_batch_urls',side_effect=lambda urls:urls),patch.object(main.executor,'submit'):
        assert client.post('/api/settings',json={'group_by_site':True,'speed_limit_kbps':0,'folder_rule':'playlist','name_rule':'date_title'}).status_code==200
        response=client.post('/api/batch',json={'urls':['https://example.com/video'],'mode':'both','collection':'My collection'})
        assert response.status_code==202
        for record in response.json()['jobs']:
            job=main.jobs.get(record['id'])
            assert job.collection=='My collection' and job.organization=={'folder_rule':'playlist','name_rule':'date_title'}
        preferences.change(folder_rule='creator')
        assert job.organization['folder_rule']=='playlist'
    assert Settings(preferences.path,tmp_path).get()['folder_rule']=='creator'
    assert client.post('/api/settings',json={'group_by_site':True,'folder_rule':'../../outside'}).status_code==422


def test_malformed_settings_root_is_safe(tmp_path):
    path=tmp_path/'settings.json';path.write_text('null')
    assert Settings(path,tmp_path).get()['folder_rule']=='none'


def test_support_export_is_bounded_redacted_and_excludes_profile(tmp_path,monkeypatch):
    monkeypatch.setattr(support,'CONFIG_ROOT',tmp_path)
    (tmp_path/'diagnostics.log').write_text('x'*200000+'\nWinError 10048 https://example.com/?token=private\nAuthorization: Bearer secret\npassword=secret\n'+str(Path.home())+'\n')
    (tmp_path/'cookies.txt').write_text('private cookies')
    (tmp_path/'queue.json').write_text('private history')
    response=client.get('/api/support/bundle')
    assert response.status_code==200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert set(archive.namelist())=={'health.json','README.txt',*support.LOGS}
        log=archive.read('diagnostics.log').decode()
        assert len(log)<170000 and 'secret' not in log and 'example.com' not in log and str(Path.home()) not in log
        assert 'port_in_use' in json.loads(archive.read('health.json'))['findings']


def test_job_inline_playback_supports_range_requests(tmp_path):
    output=tmp_path/'movie.mp4';output.write_bytes(b'0123456789')
    job=main.jobs.create(url='local://test',kind='video',container='mp4',quality='best',directory=str(tmp_path),status='completed',filename=str(output))
    response=client.get(f'/api/jobs/{job.id}/file?inline=true',headers={'Range':'bytes=2-5'})
    assert response.status_code==206 and response.content==b'2345'
    assert response.headers['content-disposition'].startswith('inline')
    assert response.headers['content-range']=='bytes 2-5/10'


def test_download_moves_media_and_subtitles_under_safe_creator_folder(tmp_path):
    import app.downloader as downloader
    work=tmp_path/'work';work.mkdir()
    job=main.jobs.create(url='https://example.com/video',kind='video',container='mp4',quality='best',directory=str(work),destination=str(tmp_path/'outputs'),organization={'folder_rule':'creator','name_rule':'title'})
    class FakeDownloader:
        def __init__(self,options):self.hooks=options['progress_hooks'][:]
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def add_progress_hook(self,hook):self.hooks.append(hook)
        def download(self,urls):
            (work/'original.mp4').write_bytes(b'media')
            (work/'original.en.srt').write_text('subtitle')
            for hook in self.hooks:
                hook({'status':'finished','downloaded_bytes':5,'total_bytes':5,'info_dict':{'title':'My title','uploader':'../../Creator'}})
    with patch.object(downloader,'YoutubeDL',FakeDownloader):
        downloader.run_download(job)
    assert job.status=='completed',job.error
    output=Path(job.filename)
    assert output.is_relative_to(tmp_path/'outputs')
    assert output.parent.name==component('../../Creator') and output.name=='My title.mp4'
    assert output.with_suffix('.en.srt').read_text()=='subtitle'
    assert not (work/'original.mp4').exists()


def test_organization_rules_survive_queue_restart(tmp_path):
    store=JobStore();store.enable_persistence(tmp_path/'queue.json')
    job=store.create(url='https://example.com',kind='audio',container='mp3',quality='best',directory=str(tmp_path),organization={'folder_rule':'playlist','name_rule':'date_title'},collection='Arabic قائمة')
    recovered=JobStore();recovered.enable_persistence(tmp_path/'queue.json')
    assert recovered.get(job.id).organization==job.organization
    assert recovered.get(job.id).collection==job.collection
