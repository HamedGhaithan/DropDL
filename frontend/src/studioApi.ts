import {API_BASE,request} from './api'
import {EditProject} from './editorProject'
/** Clip Studio 3.0: standalone projects, smart analysis, transcripts and hardware status. */
export type StudioProject={id:string;name:string;created:number;modified:number;aspect:string;ratio:string;duration:number;clips:number;media:Record<string,{path:string;title:string}>;poster:{job:string;at:number}|null;missing?:number}
export type TranscriptLine={start:number;end:number;text:string;words?:number[]}
export type Transcript={segments:TranscriptLine[];source:'file'|'subtitles'|'auto'|'import'|null;language:string;can_fetch:boolean;title?:string;words?:number}
export type Hardware={gpu:string|null;h264:string|null;hevc:string|null;av1:string|null;checked_at:number|null;error:string|null}
export type SearchHit={kind:string;id:string;title:string;job_id:string;path:string;start:number;end:number;text:string}

const put=async<T>(path:string,data:unknown)=>{const r=await fetch(API_BASE+path,{method:'PUT',headers:{'content-type':'application/json'},body:JSON.stringify(data)});const body=await r.json();if(!r.ok)throw Error(typeof body.detail==='string'?body.detail:'Request failed');return body as T}
export const listProjects=()=>request<{projects:StudioProject[]}>('/api/studio/projects')
export const createProject=(options:{name?:string;aspect?:string;media?:string[];template?:string})=>request<StudioProject>('/api/studio/projects',options)
export const openProject=(id:string)=>request<{record:StudioProject;project:EditProject;relinked:number;missing:string[]}>(`/api/studio/projects/${id}`)
export const renameProject=(id:string,name:string)=>request<StudioProject>(`/api/studio/projects/${id}/rename`,{name})
export const duplicateProject=(id:string)=>request<StudioProject>(`/api/studio/projects/${id}/duplicate`,{})
export const removeProject=(id:string)=>request<{ok:boolean}>(`/api/studio/projects/${id}/remove`,{})
export const projectPoster=(project:StudioProject)=>`${API_BASE}/api/studio/projects/${project.id}/poster?v=${Math.round(project.modified)}`
export const saveProjectTimeline=(id:string,project:EditProject)=>put<{history:{id:string;time:number;project:EditProject}[]}>(`/api/editor/projects/${id}`,{project})

export const analyzeSilence=(source_job_id:string,start:number,end:number,threshold:number,minimum:number,padding:number)=>request<{silences:[number,number][];keep:[number,number][];removed:number}>('/api/studio/analyze/silence',{source_job_id,start,end,threshold,minimum,padding})
export const analyzeScenes=(source_job_id:string,start:number,end:number,sensitivity:number)=>request<{cuts:number[]}>('/api/studio/analyze/scenes',{source_job_id,start,end,sensitivity})
export const analyzeBeats=(source_job_id:string,start:number,end:number)=>request<{bpm:number;beats:number[]}>('/api/studio/analyze/beats',{source_job_id,start,end})
export const analyzeLoudness=(source_job_id:string,start:number,end:number)=>request<{integrated:number;true_peak:number;range:number}>('/api/studio/analyze/loudness',{source_job_id,start,end})

export const getTranscript=(job:string)=>request<Transcript>(`/api/studio/transcript/${job}`)
export const fetchTranscript=(job:string)=>request<Transcript>(`/api/studio/transcript/${job}/fetch`,{})
export const importTranscript=(job:string,text:string)=>request<Transcript>(`/api/studio/transcript/${job}/import`,{text})
export const removeTranscript=(job:string)=>request<Transcript>(`/api/studio/transcript/${job}/remove`,{})
export const transcriptFile=(job:string,format:'srt'|'txt')=>`${API_BASE}/api/studio/transcript/${job}/export?format=${format}`
export const searchTranscripts=(q:string)=>request<{results:SearchHit[]}>(`/api/studio/transcripts/search?q=${encodeURIComponent(q)}`)
export const getHardware=()=>request<Hardware>('/api/hardware')

/** Open a Studio project in its own editor window (desktop) or a popup (browser). */
export async function openStudioProject(id:string,lang:string,time=0){
 if(window.pywebview?.api.open_project){if(!await window.pywebview.api.open_project(id,lang,time))throw Error('The project window could not open.');return}
 const link=new URL(location.href);link.search='';link.searchParams.set('project',id);link.searchParams.set('lang',lang);if(time)link.searchParams.set('t',String(time))
 if(!window.open(link.toString(),'dropdl-project-'+id,'popup,width=1440,height=940,resizable=yes'))throw Error(lang==='ar'?'اسمح بفتح نافذة المحرر.':'Allow the editor popup to open.')
}
export const clock=(n:number)=>{const s=Math.max(0,Math.floor(n));return (s>=3600?[Math.floor(s/3600),Math.floor(s%3600/60),s%60]:[Math.floor(s/60),s%60]).map((v,i)=>i?String(v).padStart(2,'0'):String(v)).join(':')}
