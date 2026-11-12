"""Release regressions: native-only export folder, migration and real publishing."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from fastapi.testclient import TestClient
from app.main import app
import app.main as main
from app.settings import Settings
from app.native import NativeAPI
from app.jobs import jobs
from app.converter import run_conversion
from app.server_process import BackendProcess,RemoteSettings
client=TestClient(app)


def test_old_settings_migrate_export_folder_without_changing_downloads(tmp_path):
    path=tmp_path/'settings.json';download=tmp_path/'custom downloads'
    path.write_text(json.dumps({'download_directory':str(download),'group_by_site':False,'speed_limit_kbps':25}))
    store=Settings(path,tmp_path/'fallback')
    assert store.get()['export_directory']==str(download/'Exports')
    export=tmp_path/'edits'
    store.change(export_directory=str(export))
    restored=Settings(path,tmp_path/'fallback')
    assert restored.get()['export_directory']==str(export)
    assert restored.get()['download_directory']==str(download)
    assert not restored.get()['group_by_site'] and restored.get()['speed_limit_kbps']==25
    restored.change(download_directory=str(tmp_path/'new downloads'))
    assert restored.get()['export_directory']==str(export)


def test_export_folder_native_picker_cancel_and_selection(tmp_path):
    import webview
    store=Settings(tmp_path/'settings.json',tmp_path/'downloads')
    bridge=NativeAPI(store);bridge._window=MagicMock()
    before=store.get()
    bridge._window.create_file_dialog.return_value=None
    assert bridge.choose_export_folder() is None and store.get()==before
    bridge._window.create_file_dialog.return_value=[str(tmp_path/'Arabic exports فيديو')]
    selected=bridge.choose_export_folder()
    assert selected['export_directory']==str(tmp_path/'Arabic exports فيديو')
    assert selected['download_directory']==before['download_directory']
    assert bridge._window.create_file_dialog.call_args.args==(webview.FileDialog.FOLDER,)
    assert selected['native_folder_picker']


def test_export_destination_requires_native_token_and_validates_write(tmp_path,monkeypatch):
    store=Settings(tmp_path/'settings.json',tmp_path/'downloads')
    monkeypatch.setattr(main,'settings',store);monkeypatch.setenv('DROPDL_NATIVE_TOKEN','export-private')
    payload={'export_directory':str(tmp_path/'exports')};headers={'X-DropDL-Native-Token':'export-private'}
    before=store.get()
    assert client.post('/api/native/export-destination',json=payload).status_code==403
    assert client.post('/api/native/export-destination',json=payload,headers={'X-DropDL-Native-Token':'bad'}).status_code==403
    assert client.post('/api/native/export-destination',json={'export_directory':'relative'},headers=headers).status_code==400
    assert client.post('/api/native/export-destination',json={'export_directory':'/nul\x00'},headers=headers).status_code==400
    obstacle=tmp_path/'not a folder';obstacle.write_text('keep')
    assert client.post('/api/native/export-destination',json={'export_directory':str(obstacle)},headers=headers).status_code==422
    assert store.get()==before
    response=client.post('/api/native/export-destination',json=payload,headers=headers)
    assert response.status_code==200 and response.json()['export_directory']==payload['export_directory']
    assert response.json()['download_directory']==before['download_directory']
    # A regular frontend settings request cannot change native path preferences.
    response=client.post('/api/settings',json={'group_by_site':True,'export_directory':str(tmp_path/'unauthorized')})
    assert response.status_code==200 and store.get()['export_directory']==payload['export_directory']


def test_remote_export_picker_uses_private_endpoint():
    backend=MagicMock();remote=RemoteSettings(backend)
    remote.change(export_directory='/chosen')
    backend.request.assert_called_once_with('/api/native/export-destination',{'export_directory':'/chosen'})


def test_enqueue_checks_actual_export_drive_before_creating_task(tmp_path,monkeypatch):
    from collections import namedtuple
    store=Settings(tmp_path/'settings.json',tmp_path/'downloads');monkeypatch.setattr(main,'settings',store)
    usage=namedtuple('usage','total used free');seen=[]
    def disk(path):
        seen.append(Path(path));return usage(1000,999,1)
    with patch('shutil.disk_usage',side_effect=disk),patch.object(jobs,'create') as create:
        with pytest.raises(main.HTTPException) as error:
            main.enqueue('local://test','video','mp4','best',destination=str(tmp_path/'exports'))
        assert error.value.status_code==507
        create.assert_not_called()
    assert seen==[tmp_path/'exports']
    obstacle=tmp_path/'blocked';obstacle.write_text('keep')
    with patch.object(jobs,'create') as create:
        with pytest.raises(main.HTTPException) as error:
            main.enqueue('local://test','video','mp4','best',destination=str(obstacle))
        assert error.value.status_code==422
        create.assert_not_called()


def test_editor_real_export_uses_selected_folder_and_keeps_snapshot(tmp_path,monkeypatch):
    import subprocess
    store=Settings(tmp_path/'settings.json',tmp_path/'downloads');monkeypatch.setattr(main,'settings',store)
    monkeypatch.setattr(main,'CONFIG_ROOT',tmp_path/'state')
    chosen=tmp_path/'edited exports';store.change(export_directory=str(chosen))
    sourcefile=tmp_path/'source.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=160x90:rate=24','-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','1','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-y',str(sourcefile)],check=True,capture_output=True)
    original=sourcefile.read_bytes()
    source=jobs.create(url='https://youtube.com/test',kind='video',container='mp4',quality='best',directory=str(tmp_path/'original-work'),status='completed',filename=str(sourcefile),title='Release source')
    with patch.object(main.editor,'submit') as submit:
        response=client.post('/api/editor/export',json={'source_job_id':source.id,'destination':str(tmp_path/'unauthorized'),'project':{'segments':[{'start':0,'end':.75,'speed':1}]}})
        assert response.status_code==202,response.text
        job=jobs.get(response.json()['id']);submit.assert_called_once()
    assert job.destination==str(chosen)
    store.change(export_directory=str(tmp_path/'later'))
    run_conversion(job)
    assert job.status=='completed',job.error
    assert Path(job.filename).parent==chosen and Path(job.filename).is_file()
    assert sourcefile.read_bytes()==original
    assert job.destination==str(chosen)


def test_remote_validation_explains_unwritable_export_drive():
    from urllib.error import HTTPError
    from io import BytesIO
    error=HTTPError('http://127.0.0.1',422,'Unprocessable',{},BytesIO(b'{"detail":"The export folder is unavailable or not writable."}'))
    with patch('app.server_process.urlopen',side_effect=error):
        with pytest.raises(ValueError,match='export folder is unavailable'):
            BackendProcess(17321).request('/api/native/export-destination',{'export_directory':'/selected'})
