// DropDL Phone Link: a remote for DropDL on your PC. No framework, no build step.
const app = document.getElementById('app');

// ---------------------------------------------------------------- words
const WORDS = {
  en: {
    connectTitle: 'Connect to your PC', connectBody: 'Use this phone to download on your PC, then save the result here.',
    step1: 'Open DropDL on your PC and choose Connect.', step2: 'Turn on Phone Link.', step3: 'Scan the code with this phone’s camera, or type it below.',
    codeLabel: 'Code shown on your PC', nameLabel: 'Name this phone (optional)', namePlaceholder: 'My phone', connect: 'Connect', connecting: 'Connecting…',
    connected: 'Connected to {pc}', badCode: 'Enter the 8-character code shown on your PC.',
    getTitle: 'Download anything', getBody: 'Paste or share a link. Your PC downloads it with its own connection and YouTube sign-in.',
    linkPlaceholder: 'Paste a link (YouTube, Vimeo, SoundCloud…)', paste: 'Paste', clear: 'Clear',
    looking: 'Looking up the link…', video: 'Video', audio: 'Audio', best: 'Best', downloadOnPc: 'Download on PC',
    started: 'Started on your PC', youtubeHint: 'YouTube needs your sign-in. On your PC, open DropDL → Connect → Connect YouTube.',
    notALink: 'That does not look like a link. Copy the address of a video or song and paste it here.',
    tryAgain: 'Try again', live: 'Live streams cannot be downloaded from here.',
    tabGet: 'Download', tabActivity: 'Activity', tabLibrary: 'Library',
    recent: 'Recent', fromPc: 'Sent from your PC', everything: 'All downloads',
    noActivity: 'Nothing here yet. Downloads you start on this phone or on your PC appear here.',
    waiting: 'Waiting', downloading: 'Downloading', finishing: 'Finishing', paused: 'Paused', stopping: 'Stopping', ready: 'Ready', failed: 'Failed', cancelled: 'Cancelled',
    save: 'Save to phone', play: 'Play', retry: 'Retry', cancel: 'Cancel', done: 'Done', left: 'left',
    fromPhone: 'From a phone', fromThisPhone: 'This phone',
    search: 'Search the library on your PC', more: 'Show more', emptyLibrary: 'No files found on your PC.', loading: 'Loading…',
    menu: 'Menu', language: 'العربية', unpair: 'Disconnect this phone', unpairAsk: 'Disconnect this phone from {pc}? You can pair again any time.',
    tipsTitle: 'Send links faster', tipAndroid: 'Android: in YouTube tap Share → Copy link, then paste it here. Add this page to your home screen (browser menu → Add to Home screen) to open DropDL in one tap.',
    tipIphone: 'iPhone: in the Shortcuts app make a shortcut that receives URLs from the Share Sheet and opens this address with the link added:',
    tipInstall: 'Install DropDL from your browser menu to see it in the share sheet.',
    offline: 'Can’t reach your PC. Make sure DropDL is open and this phone is on the same Wi-Fi.',
    genericError: 'Something went wrong. Try again.', close: 'Close', version: 'DropDL {version} on {pc}',
    sizeApprox: '≈ {size}',
  },
  ar: {
    connectTitle: 'اتصل بجهاز الكمبيوتر', connectBody: 'استخدم هذا الهاتف للتنزيل على جهاز الكمبيوتر، ثم احفظ الملف هنا.',
    step1: 'افتح DropDL على الكمبيوتر واختر «اتصال».', step2: 'شغّل «ربط الهاتف».', step3: 'امسح الرمز بكاميرا هذا الهاتف، أو اكتبه بالأسفل.',
    codeLabel: 'الرمز الظاهر على الكمبيوتر', nameLabel: 'اسم هذا الهاتف (اختياري)', namePlaceholder: 'هاتفي', connect: 'اتصال', connecting: 'جارٍ الاتصال…',
    connected: 'متصل بـ {pc}', badCode: 'أدخل الرمز المكوّن من 8 أحرف الظاهر على الكمبيوتر.',
    getTitle: 'نزّل أي شيء', getBody: 'الصق رابطًا أو شاركه. يقوم الكمبيوتر بالتنزيل باتصاله وتسجيل دخوله في يوتيوب.',
    linkPlaceholder: 'الصق رابطًا (يوتيوب، فيميو، ساوندكلاود…)', paste: 'لصق', clear: 'مسح',
    looking: 'جارٍ فحص الرابط…', video: 'فيديو', audio: 'صوت', best: 'الأفضل', downloadOnPc: 'نزّل على الكمبيوتر',
    started: 'بدأ التنزيل على الكمبيوتر', youtubeHint: 'يوتيوب يحتاج إلى تسجيل دخولك. على الكمبيوتر افتح DropDL ← اتصال ← ربط يوتيوب.',
    notALink: 'هذا لا يبدو رابطًا. انسخ عنوان فيديو أو مقطع صوتي والصقه هنا.',
    tryAgain: 'حاول مجددًا', live: 'لا يمكن تنزيل البث المباشر من هنا.',
    tabGet: 'تنزيل', tabActivity: 'النشاط', tabLibrary: 'المكتبة',
    recent: 'الأحدث', fromPc: 'أُرسل من الكمبيوتر', everything: 'كل التنزيلات',
    noActivity: 'لا شيء بعد. ستظهر هنا التنزيلات التي تبدؤها من الهاتف أو الكمبيوتر.',
    waiting: 'بالانتظار', downloading: 'جارٍ التنزيل', finishing: 'جارٍ الإنهاء', paused: 'متوقف مؤقتًا', stopping: 'جارٍ الإيقاف', ready: 'جاهز', failed: 'فشل', cancelled: 'أُلغي',
    save: 'احفظ على الهاتف', play: 'تشغيل', retry: 'إعادة المحاولة', cancel: 'إلغاء', done: 'تم', left: 'متبقٍ',
    fromPhone: 'من هاتف', fromThisPhone: 'هذا الهاتف',
    search: 'ابحث في مكتبة الكمبيوتر', more: 'عرض المزيد', emptyLibrary: 'لا توجد ملفات على الكمبيوتر.', loading: 'جارٍ التحميل…',
    menu: 'القائمة', language: 'English', unpair: 'افصل هذا الهاتف', unpairAsk: 'فصل هذا الهاتف عن {pc}؟ يمكنك الربط مجددًا في أي وقت.',
    tipsTitle: 'أرسل الروابط أسرع', tipAndroid: 'أندرويد: في يوتيوب اضغط مشاركة ← نسخ الرابط، ثم الصقه هنا. أضف هذه الصفحة إلى الشاشة الرئيسية (قائمة المتصفح ← إضافة إلى الشاشة الرئيسية) لفتح DropDL بلمسة.',
    tipIphone: 'آيفون: في تطبيق «الاختصارات» أنشئ اختصارًا يستقبل الروابط من ورقة المشاركة ويفتح هذا العنوان مع الرابط:',
    tipInstall: 'ثبّت DropDL من قائمة المتصفح ليظهر في قائمة المشاركة.',
    offline: 'تعذّر الوصول إلى الكمبيوتر. تأكد أن DropDL مفتوح وأن الهاتف على شبكة Wi-Fi نفسها.',
    genericError: 'حدث خطأ. حاول مجددًا.', close: 'إغلاق', version: 'DropDL {version} على {pc}',
    sizeApprox: '≈ {size}',
  },
};
let lang = 'en';
try { lang = localStorage.getItem('dropdl.lang') || ((navigator.language || '').toLowerCase().startsWith('ar') ? 'ar' : 'en'); } catch { /* storage may be blocked */ }
const t = (key, vars = {}) => (WORDS[lang][key] ?? WORDS.en[key] ?? key).replace(/\{(\w+)\}/g, (_, name) => vars[name] ?? '');
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const ltr = value => `<bdi dir="ltr">${esc(value)}</bdi>`;

