"""Desktop workspace API: converter, catalogue, queue tools and storage."""
import json
import os
import shutil
import time
from pathlib import Path
from threading import Lock,BoundedSemaphore
from uuid import uuid4
from fastapi import APIRouter,HTTPException,Header
from fastapi.responses import FileResponse
from pydantic import BaseModel,Field,model_validator
from .converter import PRESETS,probe_media,run_conversion
from .media_library import library
from .jobs import jobs
from .settings import CONFIG_ROOT

thumbnail_slots=BoundedSemaphore(2)
router=APIRouter(prefix='/api')
context=None

def configure(main):
    global context
    context=main

def require_media(identity):
    record=library.get(identity)
    if not record:raise HTTPException(404,'Media not found.')
    if not record['exists']:raise HTTPException(410,'The file was moved or removed.')
    return record

class ImportRequest(BaseModel):
    paths:list[str]=Field(min_length=1,max_length=200)

@router.post('/native/import')
def import_media(payload:ImportRequest,x_dropdl_native_token:str|None=Header(default=None)):
    context.require_native_token(x_dropdl_native_token)
    records=[];errors=[]
    for name in payload.paths:
        path=Path(name).resolve()
        try:
            metadata=probe_media(path)
            records.append(library.add(path,kind=metadata['kind'],metadata={k:v for k,v in metadata.items() if k!='streams'}))
        except (ValueError,OSError,RuntimeError) as exc:errors.append({'name':path.name,'error':str(exc)})
    return {'files':records,'errors':errors}

@router.get('/library')
def list_media():return {'files':library.list()}

class CollectionName(BaseModel):
    name:str=Field(min_length=1,max_length=60)
@router.get('/collections')
def list_collections():return {'collections':library.collections()}
@router.post('/collections')
def create_collection(payload:CollectionName):
    try:return library.save_collection(payload.name)
    except ValueError as exc:raise HTTPException(400,str(exc)) from exc
@router.post('/collections/{identity}/rename')
def rename_collection(identity:str,payload:CollectionName):
    try:return library.save_collection(payload.name,identity)
    except ValueError as exc:raise HTTPException(400,str(exc)) from exc
@router.post('/collections/{identity}/remove')
def remove_collection(identity:str):
    try:library.remove_collection(identity)
    except ValueError as exc:raise HTTPException(404,str(exc)) from exc
    return {'ok':True}
class OrganizeMedia(BaseModel):
    ids:list[str]=Field(min_length=1,max_length=500)
    favorite:bool|None=None
    collection_id:str|None=Field(default=None,max_length=100)
    title:str|None=Field(default=None,min_length=1,max_length=200)
@router.post('/library/selection/organize')
def organize_media(payload:OrganizeMedia):
    if not (payload.model_fields_set-{'ids'}):raise HTTPException(400,'Choose an organization action.')
    try:return {'files':library.organize(payload.ids,favorite=payload.favorite,collection_id=payload.collection_id,change_collection='collection_id' in payload.model_fields_set,title=payload.title)}
    except ValueError as exc:raise HTTPException(400,str(exc)) from exc
class RelinkMedia(BaseModel):
    path:str=Field(min_length=1,max_length=4096)
@router.post('/native/library/{identity}/relink')
def relink_media(identity:str,payload:RelinkMedia,x_dropdl_native_token:str|None=Header(default=None)):
    context.require_native_token(x_dropdl_native_token)
    path=Path(payload.path).resolve()
    try:
        if not library.get(identity):raise HTTPException(404,'Media not found.')
        metadata=probe_media(path)
        record=library.relink(identity,path,{k:v for k,v in metadata.items() if k!='streams'})
    except (OSError,ValueError,RuntimeError) as exc:raise HTTPException(400,str(exc)) from exc
    (CONFIG_ROOT/'thumbnails'/(identity+'.jpg')).unlink(missing_ok=True)
    return record
