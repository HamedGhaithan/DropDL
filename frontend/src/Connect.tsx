import {useEffect,useRef,useState} from 'react'
import {dismissFirewallHint,disconnectYouTube,getPhoneStatus,getYouTubeStatus,PhoneStatus,Preferences,removePhone,renewPhoneCode,setPhoneEnabled,YouTubeStatus} from './api'
import {Icon} from './visuals'
import BrowserInbox from './BrowserInbox'
import Subscriptions from './Subscriptions'
import {Language} from './i18n'

function ago(seconds:number|null|undefined,lang:Language){
  if(!seconds)return lang==='ar'?'لم يتصل بعد':'never'
  const s=Math.max(0,Date.now()/1000-seconds)
  if(s<90)return lang==='ar'?'الآن':'just now'
  const m=Math.round(s/60);if(m<60)return lang==='ar'?`قبل ${m} د`:`${m} min ago`
  const h=Math.round(m/60);if(h<48)return lang==='ar'?`قبل ${h} س`:`${h} h ago`
  const d=Math.round(h/24);return lang==='ar'?`قبل ${d} يوم`:`${d} days ago`
}
const clock=(s:number)=>`${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}`

export default function Connect({lang,preferences,onPreferences,onLink}:{lang:Language;preferences:Preferences|null;onPreferences:(changes:Partial<Preferences>)=>Promise<void>;onLink:(url:string)=>void}){
  const L=(en:string,ar:string)=>lang==='ar'?ar:en
  const [phone,setPhone]=useState<PhoneStatus|null>(null)
  const [address,setAddress]=useState('')
  const [yt,setYt]=useState<YouTubeStatus|null>(null)
  const [busy,setBusy]=useState('')
  const [error,setError]=useState('')
  const [notice,setNotice]=useState('')
  const [left,setLeft]=useState(0)
  const native=window.pywebview?.api
  const desktop=!!native?.youtube_sign_in
  const alive=useRef(true)

  async function act(name:string,run:()=>Promise<void>){setBusy(name);setError('');try{await run()}catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy('')}}
  async function refreshPhone(){try{const s=await getPhoneStatus(address);if(alive.current){setPhone(s);setLeft(s.pairing.expires_in)}}catch(e){if(alive.current)setError(e instanceof Error?e.message:String(e))}}
  async function refreshYouTube(){try{const s=await getYouTubeStatus();if(alive.current)setYt(s)}catch{/* shown elsewhere */}}

  useEffect(()=>{alive.current=true;void refreshPhone();const id=setInterval(()=>void refreshPhone(),4000);return()=>{alive.current=false;clearInterval(id)}// eslint-disable-next-line react-hooks/exhaustive-deps
  },[address])
  useEffect(()=>{const id=setInterval(()=>setLeft(v=>Math.max(0,v-1)),1000);return()=>clearInterval(id)},[])
  useEffect(()=>{if(left===0&&phone?.running)void refreshPhone()// eslint-disable-next-line react-hooks/exhaustive-deps
  },[left])
  useEffect(()=>{void refreshYouTube()
    const on=(event:Event)=>{const detail=(event as CustomEvent<{ok:boolean;status?:YouTubeStatus;error?:string}>).detail
      if(detail?.ok&&detail.status){setYt(detail.status);setNotice(L('YouTube is connected. Downloads on this PC and from your phone now use your sign-in.','تم ربط يوتيوب. ستستخدم التنزيلات على هذا الكمبيوتر ومن هاتفك تسجيل دخولك.'))}
      else if(detail?.error)setError(detail.error)}
    window.addEventListener('dropdl:youtube',on);return()=>window.removeEventListener('dropdl:youtube',on)// eslint-disable-next-line react-hooks/exhaustive-deps
  },[])

  const on=!!phone?.enabled, running=!!phone?.running
  const phoneCount=(n:number)=>lang==='ar'?(n===0?'لا هواتف متصلة':n===1?'هاتف واحد متصل':`${n} هواتف متصلة`):(n===0?'No phones online':n===1?'1 phone online':`${n} phones online`)
  const toggle=(key:'clipboard_watch'|'notify_done',value:boolean)=>act(key,async()=>{await onPreferences({[key]:value});if(key==='clipboard_watch')await native?.configure_clipboard?.(value,lang)})

  const phoneCard=<section className="connect-card phone-card" aria-labelledby="phone-title">
    <div className="card-head">
      <span className="card-icon gradient"><Icon name="phone" size={22}/></span>
      <div><h3 id="phone-title">{L('Phone Link','ربط الهاتف')}</h3><p>{L('Start downloads from your phone. This PC does the work, with your YouTube sign-in, and you save the result to the phone.','ابدأ التنزيل من هاتفك. هذا الكمبيوتر يقوم بالعمل بتسجيل دخولك في يوتيوب، ثم تحفظ الملف على الهاتف.')}</p></div>
      <label className="switch" title={on?L('Turn off','إيقاف'):L('Turn on','تشغيل')}><input type="checkbox" role="switch" checked={on} disabled={!phone||busy==='enable'} onChange={e=>void act('enable',async()=>setPhone(await setPhoneEnabled(e.target.checked)))}/><span/></label>
    </div>
    {!phone&&<p className="muted small" role="status">{L('Checking Phone Link…','جارٍ التحقق من ربط الهاتف…')}</p>}
    {phone&&!on&&<div className="phone-off">
      <ul className="benefits">
        <li><Icon name="down" size={17}/>{L('Share a YouTube link from your phone and it downloads here','شارك رابط يوتيوب من هاتفك ليُنزَّل هنا')}</li>
        <li><Icon name="play" size={17}/>{L('Watch progress live, then play or save the file on the phone','تابع التقدم مباشرة ثم شغّل الملف أو احفظه على الهاتف')}</li>
        <li><Icon name="shield" size={17}/>{L('Home network only, paired phones only. Nothing is exposed to the internet','الشبكة المنزلية فقط وللهواتف المرتبطة فقط. لا شيء مكشوف للإنترنت')}</li>
      </ul>
      <button className="primary big" disabled={!phone||busy==='enable'} onClick={()=>void act('enable',async()=>setPhone(await setPhoneEnabled(true)))}><Icon name="phone" size={18}/>{busy==='enable'?L('Starting…','جارٍ التشغيل…'):L('Turn on Phone Link','شغّل ربط الهاتف')}</button>
    </div>}
    {on&&!running&&<div className="connect-error" role="alert"><strong>{L('Phone Link could not start.','تعذر تشغيل ربط الهاتف.')}</strong> <span>{phone?.error}</span> <button className="secondary compact" onClick={()=>void act('enable',async()=>setPhone(await setPhoneEnabled(true)))}>{L('Try again','حاول مجددًا')}</button></div>}
    {on&&running&&phone&&<div className="phone-on">
      <div className="qr-block">
        {phone.pairing.qr?<div className="qr" role="img" aria-label={L('Pairing code for your phone camera','رمز الربط لكاميرا الهاتف')} dangerouslySetInnerHTML={{__html:phone.pairing.qr}}/>:<div className="qr empty"><Icon name="wifi" size={36}/><span>{L('Connect this PC to Wi-Fi','صِل الكمبيوتر بشبكة Wi-Fi')}</span></div>}
        <div className="pair-code" dir="ltr">{phone.pairing.code}</div>
        <div className="pair-meta"><span>{L('New code in','رمز جديد خلال')} <b dir="ltr">{clock(left)}</b></span><button className="ghost compact" onClick={()=>void act('renew',async()=>{const s=await renewPhoneCode();setPhone(s);setLeft(s.pairing.expires_in)})}><Icon name="retry" size={14}/>{L('New code','رمز جديد')}</button></div>
      </div>
      <div className="phone-side">
        <ol className="pair-steps">
          <li>{L('Connect your phone to the same Wi-Fi as this PC.','صِل هاتفك بشبكة Wi-Fi نفسها التي يستخدمها هذا الكمبيوتر.')}</li>
          <li>{L('Point the phone’s camera at the code and open the link.','وجّه كاميرا الهاتف إلى الرمز وافتح الرابط.')}</li>
          <li>{L('Paste or share links on the phone. Downloads appear here too.','الصق الروابط أو شاركها على الهاتف. ستظهر التنزيلات هنا أيضًا.')}</li>
        </ol>
        {phone.addresses.length>0&&<div className="address-row"><span className="eyebrow">{L('Address','العنوان')}</span>
          <div className="address-chips">{phone.addresses.map(a=><button key={a.url} className={`chip ${phone.chosen===a.ip?'selected':''}`} onClick={()=>setAddress(a.ip)} title={a.kind==='vpn'?L('VPN adapter — only works if the phone is on the same VPN','محول VPN — يعمل فقط إن كان الهاتف على شبكة VPN نفسها'):undefined}>
            <Icon name={a.kind==='tailscale'||a.kind==='vpn'?'globe':'wifi'} size={14}/><span>{a.label||(a.kind==='tailscale'?'Tailscale':'LAN')}</span><code dir="ltr">{a.ip}</code></button>)}</div>
          <p className="muted small">{L('Or type it on the phone:','أو اكتبه على الهاتف:')} <code dir="ltr">{phone.addresses.find(a=>a.ip===phone.chosen)?.url||phone.addresses[0].url}</code> {L('and enter the code above.','ثم أدخل الرمز أعلاه.')}</p></div>}
        {phone.firewall_hint&&<div className="connect-note"><Icon name="shield" size={16}/><span>{L('If Windows asks about the firewall, allow DropDL on private networks so your phone can reach it.','إن سألك Windows عن جدار الحماية، اسمح لـ DropDL على الشبكات الخاصة ليصل إليه هاتفك.')}</span><button className="ghost compact" onClick={()=>void act('hint',async()=>setPhone(await dismissFirewallHint()))}>{L('Got it','حسنًا')}</button></div>}
      </div>
    </div>}
    {on&&phone&&phone.devices.length>0&&<div className="devices">
      <span className="eyebrow">{L('Paired phones','الهواتف المرتبطة')}</span>
      {phone.devices.map(d=><div className="device" key={d.id}><span className={`device-dot ${d.online?'online':''}`}/><Icon name="phone" size={18}/><div><strong dir="auto">{d.name}</strong><small>{d.online?L('Connected now','متصل الآن'):`${L('Last seen','آخر ظهور')} ${ago(d.last_seen,lang)}`}</small></div>
        <button className="ghost compact danger-text" onClick={()=>void act('remove',async()=>setPhone(await removePhone(d.id)))}>{L('Remove','إزالة')}</button></div>)}
    </div>}
    {on&&<p className="muted small away"><Icon name="globe" size={14}/>{L('Away from home? Install Tailscale on this PC and your phone; its address appears above.','خارج المنزل؟ ثبّت Tailscale على الكمبيوتر والهاتف وسيظهر عنوانه أعلاه.')}</p>}
  </section>

  const signedIn=!!yt?.signed_in
  const ytCard=<section className="connect-card" aria-labelledby="yt-title">
    <div className="card-head">
      <span className="card-icon red"><Icon name="play" size={20}/></span>
      <div><h3 id="yt-title">{L('YouTube account','حساب يوتيوب')}</h3><p>{L('YouTube asks downloaders to sign in. DropDL keeps the session in its own window, never your everyday browser, and stores only youtube.com cookies on this PC.','يطلب يوتيوب تسجيل الدخول للتنزيل. يحتفظ DropDL بالجلسة في نافذته الخاصة لا في متصفحك المعتاد، ويخزّن ملفات تعريف youtube.com فقط على هذا الكمبيوتر.')}</p></div>
      <span className={`state-pill ${signedIn?'good':''}`}>{signedIn?L('Signed in','مسجّل'):yt?.configured?L('Cookies saved','ملفات محفوظة'):L('Not connected','غير مرتبط')}</span>
    </div>
    {signedIn&&<dl className="yt-facts"><div><dt>{L('Source','المصدر')}</dt><dd>{yt?.source==='signin'?L('DropDL sign-in window','نافذة تسجيل DropDL'):L('Imported cookies.txt','ملف cookies.txt مستورد')}</dd></div>
      <div><dt>{L('Updated','آخر تحديث')}</dt><dd>{ago(yt?.updated_at,lang)}</dd></div>
      {yt?.expires_at&&<div><dt>{L('Session valid until','الجلسة صالحة حتى')}</dt><dd>{new Date(yt.expires_at*1000).toLocaleDateString(lang==='ar'?'ar':'en',{dateStyle:'medium'})}</dd></div>}</dl>}
    <div className="button-row wrap">
      {desktop&&<button className="primary" disabled={busy==='signin'} onClick={()=>void act('signin',async()=>{await native!.youtube_sign_in!(lang);setNotice(L('Sign in to YouTube in the window that opened. DropDL saves the session and closes it for you.','سجّل الدخول إلى يوتيوب في النافذة التي فُتحت. سيحفظ DropDL الجلسة ويغلقها لك.'))})}><Icon name="account" size={17}/>{signedIn?L('Sign in again','سجّل الدخول مجددًا'):L('Connect YouTube','اربط يوتيوب')}</button>}
      {desktop&&signedIn&&yt?.source==='signin'&&<button className="secondary" disabled={busy==='refresh'} onClick={()=>void act('refresh',async()=>{const r=await native!.youtube_refresh!();if(r.refreshed)setNotice(L('Session refreshed.','تم تحديث الجلسة.'));else setError(L('The sign-in window has no YouTube session any more. Sign in again.','لم تعد نافذة تسجيل الدخول تحتوي على جلسة يوتيوب. سجّل الدخول مجددًا.'));await refreshYouTube()})}><Icon name="retry" size={16}/>{L('Refresh session','حدّث الجلسة')}</button>}
      {native?.choose_cookies&&<button className="secondary" onClick={()=>void act('import',async()=>{if(await native.choose_cookies!())await refreshYouTube()})}><Icon name="folder" size={16}/>{L('Import cookies.txt','استيراد cookies.txt')}</button>}
      {yt?.configured&&<button className="ghost danger-text" disabled={busy==='disconnect'} onClick={()=>void act('disconnect',async()=>{setYt(native?.youtube_disconnect?await native.youtube_disconnect():await disconnectYouTube())})}>{L('Disconnect','فصل')}</button>}
    </div>
    {!desktop&&<p className="muted small">{L('Open the DropDL desktop app to sign in with its built-in window.','افتح تطبيق DropDL على سطح المكتب لتسجيل الدخول عبر نافذته المدمجة.')}</p>}
    <p className="muted small">{L('If Google says this browser is not supported, export cookies.txt from your browser and use Import cookies.txt. A spare Google account is the safest choice for downloading.','إن قالت Google إن هذا المتصفح غير مدعوم، صدّر cookies.txt من متصفحك واستخدم «استيراد cookies.txt». حساب Google احتياطي هو الخيار الأكثر أمانًا للتنزيل.')}</p>
  </section>

  const helpersCard=<section className="connect-card" aria-labelledby="helpers-title">
    <div className="card-head"><span className="card-icon violet"><Icon name="bolt" size={20}/></span><div><h3 id="helpers-title">{L('Smart helpers','مساعدات ذكية')}</h3><p>{L('DropDL notices what you are doing and offers the next step.','يلاحظ DropDL ما تفعله ويقترح الخطوة التالية.')}</p></div></div>
    <label className="helper-row"><span className="helper-icon"><Icon name="clipboard" size={18}/></span><span><strong>{L('Offer copied links','اقتراح الروابط المنسوخة')}</strong><small>{L('Copy a video link anywhere and DropDL offers to download it. Links stay on this PC.','انسخ رابط فيديو من أي مكان وسيعرض DropDL تنزيله. تبقى الروابط على هذا الكمبيوتر.')}</small></span>
      <span className="switch small"><input type="checkbox" role="switch" checked={preferences?.clipboard_watch!==false} disabled={!preferences||!native?.configure_clipboard} onChange={e=>void toggle('clipboard_watch',e.target.checked)}/><span/></span></label>
    <label className="helper-row"><span className="helper-icon"><Icon name="bell" size={18}/></span><span><strong>{L('Notify when downloads finish','إشعار عند انتهاء التنزيلات')}</strong><small>{L('A Windows notification when DropDL is in the background. Click it to open the file’s task.','إشعار من Windows عندما يعمل DropDL في الخلفية. انقر عليه لفتح المهمة.')}</small></span>
      <span className="switch small"><input type="checkbox" role="switch" checked={preferences?.notify_done!==false} disabled={!preferences} onChange={e=>void toggle('notify_done',e.target.checked)}/><span/></span></label>
    {!native&&<p className="muted small">{L('These work in the DropDL desktop app.','تعمل هذه في تطبيق DropDL على سطح المكتب.')}</p>}
  </section>

  return <div className="connect">
    <header className="connect-hero">
      <div><span className="eyebrow">{L('New in DropDL 3.0','جديد في DropDL 3.0')}</span><h2>{L('Your downloads, everywhere','تنزيلاتك في كل مكان')}</h2>
        <p>{L('Use DropDL from your phone, keep YouTube signed in, and catch links the moment you copy them.','استخدم DropDL من هاتفك، وأبقِ يوتيوب مسجّلًا، والتقط الروابط لحظة نسخها.')}</p></div>
      <div className="hero-status">
        <span className={`hero-chip ${running?'good':''}`}><Icon name="phone" size={15}/>{running?phoneCount(phone?.devices.filter(d=>d.online).length||0):L('Phone Link off','ربط الهاتف متوقف')}</span>
        <span className={`hero-chip ${signedIn?'good':''}`}><Icon name="account" size={15}/>{signedIn?L('YouTube signed in','يوتيوب مسجّل'):L('YouTube not connected','يوتيوب غير مرتبط')}</span>
      </div>
    </header>
    {error&&<div className="error-card" role="alert"><div><strong>{L('Something needs attention','شيء يحتاج إلى انتباه')}</strong><p dir="auto">{error}</p></div><button className="ghost compact" onClick={()=>setError('')}>{L('Dismiss','إغلاق')}</button></div>}
    {notice&&<div className="connect-notice" role="status"><Icon name="check" size={16}/><span>{notice}</span><button className="ghost compact" onClick={()=>setNotice('')}>{L('OK','حسنًا')}</button></div>}
    <div className="connect-grid">
      {phoneCard}
      <div className="connect-column">{ytCard}{helpersCard}</div>
      <section className="connect-card wide" aria-label={L('Browser and subscriptions','المتصفح والاشتراكات')}>
        <div className="card-head"><span className="card-icon blue"><Icon name="globe" size={20}/></span><div><h3>{L('Browser extension & subscriptions','إضافة المتصفح والاشتراكات')}</h3><p>{L('Send pages from your browser, and download new uploads from playlists and channels automatically.','أرسل الصفحات من متصفحك ونزّل الإصدارات الجديدة من القوائم والقنوات تلقائيًا.')}</p></div></div>
        <BrowserInbox lang={lang} onLink={onLink}/><Subscriptions lang={lang}/>
      </section>
    </div>
  </div>
}
