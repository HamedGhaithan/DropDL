import {useState} from 'react'
import {cancelDownload,Job,pauseDownload,removeSelectedTasks,retryDownload,selectedArchiveUrl} from './api'
import {Language} from './i18n'
export const selectionWords={select:['Select task','تحديد المهمة'],all:['Select all matches','تحديد كل النتائج'],page:['Select this page','تحديد هذه الصفحة'],clear:['Clear selection','إلغاء التحديد'],chosen:['selected','محددة'],save:['Save selected as ZIP','حفظ المحدد كملف ZIP'],pause:['Pause selected','إيقاف المحدد مؤقتًا'],resume:['Resume / retry selected','استئناف / إعادة محاولة المحدد'],cancel:['Cancel selected','إلغاء المهام المحددة'],remove:['Remove selected tasks','إزالة المهام المحددة'],confirm:['Remove these tasks?','إزالة هذه المهام؟'],hint:['Downloaded files stay in your media library. Active selected tasks will be cancelled.','تبقى الملفات المُنزّلة في مكتبة الوسائط. ستُلغى المهام المحددة النشطة.'],back:['Back','رجوع'],apply:['Remove tasks','إزالة المهام'],failed:['Some actions failed','تعذر تنفيذ بعض الإجراءات'],limit:['Selection is limited to 500 items.','يمكن تحديد ٥٠٠ عنصر كحد أقصى.']} as const
export const selectionText=(lang:Language,key:keyof typeof selectionWords)=>selectionWords[key][lang==='ar'?1:0]
export default function TaskSelection({lang,jobs,selected,setSelected,refresh,onError}:{lang:Language;jobs:Job[];selected:Set<string>;setSelected:(ids:Set<string>)=>void;refresh:()=>Promise<void>;onError:(error:string)=>void}){
 const w=(key:keyof typeof selectionWords)=>selectionText(lang,key)
 const [busy,setBusy]=useState(false),[confirm,setConfirm]=useState(false)
 const picked=jobs.filter(j=>selected.has(j.id))
 const completed=picked.filter(j=>j.status==='completed')
 const pausable=picked.filter(j=>j.purpose==='download'&&['queued','starting','downloading'].includes(j.status))
 const resumable=picked.filter(j=>['paused','failed','cancelled'].includes(j.status))
 const cancellable=picked.filter(j=>!['completed','failed','cancelled'].includes(j.status))
 async function run(items:Job[],action:(id:string)=>Promise<unknown>){setBusy(true);onError('');const errors:string[]=[];try{for(const item of items){try{await action(item.id)}catch(e){errors.push(`${item.title||item.id}: ${e instanceof Error?e.message:String(e)}`)}}await refresh();if(errors.length)onError(`${w('failed')}: ${errors.join('; ')}`)}catch(e){onError(String(e))}finally{setBusy(false)}}
 async function remove(){setBusy(true);onError('');try{const result=await removeSelectedTasks(picked.map(j=>j.id));setSelected(new Set([...selected].filter(id=>!result.removed.includes(id))));setConfirm(false);await refresh()}catch(e){onError(String(e))}finally{setBusy(false)}}
 if(!picked.length)return null
 return <section className="selection-bar" aria-label={w('chosen')}><strong>{picked.length} {w('chosen')}</strong><div className="button-row">
 {completed.length>0&&<a className="secondary compact link-button" href={selectedArchiveUrl(completed.map(j=>j.id))}>{w('save')} ({completed.length})</a>}
 <button className="secondary compact" disabled={busy||!pausable.length} onClick={()=>void run(pausable,pauseDownload)}>{w('pause')}</button>
 <button className="secondary compact" disabled={busy||!resumable.length} onClick={()=>void run(resumable,retryDownload)}>{w('resume')}</button>
 <button className="secondary compact" disabled={busy||!cancellable.length} onClick={()=>void run(cancellable,cancelDownload)}>{w('cancel')}</button>
 <button className="danger compact" disabled={busy} onClick={()=>setConfirm(true)}>{w('remove')}</button>
 <button className="ghost compact" disabled={busy} onClick={()=>setSelected(new Set())}>{w('clear')}</button></div>
 {confirm&&<div className="selection-confirm" role="group" aria-label={w('confirm')}><strong>{w('confirm')} ({picked.length})</strong><p>{w('hint')}</p><div className="button-row"><button className="danger compact" disabled={busy} onClick={()=>void remove()}>{w('apply')}</button><button className="secondary compact" disabled={busy} onClick={()=>setConfirm(false)}>{w('back')}</button></div></div>}
 </section>
}