media_info_slots=BoundedSemaphore(2)
@router.get('/library/{identity}/info')
def library_info(identity:str):
    record=require_media(identity)
    try:
        with media_info_slots:metadata=probe_media(record['path'])
        info={k:v for k,v in metadata.items() if k!='streams'};library.cache_info(identity,record['path'],info)
        return {'file':library.get(identity),'info':info}
    except (OSError,ValueError,RuntimeError) as exc:raise HTTPException(422,str(exc)) from exc

@router.get('/library/{identity}/file')
def media_file(identity:str):
    record=require_media(identity)
    import mimetypes
    return FileResponse(record['path'],media_type=mimetypes.guess_type(record['filename'])[0] or 'application/octet-stream',filename=record['filename'],content_disposition_type='inline')

@router.get('/library/{identity}/thumbnail')
def thumbnail(identity:str):
    record=require_media(identity)
    # 2.1: representative frame for video, embedded cover art for audio.
    folder=CONFIG_ROOT/'thumbnails';target=folder/(identity+'-poster.jpg')
    if not target.exists():
        from .posters import make_poster
        with thumbnail_slots:
            if not make_poster(record['path'],target,320):
                raise HTTPException(404 if record['kind']=='audio' else 422,'Thumbnail unavailable.')
    return FileResponse(target,media_type='image/jpeg')

class RemoveRequest(BaseModel):delete_file:bool=False

class SelectedMediaRequest(RemoveRequest):
    ids:list[str]=Field(min_length=1,max_length=500)

@router.post('/library/selection/remove')
def remove_selected_media(payload:SelectedMediaRequest):
    identities=list(dict.fromkeys(payload.ids))
    records=[library.get(identity) for identity in identities]
    if any(record is None for record in records):raise HTTPException(404,'Media not found.')
    if payload.delete_file and any(not record['owned'] for record in records):
        raise HTTPException(400,'Imported originals cannot be deleted. Select output files only.')
    removed=[];errors=[]
    for identity in identities:
        try:
            library.remove(identity,payload.delete_file)
            removed.append(identity)
        except (OSError,ValueError) as exc:errors.append({'id':identity,'error':str(exc)})
    return {'removed':removed,'errors':errors}

@router.get('/library/selection/archive')
def archive_selected_media(ids:str):
    identities=list(dict.fromkeys(ids.split(',')))
    if not identities or len(identities)>500 or any(len(i)!=32 or any(c not in '0123456789abcdef' for c in i) for i in identities):
        raise HTTPException(400,'Choose between 1 and 500 media files.')
    from types import SimpleNamespace
    records=[require_media(identity) for identity in identities]
    if any(not record['exists'] for record in records):raise HTTPException(410,'A selected file is no longer available.')
    return context.archive_files([SimpleNamespace(filename=record['path'],kind=record['kind']) for record in records],'DropDL-selected-media.zip')


@router.post('/library/{identity}/remove')
def remove_media(identity:str,payload:RemoveRequest):
    # Removing a reference is reversible by importing it again. Actual deletion is explicit in the UI.
    try:library.remove(identity,payload.delete_file)
    except ValueError as exc:raise HTTPException(400,str(exc)) from exc
    return {'ok':True}

@router.post('/library/{identity}/preview',status_code=202)
def media_preview(identity:str):
    source=require_media(identity)
    # Register a playable local reference, without submitting it to any worker.
    for item in jobs.list():
        cached=jobs.get(item['id'])
        if cached and cached.status=='completed' and cached.filename==source['path']:
            return dict(cached.public(),preview_ready=True)
    job=jobs.create(url=source['url'] or 'local://'+identity,kind=source['kind'],container=Path(source['path']).suffix.lstrip('.'),quality='best',directory=str(CONFIG_ROOT/'work'/uuid4().hex),source_filename=source['path'],purpose='preview',title=source['title'],status='completed',percent=100,filename=source['path'],preview_filename=source['path'])
    return job.public()