const ICON = {
  link: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 14a4.5 4.5 0 0 0 6.4 0l3-3a4.5 4.5 0 0 0-6.4-6.4l-1 1"/><path d="M14 10a4.5 4.5 0 0 0-6.4 0l-3 3a4.5 4.5 0 0 0 6.4 6.4l1-1"/></svg>',
  down: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v11"/><path d="m7 11 5 5 5-5"/><path d="M5 20h14"/></svg>',
  pulse: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h4l3-8 4 16 3-8h4"/></svg>',
  library: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="3"/><path d="m10 9 5 3-5 3z"/></svg>',
  film: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="3"/><path d="m10 9.5 4.5 2.5L10 14.5z"/></svg>',
  music: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18V6l11-2v12"/><circle cx="6.5" cy="18" r="2.5"/><circle cx="17.5" cy="16" r="2.5"/></svg>',
  play: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5.5v13l11-6.5z"/></svg>',
  save: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v11"/><path d="m7 11 5 5 5-5"/><path d="M5 20h14"/></svg>',
  retry: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12a8 8 0 1 0 2.4-5.7L4 8.5"/><path d="M4 3.5v5h5"/></svg>',
  x: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg>',
  menu: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M4 7h16M4 12h16M4 17h16"/></svg>',
  search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>',
  info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/></svg>',
  check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>',
  pc: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/></svg>',
};

