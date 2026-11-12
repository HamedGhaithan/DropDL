"""Opt-in source checks, only while the desktop backend is running."""
import json
import re
import time
from pathlib import Path
from threading import Lock,Event,Thread
from uuid import uuid4
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,Field
from .settings import CONFIG_ROOT
router=APIRouter(prefix='/api/subscriptions');lock=Lock();context=None;stop=Event();thread=None

def load():
    try:return json.loads((CONFIG_ROOT/'subscriptions.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):return []
def save(rows):
    path=CONFIG_ROOT/'subscriptions.json';path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(rows,ensure_ascii=False),encoding='utf-8');tmp.replace(path)
class SubscriptionRequest(BaseModel):
    name:str=Field(min_length=1,max_length=80)
    url:str=Field(min_length=8,max_length=4096)
    interval_hours:int=Field(default=24,ge=1,le=720)
    mode:str=Field(default='video',pattern='^(video|audio|both)$')
    quality:str=Field(default='1080p',pattern='^(best|[0-9]{3,4}p)$')
    title_contains:str=Field(default='',max_length=100)
    max_duration:int=Field(default=0,ge=0,le=86400)
@router.get('')
def list_subscriptions():return {'subscriptions':load()}
@router.post('')
def add(payload:SubscriptionRequest):
    context.checked_url(payload.url)
    row={'id':uuid4().hex,**payload.model_dump(),'enabled':True,'next_check':time.time(),'last_check':None,'error':None}
    with lock:
        rows=load();rows.append(row);save(rows)
    return row
class ChangeRequest(BaseModel):enabled:bool
@router.post('/{identity}/toggle')
def toggle(identity:str,payload:ChangeRequest):
    with lock:
        rows=load();row=next((r for r in rows if r['id']==identity),None)
        if not row:raise HTTPException(404,'Subscription not found.')
        row['enabled']=payload.enabled;save(rows)
    return row
@router.post('/{identity}/remove')
def remove(identity:str):
    with lock:save([r for r in load() if r['id']!=identity])
    return {'ok':True}
@router.post('/{identity}/check')
def check_now(identity:str):
    with lock:
        rows=load();row=next((r for r in rows if r['id']==identity),None)
        if not row:raise HTTPException(404,'Subscription not found.')
        row['next_check']=0;save(rows)
    return {'ok':True}

def check(row):
    result=context.inspect_playlist(context.checked_url(row['url']),1,100)
    urls=[e['url'] for e in result['entries'] if e.get('url') and (not row['title_contains'] or row['title_contains'].lower() in e['title'].lower()) and (not row['max_duration'] or e.get('duration') is not None and e['duration']<=row['max_duration'])]
    if urls:context.batch(context.BatchRequest(urls=urls,mode=row['mode'],quality=row['quality'],skip_duplicates=True))
    return len(urls)

def loop():
    while not stop.wait(10):
        for row in load():
            if not row['enabled'] or row['next_check']>time.time():continue
            try:count=check(row);error=None
            except Exception as exc:count=0;error=str(exc)
            with lock:
                rows=load();current=next((r for r in rows if r['id']==row['id']),None)
                if current:
                    current.update(last_check=time.time(),next_check=time.time()+current['interval_hours']*3600,error=error,last_matches=count);save(rows)
def start(main):
    global context,thread
    context=main;stop.clear()
    if thread is None or not thread.is_alive():thread=Thread(target=loop,daemon=True,name='subscriptions');thread.start()