class Crop(BaseModel):
    width:int=Field(ge=2,le=16384);height:int=Field(ge=2,le=16384);x:int=Field(default=0,ge=0,le=16384);y:int=Field(default=0,ge=0,le=16384)

class ConvertOptions(BaseModel):
    preset:str='device'
    container:str|None=None
    height:int|None=Field(default=None,ge=144,le=4320)
    fps:float|None=Field(default=None,ge=1,le=120,allow_inf_nan=False)
    rotate:int=Field(default=0)
    normalize:bool=False
    target_mb:float|None=Field(default=None,ge=.1,le=100000,allow_inf_nan=False)
    start:float=Field(default=0,ge=0,allow_inf_nan=False)
    finish:float|None=Field(default=None,gt=0,allow_inf_nan=False)
    crop:Crop|None=None
    sample:bool=False
    @model_validator(mode='after')
    def validate_preset(self):
        if self.preset not in PRESETS:raise ValueError('Unknown conversion preset.')
        if self.rotate not in {0,90,180,270}:raise ValueError('Unsupported rotation.')
        if self.container and self.preset!='remux':raise ValueError('Container overrides apply only to fast container changes.')
        if self.container and self.container not in {'mp4','mkv','mov','webm'}:raise ValueError('Unsupported output container.')
        if self.finish is not None and self.finish<=self.start:raise ValueError('Finish must be after start.')
        return self

class ConvertRequest(ConvertOptions):
    media_ids:list[str]=Field(min_length=1,max_length=200)

@router.get('/convert/presets')
def presets():return {'presets':PRESETS,'custom':load_custom()}

@router.post('/convert',status_code=202)
def convert(payload:ConvertRequest):
    context.check_storage()
    sources=[require_media(identity) for identity in dict.fromkeys(payload.media_ids)]
    options=payload.model_dump(exclude={'media_ids'},exclude_none=True);preset=PRESETS[payload.preset];preferences=context.settings.get();batch=uuid4().hex
    specifications=[dict(url=record['url'] or 'local://'+record['id'],kind=preset['kind'],container=payload.container or preset['container'],quality='best',title=record['title'],site=record['site'],source_filename=record['path'],purpose='conversion_sample' if payload.sample else 'conversion',conversion_options=options,directory=str(CONFIG_ROOT/'work'/uuid4().hex),destination=str(Path(preferences['download_directory'])/'Converted'),batch_id=batch) for record in sources]
    created=jobs.create_many(specifications)
    for job in created:context.executor.submit(run_conversion,job)
    return {'batch_id':batch,'jobs':[job.public() for job in created]}

