import os
import sys,hashlib,json,re,socket,threading
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.output_files import publish_download
from app.jobs import JobStore,jobs
from app.settings import Settings
from app.downloader import run_download

def test_duplicate_names_are_exclusive_across_workers(tmp_path):
    destination=tmp_path/'outputs'
    sources=[]
    for n in range(8):
        source=tmp_path/f'{n}.mp4';source.write_bytes(bytes([n])*1000);sources.append(source)
    with ThreadPoolExecutor(max_workers=8) as executor:
        outputs=list(executor.map(lambda source:publish_download(source,destination,'My video'),sources))
    assert {p.name for p,_ in outputs}=={'My video.mp4'}|{f'My video (+{n}).mp4' for n in range(1,8)}
    assert len({p.read_bytes() for p,_ in outputs})==8
    assert all(not p.exists() for p in sources)

def test_new_duplicate_default_and_migration(tmp_path):
    prefs=tmp_path/'settings.json'
    assert Settings(prefs,tmp_path).get()['skip_duplicates'] is False
    prefs.write_text(json.dumps({'skip_duplicates':True}))
    assert Settings(prefs,tmp_path).get()['skip_duplicates'] is False
    settings=Settings(prefs,tmp_path);settings.change(skip_duplicates=True)
    assert Settings(prefs,tmp_path).get()['skip_duplicates'] is True

def test_worker_segments_and_duplicate_title(tmp_path):
    captured=[]
    class Downloader:
        def __init__(self,options):captured.append(options);self.options=options
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def add_progress_hook(self,hook):pass
        def download(self,urls):Path(self.options['outtmpl']).parent.joinpath('Title [host-id].mp4').write_bytes(b'video')
    with patch('app.downloader.YoutubeDL',Downloader):
        for i in range(2):
            job=jobs.create(url='https://example.com/video',title='Title',kind='video',container='mp4',quality='best',directory=str(tmp_path/f'work-{i}'),destination=str(tmp_path/'out'))
            run_download(job);assert job.status=='completed',job.error
    assert Path(job.filename).name=='Title [host-id] (+1).mp4' and job.title=='Title (+1)'
    assert captured[0]['http_chunk_size']==10*1024**2 and captured[0]['concurrent_fragment_downloads']==4
    assert captured[0]['continuedl'] and captured[0]['nopart'] is False and captured[0]['skip_unavailable_fragments'] is False

