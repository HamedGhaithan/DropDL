import {useEffect, useRef, useState} from 'react'
import {Language, translate} from './i18n'
const titles = ['newDownload','chooseSource','chooseOutput','destination','clipMaker','downloads'] as const
const targets = ['tour-add','tour-source','tour-output','tour-destination','tour-clip','tour-queue']
export default function Tour({step,lang,move,finish}:{step:number;lang:Language;move:(step:number)=>void;finish:()=>void}) {
  const [rect,setRect]=useState({top:0,left:0,width:0,height:0})
  const next=useRef<HTMLButtonElement>(null)
  const t=(key:Parameters<typeof translate>[1])=>translate(lang,key)
  useEffect(()=>{
    const target=document.getElementById(targets[step]); target?.scrollIntoView({block:'center',behavior:'instant'})
    const update=()=>{const r=target?.getBoundingClientRect();if(r)setRect({top:r.top-6,left:r.left-6,width:r.width+12,height:r.height+12})}
    const frame=requestAnimationFrame(update);window.addEventListener('resize',update);window.addEventListener('scroll',update,true);next.current?.focus()
    return()=>{cancelAnimationFrame(frame);window.removeEventListener('resize',update);window.removeEventListener('scroll',update,true)}
  },[step])
  const width=Math.min(360,window.innerWidth-28)
  const left=Math.min(Math.max(14,rect.left),window.innerWidth-width-14)
  const top=rect.top+rect.height+16+240<window.innerHeight ? rect.top+rect.height+16 : Math.max(14,rect.top-246)
  return <div className="tour-overlay" onKeyDown={e=>{if(e.key==='Escape')finish();if(e.key==='Tab'){const buttons=[...e.currentTarget.querySelectorAll<HTMLButtonElement>('button:not(:disabled)')];const index=buttons.indexOf(document.activeElement as HTMLButtonElement);e.preventDefault();buttons[(index+(e.shiftKey?-1:1)+buttons.length)%buttons.length]?.focus()}}}><div className="tour-shade"/><div className="tour-highlight" style={rect}/><section className="tour-card" role="dialog" aria-modal="true" aria-labelledby="tour-title" style={{top,left,width}}><span className="eyebrow">{t('tourStep')} {step+1} {t('tourOf')} 6</span><div className="tour-step-content" key={step}><h2 id="tour-title">{t(titles[step])}</h2><p>{t(`tour${step+1}` as 'tour1')}</p></div><div className="tour-dots">{targets.map((_,i)=><i key={i} className={i===step?'active':''}/>)}</div><div className="tour-actions"><button className="ghost" onClick={finish}>{t('skip')}</button><div>{step>0&&<button className="secondary" onClick={()=>move(step-1)}>{t('previous')}</button>}<button ref={next} className="primary" onClick={()=>step===5?finish():move(step+1)}>{t(step===5?'done':'next')}</button></div></div></section></div>
}
