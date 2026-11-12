"""Regression checks for task selection, exports, and release consistency."""
import io
import json
import sys
import zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from fastapi.testclient import TestClient
from app.jobs import JobStore
import app.main as main
import app.workspace as workspace
from app.media_library import MediaLibrary
from app.version import VERSION
client=TestClient(main.app)

def make_task(store,tmp_path,status='completed'):
    output=tmp_path/('file-'+str(len(store.list()))+'.mp4')
    output.write_bytes(b'selected-media')
    job=store.create(url='https://example.com/video',kind='video',container='mp4',quality='best',directory=str(tmp_path/'work'),status=status,filename=str(output))
    return job,output

def test_selected_remove_preserves_unselected_and_files(tmp_path,monkeypatch):
    store=JobStore();store.enable_persistence(tmp_path/'queue.json');monkeypatch.setattr(main,'jobs',store)
    chosen,path=make_task(store,tmp_path,'downloading');other,other_path=make_task(store,tmp_path)
    response=client.post('/api/queue/remove',json={'ids':[chosen.id,chosen.id,'missing']})
    assert response.status_code==200
    assert response.json()=={'removed':[chosen.id],'missing':['missing'],'stopped':1}
    assert chosen.cancel_event.is_set() and store.get(other.id) is other
    assert path.exists() and other_path.exists()
    assert store.update_attempt(chosen,status='completed') is None
    recovered=JobStore();recovered.enable_persistence(tmp_path/'queue.json')
    assert recovered.get(chosen.id) is None and recovered.get(other.id)

def test_selected_archive_contains_only_selected_files(tmp_path,monkeypatch):
    store=JobStore();monkeypatch.setattr(main,'jobs',store);monkeypatch.setattr(main,'DOWNLOAD_ROOT',tmp_path)
    a,_=make_task(store,tmp_path);b,_=make_task(store,tmp_path);make_task(store,tmp_path)
    response=client.get('/api/queue/archive',params={'ids':a.id+','+b.id+','+a.id})
    assert response.status_code==200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert len(archive.namelist())==2
        assert all(archive.read(name)==b'selected-media' for name in archive.namelist())
    assert not list((tmp_path/'_archives').glob('*.zip'))
    a.status='downloading'
    assert client.get('/api/queue/archive',params={'ids':a.id}).status_code==409
    assert client.get('/api/queue/archive',params={'ids':'../file.mp4'}).status_code==400
    assert client.post('/api/queue/remove',json={'ids':[]}).status_code==422

def test_selected_media_deletion_protects_originals_and_handles_missing(tmp_path,monkeypatch):
    lib=MediaLibrary(tmp_path/'library.sqlite3');monkeypatch.setattr(workspace,'library',lib)
    original=tmp_path/'original.mp4';original.write_bytes(b'original');a=lib.add(original)
    output=tmp_path/'output.mp4';output.write_bytes(b'output');b=lib.add(output,owned=True)
    r=client.post('/api/library/selection/remove',json={'ids':[a['id'],b['id']],'delete_file':True})
    assert r.status_code==400 and original.exists() and output.exists()
    r=client.post('/api/library/selection/remove',json={'ids':[b['id']],'delete_file':True})
    assert r.json()['removed']==[b['id']] and not output.exists() and original.exists()
    original.unlink()
    assert client.post('/api/library/selection/remove',json={'ids':[a['id']]}).json()['removed']==[a['id']]

def test_selected_media_export_allows_original_copy(tmp_path,monkeypatch):
    lib=MediaLibrary(tmp_path/'library.sqlite3');monkeypatch.setattr(workspace,'library',lib);monkeypatch.setattr(main,'DOWNLOAD_ROOT',tmp_path)
    original=tmp_path/'original.wav';original.write_bytes(b'original');a=lib.add(original,kind='audio')
    response=client.get('/api/library/selection/archive',params={'ids':a['id']})
    assert response.status_code==200 and original.read_bytes()==b'original'
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:assert z.read(z.namelist()[0])==b'original'

def test_built_interface_and_backend_versions_agree():
    root=Path(__file__).resolve().parents[1]
    build=json.loads((root/'frontend/dist/build.json').read_text(encoding='utf-8'))
    assert build['version']==VERSION==json.loads((root/'frontend/package.json').read_text(encoding='utf-8'))['version']
    assert {'converter','clip-studio','media-library','queue-tools','selection'}<=set(build['features'])
    import re
    index=(root/'frontend/dist/index.html').read_text(encoding='utf-8')
    entry=re.search(r'src="(/assets/[^"]+\.js)"',index).group(1)
    bundle=(root/'frontend/dist'/entry.lstrip('/')).read_text(encoding='utf-8')
    for label in [VERSION,'Media library','Clip Studio','Pause downloads','Save selected as ZIP']:
        assert label in bundle
    assert client.get('/api/health').json()['version']==VERSION
    for path in ['/','/index.html','/api/health','/build.json']:
        r=client.get(path);assert r.status_code==200 and 'no-store' in r.headers['cache-control']
