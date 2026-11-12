import {useEffect,useState} from 'react'
export function parseClipTime(raw:string):number|null {
  const text=raw.trim().replace(/[٠-٩۰-۹]/g,ch=>String('٠١٢٣٤٥٦٧٨٩'.indexOf(ch)>=0?'٠١٢٣٤٥٦٧٨٩'.indexOf(ch):'۰۱۲۳۴۵۶۷۸۹'.indexOf(ch))).replace('٫','.')
  if(!/^\d+(?::\d{1,2}){0,2}(?:\.\d{1,3})?$/.test(text))return null
  const parts=text.split(':').map(Number)
  if(parts.length>1&&parts.slice(1).some(n=>n>=60))return null
  const value=parts.reduce((sum,n)=>sum*60+n,0)
  return Number.isFinite(value)?value:null
}
export function clipClock(seconds:number):string {
  const ticks=Math.round(Math.max(0,Number.isFinite(seconds)?seconds:0)*10)
  const h=Math.floor(ticks/36000),m=Math.floor(ticks%36000/600),s=Math.floor(ticks%600/10)
  return `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}.${ticks%10}`
}
export default function ClipTimeInput({value,onChange,label,lang,onValid}:{value:number;onChange:(n:number)=>void;label:string;lang:'en'|'ar';onValid:(valid:boolean)=>void}) {
  const [text,setText]=useState(clipClock(value)),[focused,setFocused]=useState(false)
  const valid=parseClipTime(text)!==null
  useEffect(()=>{if(!focused){setText(clipClock(value));onValid(true)}},[value,focused])
  return <><input aria-label={label} aria-invalid={!valid} dir="ltr" type="text" placeholder="HH:MM:SS.s" value={text} onFocus={()=>setFocused(true)} onChange={e=>{setText(e.target.value);const n=parseClipTime(e.target.value);onValid(n!==null);if(n!==null)onChange(n)}} onBlur={()=>{if(valid){setFocused(false);setText(clipClock(value))}}}/><small className="muted">{lang==='ar'?'ساعة:دقيقة:ثانية، أو أدخل الثواني (مثال: 29.9)':'HH:MM:SS.s, or enter seconds (e.g. 29.9)'}</small>{!valid&&<small role="alert" className="job-error">{lang==='ar'?'أدخل وقتًا صحيحًا':'Enter a valid timestamp'}</small>}</>
}
