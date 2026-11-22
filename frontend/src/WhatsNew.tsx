import {useEffect,useRef} from 'react'
import {Logo,Icon} from './visuals'
type Props={lang:string;onClose:()=>void;onStudio:()=>void;onNewProject:()=>void}
const TILES:[string,string,string,string,string][]=[
 ['studio','New project, no clip needed','مشروع جديد بلا مقاطع','A Studio home with templates, recent projects and Download & edit.','صفحة استوديو بقوالب ومشاريع حديثة وتنزيل وتحرير.'],
 ['silence','Cuts the silences for you','يقص الصمت عنك','Pauses and scene changes found and cut in one click.','يجد فترات الصمت وتغيّر المشاهد ويقصها بنقرة.'],
 ['text','Edit by transcript','التحرير بالنص','Delete a sentence and the video is cut to match.','احذف جملة فيُقص الفيديو ليطابقها.'],
 ['words','Word-by-word captions','ترجمة كلمة بكلمة','Karaoke and pop styles that follow every spoken word.','أنماط كاريوكي وقفز تتبع كل كلمة منطوقة.'],
 ['beat','Cut to the beat','القص على الإيقاع','Finds the tempo of your music and lands every cut on a beat.','يجد إيقاع موسيقاك ويضع كل قطع على نبضة.'],
 ['motion','Looks, motion and titles','مظاهر وحركة وعناوين','Ten looks, Ken Burns moves, animated titles, picture in picture.','عشرة مظاهر وحركة بطيئة وعناوين متحركة وصورة داخل صورة.'],
 ['gpu','Exports 3× faster','تصدير أسرع بثلاث مرات','Your graphics card encodes, tuned to match x264 quality.','بطاقة الرسوميات تُرمّز بجودة تطابق x264.'],
 ['phone','Phone Link','ربط الهاتف','Send a link from your phone; your PC downloads it.','أرسل رابطًا من هاتفك فينزله جهازك.'],
 ['account','YouTube in one click','يوتيوب بنقرة','Sign in once inside DropDL. No more cookies.txt.','سجّل الدخول مرة داخل DropDL دون cookies.txt.'],
]
/** A one-time showcase of what DropDL 3.0 adds, shown after the update (and from the command palette). */
export default function WhatsNew({lang,onClose,onStudio,onNewProject}:Props){
 const w=(en:string,ar:string)=>lang==='ar'?ar:en,panel=useRef<HTMLElement>(null)
 useEffect(()=>{panel.current?.querySelector<HTMLElement>('.whats-new-actions .primary')?.focus();const key=(e:KeyboardEvent)=>{if(e.key==='Escape')onClose()};window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key)},[])
 return <div className="whats-new-backdrop" onClick={onClose}><section ref={panel} className="whats-new" role="dialog" aria-modal="true" aria-labelledby="whats-new-title" onClick={e=>e.stopPropagation()} dir={lang==='ar'?'rtl':'ltr'}>
  <button className="icon-button whats-new-close" aria-label={w('Close','إغلاق')} onClick={onClose}><Icon name="close"/></button>
  <header className="whats-new-hero"><div className="whats-new-logo"><Logo/></div><span className="eyebrow">{w('New in DropDL 3.0','الجديد في DropDL 3.0')}</span><h2 id="whats-new-title">{w('From link to finished video, in one app.','من الرابط إلى فيديو جاهز، في تطبيق واحد.')}</h2><p>{w('Clip Studio is now a studio of its own, and DropDL reaches your phone.','أصبح استوديو القص استوديو قائمًا بذاته، ووصل DropDL إلى هاتفك.')}</p></header>
  <ul className="whats-new-grid">{TILES.map(([icon,en,ar,den,dar],i)=><li key={icon} style={{animationDelay:`${80+i*45}ms`}}><i className={`wn-icon ${icon}`} aria-hidden="true"/><b>{w(en,ar)}</b><span>{w(den,dar)}</span></li>)}</ul>
  <footer className="whats-new-actions"><button className="primary" onClick={()=>{onClose();onNewProject()}}><Icon name="plus" size={16}/>{w('Start a new project','ابدأ مشروعًا جديدًا')}</button><button className="secondary" onClick={()=>{onClose();onStudio()}}>{w('Open Clip Studio','افتح استوديو القص')}</button><button className="ghost" onClick={onClose}>{w('Later','لاحقًا')}</button></footer>
 </section></div>
}
