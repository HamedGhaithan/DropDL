// Pro editor building blocks (2.3): SMPTE timecode, tool/track icons, audio meters.
import {useEffect,useRef,useState} from 'react'

/** HH:MM:SS:FF timecode at the given frame rate (non-drop-frame). */
export function timecode(seconds:number,fps=30){
 const rate=Math.max(1,Math.round(fps||30)),total=Math.max(0,Math.round((Number.isFinite(seconds)?seconds:0)*rate))
 const frames=total%rate,whole=Math.floor(total/rate)
 return [Math.floor(whole/3600),Math.floor(whole%3600/60),whole%60,frames].map(n=>String(n).padStart(2,'0')).join(':')
}

const paths:Record<string,import('react').ReactNode>={
 select:<path d="M6 3l12 9-5.2 1.1 3 6.2-2.4 1.2-3-6.3L6 18V3z" fill="currentColor" stroke="none"/>,
 razor:<><path d="M4 20 20 4"/><path d="M14.5 4.5l5 5-4 4-5-5z" fill="currentColor"/><circle cx="7" cy="17" r="1.6"/></>,
 roll:<><path d="M12 4v16"/><path d="M8 8l-4 4 4 4M16 8l4 4-4 4"/></>,
 slip:<><path d="M5 7h14v10H5z"/><path d="M9 12H3m2-2-2 2 2 2M15 12h6m-2-2 2 2-2 2"/></>,
 eye:<><path d="M2 12s3.6-6 10-6 10 6 10 6-3.6 6-10 6S2 12 2 12z"/><circle cx="12" cy="12" r="2.6"/></>,
 lock:<><rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></>,
 speaker:<><path d="M4 9h4l5-4v14l-5-4H4z"/><path d="M17 9a4 4 0 0 1 0 6"/></>,
 start:<><path d="M6 5v14"/><path d="M18 5 9 12l9 7z" fill="currentColor"/></>,
 end:<><path d="M18 5v14"/><path d="M6 5l9 7-9 7z" fill="currentColor"/></>,
 back:<><path d="M15 6l-6 6 6 6"/></>,
 forward:<><path d="M9 6l6 6-6 6"/></>,
 safe:<><rect x="3" y="5" width="18" height="14" rx="2"/><rect x="6" y="8" width="12" height="8" rx="1" strokeDasharray="2 2"/></>,
 undo:<><path d="M9 14 4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 0 12h-3"/></>,
 redo:<><path d="m15 14 5-5-5-5"/><path d="M20 9H10a6 6 0 0 0 0 12h3"/></>,
 grid:<><rect x="4" y="4" width="7" height="7" rx="1"/><rect x="13" y="4" width="7" height="7" rx="1"/><rect x="4" y="13" width="7" height="7" rx="1"/><rect x="13" y="13" width="7" height="7" rx="1"/></>,
 list:<><path d="M8 6h12M8 12h12M8 18h12"/><circle cx="4" cy="6" r="1"/><circle cx="4" cy="12" r="1"/><circle cx="4" cy="18" r="1"/></>,
 magnet:<><path d="M6 4v8a6 6 0 0 0 12 0V4"/><path d="M6 8h4M14 8h4"/></>,
 frames:<><rect x="3" y="6" width="18" height="12" rx="2"/><path d="M8 6v12M16 6v12"/></>,
}
export function ProIcon({name,size=18}:{name:string;size?:number}){
 return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>
}

export const AUDIO_LEVEL_EVENT='dropdl-audio-levels'
const DB_MARKS=[0,-6,-12,-18,-24,-36,-48]
const toPercent=(db:number)=>Math.max(0,Math.min(100,(db+60)/60*100))
const toDb=(peak:number)=>peak>0?20*Math.log10(peak):-Infinity

/** Stereo peak meters fed by the preview mixer's analysers. */
export function AudioMeters({lang}:{lang:string}){
 const [levels,setLevels]=useState<[number,number]>([-Infinity,-Infinity]),[holds,setHolds]=useState<[number,number]>([-Infinity,-Infinity]),[clipped,setClipped]=useState(false)
 const holdTimes=useRef([0,0]),last=useRef(0)
 useEffect(()=>{
  const receive=(event:Event)=>{const {left,right}=(event as CustomEvent<{left:number;right:number}>).detail||{left:0,right:0};const now=performance.now();last.current=now;const next:[number,number]=[toDb(left),toDb(right)];setLevels(next);setHolds(old=>old.map((value,i)=>{if(next[i]>=value||now-holdTimes.current[i]>1500){holdTimes.current[i]=now;return next[i]}return value}) as [number,number]);if(left>=.99||right>=.99)setClipped(true)}
  window.addEventListener(AUDIO_LEVEL_EVENT,receive)
  const decay=setInterval(()=>{if(performance.now()-last.current>180)setLevels(old=>old.map(v=>v<=-60?-Infinity:v-6) as [number,number])},60)
  return()=>{window.removeEventListener(AUDIO_LEVEL_EVENT,receive);clearInterval(decay)}
 },[])
 return <aside className="pp-meters" aria-label={lang==='ar'?'مقياس الصوت':'Audio meters'}>
  <button className={`pp-clip-led ${clipped?'on':''}`} title={lang==='ar'?'تشبع الصوت · انقر لإعادة الضبط':'Clipping · click to reset'} aria-label={lang==='ar'?'إعادة ضبط مؤشر التشبع':'Reset clip indicator'} onClick={()=>setClipped(false)}/>
  <div className="pp-meter-body">
   <div className="pp-meter-scale">{DB_MARKS.map(db=><span key={db} style={{bottom:`${toPercent(db)}%`}}>{db}</span>)}</div>
   {[0,1].map(channel=><div key={channel} className="pp-meter-bar"><i style={{height:`${100-toPercent(levels[channel])}%`}}/><b style={{bottom:`${toPercent(holds[channel])}%`,opacity:Number.isFinite(holds[channel])?1:0}}/></div>)}
  </div>
  <div className="pp-meter-labels"><span>L</span><span>R</span></div>
 </aside>
}