def test_interrupted_range_download_resumes_and_matches_original(tmp_path):
    from yt_dlp import YoutubeDL
    from yt_dlp.downloader.http import HttpFD
    body=bytes(range(256))*(12*1024*1024//256);ranges=[];interrupt=[True]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            raw=self.headers.get('Range');ranges.append(raw)
            match=re.match(r'bytes=(\d+)-(\d*)',raw or '')
            start=int(match[1]) if match else 0;end=min(int(match[2]) if match and match[2] else len(body)-1,len(body)-1)
            if start>=len(body):self.send_response(416);self.send_header('Content-Range',f'bytes */{len(body)}');self.end_headers();return
            if interrupt[0] and start>=256*1024:self.send_response(503);self.end_headers();return
            self.send_response(206 if match else 200);self.send_header('Content-Length',str(end-start+1));self.send_header('Accept-Ranges','bytes')
            if match:self.send_header('Content-Range',f'bytes {start}-{end}/{len(body)}')
            self.end_headers()
            if interrupt[0]:
                self.wfile.write(body[start:start+256*1024]);self.wfile.flush();self.connection.shutdown(socket.SHUT_RDWR);self.connection.close()
            else:self.wfile.write(body[start:end+1])
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    target=tmp_path/'large.bin';options={'quiet':True,'no_warnings':True,'continuedl':True,'http_chunk_size':1024*1024,'retries':0,'ignoreerrors':True}
    try:
        with YoutubeDL(options) as ydl:
            downloader=HttpFD(ydl,options);info={'url':f'http://127.0.0.1:{server.server_port}/large.bin'}
            downloader.download(str(target),info)
            partial=Path(str(target)+'.part');assert partial.exists() and partial.stat().st_size>0
            offset=partial.stat().st_size;count=len(ranges);interrupt[0]=False
            assert HttpFD(ydl,{**options,'retries':2}).download(str(target),info)[0]
        assert any(r and int(re.match(r'bytes=(\d+)',r)[1])==offset for r in ranges[count:])
        assert len(ranges)>3 and hashlib.sha256(target.read_bytes()).digest()==hashlib.sha256(body).digest()
        assert not partial.exists()
    finally:server.shutdown();server.server_close();thread.join()

def test_restart_keeps_directory_and_retry_progress(tmp_path):
    path=tmp_path/'queue.json';store=JobStore();store.enable_persistence(path)
    job=store.create(url='https://example.com/video',kind='video',container='mp4',quality='best',directory=str(tmp_path/'partial'))
    with patch('app.jobs.time',return_value=job.created_at+2):store.update(job.id,status='downloading',percent=42,downloaded_bytes=420,total_bytes=1000)
    restored=JobStore();restored.enable_persistence(path);retry=restored.retry(job.id)
    assert retry.directory==job.directory and retry.percent==42 and retry.downloaded_bytes==420
    assert retry.id==job.id and retry.attempt==2


@pytest.mark.skipif(os.name=='nt',reason='Windows uses the WebView2/pythonnet drop path, which needs the live pywebview runtime')
def test_native_drop_uses_local_references_and_emits_result(tmp_path):
    from types import SimpleNamespace
    from app.native import NativeAPI
    class Event:
        def __iadd__(self,handler):self.handler=handler;return self
    class SettingsBridge:
        def import_files(self,paths):
            self.paths=paths
            return {'files':[{'id':'local-file','title':"A 'quoted' video"}],'errors':[]}
    event=Event();scripts=[];settings=SettingsBridge();bridge=NativeAPI(settings)
    bridge._window=SimpleNamespace(dom=SimpleNamespace(document=SimpleNamespace(events=SimpleNamespace(drop=event,dragover=Event()))),evaluate_js=scripts.append)
    bridge.bind_editor_drops()
    assert event.handler.prevent_default and not event.handler.stop_propagation
    event.handler.callback({'dataTransfer':{'files':[{'pywebviewFullPath':str(tmp_path/'local.mp4')}]}})
    assert settings.paths==[str(tmp_path/'local.mp4')]
    assert 'dropdl-files' in scripts[0] and 'local-file' in scripts[0]
    event.handler.callback({'dataTransfer':{'files':[]}});assert len(scripts)==1

def test_windows_native_drop_reads_objects_without_name_cache(tmp_path):
    from types import SimpleNamespace
    from unittest.mock import patch
    from app.native import NativeAPI
    class Event:
        def __iadd__(self,handler):self.handler=handler;return self
    ui_callbacks=[];worker_callbacks=[];on_ui=[False]
    class ImmediateThread:
        def __init__(self,target,daemon=False):self.target=target
        def start(self):worker_callbacks.append(self.target)
    class CoreWebView2File:
        def __init__(self,path):self.Path=path
    class Settings:
        def import_files(self,paths):self.paths=paths;return {'files':[{'id':'native-real'}],'errors':[]}
    scripts=[];settings=Settings();bridge=NativeAPI(settings)
    core=SimpleNamespace(WebMessageReceived=Event())
    class Browser:
        @property
        def CoreWebView2(self):
            assert on_ui[0], 'COM access occurred off the UI thread'
            return core
    def evaluate(script):
        assert not on_ui[0], 'Synchronous JS evaluation blocks the UI message pump'
        scripts.append(script)
    bridge._window=SimpleNamespace(native=SimpleNamespace(webview=Browser(),BeginInvoke=ui_callbacks.append),evaluate_js=evaluate)
    def drain():
        while worker_callbacks:worker_callbacks.pop(0)()

    path=str(tmp_path/'عربي [clip].mp4')
    args=SimpleNamespace(Source='http://127.0.0.1:17321/?editor=x',get_WebMessageAsJson=lambda:'"FilesDropped"',get_AdditionalObjects=lambda:[CoreWebView2File(path)])
    with patch('os.name','nt'),patch('threading.Thread',ImmediateThread),patch.dict('sys.modules',{'System':SimpleNamespace(Action=lambda callback:callback)}):
        bridge.bind_editor_drops();bridge.bind_editor_drops()
        assert not hasattr(core.WebMessageReceived,'handler')
        assert not scripts
        while ui_callbacks:
            on_ui[0]=True;ui_callbacks.pop(0)();on_ui[0]=False;drain()
        core.WebMessageReceived.handler(None,args);drain()
    assert settings.paths==[path]
    assert 'native-real' in scripts[-1]
    assert 'const files=Array.from(e.dataTransfer.files)' in scripts[0]
    assert "postMessageWithAdditionalObjects('FilesDropped',files)" in scripts[0]
    del settings.paths
    args.Source='https://untrusted.example/'
    core.WebMessageReceived.handler(None,args)
    assert not hasattr(settings,'paths')
