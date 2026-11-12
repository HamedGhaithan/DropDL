import {accentColor} from './theme'
import {useEffect,useState} from 'react'
import MiniPlayer,{PlayingMedia} from './MiniPlayer'
import {API_BASE,Job,MediaFile} from './api'
import {Language} from './i18n'
export default function PlayerApp(){
 const params=new URLSearchParams(location.search),key=params.get('player')||'',lang:Language=params.get('lang')==='ar'?'ar':'en'
 const [media,setMedia]=useState<PlayingMedia|null>(null),[error,setError]=useState('')
 useEffect(()=>{let active=true;document.documentElement.dir=lang==='ar'?'rtl':'ltr';document.documentElement.lang=lang;const stored=(key:string)=>{try{return localStorage.getItem(key)}catch{return null}};document.documentElement.dataset.theme=stored('dropdl-theme')==='light'?'light':'dark';document.documentElement.style.setProperty('--accent',accentColor(document.documentElement.dataset.theme,stored('dropdl-accent')));
  const [type,id]=key.split(':');if(!['job','library'].includes(type)||!id||!/^[a-zA-Z0-9_-]+$/.test(id)){setError('Invalid media identity');return}
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),6000)
  void fetch(API_BASE+`/api/${type==='job'?'jobs':'library'}/${id}`,{signal:controller.signal}).then(async response=>{if(!response.ok)throw Error(lang==='ar'?'الملف غير متاح.':'The media is unavailable.');const record:Job&MediaFile=await response.json();if(type==='job'&&record.status!=='completed'||type==='library'&&!record.exists)throw Error(lang==='ar'?'الملف غير متاح.':'The media is unavailable.');const time=Number(params.get('time'));if(Number.isFinite(time)&&time>=0&&time<=86400){const saved=JSON.parse(localStorage.getItem('dropdl-playback')||'{}');saved[key]=time;localStorage.setItem('dropdl-playback',JSON.stringify(saved))}const rate=Number(params.get('rate'));if([.5,.75,1,1.25,1.5,2].includes(rate))localStorage.setItem('dropdl-playback-rate',String(rate));if(active)setMedia({key,url:API_BASE+`/api/${type==='job'?'jobs':'library'}/${id}/file?inline=true`,title:record.title||record.filename,kind:record.kind})}).catch(e=>{if(active)setError(String(e.message||e))}).finally(()=>clearTimeout(timer));return()=>{active=false;controller.abort();clearTimeout(timer)}
 },[key,lang])
 const close=()=>{if(window.pywebview?.api.close_player)void window.pywebview.api.close_player();else window.close()}
 const external=async()=>{const [type,id]=key.split(':');const api=window.pywebview?.api;if(type==='job'&&api?.open_downloaded)return api.open_downloaded(id);if(type==='library'&&api?.open_library)return api.open_library(id);throw Error(lang==='ar'?'مشغل النظام غير متاح.':'Desktop player unavailable.')}
 const dock=async()=>{const video=document.querySelector<HTMLMediaElement>('video,audio'),time=video?.currentTime||0,rate=video?.playbackRate||1;if(window.pywebview?.api.dock_player)return window.pywebview.api.dock_player(time,rate);if(!window.opener||window.opener.closed)throw Error(lang==='ar'?'النافذة الرئيسية مغلقة.':'The main window is closed.');window.opener.dispatchEvent(new CustomEvent('dropdl-player-docked',{detail:{key,time,rate}}));window.close()}
 return media?<MiniPlayer media={media} lang={lang} onClose={close} onExternal={external} detached onDock={dock}/>:<main className="ui-recovery" dir={lang==='ar'?'rtl':'ltr'}><p role={error?'alert':'status'}>{error||(lang==='ar'?'تحميل الوسائط…':'Loading media…')}</p><button onClick={close}>{lang==='ar'?'إغلاق':'Close'}</button></main>
}
