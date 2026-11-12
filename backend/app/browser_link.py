"""Explicitly paired browser extension; tokens grant link submission only."""
import json
import secrets
import time
from pathlib import Path
from threading import Lock
from fastapi import APIRouter,HTTPException,Header
from pydantic import BaseModel,Field
from .settings import CONFIG_ROOT
router=APIRouter(prefix='/api/browser');context=None;lock=Lock();code=None;expires=0;failures=[]

def read_state():
    try:return json.loads((CONFIG_ROOT/'browser.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):return {'tokens':[],'inbox':[]}
def write_state(data):
    path=CONFIG_ROOT/'browser.json';path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8');temp.replace(path);path.chmod(0o600)
@router.post('/pair-code')
def pair_code():
    global code,expires
    with lock:code=f'{secrets.randbelow(1000000):06d}';expires=time.time()+300
    return {'code':code,'expires_in':300}
class PairRequest(BaseModel):code:str=Field(min_length=6,max_length=6)
@router.post('/pair')
def pair(payload:PairRequest):
    global code,failures
    with lock:
        failures=[t for t in failures if t>time.time()-60]
        if len(failures)>=10:raise HTTPException(429,'Too many pairing attempts. Wait one minute.')
        if not code or expires<time.time() or not secrets.compare_digest(code,payload.code):
            failures.append(time.time());raise HTTPException(403,'Pairing code is invalid or expired.')
        token=secrets.token_hex(32);data=read_state();data['tokens'].append(token);data['tokens']=data['tokens'][-10:];write_state(data);code=None
    return {'token':token}
class LinkRequest(BaseModel):url:str=Field(min_length=8,max_length=4096);title:str=Field(default='',max_length=200)
@router.post('/inbox')
def submit(payload:LinkRequest,authorization:str|None=Header(default=None)):
    token=(authorization or '').removeprefix('Bearer ')
    with lock:
        data=read_state()
        if not any(secrets.compare_digest(token,t) for t in data['tokens']):raise HTTPException(403,'Pair the extension with DropDL first.')
        # Validation rejects local/private destinations just like the normal downloader.
        url=context.checked_url(payload.url)
        entry={'id':secrets.token_hex(8),'url':url,'title':payload.title,'created':time.time()}
        data['inbox'].append(entry);data['inbox']=data['inbox'][-100:];write_state(data)
    return {'ok':True}
@router.get('/inbox')
def inbox():return {'links':read_state()['inbox']}
@router.post('/inbox/{identity}/remove')
def remove(identity:str):
    with lock:
        data=read_state();data['inbox']=[r for r in data['inbox'] if r['id']!=identity];write_state(data)
    return {'ok':True}
@router.post('/unpair')
def unpair():
    with lock:
        data=read_state();data['tokens']=[];write_state(data)
    return {'ok':True}
