"""Actual render tests cover heterogeneous clips, silence and export codecs."""
import sys
from pathlib import Path
import subprocess
from unittest.mock import patch
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.editor import build_edit_command
from app.converter import probe_media
from app.jobs import jobs
from app.main import app
import app.main as main
from fastapi.testclient import TestClient
client=TestClient(app)

def make(path,inputs,codecs):
    result=subprocess.run(['ffmpeg','-v','error',*inputs,'-t','2',*codecs,'-y',str(path)],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    return path
@pytest.fixture
def media(tmp_path):
    v=make(tmp_path/'video.mp4',['-f','lavfi','-i','testsrc2=size=320x180:rate=24'],['-c:v','libx264','-pix_fmt','yuv420p'])
    av=make(tmp_path/'portrait.mp4',['-f','lavfi','-i','color=red:size=180x320:rate=25','-f','lavfi','-i','sine=frequency=600:sample_rate=44100'],['-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac'])
    a=make(tmp_path/'music.wav',['-f','lavfi','-i','sine=frequency=220:sample_rate=48000'],['-c:a','pcm_s16le'])
    return v,av,a

@pytest.mark.parametrize('format,codec',[('mp4','h264'),('prores','prores')])
def test_multi_source_timeline_render(media,tmp_path,format,codec):
    v,av,a=media;originals=[p.read_bytes() for p in media]
    sources={key:{'path':str(p),'metadata':probe_media(p)} for key,p in zip(['v','av','a'],media)}
    edit={'_sources':sources,'_default_source':'v','segments':[{'start':0,'end':1,'speed':1},{'source_job_id':'av','start':.2,'end':1.2,'speed':2,'gain':.5},{'source_job_id':'a','start':0,'end':.5,'speed':.5}], 'soundtrack':{'source_job_id':'a','start':.1,'offset':.2,'gain':.2},'fps':25,'export_format':format}
    target=tmp_path/('timeline.mov' if format=='prores' else 'timeline.mp4')
    result=subprocess.run(build_edit_command(v,target,edit,probe_media(v)),capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr
    info=probe_media(target)
    assert info['duration']==pytest.approx(2.5,abs=.08)
    assert (info['width'],info['height'])==(320,180) and info['fps']==25
    assert info['video_codec']==codec and info['audio_codec']==('pcm_s24le' if format=='prores' else 'aac')
    assert [p.read_bytes() for p in media]==originals
    # Verify the inserted portrait clip is red in the middle of the final sequence.
    result=subprocess.run(['ffmpeg','-v','error','-ss','1.25','-i',str(target),'-frames:v','1','-vf','scale=1:1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True)
    assert result.stdout[0]>result.stdout[1]*2 and result.stdout[0]>result.stdout[2]*2

def test_editor_validates_every_source_and_no_arbitrary_paths(media,tmp_path):
    records=[jobs.create(url='local://timeline',kind='video',container=p.suffix[1:],quality='best',directory=str(tmp_path),status='completed',filename=str(p)) for p in media]
    payload={'source_job_id':records[0].id,'project':{'segments':[{'source_job_id':records[1].id,'start':0,'end':1,'speed':1}]}}
    with patch.object(main.editor,'submit') as editor:
        result=client.post('/api/editor/export',json=payload);assert result.status_code==202
        assert result.json()['purpose']=='clip';editor.assert_called_once();client.post('/api/jobs/'+result.json()['id']+'/cancel')
        payload['project']['segments'][0]['source_job_id']=str(media[0])
        # 422 when the temp path exceeds the 100-character ID limit (common on Windows).
        assert client.post('/api/editor/export',json=payload).status_code in (409,422)
        payload['project']['segments'][0]['source_job_id']=records[1].id;payload['project']['segments'][0]['end']=200
        assert client.post('/api/editor/export',json=payload).status_code==422
        for bad in [{'fps':23},{'height':17},{'export_format':'bad'},{'soundtrack':{'source_job_id':records[0].id}}]:
            p={'source_job_id':records[0].id,'project':{'segments':[{'start':0,'end':1,'speed':1}],**bad}}
            assert client.post('/api/editor/export',json=p).status_code==422

def test_updater_route_precedes_static_mount():
    result=client.get('/api/engine-update');assert result.status_code==200 and result.json()['channel']=='stable'

def test_text_export_is_timed_and_literal(media,tmp_path):
    source=media[0];folder=tmp_path/"user's [edits];";folder.mkdir();target=folder/'text.mp4'
    edit={'segments':[{'start':0,'end':2,'speed':1}], 'texts':[{'start':.4,'end':1.4,'kind':'caption','text':r'Hello {\\pos(0,0)} مرحباً'}, {'start':.5,'end':1,'kind':'title','text':'A title'}]}
    result=subprocess.run(build_edit_command(source,target,edit,probe_media(source)),capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr
    content=target.with_suffix('.captions.ass').read_text(encoding='utf-8')
    assert r'{\\pos' not in content and 'مرحبا' in content.replace('ً','')
    def frame(path,at):
        return subprocess.run(['ffmpeg','-v','error','-ss',str(at),'-i',str(path),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,check=True).stdout
    # Separate no-text render accounts for re-encoding; cue must add substantial visual change.
    plain=tmp_path/'plain.mp4';no_text={**edit,'texts':[]}
    subprocess.run(build_edit_command(source,plain,no_text,probe_media(source)),capture_output=True,check=True,timeout=60)
    inside=sum(abs(a-b) for a,b in zip(frame(target,.8),frame(plain,.8)))
    outside=sum(abs(a-b) for a,b in zip(frame(target,1.8),frame(plain,1.8)))
    assert inside>outside*2 and inside>10000


def test_project_recovery_bounded_atomic_and_fallback(tmp_path):
    import app.workspace as workspace
    with patch.object(workspace,'CONFIG_ROOT',tmp_path):
        project={'segments':[{'start':0,'end':2,'speed':1}]}
        for i in range(35):
            project['brightness']=i/100
            result=client.put('/api/editor/projects/source',json={'project':project});assert result.status_code==200
        saved=client.get('/api/editor/projects/source').json()['history']
        assert len(saved)==30 and saved[0]['project']['brightness']==.34
        assert client.put('/api/editor/projects/source',json={'project':project}).json()['history']==saved
        workspace.project_path('source').write_text('broken json')
        recovered=client.get('/api/editor/projects/source').json()['history']
        assert len(recovered)==30 and recovered[0]['project']['brightness']==.33
        assert workspace.project_path('../unsafe').parent==tmp_path/'editor-projects'
        assert client.put('/api/editor/projects/source',json={'project':{'segments':[{'start':0,'end':2,'speed':1}],'texts':[{'start':1,'end':.1,'text':'bad'}]}}).status_code==422


def test_proxy_is_separate_from_normal_preview(media,tmp_path):
    record=jobs.create(url='local://proxy',kind='video',container='mp4',quality='best',directory=str(tmp_path),status='completed',filename=str(media[0]))
    with patch.object(main.editor,'submit') as submit:
        result=client.post('/api/preview',json={'source_job_id':record.id,'proxy':True})
        assert result.status_code==202 and result.json()['purpose']=='preview'
        item=jobs.get(result.json()['id']);assert item.conversion_options['proxy'] is True
        submit.assert_called_once();client.post('/api/jobs/'+item.id+'/cancel')

def test_light_preview_encodes_smaller_copy(tmp_path):
    from app.downloader import prepare_preview
    source=make(tmp_path/'wide.mp4',['-f','lavfi','-i','testsrc2=size=1280x720:rate=24'],['-c:v','libx264','-pix_fmt','yuv420p'])
    original=source.read_bytes()
    work=tmp_path/'proxy';work.mkdir()
    job=jobs.create(url='local://wide',kind='video',container='mp4',quality='best',directory=str(work),purpose='preview',source_filename=str(source),conversion_options={'proxy':True})
    preview=prepare_preview(job,source);info=probe_media(preview)
    assert info['width']==640 and info['height']==360
    assert info['duration']==pytest.approx(2,abs=.05) and info['video_codec']=='h264'
    assert source.read_bytes()==original

@pytest.mark.parametrize('message,option',[("Missing argument for option '/filter_complex'.",'-/filter_complex'),("Unrecognized option '/filter_complex'.",'-filter_complex_script')])
def test_export_filter_syntax_detection(message,option):
    from app.editor import filter_script_option
    filter_script_option.cache_clear()
    with patch('app.editor.subprocess.run',return_value=subprocess.CompletedProcess([],1,'',message)) as probe:
        assert filter_script_option('fake-ffmpeg')==option
        assert filter_script_option('fake-ffmpeg')==option
        assert probe.call_count==1
    filter_script_option.cache_clear()


def test_export_filter_probe_failure_is_actionable():
    from app.editor import filter_script_option
    filter_script_option.cache_clear()
    with patch('app.editor.subprocess.run',side_effect=FileNotFoundError):
        with pytest.raises(RuntimeError,match='Repair FFmpeg'):filter_script_option('missing')
    filter_script_option.cache_clear()

def test_multitrack_overlap_gap_and_higher_track_wins(media,tmp_path):
    v,av,a=media
    sources={key:{'path':str(p),'metadata':probe_media(p)} for key,p in zip(['v','red','a'],media)}
    edit={'_sources':sources,'_default_source':'v','fps':25,'segments':[
        {'start':0,'end':1,'speed':1,'offset':0,'track':0},
        {'source_job_id':'red','start':0,'end':1,'speed':1,'offset':.5,'track':1},
        {'start':0,'end':.5,'speed':1,'offset':2,'track':0}]}
    target=tmp_path/'tracks.mp4'
    result=subprocess.run(build_edit_command(v,target,edit,probe_media(v)),capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr
    assert probe_media(target)['duration']==pytest.approx(2.5,abs=.08)
    def pixel(t):
        result=subprocess.run(['ffmpeg','-v','error','-ss',str(t),'-i',str(target),'-frames:v','1','-vf','scale=1:1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,timeout=30)
        assert result.returncode==0,result.stderr
        return result.stdout
    red=pixel(.75);assert red[0]>red[1]*2 and red[0]>red[2]*2
    gap=pixel(1.75);assert max(gap)<8
    resumed=pixel(2.25);assert max(resumed)>30

@pytest.mark.parametrize('field,value',[('offset',-1),('offset',float('inf')),('track',8),('track',-1)])
def test_track_coordinates_are_validated(field,value):
    from app.workspace import EditSegment
    from pydantic import ValidationError
    with pytest.raises(ValidationError):EditSegment(start=0,end=1,speed=1,**{field:value})

def test_audio_only_overlay_does_not_cover_video(media,tmp_path):
    v,_,a=media
    sources={key:{'path':str(p),'metadata':probe_media(p)} for key,p in zip(['v','audio'],[v,a])}
    edit={'_sources':sources,'_default_source':'v','segments':[
        {'start':0,'end':1,'speed':1,'offset':0,'track':0},
        {'source_job_id':'audio','start':0,'end':1,'speed':1,'offset':0,'track':2}]}
    target=tmp_path/'audio-overlay.mp4'
    result=subprocess.run(build_edit_command(v,target,edit,probe_media(v)),capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr
    info=probe_media(target);assert info['audio_codec'] and info['video_codec']
    result=subprocess.run(['ffmpeg','-v','error','-ss','0.5','-i',str(target),'-frames:v','1','-vf','scale=1:1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,timeout=30)
    assert result.returncode==0,result.stderr
    assert max(result.stdout)>30

@pytest.mark.parametrize('format,codec',[('mp3','mp3'),('m4a','aac'),('wav','pcm_s24le')])
def test_editor_audio_exports_from_video(media,tmp_path,format,codec):
    source=media[1];original=source.read_bytes();target=tmp_path/('audio.'+format)
    edit={'segments':[{'start':0,'end':1,'speed':1,'offset':.25}], 'export_format':format,'audio_bitrate':192}
    result=subprocess.run(build_edit_command(source,target,edit,probe_media(source)),capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr
    info=probe_media(target);assert info['video_codec'] is None and info['audio_codec']==codec
    assert info['duration']==pytest.approx(1.25,abs=.08);assert source.read_bytes()==original

def test_hidden_track_keeps_audio_and_duration(media,tmp_path):
    source=media[1];target=tmp_path/'hidden.mp4'
    edit={'segments':[{'start':0,'end':1,'speed':1,'offset':.5,'track':1}], 'tracks':[{}, {'hidden':True}], 'fps':25}
    result=subprocess.run(build_edit_command(source,target,edit,probe_media(source)),capture_output=True,text=True,timeout=60);assert result.returncode==0,result.stderr
    info=probe_media(target);assert info['duration']==pytest.approx(1.5,abs=.08) and info['audio_codec']=='aac'
    pixel=subprocess.run(['ffmpeg','-v','error','-ss','0.8','-i',str(target),'-frames:v','1','-vf','scale=1:1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,check=True).stdout
    assert max(pixel)<8
    samples=subprocess.run(['ffmpeg','-v','error','-i',str(target),'-f','s16le','-ac','1','pipe:1'],capture_output=True,check=True).stdout
    assert any(samples)

def test_muted_track_and_soundtrack_render_silence(media,tmp_path):
    source=media[1];target=tmp_path/'muted.wav'
    edit={'_default_source':'av','_sources':{'av':{'path':str(source)},'a':{'path':str(media[2])}},'segments':[{'start':0,'end':1,'speed':1,'track':0}], 'tracks':[{'muted':True}], 'soundtrack':{'source_job_id':'a','gain':1,'muted':True},'export_format':'wav'}
    result=subprocess.run(build_edit_command(source,target,edit,probe_media(source)),capture_output=True,text=True,timeout=60);assert result.returncode==0,result.stderr
    samples=subprocess.run(['ffmpeg','-v','error','-i',str(target),'-f','s16le','-ac','1','pipe:1'],capture_output=True,check=True).stdout
    assert len(samples)>90000 and not any(samples)

def test_track_settings_recovery_and_validation(tmp_path):
    import app.workspace as workspace
    with patch.object(workspace,'CONFIG_ROOT',tmp_path):
        project={'segments':[{'start':0,'end':1,'speed':1}],'tracks':[{'muted':True,'hidden':True,'locked':True}],'export_format':'wav','audio_bitrate':192,'export_preset':'wav','height':1920}
        response=client.put('/api/editor/projects/tracks140',json={'project':project});assert response.status_code==200
        saved=client.get('/api/editor/projects/tracks140').json()['history'][0]['project'];assert saved['tracks']==project['tracks'] and saved['export_format']=='wav' and saved['audio_bitrate']==192
        for patch_settings in [{'tracks':[{}]*9},{'audio_bitrate':13}]:
            assert client.put('/api/editor/projects/tracks140',json={'project':{**project,**patch_settings}}).status_code==422

@pytest.mark.parametrize('format',['mp3','m4a','wav'])
def test_audio_export_route_uses_requested_container(media,tmp_path,format):
    source=jobs.create(url='local://audio140',kind='video',container='mp4',quality='best',directory=str(tmp_path),status='completed',filename=str(media[1]))
    with patch.object(main.editor,'submit') as submit:
        result=client.post('/api/editor/export',json={'source_job_id':source.id,'project':{'segments':[{'start':0,'end':1,'speed':1}],'export_format':format}})
        assert result.status_code==202 and result.json()['container']==format and result.json()['kind']=='audio';submit.assert_called_once();client.post('/api/jobs/'+result.json()['id']+'/cancel')
