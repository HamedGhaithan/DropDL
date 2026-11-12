export type Segment={start:number;end:number;speed:number;source_job_id?:string;gain?:number;offset?:number;track?:number}
export type TextCue={start:number;end:number;text:string;kind:'caption'|'title'}
export type TrackSettings={muted?:boolean;hidden?:boolean;locked?:boolean}
export type EditProject={tracks?:TrackSettings[];segments:Segment[];texts?:TextCue[];soundtrack?:{source_job_id:string;start:number;offset:number;gain:number;muted?:boolean;locked?:boolean};export_preset?:string;audio_bitrate?:number;export_format?:string;fps?:number;height?:number;crf?:number;ratio:string;rotate:number;flip:boolean;brightness:number;contrast:number;saturation:number;volume:number;fadeIn:number;fadeOut:number}
export const trackState=(p:EditProject,lane:number):TrackSettings=>p.tracks?.[lane]||{}
export const clipLocked=(p:EditProject,s:Segment)=>!!trackState(p,s.track||0).locked
export const setTrack=(p:EditProject,lane:number,patch:TrackSettings):EditProject=>({...p,tracks:Array.from({length:Math.max(p.tracks?.length||3,lane+1)},(_,i)=>({...trackState(p,i),...(i===lane?patch:{})}))})
export const freshProject=(duration:number):EditProject=>({segments:[{start:0,end:duration,speed:1}],ratio:'original',rotate:0,flip:false,brightness:0,contrast:1,saturation:1,volume:1,fadeIn:0,fadeOut:0})
export const clipLength=(s:Segment)=>(s.end-s.start)/s.speed
export const positioned=(p:EditProject):EditProject=>{let cursor=0;return {...p,segments:p.segments.map(s=>{const offset=s.offset??cursor;cursor=offset+clipLength(s);return {...s,offset,track:s.track??0}})}}
export const clipOffset=(p:EditProject,index:number)=>positioned(p).segments[index]?.offset||0
export const outputDuration=(p:EditProject)=>Math.max(0,...positioned(p).segments.map(s=>s.offset!+clipLength(s)))
export function splitSegment(p:EditProject,index:number,at:number):EditProject{const base=positioned(p),s=base.segments[index];if(!s||clipLocked(p,s)||at<=s.start+.05||at>=s.end-.05)return p;return {...base,segments:[...base.segments.slice(0,index),{...s,end:at},{...s,start:at,offset:s.offset!+(at-s.start)/s.speed},...base.segments.slice(index+1)]}}
export const editorLabel=(lang:string,en:string,ar:string)=>lang==='ar'?ar:en
export async function openEditor(id:string,lang:string){
 if(window.pywebview?.api.open_editor){if(!await window.pywebview.api.open_editor(id,lang))throw Error('The editor window could not open.');return}
 const link=new URL(location.href);link.search='';link.searchParams.set('editor',id);link.searchParams.set('lang',lang)
 if(!window.open(link.toString(),'dropdl-editor-'+id,'popup,width=1440,height=940,resizable=yes'))throw Error(editorLabel(lang,'Allow the editor popup to open.','اسمح بفتح نافذة المحرر.'))
}

/** Nearest supported export rate to the source (24 stays 24, 29.97 becomes 30). 1.x always used 30. */
export const exportFps=(sourceFps?:number)=>{const target=sourceFps&&Number.isFinite(sourceFps)?sourceFps:30;return [24,25,30,50,60].reduce((best,rate)=>Math.abs(rate-target)<Math.abs(best-target)?rate:best,30)}