custom_lock=Lock()
def load_custom():
    try:return json.loads((CONFIG_ROOT/'presets.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):return []
class CustomPreset(BaseModel):
    name:str=Field(min_length=1,max_length=60)
    options:ConvertOptions
@router.post('/convert/presets')
def save_preset(payload:CustomPreset):
    with custom_lock:
        records=[r for r in load_custom() if r['name']!=payload.name]
        records.append(payload.model_dump());records=records[-50:]
        CONFIG_ROOT.mkdir(parents=True,exist_ok=True)
        path=CONFIG_ROOT/'presets.json';temp=path.with_suffix('.tmp');temp.write_text(json.dumps(records,ensure_ascii=False),encoding='utf-8');temp.replace(path)
    return {'custom':records}

class QueueControl(BaseModel):action:str=Field(pattern='^(pause|resume)$')
@router.post('/queue/control')
def queue_control(payload:QueueControl):
    context.executor.paused=payload.action=='pause'
    for record in jobs.list():
        job=jobs.get(record['id'])
        if payload.action=='pause' and job.purpose in {'download','preview'} and job.status not in {'completed','failed','cancelled','paused'}:
            job.pause_requested=True;job.cancel_event.set();jobs.update(job.id,interrupted=False,status='paused' if job.status=='queued' else 'pausing')
        elif payload.action=='resume' and job.status=='paused':
            replacement=jobs.retry(job.id)
            if replacement:context.executor.submit(context.run_download,replacement)
    return {'paused':context.executor.paused}

@router.post('/jobs/{identity}/pause')
def pause_job(identity:str):
    job=jobs.get(identity)
    if not job or job.purpose not in {'download','preview'} or job.status not in {'queued','starting','downloading'}:raise HTTPException(409,'Pause is available for queued or downloading media. Use Cancel during conversion or processing.')
    job.pause_requested=True;job.cancel_event.set();jobs.update(job.id,interrupted=False,status='paused' if job.status=='queued' else 'pausing');return job.public()

class PriorityRequest(BaseModel):
    priority:int=Field(default=0,ge=-1000,le=1000)
    scheduled_at:float=Field(default=0,ge=0,allow_inf_nan=False)
@router.post('/jobs/{identity}/priority')
def priority(identity:str,payload:PriorityRequest):
    job=jobs.get(identity)
    if not job or job.status not in {'queued','paused'}:raise HTTPException(409,'Only waiting tasks can be reordered or scheduled.')
    jobs.update(identity,**payload.model_dump());return job.public()

class ReorderRequest(BaseModel):ids:list[str]=Field(max_length=1000)
@router.post('/queue/reorder')
def reorder(payload:ReorderRequest):
    for index,identity in enumerate(dict.fromkeys(payload.ids)):
        job=jobs.get(identity)
        if job and job.status=='queued':jobs.update(identity,priority=min(1000,len(payload.ids)-index))
    return {'ok':True}

@router.get('/storage')
def storage():
    directory=Path(context.settings.get()['download_directory']);directory.mkdir(parents=True,exist_ok=True);disk=shutil.disk_usage(directory)
    work=CONFIG_ROOT/'work';temporary=0
    for p in work.rglob('*') if work.exists() else []:
        try:
            if p.is_file():temporary+=p.stat().st_size
        except OSError:pass
    return {'free':disk.free,'total':disk.total,'used':disk.used,'temporary_bytes':temporary,'directory':str(directory),'low_space':disk.free<1024**3}

@router.post('/storage/cleanup')
def cleanup(min_age_seconds:int=0):
    active={Path(jobs.get(j['id']).directory).resolve() for j in jobs.list() if j['status'] not in {'completed','failed','cancelled'}}
    removed=0;work=CONFIG_ROOT/'work'
    referenced={Path(r['path']).resolve() for r in library.list() if r['exists']}
    referenced.update(Path(jobs.get(j['id']).source_filename).resolve() for j in jobs.list() if jobs.get(j['id']) and jobs.get(j['id']).source_filename and j['status']!='completed')
    for directory in work.iterdir() if work.exists() else []:
        # Preserve paused/active partials, imported originals and registered media.
        live={Path(jobs.get(j['id']).directory).resolve() for j in jobs.list() if jobs.get(j['id']) and j['status'] not in {'completed','failed','cancelled'}}
        if not directory.is_dir() or time.time()-directory.stat().st_mtime<min_age_seconds:continue
        retry_directory=any(jobs.get(j['id']) and Path(jobs.get(j['id']).directory).resolve()==directory.resolve() and j['status'] in {'failed','cancelled'} for j in jobs.list())
        if directory.resolve() not in active|live and not retry_directory and not any(p.is_relative_to(directory.resolve()) for p in referenced):
            shutil.rmtree(directory);removed+=1
    return {'removed':removed}

class CookieRequest(BaseModel):path:str=Field(min_length=1,max_length=4096)
@router.post('/native/cookies')
def import_cookies(payload:CookieRequest,x_dropdl_native_token:str|None=Header(default=None)):
    context.require_native_token(x_dropdl_native_token)
    source=Path(payload.path)
    if not source.is_file() or source.stat().st_size>5*1024*1024:raise HTTPException(400,'Choose a Netscape-format cookie text file smaller than 5 MB.')
    text=source.read_text(encoding='utf-8')
    if 'Netscape HTTP Cookie File' not in text[:500] and 'HTTP Cookie File' not in text[:500]:raise HTTPException(400,'This is not a Netscape-format cookie export.')
    CONFIG_ROOT.mkdir(parents=True,exist_ok=True);target=CONFIG_ROOT/'cookies.txt';target.write_text(text,encoding='utf-8');target.chmod(0o600)
    return {'configured':True}
@router.get('/cookies')
def cookie_status():return {'configured':(CONFIG_ROOT/'cookies.txt').is_file()}
@router.post('/cookies/remove')
def remove_cookies():
    (CONFIG_ROOT/'cookies.txt').unlink(missing_ok=True);return {'configured':False}

@router.get('/jobs/{identity}/media-info')
def job_media_info(identity:str):
    job=jobs.get(identity)
    if not job or job.status!='completed' or not job.filename:raise HTTPException(409,'Complete the source preview first.')
    return probe_media(job.filename)

@router.get('/jobs/{identity}/frame/{index}')
def frame(identity:str,index:int):
    if index<0 or index>7:raise HTTPException(400,'Invalid frame index.')
    job=jobs.get(identity)
    if not job or job.status!='completed' or not job.filename:raise HTTPException(409,'Source is not ready.')
    folder=CONFIG_ROOT/'thumbnails';folder.mkdir(parents=True,exist_ok=True);target=folder/f'{identity}-{index}.jpg'
    if not target.exists():
        import subprocess
        from .downloader import _tool
        with thumbnail_slots:
            data=probe_media(job.filename);position=data['duration']*index/8
            process=subprocess.run([_tool('ffmpeg'),'-nostdin','-v','error','-y','-ss',str(position),'-threads','2','-i',job.filename,'-frames:v','1','-vf','scale=180:-2','-threads','2',str(target)],capture_output=True,timeout=25,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        if process.returncode:raise HTTPException(422,'Frame unavailable.')
    return FileResponse(target,media_type='image/jpeg')

@router.get('/jobs/{identity}/poster')
def job_poster(identity:str):
    """Representative image (not the first, often black, frame) for a finished task."""
    job=jobs.get(identity)
    if not job or job.status!='completed' or not job.filename:raise HTTPException(409,'Source is not ready.')
    target=CONFIG_ROOT/'thumbnails'/f'{identity}-poster.jpg'
    if not target.exists():
        from .posters import make_poster
        with thumbnail_slots:
            if not make_poster(job.filename,target,320):raise HTTPException(404,'No picture in this media.')
    return FileResponse(target,media_type='image/jpeg')

@router.get('/jobs/{identity}/waveform')
def waveform(identity:str,variant:str=''):
    job=jobs.get(identity)
    if not job or job.status!='completed' or not job.filename:raise HTTPException(409,'Source is not ready.')
    if variant not in ('','strip'):raise HTTPException(400,'Unknown waveform variant.')
    folder=CONFIG_ROOT/'thumbnails';folder.mkdir(parents=True,exist_ok=True);target=folder/f'{identity}-wave{"-strip" if variant else ""}.png'
    # 'strip': wide, transparent, perceptually scaled waveform drawn under timeline clips (2.3).
    spec='aformat=channel_layouts=mono,showwavespic=s=4000x96:colors=5fd8a4:scale=sqrt' if variant else 'aformat=channel_layouts=mono,showwavespic=s=1000x100:colors=70a8ff'
    if not target.exists():
        import subprocess
        from .downloader import _tool
        with thumbnail_slots:
            process=subprocess.run([_tool('ffmpeg'),'-nostdin','-v','error','-y','-i',job.filename,'-filter_complex',spec,'-frames:v','1',str(target)],capture_output=True,timeout=90,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        if process.returncode:raise HTTPException(422,'Waveform unavailable (the source may have no audio).')
    return FileResponse(target,media_type='image/png')


@router.get('/library/{identity}')
def media_record(identity:str):
    return require_media(identity)


class EditSegment(BaseModel):
    offset:float|None=Field(default=None,ge=0,le=86400,allow_inf_nan=False)
    track:int=Field(default=0,ge=0,le=7)
    source_job_id:str|None=Field(default=None,max_length=100)
    gain:float=Field(default=1,ge=0,le=2,allow_inf_nan=False)
    start:float=Field(ge=0,allow_inf_nan=False)
    end:float=Field(gt=0,allow_inf_nan=False)
    speed:float=Field(ge=.25,le=4,allow_inf_nan=False)
    @model_validator(mode='after')
    def valid_range(self):
        if self.end-self.start<.05:raise ValueError('Keep at least 0.05 seconds per segment.')
        return self
class TrackSettings(BaseModel):
    muted:bool=False
    hidden:bool=False
    locked:bool=False

class Soundtrack(BaseModel):
    muted:bool=False
    locked:bool=False
    source_job_id:str=Field(max_length=100)
    start:float=Field(default=0,ge=0,allow_inf_nan=False)
    offset:float=Field(default=0,ge=0,le=86400,allow_inf_nan=False)
    gain:float=Field(default=.3,ge=0,le=2,allow_inf_nan=False)

class TextCue(BaseModel):
    start:float=Field(ge=0,allow_inf_nan=False)
    end:float=Field(gt=0,allow_inf_nan=False)
    text:str=Field(max_length=2000)
    kind:str=Field(default='caption',pattern='^(caption|title)$')
    @model_validator(mode='after')
    def time_range(self):
        if self.end<=self.start:raise ValueError('Text end must follow its start.')
        return self

class EditSettings(BaseModel):
    tracks:list[TrackSettings]=Field(default_factory=list,max_length=8)
    export_preset:str|None=Field(default=None,max_length=60)
    audio_bitrate:int=Field(default=256)
    texts:list[TextCue]=Field(default_factory=list,max_length=500)
    segments:list[EditSegment]=Field(min_length=1,max_length=100)
    soundtrack:Soundtrack|None=None
    export_format:str=Field(default='mp4',pattern='^(mp4|prores|mp3|m4a|wav)$')
    fps:int=Field(default=30)
    height:int=Field(default=0)
    crf:int=Field(default=18,ge=14,le=28)
    ratio:str=Field(default='original',pattern='^(original|16:9|9:16|1:1|4:3)$')
    rotate:int=Field(default=0)
    flip:bool=False
    brightness:float=Field(default=0,ge=-.5,le=.5,allow_inf_nan=False)
    contrast:float=Field(default=1,ge=.2,le=2,allow_inf_nan=False)
    saturation:float=Field(default=1,ge=0,le=2,allow_inf_nan=False)
    volume:float=Field(default=1,ge=0,le=2,allow_inf_nan=False)
    fadeIn:float=Field(default=0,ge=0,le=10,allow_inf_nan=False)
    fadeOut:float=Field(default=0,ge=0,le=10,allow_inf_nan=False)
    @model_validator(mode='after')
    def rotation(self):
        if self.fps not in (24,25,30,50,60) or self.height not in (0,720,1080,1920,2160):raise ValueError('Invalid export frame rate or resolution.')
        if self.audio_bitrate not in (128,192,256,320):raise ValueError('Invalid audio bitrate.')
        if self.rotate not in (0,90,180,270):raise ValueError('Invalid rotation.')
        return self
class EditorExport(BaseModel):
    source_job_id:str=Field(max_length=100)
    project:EditSettings
@router.post('/editor/export',status_code=202)
def editor_export(payload:EditorExport):
    source=jobs.get(payload.source_job_id)
    if not source or source.status!='completed' or not source.filename:raise HTTPException(409,'Complete the source first.')
    if not Path(source.filename).is_file():raise HTTPException(410,'Source file is missing.')
    metadata=probe_media(source.filename)
    project=payload.project.model_dump(exclude_none=True)
    sources={}
    for identity in dict.fromkeys([part.source_job_id or source.id for part in payload.project.segments]+([payload.project.soundtrack.source_job_id] if payload.project.soundtrack else [])):
        item=jobs.get(identity)
        if not item or item.status!='completed' or not item.filename:raise HTTPException(409,'A timeline source is not ready.')
        if not Path(item.filename).is_file():raise HTTPException(410,'A timeline source is missing.')
        sources[identity]={'path':item.filename,'metadata':probe_media(item.filename)}
    for part in payload.project.segments:
        info=sources[part.source_job_id or source.id]['metadata']
        if part.end>info['duration']+.05:raise HTTPException(422,'A segment exceeds its source duration.')
    if payload.project.soundtrack:
        info=sources[payload.project.soundtrack.source_job_id]['metadata']
        if not info['audio_codec'] or payload.project.soundtrack.start>=info['duration']:raise HTTPException(422,'Soundtrack has no usable audio.')
    video=payload.project.export_format not in ('mp3','m4a','wav') and any(sources[p.source_job_id or source.id]['metadata']['video_codec'] for p in payload.project.segments)
    if not video and not any(v['metadata']['audio_codec'] for v in sources.values()):raise HTTPException(422,'This timeline has no audio to export.')
    project['_sources']=sources;project['_default_source']=source.id
    container=('mov' if payload.project.export_format=='prores' else 'mp4') if video else payload.project.export_format if payload.project.export_format in ('mp3','m4a','wav') else 'mp3'
    return context.enqueue(source.url,'video' if video else 'audio',container,'best',purpose='clip',source_filename=source.filename,title=source.title+' — edit',destination=context.settings.get()['export_directory'],conversion_options={'preset':'device' if video else 'mp3','edit':project})


class ProjectSnapshot(BaseModel):
    project:EditSettings

_project_lock=Lock()
def project_path(identity):
    # Hash the ID: external IDs can never become path components.
    import hashlib
    return CONFIG_ROOT/'editor-projects'/(hashlib.sha256(identity.encode()).hexdigest()+'.json')

def project_history(identity):
    path=project_path(identity)
    for candidate in (path,path.with_suffix('.backup.json')):
        try:
            data=json.loads(candidate.read_text(encoding='utf-8'))
            if not isinstance(data,list):continue
            return [dict(id=item['id'],time=item['time'],project=EditSettings.model_validate(item['project']).model_dump(exclude_none=True)) for item in data[:30]]
        except (OSError,ValueError,KeyError,TypeError):continue
    return []

@router.get('/editor/projects/{identity}')
def load_editor_project(identity:str):
    with _project_lock:return {'history':project_history(identity)}

@router.put('/editor/projects/{identity}')
def save_editor_project(identity:str,payload:ProjectSnapshot):
    if len(identity)>100:raise HTTPException(422,'Invalid project identity.')
    with _project_lock:
        history=project_history(identity);project=payload.project.model_dump(exclude_none=True)
        if history and history[0]['project']==project:return {'history':history}
        path=project_path(identity);path.parent.mkdir(parents=True,exist_ok=True)
        backup=path.with_suffix('.backup.json');temp=path.with_suffix('.tmp')
        if history:backup.write_text(json.dumps(history,ensure_ascii=False),encoding='utf-8')
        history=[{'id':uuid4().hex,'time':time.time(),'project':project}]+history[:29]
        temp.write_text(json.dumps(history,ensure_ascii=False),encoding='utf-8');os.replace(temp,path)
        return {'history':history}
