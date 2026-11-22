import {useEffect,useMemo,useRef,useState} from 'react'
import {EditProject,positioned} from './editorProject'
import {Transcript,getTranscript,fetchTranscript,importTranscript,removeTranscript,transcriptFile,clock} from './studioApi'
import {keepRanges,removeRanges,transcriptCues,withCaptions,currentLine} from './studioModel'
type Props={project:EditProject;active:number;lang:string;position:number;commit:(p:EditProject,index?:number,at?:number)=>void;change:(key:keyof EditProject,value:unknown)=>void;seek:(index:number,source:number)=>void;notify:(text:string)=>void;fail:(text:string)=>void}
/** The words of the selected clip, timed: read, search, click to jump, cut by text and turn into captions. */
export default function TranscriptPanel({project,active,lang,position,commit,change,seek,notify,fail}:Props){
 const w=(en:string,ar:string)=>lang==='ar'?ar:en
 const s=positioned(project).segments[active],id=s?.source_job_id||''
 const [data,setData]=useState<Transcript|null>(null),[busy,setBusy]=useState(''),[query,setQuery]=useState(''),[picked,setPicked]=useState<Set<number>>(new Set()),[anchor,setAnchor]=useState<number|null>(null),[onlyClip,setOnlyClip]=useState(true),[phrases,setPhrases]=useState(true)
 const list=useRef<HTMLOListElement>(null)
 useEffect(()=>{let live=true;setData(null);setPicked(new Set());if(!id)return;setBusy('load');getTranscript(id).then(t=>{if(live)setData(t)}).catch(e=>{if(live)fail(String(e.message||e))}).finally(()=>{if(live)setBusy('')});return()=>{live=false}},[id])
 const lines=data?.segments||[],now=currentLine(lines,position)
 const shown=useMemo(()=>{const words=query.toLowerCase().split(/\s+/).filter(Boolean);return lines.map((line,i)=>({line,i})).filter(({line})=>(!onlyClip||!s||(line.end>s.start&&line.start<s.end))&&words.every(word=>line.text.toLowerCase().includes(word)))},[lines,query,onlyClip,s?.start,s?.end])
 useEffect(()=>{if(now<0||!list.current)return;list.current.querySelector<HTMLElement>(`[data-line="${now}"]`)?.scrollIntoView({block:'nearest'})},[now])
 if(!s)return <div className="transcript-panel"><p className="inspector-help">{w('Select a clip to see what is said in it.','حدد مقطعًا لترى ما يُقال فيه.')}</p></div>
 async function run(kind:string,work:()=>Promise<Transcript>){setBusy(kind);try{const t=await work();setData(t);setPicked(new Set());if(t.segments.length)notify(w(`${t.segments.length} lines ready.`,`${t.segments.length} سطر جاهز.`))}catch(e){fail(String(e instanceof Error?e.message:e))}finally{setBusy('')}}
 function toggle(i:number,shift:boolean){setPicked(old=>{const next=new Set(old);if(shift&&anchor!==null){const [a,b]=[Math.min(anchor,i),Math.max(anchor,i)];for(let n=a;n<=b;n++)next.add(n)}else next.has(i)?next.delete(i):next.add(i);return next});setAnchor(i)}
 const chosen=[...picked].sort((a,b)=>a-b).map(i=>lines[i]).filter(Boolean),ranges=chosen.map(l=>[l.start,l.end] as [number,number])
 function cut(keep:boolean){const result=keep?keepRanges(project,active,ranges):removeRanges(project,active,ranges);if(!result){notify(w('Those lines are outside this clip.','هذه الأسطر خارج المقطع.'));return}commit(result.project,result.index,result.project.segments[result.index].start);setPicked(new Set());notify(keep?w(`Kept ${chosen.length} ${chosen.length===1?'line':'lines'}; ${result.removed.toFixed(1)} s removed.`,`أُبقي ${chosen.length} سطر؛ أُزيلت ${result.removed.toFixed(1)} ث.`):w(`Cut ${chosen.length} ${chosen.length===1?'line':'lines'} (${result.removed.toFixed(1)} s).`,`قُص ${chosen.length} سطر (${result.removed.toFixed(1)} ث).`))}
 function captions(){const cues=transcriptCues(project,active,picked.size?chosen:lines,phrases?4:0);if(!cues.length){notify(w('No lines fall inside this clip.','لا توجد أسطر داخل هذا المقطع.'));return}commit(withCaptions(project,active,cues),active);notify(w(`${cues.length} ${cues.length===1?'caption':'captions'} added under this clip. They are burned into video exports.`,`أُضيفت ${cues.length} ترجمة تحت المقطع وتُدمج في الفيديو عند التصدير.`))}
 return <div className="transcript-panel">
  {!data&&busy==='load'&&<p className="inspector-help" role="status">{w('Looking for a transcript…','جارٍ البحث عن نص…')}</p>}
  {data&&!lines.length&&<div className="transcript-empty">
   <h3>{w('Edit by text','التحرير بالنص')}</h3>
   <p>{w('Get the words spoken in this clip, then click any line to jump to it, delete sentences to cut them, or turn them into captions.','احصل على الكلمات المنطوقة في المقطع، ثم انقر أي سطر للانتقال إليه أو احذف الجمل لقصها أو حوّلها إلى ترجمة.')}</p>
   <div className="button-row">{data.can_fetch&&<button className="primary compact" disabled={!!busy} onClick={()=>void run('fetch',()=>fetchTranscript(id))}>{busy==='fetch'?w('Fetching captions…','جارٍ جلب الترجمة…'):w('Get captions from the video page','جلب الترجمة من صفحة الفيديو')}</button>}<label className="secondary compact file-button">{w('Import .srt / .vtt','استيراد ‎.srt / .vtt')}<input type="file" accept=".srt,.vtt,text/vtt" hidden onChange={async e=>{const file=e.target.files?.[0];e.target.value='';if(!file)return;if(file.size>4_000_000){fail(w('That subtitle file is too large.','ملف الترجمة كبير جدًا.'));return}const text=await file.text();void run('import',()=>importTranscript(id,text))}}/></label></div>
   <small>{data.can_fetch?w('Only the caption text is downloaded. Sites without captions need a subtitle file.','يُنزَّل نص الترجمة فقط. المواقع التي بلا ترجمة تحتاج ملف ترجمة.'):w('This file is on your PC, so import its subtitle file.','هذا الملف على جهازك، لذا استورد ملف ترجمته.')}</small>
  </div>}
  {lines.length>0&&<>
   <div className="transcript-tools">
    <input type="search" placeholder={w('Search the words…','ابحث في الكلمات…')} value={query} onChange={e=>setQuery(e.target.value)} aria-label={w('Search transcript','ابحث في النص')}/>
    <label className="inspector-check"><input type="checkbox" checked={onlyClip} onChange={e=>setOnlyClip(e.target.checked)}/>{w('This clip only','هذا المقطع فقط')}</label>
   </div>
   <p className="transcript-meta">{lines.length} {w('lines','سطر')}{data?.language?` · ${data.language}`:''} · {data?.source==='auto'?w('automatic captions','ترجمة تلقائية'):data?.source==='import'?w('imported','مستوردة'):data?.source==='file'?w('saved with the download','محفوظة مع التنزيل'):w('subtitles','ترجمة')}</p>
   <ol className="transcript-lines" ref={list}>{shown.map(({line,i})=>{const inside=line.end>s.start&&line.start<s.end;return <li key={i} data-line={i} className={`${i===now?'current':''} ${picked.has(i)?'picked':''} ${inside?'':'outside'}`}>
    <input type="checkbox" aria-label={w('Select line','حدد السطر')} checked={picked.has(i)} onClick={e=>{e.stopPropagation();toggle(i,e.shiftKey)}} readOnly/>
    <button className="line-time" dir="ltr" onClick={()=>inside?seek(active,Math.max(s.start,line.start)):notify(w('That line is outside this clip. Trim the clip to include it.','هذا السطر خارج المقطع. وسّع المقطع ليشمله.'))}>{clock(line.start)}</button>
    <span dir="auto" onClick={e=>toggle(i,e.shiftKey)}>{line.text}</span>
   </li>})}{!shown.length&&<li className="outside"><span>{w('No lines match.','لا توجد أسطر مطابقة.')}</span></li>}</ol>
   <div className="transcript-actions">
    {picked.size>0?<><b>{picked.size} {w('selected','محدد')}</b><button className="secondary compact" onClick={()=>cut(false)}>{w('Cut these lines','قص هذه الأسطر')}</button><button className="secondary compact" onClick={()=>cut(true)}>{w('Keep only these','أبقِ هذه فقط')}</button><button className="ghost compact" onClick={()=>setPicked(new Set())}>{w('Clear','مسح')}</button></>:<small>{w('Tick lines (Shift for a range) to cut or keep them.','حدد أسطرًا (Shift لنطاق) لقصها أو إبقائها.')}</small>}
   </div>
   <div className="transcript-captions">
    <button className="primary compact" onClick={captions}>{picked.size?w('Captions from selection','ترجمة من التحديد'):w('Add captions to this clip','أضف الترجمة للمقطع')}</button>
    <label className="inspector-check"><input type="checkbox" checked={phrases} onChange={e=>setPhrases(e.target.checked)}/>{w('Short phrases','عبارات قصيرة')}</label>
    <select aria-label={w('Caption style','نمط الترجمة')} value={project.caption_style||'classic'} onChange={e=>change('caption_style',e.target.value)}><option value="classic">{w('Classic','كلاسيكي')}</option><option value="bold">{w('Bold','عريض')}</option><option value="highlight">{w('Highlight','مميز')}</option><option value="boxed">{w('Boxed','داخل مربع')}</option><option value="karaoke">{w('Karaoke (word by word)','كاريوكي (كلمة بكلمة)')}</option><option value="pop">{w('Pop (word by word)','قفز (كلمة بكلمة)')}</option></select>
   </div>
   <div className="transcript-footer"><a className="ghost compact link-button" href={transcriptFile(id,'srt')} download>{w('Save .srt','حفظ ‎.srt')}</a><a className="ghost compact link-button" href={transcriptFile(id,'txt')} download>{w('Save text','حفظ النص')}</a><button className="ghost compact" disabled={!!busy} onClick={()=>void removeTranscript(id).then(setData).catch(e=>fail(String(e)))}>{w('Remove transcript','إزالة النص')}</button></div>
  </>}
 </div>
}
