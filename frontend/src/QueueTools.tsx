import {useState} from 'react'
import {Job,queueControl,setPriority} from './api'
import {Language} from './i18n'
export const queueWords={pause:['Pause','إيقاف مؤقت'],resume:['Resume','استئناف'],pausing:['Pausing','جارٍ الإيقاف المؤقت'],paused:['Paused','متوقفة مؤقتًا'],converting:['Converting','جارٍ التحويل'],pauseAll:['Pause downloads','إيقاف التنزيلات مؤقتًا'],resumeAll:['Resume downloads','استئناف التنزيلات'],priority:['Priority','الأولوية'],normal:['Normal','عادية'],high:['High','عالية'],low:['Low','منخفضة'],schedule:['Start at','وقت البدء'],save:['Apply','تطبيق'],queueHint:['Drag waiting tasks to reorder. Pausing retains partial files; resume depends on the source.','اسحب المهام المنتظرة لإعادة ترتيبها. يحفظ الإيقاف المؤقت الملفات الجزئية؛ يعتمد الاستئناف على المصدر.']} as const
export const qText=(lang:Language,key:keyof typeof queueWords)=>queueWords[key][lang==='ar'?1:0]
export function QueueTools({lang,refresh,onError}:{lang:Language;refresh:()=>void;onError:(error:string)=>void}){
 const [busy,setBusy]=useState(false)
 const run=async(action:'pause'|'resume')=>{setBusy(true);try{await queueControl(action);refresh()}catch(e){onError(String(e))}finally{setBusy(false)}}
 return <div className="queue-controls"><button className="secondary compact" disabled={busy} onClick={()=>void run('pause')}>{qText(lang,'pauseAll')}</button><button className="secondary compact" disabled={busy} onClick={()=>void run('resume')}>{qText(lang,'resumeAll')}</button><small>{qText(lang,'queueHint')}</small></div>
}
export function PriorityControls({job,lang,refresh,onError}:{job:Job;lang:Language;refresh:()=>void;onError:(error:string)=>void}){
 const [priority,setLevel]=useState(job.priority||0),[scheduled,setScheduled]=useState(job.scheduled_at?new Date(job.scheduled_at*1000-new Date().getTimezoneOffset()*60000).toISOString().slice(0,16):'')
 return <div className="settings-grid"><label>{qText(lang,'priority')}<select value={priority} onChange={e=>setLevel(Number(e.target.value))}><option value={0}>{qText(lang,'normal')}</option><option value={100}>{qText(lang,'high')}</option><option value={-100}>{qText(lang,'low')}</option></select></label><label>{qText(lang,'schedule')}<input type="datetime-local" value={scheduled} onChange={e=>setScheduled(e.target.value)}/></label><button className="secondary" onClick={()=>void setPriority(job.id,priority,scheduled?new Date(scheduled).getTime()/1000:0).then(refresh).catch(e=>onError(String(e)))}>{qText(lang,'save')}</button></div>
}