// ---------------------------------------------------------------- helpers
const bytes = n => {
  if (!n || n <= 0) return '';
  const u = ['B', 'KB', 'MB', 'GB', 'TB']; let i = 0; let v = n;
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return `${v >= 100 || i === 0 ? Math.round(v) : v.toFixed(1)} ${u[i]}`;
};
const clock = s => {
  if (!s && s !== 0) return '';
  s = Math.round(s); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), sec = s % 60;
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}` : `${m}:${String(sec).padStart(2, '0')}`;
};
const firstUrl = text => (String(text || '').match(/https?:\/\/[^\s<>"']+/i) || [''])[0].replace(/[),.;!?]+$/, '');

async function api(path, { method = 'GET', body } = {}) {
  const response = await fetch('/api' + path, {
    method, credentials: 'same-origin', cache: 'no-store',
    headers: body ? { 'content-type': 'application/json' } : {}, body: body ? JSON.stringify(body) : undefined,
  });
  let data = null;
  try { data = await response.json(); } catch { /* empty body */ }
  if (!response.ok) {
    const error = new Error(typeof data?.detail === 'string' ? data.detail : t('genericError'));
    error.status = response.status; throw error;
  }
  return data;
}

let toastTimer;
function toast(message, bad = false) {
  document.querySelector('.toast')?.remove();
  const node = document.createElement('div');
  node.className = 'toast' + (bad ? ' bad' : ''); node.setAttribute('role', 'status');
  node.innerHTML = (bad ? ICON.info : ICON.check) + `<span>${esc(message)}</span>`;
  document.body.appendChild(node);
  clearTimeout(toastTimer); toastTimer = setTimeout(() => node.remove(), 3400);
}

function applyLang() {
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
}

// ---------------------------------------------------------------- state
const S = {
  session: null, tab: 'get', online: true,
  link: '', info: null, infoState: 'idle', infoError: '', mode: 'video', quality: 'best', audio: 'mp3',
  jobs: [], inbox: [], lib: { q: '', items: [], total: 0, loading: false, loaded: false },
};

// ---------------------------------------------------------------- pairing
function renderPair(error = '', busy = false) {
  app.innerHTML = `
  <main class="pair">
    <div class="pair-hero">
      <div class="art"><img src="logo.svg" alt="" width="64" height="64"></div>
      <h1>${t('connectTitle')}</h1>
      <p>${t('connectBody')}</p>
    </div>
    <section class="card">
      <ol class="steps"><li>${t('step1')}</li><li>${t('step2')}</li><li>${t('step3')}</li></ol>
    </section>
    <form class="card" id="pairform" autocomplete="off">
      <div class="field"><label for="code">${t('codeLabel')}</label>
        <div class="code"><input id="code" name="code" maxlength="9" inputmode="text" autocapitalize="characters" spellcheck="false" placeholder="XXXX-XXXX" required></div></div>
      <div class="field"><label for="devname">${t('nameLabel')}</label><input id="devname" name="name" maxlength="60" placeholder="${t('namePlaceholder')}"></div>
      <button class="primary" type="submit" ${busy ? 'disabled' : ''}>${busy ? t('connecting') : t('connect')}</button>
      ${error ? `<p class="note" role="alert">${ICON.info}<span>${esc(error)}</span></p>` : ''}
    </form>
  </main>`;
  const code = document.getElementById('code');
  code.addEventListener('input', () => {
    const raw = code.value.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 8);
    code.value = raw.length > 4 ? `${raw.slice(0, 4)}-${raw.slice(4)}` : raw;
  });
  document.getElementById('pairform').addEventListener('submit', event => {
    event.preventDefault();
    const raw = code.value.replace(/[^A-Za-z0-9]/g, '');
    if (raw.length !== 8) { renderPair(t('badCode')); return; }
    pair(raw, document.getElementById('devname').value);
  });
}

async function pair(code, name, automatic = false) {
  if (!automatic) renderPair('', true);
  try {
    await api('/pair', { method: 'POST', body: { code, name } });
    S.session = await api('/session');
    toast(t('connected', { pc: S.session.pc }));
    renderMain(); poll(true);
  } catch (error) { renderPair(error.message); }
}

// ---------------------------------------------------------------- shell
function renderMain() {
  app.innerHTML = `
  <header class="top">
    <div class="brand"><img src="logo.svg" alt="">DropDL</div>
    <div class="pc-chip" id="pc">${ICON.pc}<span>${esc(S.session.pc)}</span><i class="dot" id="pcdot"></i></div>
    <button class="icon-btn" data-action="menu" aria-label="${t('menu')}">${ICON.menu}</button>
  </header>
  <div id="offline"></div>
  <main id="view"></main>
  <div class="tabs"><nav aria-label="DropDL">
    <button data-tab="get">${ICON.down}<span>${t('tabGet')}</span></button>
    <button data-tab="activity">${ICON.pulse}<span>${t('tabActivity')}</span><b class="count" id="activecount" hidden></b></button>
    <button data-tab="library">${ICON.library}<span>${t('tabLibrary')}</span></button>
  </nav></div>`;
  renderTab();
}

function renderTab() {
  listState.clear();
  document.querySelectorAll('.tabs button').forEach(b => b.setAttribute('aria-current', b.dataset.tab === S.tab ? 'page' : 'false'));
  const view = document.getElementById('view');
  if (S.tab === 'get') {
    view.innerHTML = `
    <section class="card">
      <h1>${t('getTitle')}</h1><p>${t('getBody')}</p>
      <form class="linkbox mt16" id="linkform">${ICON.link}
        <input id="link" type="url" inputmode="url" enterkeyhint="go" autocomplete="off" autocorrect="off" spellcheck="false" placeholder="${esc(t('linkPlaceholder'))}" value="${esc(S.link)}">
        <button type="button" class="pill-btn" id="linkbtn"></button>
      </form>
      <div id="preview"></div>
    </section>
    <div id="recentwrap"></div>
    ${tips()}`;
    const input = document.getElementById('link');
    input.addEventListener('input', () => { S.link = input.value; updateLinkButton(); scheduleAnalyze(); });
    document.getElementById('linkform').addEventListener('submit', event => { event.preventDefault(); analyze(); input.blur(); });
    updateLinkButton(); renderPreview(); renderJobs();
  } else if (S.tab === 'activity') {
    view.innerHTML = `<div id="inboxwrap"></div><h2>${t('everything')}</h2><div id="jobs"></div>`;
    renderJobs();
  } else {
    view.innerHTML = `
    <form class="linkbox" id="libform" role="search">${ICON.search}
      <input id="libq" type="search" enterkeyhint="search" placeholder="${esc(t('search'))}" value="${esc(S.lib.q)}" autocomplete="off">
    </form>
    <div id="lib" class="mt14"></div>`;
    const q = document.getElementById('libq');
    let timer;
    q.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(() => loadLibrary(q.value), 300); });
    document.getElementById('libform').addEventListener('submit', event => { event.preventDefault(); loadLibrary(q.value); q.blur(); });
    if (!S.lib.loaded) loadLibrary(S.lib.q); else renderLibrary();
  }
}

function updateLinkButton() {
  const button = document.getElementById('linkbtn');
  if (!button) return;
  const canPaste = !!(navigator.clipboard && window.isSecureContext);
  if (S.link) { button.textContent = t('clear'); button.dataset.action = 'clear'; button.hidden = false; }
  else { button.textContent = t('paste'); button.dataset.action = 'paste'; button.hidden = !canPaste; }
}

function tips() {
  const shortcut = `${location.origin}/?url=`;
  return `<details class="tips card"><summary>${ICON.info}${t('tipsTitle')}</summary>
    <div class="stack small"><p>${window.isSecureContext ? t('tipInstall') : t('tipAndroid')}</p>
    <p>${t('tipIphone')}</p><p class="mono">${esc(shortcut)}[Shortcut Input]</p></div></details>`;
}

// ---------------------------------------------------------------- analyse a link
let analyzeTimer, analyzeSeq = 0;
function scheduleAnalyze() {
  clearTimeout(analyzeTimer);
  const url = firstUrl(S.link);
  if (!url) { S.info = null; S.infoState = S.link.trim() ? 'notlink' : 'idle'; renderPreview(); return; }
  analyzeTimer = setTimeout(analyze, 450);
}

async function analyze() {
  const url = firstUrl(S.link);
  if (!url) { S.infoState = S.link.trim() ? 'notlink' : 'idle'; renderPreview(); return; }
  if (S.info && S.info._for === url && S.infoState === 'ready') return;
  const seq = ++analyzeSeq;
  S.infoState = 'loading'; S.info = null; renderPreview();
  try {
    const info = await api('/info', { method: 'POST', body: { url } });
    if (seq !== analyzeSeq) return;
    S.info = { ...info, _for: url }; S.infoState = 'ready'; S.quality = 'best';
  } catch (error) {
    if (seq !== analyzeSeq) return;
    S.infoState = 'error'; S.infoError = error.message;
  }
  renderPreview();
}

const isYouTube = info => /youtube|youtu\.be/i.test(`${info?.extractor || ''} ${info?.webpage_url || ''}`);

function qualityChoices(info) {
  const heights = [...new Set((info.heights || []).filter(h => h >= 144))].sort((a, b) => b - a);
  const picks = heights.filter(h => [4320, 2160, 1440, 1080, 720, 480, 360].includes(h)).slice(0, 4);
  const sizes = info.sizes || {};
  const best = Math.max(0, ...Object.values(sizes));
  return [{ id: 'best', label: t('best'), size: best }, ...picks.map(h => ({ id: `${h}p`, label: h >= 2160 ? (h === 2160 ? '4K' : `${h}p`) : `${h}p`, size: sizes[`${h}p`] }))];
}

function renderPreview() {
  const box = document.getElementById('preview');
  if (!box) return;
  if (S.infoState === 'idle') { box.innerHTML = ''; return; }
  if (S.infoState === 'notlink') { box.innerHTML = `<p class="note info">${ICON.info}<span>${t('notALink')}</span></p>`; return; }
  if (S.infoState === 'loading') {
    box.innerHTML = `<div class="preview mt18" aria-busy="true"><div class="thumb skeleton"></div>
      <div><div class="skeleton sk sk90"></div><div class="skeleton sk sk60 mt8"></div>
      <p class="small mt10">${t('looking')}</p></div></div>`;
    return;
  }
  if (S.infoState === 'error') {
    box.innerHTML = `<p class="note" role="alert">${ICON.info}<span>${esc(S.infoError)}</span></p>
      <button class="ghost mt12 w100" data-action="analyze">${ICON.retry}${t('tryAgain')}</button>`;
    return;
  }
  const info = S.info;
  const qualities = qualityChoices(info);
  if (!qualities.some(q => q.id === S.quality)) S.quality = 'best';
  const audioSize = info.audio_size;
  box.innerHTML = `
    <div class="preview mt18">
      <div class="thumb">${info.thumbnail ? `<img src="${esc(info.thumbnail)}" alt="" referrerpolicy="no-referrer">` : ''}${info.duration ? `<span class="len">${clock(info.duration)}</span>` : ''}</div>
      <div><div class="title" dir="auto">${esc(info.title)}</div>
        <div class="meta">${info.uploader ? `<span dir="auto">${esc(info.uploader)}</span>` : ''}<span>${esc(info.extractor || '')}</span></div></div>
    </div>
    <div class="seg" role="group">
      <button data-action="mode" data-mode="video" aria-pressed="${S.mode === 'video'}">${ICON.film}${t('video')}</button>
      <button data-action="mode" data-mode="audio" aria-pressed="${S.mode === 'audio'}">${ICON.music}${t('audio')}</button>
    </div>
    <div class="chips">${S.mode === 'video'
      ? qualities.map(q => `<button class="chip" data-action="quality" data-q="${q.id}" aria-pressed="${S.quality === q.id}"><b>${esc(q.label)}</b>${q.size ? `<small>${t('sizeApprox', { size: bytes(q.size) })}</small>` : ''}</button>`).join('')
      : [['mp3', 'MP3'], ['m4a', 'M4A'], ['opus', 'Opus']].map(([id, label]) => `<button class="chip" data-action="audiofmt" data-f="${id}" aria-pressed="${S.audio === id}"><b>${label}</b>${audioSize ? `<small>${t('sizeApprox', { size: bytes(audioSize) })}</small>` : ''}</button>`).join('')}
    </div>
    ${info.is_live ? `<p class="note">${ICON.info}<span>${t('live')}</span></p>` : ''}
    ${isYouTube(info) && !S.session?.youtube ? `<p class="note">${ICON.info}<span>${t('youtubeHint')}</span></p>` : ''}
    <button class="primary" data-action="download" ${info.is_live ? 'disabled' : ''}>${ICON.down}${t('downloadOnPc')}</button>`;
}

async function startDownload(button) {
  if (!S.info) return;
  button.disabled = true;
  const named = { title: S.info.title || '', thumbnail: S.info.thumbnail || '' };
  const body = S.mode === 'audio'
    ? { url: S.info._for, kind: 'audio', container: S.audio, quality: 'best', ...named }
    : { url: S.info._for, kind: 'video', container: 'mp4', quality: S.quality, ...named };
  try {
    const job = await api('/download', { method: 'POST', body });
    toast(t('started'));
    S.jobs = [job, ...S.jobs.filter(j => j.id !== job.id)];
    S.link = ''; S.info = null; S.infoState = 'idle';
    renderTab(); poll(true);
  } catch (error) { toast(error.message, true); button.disabled = false; }
}

// ---------------------------------------------------------------- jobs
const ACTIVE = new Set(['queued', 'downloading', 'processing', 'preparing', 'paused', 'cancelling', 'scheduled', 'retrying']);
function statusOf(job) {
  const s = job.status;
  if (s === 'completed') return ['done', t('ready')];
  if (s === 'failed') return ['bad', t('failed')];
  if (s === 'cancelled') return ['wait', t('cancelled')];
  if (s === 'cancelling') return ['wait', t('stopping')];
  if (s === 'paused') return ['wait', t('paused')];
  if (s === 'queued' || s === 'scheduled') return ['wait', t('waiting')];
  if (s === 'processing' || job.phase === 'processing' || job.phase === 'merging') return ['', t('finishing')];
  return ['', t('downloading')];
}

function jobCard(job) {
  const [cls, label] = statusOf(job);
  const active = ACTIVE.has(job.status) && job.status !== 'paused';
  const audio = job.kind === 'audio';
  const detail = esc(detailOf(job));
  const origin = job.mine ? `<span class="badge phone">${t('fromThisPhone')}</span>` : job.from_phone ? `<span class="badge phone">${t('fromPhone')}</span>` : '';
  const thumb = job.thumbnail && !audio ? `<img src="${esc(job.thumbnail)}" alt="" referrerpolicy="no-referrer">` : (audio ? ICON.music : ICON.film);
  let actions = '';
  if (job.status === 'completed') {
    actions = `<a class="ghost ok" href="/api/jobs/${esc(job.id)}/file" download>${ICON.save}${t('save')}</a>
      <button class="ghost" data-action="play" data-src="/api/jobs/${esc(job.id)}/file?inline=1" data-kind="${audio ? 'audio' : 'video'}" data-title="${esc(job.title || job.filename || '')}">${ICON.play}${t('play')}</button>`;
  } else if (job.status === 'failed' || job.status === 'cancelled') {
    actions = `<button class="ghost go" data-action="retry" data-id="${esc(job.id)}">${ICON.retry}${t('retry')}</button>`;
  } else if (job.status !== 'cancelling') {
    actions = `<button class="ghost warn" data-action="cancel" data-id="${esc(job.id)}">${ICON.x}${t('cancel')}</button>`;
  }
  return `<article class="job" data-id="${esc(job.id)}">
    <div class="thumb ${job.thumbnail && !audio ? '' : 'audio'}">${thumb}</div>
    <div><div class="title" dir="auto">${esc(job.title || job.filename || job.url)}</div>
      <div class="status"><span class="badge ${cls}">${label}</span>${origin}<span class="detail" dir="${job.status === 'failed' ? 'auto' : 'ltr'}">${detail}</span></div>
      ${active ? `<div class="bar ${job.percent ? '' : 'indef'}"><i data-w="${barWidth(job)}"></i></div>` : ''}
    </div>
    ${actions ? `<div class="actions">${actions}</div>` : ''}
  </article>`;
}

function detailOf(job) {
  const active = ACTIVE.has(job.status) && job.status !== 'paused';
  if (job.status === 'completed') return [job.container?.toUpperCase(), bytes(job.size)].filter(Boolean).join(' · ');
  if (job.status === 'failed') return hintFor(job);
  if (active && job.percent) return [`${Math.round(job.percent)}%`, job.speed ? `${bytes(job.speed)}/s` : '', job.eta ? `${clock(job.eta)} ${t('left')}` : ''].filter(Boolean).join(' · ');
  return '';
}
const barWidth = job => Math.max(3, Math.min(100, job.percent || 0));
function applyBars(root) { root.querySelectorAll('.bar i[data-w]').forEach(i => { i.style.width = `${i.dataset.w}%`; }); }

function hintFor(job) {
  if (job.error_code === 'bot_check' || job.error_code === 'authentication') return t('youtubeHint');
  return job.error || t('genericError');
}

function inboxCard(item) {
  const audio = /\.(mp3|m4a|opus|flac|wav|aac|ogg)$/i.test(item.title || '');
  return `<article class="job" data-inbox="${esc(item.id)}">
    <div class="thumb audio">${audio ? ICON.music : ICON.film}</div>
    <div><div class="title" dir="auto">${esc(item.title)}</div><div class="status"><span class="badge done">${t('fromPc')}</span><span dir="ltr">${bytes(item.size)}</span></div></div>
    <div class="actions"><a class="ghost ok" href="/api/inbox/${esc(item.id)}/file" download data-action="inboxsave" data-id="${esc(item.id)}">${ICON.save}${t('save')}</a>
      <button class="ghost" data-action="play" data-src="/api/inbox/${esc(item.id)}/file?inline=1" data-kind="${audio ? 'audio' : 'video'}" data-title="${esc(item.title)}">${ICON.play}${t('play')}</button>
      <button class="ghost" data-action="inboxdone" data-id="${esc(item.id)}" aria-label="${t('done')}">${ICON.check}</button></div>
  </article>`;
}

const keyOf = job => [job.id, job.status, job.mine, job.from_phone, job.thumbnail, job.phase === 'processing', !!job.percent].join('|');
const listState = new Map();
function patchList(container, jobs, empty = '') {
  const key = jobs.map(keyOf).join(';') + lang;
  const previous = listState.get(container.id);
  if (previous === key && container.childElementCount) {
    for (const job of jobs) {
      const card = container.querySelector(`[data-id="${CSS.escape(job.id)}"]`);
      if (!card) continue;
      const detail = card.querySelector('.detail');
      const text = detailOf(job);
      if (detail && detail.textContent !== text) detail.textContent = text;
      const bar = card.querySelector('.bar i');
      if (bar) bar.style.width = `${barWidth(job)}%`;
    }
    return;
  }
  listState.set(container.id, key);
  container.innerHTML = jobs.length ? jobs.map(jobCard).join('') : empty;
  applyBars(container);
}

function renderJobs() {
  const activeCount = S.jobs.filter(j => ACTIVE.has(j.status)).length;
  const badge = document.getElementById('activecount');
  if (badge) { badge.hidden = !(activeCount || S.inbox.length); badge.textContent = activeCount || S.inbox.length; }
  const recent = document.getElementById('recentwrap');
  if (recent) {
    const mine = S.jobs.filter(j => j.mine).slice(0, 3);
    if (!mine.length) { recent.innerHTML = ''; listState.delete('recentlist'); }
    else {
      if (!document.getElementById('recentlist')) { recent.innerHTML = `<h2>${t('recent')}</h2><div id="recentlist"></div>`; listState.delete('recentlist'); }
      patchList(document.getElementById('recentlist'), mine);
    }
  }
  const inbox = document.getElementById('inboxwrap');
  if (inbox) {
    const html = S.inbox.length ? `<h2>${t('fromPc')}</h2>${S.inbox.map(inboxCard).join('')}` : '';
    if (listState.get('inboxwrap') !== html) { inbox.innerHTML = html; listState.set('inboxwrap', html); }
  }
  const list = document.getElementById('jobs');
  if (list) patchList(list, S.jobs, `<div class="card empty">${ICON.pulse}<p>${t('noActivity')}</p></div>`);
}

let pollTimer, polling = false;
async function poll(now = false) {
  clearTimeout(pollTimer);
  if (!now && document.hidden) { pollTimer = setTimeout(poll, 4000); return; }
  if (polling) return;
  polling = true;
  try {
    const data = await api('/jobs');
    S.jobs = data.jobs; S.inbox = data.inbox; setOnline(true); renderJobs();
  } catch (error) {
    if (error.status === 401) { S.session = { ...S.session, paired: false }; renderPair(); polling = false; return; }
    setOnline(false);
  }
  polling = false;
  const busy = S.jobs.some(j => ACTIVE.has(j.status));
  pollTimer = setTimeout(poll, busy ? 1500 : 6000);
}

function setOnline(online) {
  if (S.online === online) return;
  S.online = online;
  document.getElementById('pcdot')?.classList.toggle('off', !online);
  const box = document.getElementById('offline');
  if (box) box.innerHTML = online ? '' : `<p class="note offline" role="alert">${ICON.info}<span>${t('offline')}</span></p>`;
}

// ---------------------------------------------------------------- library
async function loadLibrary(q, more = false) {
  S.lib.q = q; S.lib.loading = true;
  if (!more) renderLibrary();
  try {
    const data = await api(`/library?q=${encodeURIComponent(q)}&offset=${more ? S.lib.items.length : 0}&limit=30`);
    S.lib.items = more ? [...S.lib.items, ...data.items] : data.items; S.lib.total = data.total; S.lib.loaded = true;
  } catch (error) { toast(error.message, true); }
  S.lib.loading = false; renderLibrary();
}

function renderLibrary() {
  const box = document.getElementById('lib');
  if (!box) return;
  if (S.lib.loading && !S.lib.items.length) { box.innerHTML = `<p class="center small">${t('loading')}</p>`; return; }
  if (!S.lib.items.length) { box.innerHTML = `<div class="card empty">${ICON.library}<p>${t('emptyLibrary')}</p></div>`; return; }
  box.innerHTML = S.lib.items.map(item => {
    const audio = item.kind === 'audio';
    return `<article class="media">
      <div class="thumb ${audio ? 'audio' : ''}">${audio ? ICON.music : `<img src="/api/library/${esc(item.id)}/thumbnail" alt="" loading="lazy">`}</div>
      <div><div class="title" dir="auto">${esc(item.title)}</div><div class="meta"><span dir="ltr">${bytes(item.size)}</span>${item.site ? `<span>${esc(item.site)}</span>` : ''}</div></div>
      <div class="row">
        <button class="icon-btn" data-action="play" data-src="/api/library/${esc(item.id)}/file?inline=1" data-kind="${audio ? 'audio' : 'video'}" data-title="${esc(item.title)}" aria-label="${t('play')}">${ICON.play}</button>
        <a class="icon-btn" href="/api/library/${esc(item.id)}/file" download aria-label="${t('save')}">${ICON.save}</a>
      </div></article>`;
  }).join('') + (S.lib.items.length < S.lib.total ? `<button class="ghost w100 mt12" data-action="more">${t('more')}</button>` : '');
}

// ---------------------------------------------------------------- sheets
function sheet(html) {
  closeSheet();
  const node = document.createElement('div');
  node.className = 'sheet'; node.id = 'sheet';
  node.innerHTML = `<div class="panel" role="dialog" aria-modal="true">${html}</div>`;
  node.addEventListener('click', event => { if (event.target === node) closeSheet(); });
  document.body.appendChild(node);
  return node;
}
function closeSheet() {
  const node = document.getElementById('sheet');
  node?.querySelectorAll('video,audio').forEach(media => media.pause());
  node?.remove();
}
function openPlayer(src, kind, title) {
  const media = kind === 'audio' ? `<audio controls autoplay src="${esc(src)}"></audio>` : `<video controls autoplay playsinline src="${esc(src)}"></video>`;
  sheet(`<div class="bar-row"><strong dir="auto">${esc(title)}</strong><button class="icon-btn" data-action="closesheet" aria-label="${t('close')}">${ICON.x}</button></div>${media}`);
}
function openMenu() {
  sheet(`<div class="bar-row"><strong>DropDL</strong><button class="icon-btn" data-action="closesheet" aria-label="${t('close')}">${ICON.x}</button></div>
    <div class="stack mt14">
      <button class="ghost w100" data-action="lang">${t('language')}</button>
      <button class="ghost warn w100" data-action="unpair">${t('unpair')}</button>
      <p class="small center">${t('version', { version: esc(S.session.version), pc: esc(S.session.pc) })}</p>
    </div>`);
}

// ---------------------------------------------------------------- events
document.addEventListener('click', async event => {
  const tab = event.target.closest('[data-tab]');
  if (tab) { S.tab = tab.dataset.tab; renderTab(); if (S.tab !== 'library') poll(true); window.scrollTo({ top: 0 }); return; }
  const el = event.target.closest('[data-action]');
  if (!el) return;
  const action = el.dataset.action;
  if (action === 'paste') {
    try { S.link = firstUrl(await navigator.clipboard.readText()) || ''; const input = document.getElementById('link'); if (input) input.value = S.link; updateLinkButton(); analyze(); } catch { /* permission denied */ }
  } else if (action === 'clear') {
    S.link = ''; S.info = null; S.infoState = 'idle'; const input = document.getElementById('link'); if (input) { input.value = ''; input.focus(); } updateLinkButton(); renderPreview();
  } else if (action === 'analyze') { S.info = null; analyze(); }
  else if (action === 'mode') { S.mode = el.dataset.mode; renderPreview(); }
  else if (action === 'quality') { S.quality = el.dataset.q; renderPreview(); }
  else if (action === 'audiofmt') { S.audio = el.dataset.f; renderPreview(); }
  else if (action === 'download') startDownload(el);
  else if (action === 'cancel' || action === 'retry') {
    el.disabled = true;
    try { await api(`/jobs/${el.dataset.id}/${action}`, { method: 'POST' }); poll(true); } catch (error) { toast(error.message, true); el.disabled = false; }
  } else if (action === 'play') { openPlayer(el.dataset.src, el.dataset.kind, el.dataset.title); }
  else if (action === 'inboxdone') {
    try { S.inbox = (await api(`/inbox/${el.dataset.id}/done`, { method: 'POST' })).inbox; renderJobs(); } catch (error) { toast(error.message, true); }
  } else if (action === 'more') { loadLibrary(S.lib.q, true); }
  else if (action === 'menu') { openMenu(); }
  else if (action === 'closesheet') { closeSheet(); }
  else if (action === 'lang') {
    lang = lang === 'ar' ? 'en' : 'ar'; try { localStorage.setItem('dropdl.lang', lang); } catch { /* ignore */ }
    applyLang(); closeSheet(); renderMain();
  } else if (action === 'unpair') {
    if (!confirm(t('unpairAsk', { pc: S.session.pc }))) return;
    try { await api('/unpair', { method: 'POST' }); } catch { /* already gone */ }
    closeSheet(); S.session = { ...S.session, paired: false }; renderPair();
  }
});
// Broken thumbnails fall back to an icon (inline handlers are blocked by the page's security policy).
document.addEventListener('error', event => {
  const img = event.target;
  if (img instanceof HTMLImageElement && img.closest('.thumb')) { const box = img.closest('.thumb'); box.classList.add('audio'); box.innerHTML = ICON.film; }
}, true);
document.addEventListener('visibilitychange', () => { if (!document.hidden && S.session?.paired) poll(true); });
// A pairing link opened while this page is already showing (only the #pair= part changes).
window.addEventListener('hashchange', () => {
  const code = new URLSearchParams(location.hash.slice(1)).get('pair');
  if (!code) return;
  history.replaceState(null, '', '/');
  if (!S.session?.paired) { renderPair('', true); pair(code, '', true); }
});
document.addEventListener('keydown', event => { if (event.key === 'Escape') closeSheet(); });

// ---------------------------------------------------------------- start
function sharedLink() {
  const params = new URLSearchParams(location.search);
  return firstUrl(params.get('url')) || firstUrl(params.get('text')) || firstUrl(params.get('title')) || '';
}

async function boot() {
  applyLang();
  const shared = sharedLink();
  const code = new URLSearchParams(location.hash.slice(1)).get('pair');
  if (location.search || location.hash) history.replaceState(null, '', '/');
  try { S.session = await api('/session'); }
  catch (error) {
    app.innerHTML = `<main class="pair"><div class="pair-hero"><div class="art"><img src="logo.svg" alt=""></div><h1>DropDL</h1><p>${t('offline')}</p></div>
      <button class="primary" data-action="reload">${ICON.retry}${t('tryAgain')}</button></main>`;
    app.querySelector('[data-action=reload]').addEventListener('click', () => location.reload());
    return;
  }
  if (!S.session.paired && code) { renderPair('', true); await pair(code, '', true); if (!S.session.paired) return; }
  if (!S.session.paired) { renderPair(); return; }
  if (shared) S.link = shared;
  renderMain();
  if (S.link) analyze();
  poll(true);
  if ('serviceWorker' in navigator && window.isSecureContext) navigator.serviceWorker.register('sw.js').catch(() => {});
}
boot();
