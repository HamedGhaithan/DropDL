import sys
from pathlib import Path
import hashlib,json
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import app.engine_update as update


def configure(monkeypatch,tmp_path):
    monkeypatch.setattr(update,'ROOT',tmp_path/'engine')
    monkeypatch.setattr(update,'state',{'checking':False,'error':None,'available':None,'pending':None,'last_check':None})
    import yt_dlp.version
    monkeypatch.setattr(yt_dlp.version,'__version__','2020.01.01')
    content=b'official package fixture';digest=hashlib.sha256(content).hexdigest()
    release={'tag_name':'2099.01.01','assets':[{'name':'yt-dlp.tar.gz','browser_download_url':'https://github.com/yt-dlp/yt-dlp/releases/download/2099.01.01/yt-dlp.tar.gz','digest':'sha256:'+digest}]}
    def fetch(url,limit=0):return json.dumps(release).encode() if url.endswith('/latest') else content
    monkeypatch.setattr(update,'fetch',fetch)
    return release

def test_verified_update_atomic_and_preserves_running_engine(monkeypatch,tmp_path):
    configure(monkeypatch,tmp_path);calls=[]
    def run(command,**kwargs):
        calls.append(command)
        if '--target' in command:
            target=Path(command[command.index('--target')+1]);(target/'yt_dlp').mkdir();(target/'yt_dlp/version.py').write_text("__version__='2099.01.01'")
        return type('Result',(),{'returncode':0,'stderr':''})()
    monkeypatch.setattr(update.subprocess,'run',run)
    before=list(sys.path);update.check()
    assert update.state['pending']=='2099.01.01' and not update.state['error']
    assert sys.path==before # No reload of modules under running jobs.
    pointer=json.loads((update.ROOT/'active.json').read_text());assert (update.ROOT/pointer['slot']/'yt_dlp/version.py').exists()
    assert any('pip' in c and '--target' in c for c in calls)
    calls.clear();update.check();assert not calls # A ready update is not installed twice.

def test_checksum_failure_and_validation_failure_keep_last_engine(monkeypatch,tmp_path):
    release=configure(monkeypatch,tmp_path);update.ROOT.mkdir();old={'slot':'2020.01.01-1234abcd','version':'2020.01.01'};(update.ROOT/'active.json').write_text(json.dumps(old))
    release['assets'][0]['digest']='sha256:'+'0'*64
    with patch.object(update.subprocess,'run') as installer:
        update.check();installer.assert_not_called()
    assert 'checksum' in update.state['error'] and json.loads((update.ROOT/'active.json').read_text())==old
    release['assets'][0]['digest']='sha256:'+hashlib.sha256(b'official package fixture').hexdigest()
    monkeypatch.setattr(update.subprocess,'run',lambda *a,**k:type('Result',(),{'returncode':1,'stderr':'fixture failure'})())
    update.check();assert 'installation failed' in update.state['error']
    assert json.loads((update.ROOT/'active.json').read_text())==old and not list(update.ROOT.glob('staging-*'))

def test_activation_rejects_path_escape(monkeypatch,tmp_path):
    configure(monkeypatch,tmp_path);update.ROOT.mkdir();(update.ROOT/'active.json').write_text(json.dumps({'slot':'../../evil'}));before=list(sys.path);update.activate();assert sys.path==before


def test_offline_error_is_nonfatal(monkeypatch,tmp_path):
    configure(monkeypatch,tmp_path)
    def offline(*args):raise OSError('offline')
    monkeypatch.setattr(update,'fetch',offline);update.check();assert update.state['error']=='offline' and not update.state['checking']
