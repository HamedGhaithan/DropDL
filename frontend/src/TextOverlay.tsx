import {CSSProperties} from 'react'
import {EditProject,TextCue} from './editorProject'
/** Titles and captions on the program monitor, animated from the timeline clock exactly like the export (libass). */
const PLACES={top:{top:'14%',left:'50%',transform:'translate(-50%,0)'},center:{top:'50%',left:'50%',transform:'translate(-50%,-50%)'},bottom:{bottom:'14%',left:'50%',transform:'translate(-50%,0)'},lower:{bottom:'16%',left:'6%',transform:'none'}} as const
export function wordTimes(cue:TextCue){
 const words=cue.text.split(/\s+/).filter(Boolean)
 if(cue.words&&cue.words.length===words.length)return {words,times:cue.words}
 const total=words.reduce((n,w)=>n+w.length+1,0)||1;let at=cue.start
 return {words,times:words.map(w=>{const t=at;at+=(cue.end-cue.start)*(w.length+1)/total;return t})}
}
function Title({cue,time}:{cue:TextCue;time:number}){
 const local=(time-cue.start)*1000,left=(cue.end-time)*1000,place=PLACES[cue.position||'top'],animation=cue.animation||'none'
 let opacity=1,extra=''
 if(animation==='fade')opacity=Math.min(1,local/350,left/350)
 if(animation==='slide'){const k=Math.min(1,local/450);opacity=Math.min(1,local/200,left/250);extra=cue.position==='lower'?` translateX(${(k-1)*8}cqw)`:` translateY(${(1-k)*4}cqh)`}
 if(animation==='pop'){const k=local<220?.3+.82*(local/220):local<340?1.12-.12*((local-220)/120):1;opacity=Math.min(1,local/90,left/200);extra=` scale(${k})`}
 let text:React.ReactNode=cue.text
 if(animation==='typewriter'){const chars=[...cue.text],step=Math.min(60,Math.floor(1400/Math.max(1,Math.min(160,chars.length))));text=chars.map((c,i)=><span key={i} style={{opacity:i>=160||local>=i*step?1:0}}>{c}</span>)}
 const style:CSSProperties={...place,opacity:Math.max(0,opacity),transform:`${place.transform==='none'?'':place.transform}${extra}`.trim()||undefined}
 return <div className={`preview-title ${cue.position==='lower'?'lower':''}`} style={style} dir="auto">{text}</div>
}
function Caption({cue,time,styleName}:{cue:TextCue;time:number;styleName:string}){
 if(styleName!=='karaoke'&&styleName!=='pop')return <div className={`preview-caption ${styleName}`} dir="auto">{cue.text}</div>
 const {words,times}=wordTimes(cue),current=times.reduce((n,t,i)=>time>=t?i:n,0)
 return <div className={`preview-caption ${styleName}`} dir="auto">{words.map((w,i)=><span key={i} className={i===current?'now':i<current?'past':''}>{w}{i<words.length-1?' ':''}</span>)}</div>
}
export default function TextOverlay({project,time}:{project:EditProject;time:number}){
 const live=(project.texts||[]).filter(t=>time>=t.start&&time<t.end)
 if(!live.length)return null
 return <div className="text-overlay" aria-hidden="true">{live.map((cue,i)=>cue.kind==='title'?<Title key={i} cue={cue} time={time}/>:<Caption key={i} cue={cue} time={time} styleName={project.caption_style||'classic'}/>)}</div>
}
