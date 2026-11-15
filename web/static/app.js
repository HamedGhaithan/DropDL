// DropDL Web: the page. Plain ES modules, no build step. All text from other sites is inserted with textContent only.
import { t, getLang, setLang, detectLang, applyStatic, fmtBytes, fmtRate, fmtDuration, errorText, ltr } from './i18n.js';

const REPO = 'https://github.com/HamedGhaithan/DropDL';
const FINAL = ['done', 'error', 'cancelled', 'expired'];
const MAX_JOBS = 12;

const $ = (selector, root = document) => root.querySelector(selector);
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const store = {
  get(key, fallback) { try { const v = localStorage.getItem(`dropdl.${key}`); return v == null ? fallback : JSON.parse(v); } catch { return fallback; } },
  set(key, value) { try { localStorage.setItem(`dropdl.${key}`, JSON.stringify(value)); } catch { /* private mode: fine */ } },
};

function el(tag, attrs = {}, ...kids) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value == null || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? '' : String(value));
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) node.append(kid.nodeType ? kid : document.createTextNode(kid));
  return node;
}
function icon(name, cls = '') {
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('class', `i ${cls}`.trim());
  svg.setAttribute('aria-hidden', 'true');
  const use = document.createElementNS(ns, 'use');
  use.setAttribute('href', `#i-${name}`);
  svg.append(use);
  return svg;
}

const S = {
  health: null,
  auth: { required: false, ok: true },
  info: null,
  opt: { kind: 'video', height: null, fmt: { video: 'mp4', audio: 'mp3' }, start: '', end: '', trimOpen: false },
  jobs: store.get('jobs', []),
  timers: new Map(),
};
const limits = () => (S.health && S.health.limits) || {};
const ctx = () => ({ maxSize: limits().max_filesize, maxDuration: limits().max_duration });

// ------------------------------------------------------------------ talking to the server
async function api(path, { method = 'GET', body, timeout = 70000 } = {}) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeout);
  let res;
  try {
    res = await fetch(path, { method, signal: ctl.signal, cache: 'no-store',
      headers: body ? { 'Content-Type': 'application/json' } : undefined, body: body ? JSON.stringify(body) : undefined });
  } catch {
    throw { code: 'offline', status: 0 };
  } finally {
    clearTimeout(timer);
  }
  if (res.status === 204) return null;
  let data = null;
  try { data = await res.json(); } catch { /* not JSON */ }
  if (!res.ok) {
    const e = (data && data.error) || {};
    if (e.code === 'unauthorized' && S.auth.required) { S.auth.ok = false; applyAuth(); }       // the sign-in expired
    throw { code: e.code || 'failed', message: e.message, status: res.status, retryAfter: Number(res.headers.get('Retry-After')) || 0 };
  }
  return data;
}

// ------------------------------------------------------------------ notices
function showNotice(kind, text, action) {
  const box = $('#notice');
  box.replaceChildren();
  const node = el('div', { class: 'notice', 'data-kind': kind, role: kind === 'error' ? 'alert' : null }, el('span', { text }));
  if (action) node.append(action);
  box.append(node);
}
const clearNotice = () => $('#notice').replaceChildren();
const desktopButton = () => el('a', { class: 'btn sm', href: `${REPO}/releases/latest`, rel: 'noopener' }, icon('download'), t('cta.btn'));

// ------------------------------------------------------------------ boot
async function boot() {
  setLang(detectLang(store.get('lang', null)));
  applyStatic();
  setTheme(store.get('theme', 'auto'));
  wire();
  wireAuth();
  renderJobs();
  setInterval(tick, 1000);
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => { /* optional */ });
  await loadHealth();
  applyAuth();
  if (!locked()) { resumeJobs(); openShared(); }
}

async function loadHealth() {
  const timer = setTimeout(() => showNotice('info', t('waking')), 3500);
  for (let attempt = 0; attempt < 9 && !S.health; attempt += 1) {
    try { S.health = await api('/api/health', { timeout: 15000 }); } catch { await sleep(Math.min(2000 + attempt * 1000, 6000)); }
  }
  clearTimeout(timer);
  clearNotice();
  if (!S.health) { showNotice('error', errorText({ code: 'offline' })); return; }
  S.auth = S.health.auth || { required: false, ok: true };
  renderStatic();
}

function renderStatic() {
  const h = S.health;
  if (!h) return;
  const L = h.limits;
  $('#limits').textContent = t('limits', { height: L.max_height, size: fmtBytes(L.max_filesize), duration: fmtDuration(L.max_duration), ttl: Math.round(L.ttl / 60) });
  const yt = $('#yt-hint');
  yt.hidden = h.youtube !== 'off';
  yt.textContent = t('youtube.off');
  $('#foot-version').textContent = `v${h.version}`;
  $('.cta').hidden = Boolean(h.auth && h.auth.required);     // the owner of a private instance doesn't need the pitch
  const contact = $('#foot-contact');
  contact.hidden = !h.contact;
  if (h.contact) $('#contact-link').setAttribute('href', h.contact);
}

function setTheme(mode) {
  document.documentElement.dataset.theme = mode;
  const dark = mode === 'dark' || (mode === 'auto' && matchMedia('(prefers-color-scheme: dark)').matches);
  $('#theme-icon use').setAttribute('href', dark ? '#i-sun' : '#i-moon');
  $('meta[name=theme-color]').setAttribute('content', dark ? '#080b12' : '#f4f6fb');
}

function wire() {
  $('#bar').addEventListener('submit', (e) => { e.preventDefault(); analyze($('#url').value); });
  $('#paste').addEventListener('click', pasteFromClipboard);
  $('#url').addEventListener('paste', () => setTimeout(() => { if (extractUrl($('#url').value)) analyze($('#url').value); }, 0));
  $('#lang').addEventListener('click', () => {
    const next = getLang() === 'ar' ? 'en' : 'ar';
    store.set('lang', next);
    setLang(next);
    applyStatic();
    renderStatic();
    if (S.info) renderResult();
    renderJobs(true);
  });
  $('#theme').addEventListener('click', () => {
    const current = document.documentElement.dataset.theme;
    const dark = current === 'dark' || (current === 'auto' && matchMedia('(prefers-color-scheme: dark)').matches);
    const next = dark ? 'light' : 'dark';
    store.set('theme', next);
    setTheme(next);
  });
}

async function pasteFromClipboard() {
  try {
    const text = await navigator.clipboard.readText();
    $('#url').value = text;
    if (extractUrl(text)) analyze(text);
  } catch {
    $('#url').focus();
    showNotice('info', t('paste.denied'));
  }
}

// ------------------------------------------------------------------ step 1: look up the link
function extractUrl(text) {
  const found = /https?:\/\/[^\s<>"']+/i.exec(text || '');
  if (found) return found[0].replace(/[),.;]+$/, '');
  const bare = (text || '').trim();
  return /^[\w-]+(\.[\w-]+)+(\/\S*)?$/.test(bare) ? `https://${bare}` : '';
}

async function analyze(raw) {
  const url = extractUrl(raw);
  clearNotice();
  if (!url) { showNotice('error', t('err.bad_url')); return; }
  $('#url').value = url;
  $('#go').disabled = true;
  $('#result').hidden = true;
  $('#skeleton').hidden = false;
  try {
    S.info = await api('/api/info', { method: 'POST', body: { url } });
    S.opt = { kind: S.info.has_video ? 'video' : 'audio', height: null, fmt: { video: 'mp4', audio: 'mp3' }, start: '', end: '', trimOpen: false };
    $('#skeleton').hidden = true;
    renderResult();
    $('#res-title').focus({ preventScroll: true });
    $('#result').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } catch (e) {
    $('#skeleton').hidden = true;
    S.info = null;
    showNotice('error', errorText(e, ctx()), ['youtube_off', 'youtube_blocked', 'playlist'].includes(e.code) ? desktopButton() : null);
  } finally {
    $('#go').disabled = false;
  }
}

// ------------------------------------------------------------------ step 2: choose what to get
function parseTime(text) {
  const s = (text || '').trim();
  if (!s) return null;
  if (!/^\d+(:\d{1,2}){0,2}(\.\d+)?$/.test(s)) return NaN;
  return s.split(':').map(Number).reduce((total, part) => total * 60 + part, 0);
}

function trimState() {
  const o = S.opt, L = limits(), i = S.info;
  const a = parseTime(o.start), b = parseTime(o.end);
  if (a === null && b === null) return { ok: true, none: true };
  if (Number.isNaN(a) || Number.isNaN(b)) return { ok: false, error: t('trim.bad') };
  const start = a ?? 0;
  let end = b;
  if (end === null) {
    if (!i.duration) return { ok: false, error: t('trim.needEnd') };
    end = i.duration;
  }
  if (i.duration) end = Math.min(end, i.duration);
  if (end <= start) return { ok: false, error: t('trim.order') };
  if (L.max_clip && end - start > L.max_clip) return { ok: false, error: t('trim.long', { max: fmtDuration(L.max_clip) }) };
  return { ok: true, start, end };
}

function clipFraction() {
  const tr = trimState();
  if (!tr.ok || tr.none || !S.info.duration) return 1;
  return Math.min(1, (tr.end - tr.start) / S.info.duration);
}

// What the finished audio file will weigh: MP3 is encoded at 192 kbit/s, WAV is 16-bit stereo, FLAC is about 60% of that.
function audioSize() {
  const i = S.info, secs = (i.duration || 0) * clipFraction();
  const byFormat = { mp3: 24000, wav: 176400, flac: 105000 }[S.opt.fmt.audio];
  if (secs && byFormat) return secs * byFormat;
  return i.audio_size == null ? null : i.audio_size * clipFraction();
}

function sizeFor(height) {
  const raw = o_kind() === 'audio' ? audioSize() : S.info.sizes[String(height)];
  return raw == null ? null : (o_kind() === 'audio' ? raw : raw * clipFraction());
}
const o_kind = () => S.opt.kind;
const tooBig = (height) => { const size = sizeFor(height); return size != null && size > limits().max_filesize; };

function ensureHeight() {
  const i = S.info, o = S.opt;
  if (o.kind !== 'video' || !i.heights.length) { o.height = null; return; }
  if (o.height && i.heights.includes(o.height) && !tooBig(o.height)) return;
  const ok = i.heights.filter((h) => !tooBig(h));
  const under = ok.filter((h) => h <= (limits().default_height || 720));
  o.height = under.length ? Math.max(...under) : ok.length ? Math.min(...ok) : Math.max(...i.heights);
}

function renderResult() {
  const i = S.info, box = $('#result');
  box.replaceChildren();
  box.hidden = false;
  const thumb = i.thumbnail
    ? el('img', { class: 'thumb', src: i.thumbnail, alt: '', referrerpolicy: 'no-referrer', loading: 'lazy', decoding: 'async' })
    : el('div', { class: 'thumb ph' }, icon(i.has_video ? 'video' : 'audio'));
  let host = '';
  try { host = ltr(new URL(i.url).hostname.replace(/^www\./, '')); } catch { host = ''; }
  const sub = [i.uploader, host, i.duration ? fmtDuration(i.duration) : ''].filter(Boolean).join(' · ');
  box.append(el('div', { class: 'res-head' }, thumb,
    el('div', { class: 'res-meta' }, el('h2', { id: 'res-title', class: 'res-title', dir: 'auto', tabindex: '-1', text: i.title || t('untitled') }),
      el('p', { class: 'res-sub', dir: 'auto', text: sub }))));
  if (i.too_long) box.append(el('p', { class: 'inline-note', 'data-kind': 'warn', text: errorText({ code: 'too_long' }, ctx()) }));
  box.append(el('div', { id: 'opts', class: 'opts' }));
  renderOptions();
}

function renderOptions(focusKey) {
  const i = S.info, o = S.opt, L = limits(), box = $('#opts');
  if (!box) return;
  ensureHeight();
  box.replaceChildren();

  const seg = el('div', { class: 'seg', role: 'radiogroup', 'aria-label': t('opt.kind') });
  for (const kind of ['video', 'audio']) {
    const disabled = (kind === 'video' && !i.has_video) || (kind === 'audio' && !i.has_audio);
    seg.append(el('button', { type: 'button', role: 'radio', 'aria-checked': String(o.kind === kind), disabled, 'data-key': `kind-${kind}`,
      onclick: () => { o.kind = kind; renderOptions(`kind-${kind}`); } }, icon(kind), t(`kind.${kind}`)));
  }
  box.append(el('div', { class: 'opt' }, seg));

  const chips = [];
  if (o.kind === 'video') {
    const heights = i.heights.length ? i.heights : [null];
    const group = el('div', { class: 'chips', role: 'group', 'aria-label': t('opt.quality') });
    for (const h of heights) {
      const sizeEl = el('small');
      const btn = el('button', { type: 'button', class: 'chip', 'data-key': `h-${h}`, onclick: () => { o.height = h; refreshChips(); updateSummary(); } },
        el('span', { text: h ? ltr(`${h}p`) : t('opt.best') }), sizeEl);
      chips.push({ h, btn, sizeEl });
      group.append(btn);
    }
    box.append(el('div', { class: 'opt' }, el('span', { class: 'opt-label', text: t('opt.quality') }), group));
  }

  const formats = o.kind === 'video' ? L.video_formats : L.audio_formats;
  const select = el('select', { id: 'fmt', 'data-key': 'fmt', onchange: (e) => { o.fmt[o.kind] = e.target.value; updateSummary(); } },
    (formats || []).map((f) => el('option', { value: f, text: f.toUpperCase(), selected: f === o.fmt[o.kind] })));
  select.setAttribute('dir', 'ltr');
  box.append(el('label', { class: 'opt', for: 'fmt' }, el('span', { class: 'opt-label', text: t('opt.format') }), select));

  const trimError = el('p', { class: 'field-error', id: 'trim-error', role: 'alert' });
  const startInput = el('input', { class: 'input', id: 'trim-start', inputmode: 'decimal', autocomplete: 'off', placeholder: '0:00', value: o.start, 'aria-describedby': 'trim-error',
    oninput: (e) => { o.start = e.target.value; onTrim(); } });
  const endInput = el('input', { class: 'input', id: 'trim-end', inputmode: 'decimal', autocomplete: 'off', placeholder: i.duration ? fmtDuration(i.duration) : '1:00', value: o.end, 'aria-describedby': 'trim-error',
    oninput: (e) => { o.end = e.target.value; onTrim(); } });
  const details = el('details', { class: 'trim', open: o.trimOpen, ontoggle: (e) => { o.trimOpen = e.target.open; } },
    el('summary', {}, icon('cut'), t('opt.trim')),
    el('div', { class: 'trim-grid' },
      el('label', { class: 'field', for: 'trim-start' }, el('span', { text: t('opt.start') }), startInput),
      el('label', { class: 'field', for: 'trim-end' }, el('span', { text: t('opt.end') }), endInput)),
    el('p', { class: 'hint', text: t('opt.trim.hint', { max: fmtDuration(L.max_clip) }) }), trimError);
  box.append(details);

  const summary = el('p', { class: 'summary', id: 'summary' });
  const go = el('button', { type: 'button', class: 'btn primary big', id: 'download', onclick: startJob }, icon('download'), t('btn.download'));
  box.append(el('div', { class: 'opt-foot' }, summary, go));

  function refreshChips() {
    for (const { h, btn, sizeEl } of chips) {
      const size = i.sizes[String(h)] == null ? null : i.sizes[String(h)] * clipFraction();
      const over = size != null && size > L.max_filesize;
      btn.disabled = over;
      btn.setAttribute('aria-pressed', String(o.height === h));
      btn.title = over ? t('opt.over', { size: fmtBytes(L.max_filesize) }) : '';
      sizeEl.textContent = size != null ? fmtBytes(size, true) : '';
    }
  }
  function onTrim() {
    const tr = trimState();
    trimError.textContent = tr.ok ? '' : tr.error;
    ensureHeight();
    refreshChips();
    updateSummary();
  }
  function updateSummary() {
    const tr = trimState(), parts = [];
    const size = o.kind === 'audio' ? audioSize() : (o.height ? sizeFor(o.height) : null);
    if (size != null) parts.push(fmtBytes(size, true));
    parts.push(ltr((o.fmt[o.kind] || '').toUpperCase()));
    if (o.kind === 'video' && o.height) parts.push(ltr(`${o.height}p`));
    if (tr.ok && !tr.none) parts.push(t('sum.trimmed', { len: fmtDuration(tr.end - tr.start) }));
    summary.textContent = parts.join(' · ');
    const blocked = !tr.ok || (i.too_long && tr.none) || (o.kind === 'video' && o.height && tooBig(o.height)) || (o.kind === 'audio' && size != null && size > L.max_filesize);
    go.disabled = Boolean(blocked);
  }
  refreshChips();
  onTrim();
  if (focusKey) box.querySelector(`[data-key="${focusKey}"]`)?.focus();
}

// ------------------------------------------------------------------ step 3: download
const fromView = (v) => {
  const fields = { status: v.status, stage: v.stage, progress: v.progress, speed: v.speed, eta: v.eta, ext: v.ext, size: v.size,
    filename: v.filename, queue_position: v.queue_position, error: v.error, expiresAt: v.expires_in != null ? Date.now() + v.expires_in * 1000 : null };
  if (v.title) fields.title = v.title;
  return fields;
};
const persist = () => store.set('jobs', S.jobs);

async function startJob() {
  const i = S.info, o = S.opt, tr = trimState();
  if (!tr.ok) return;
  const body = { url: i.url, kind: o.kind, format: o.fmt[o.kind] };
  if (o.kind === 'video' && o.height) body.height = o.height;
  if (!tr.none) { body.start = tr.start; body.end = tr.end; }
  $('#download').disabled = true;
  try {
    const view = await api('/api/jobs', { method: 'POST', body });
    addJob(view, body, i.title);
    clearNotice();
    $('#jobs').scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (e) {
    showNotice('error', errorText(e, ctx()));
  } finally {
    const btn = $('#download');
    if (btn) btn.disabled = false;
  }
}

function addJob(view, req, title) {
  S.jobs.unshift({ id: view.id, req, title: view.title || title || '', created: Date.now(), kind: req.kind, ...fromView(view) });
  while (S.jobs.length > MAX_JOBS) {
    const dead = S.jobs.map((j, idx) => [j, idx]).reverse().find(([j]) => FINAL.includes(j.status));
    S.jobs.splice(dead ? dead[1] : S.jobs.length - 1, 1);
  }
  persist();
  renderJobs();
  poll(view.id);
}

function poll(id) {
  if (S.timers.has(id)) return;
  const step = async () => {
    S.timers.delete(id);
    const job = S.jobs.find((j) => j.id === id);
    if (!job || job.status === 'expired' || (FINAL.includes(job.status) && job.status !== 'done')) return;
    let delay = document.hidden ? 4000 : job.status === 'queued' ? 2000 : 1000;
    try {
      Object.assign(job, fromView(await api(`/api/jobs/${id}`)));
      persist();
      paintJob(job);
      if (FINAL.includes(job.status)) return;
    } catch (e) {
      if (e.status === 401) return;                  // signed out: the sign-in screen is showing; polling resumes after sign-in
      if (e.status === 404) { job.status = 'expired'; persist(); paintJob(job); return; }
      delay = e.status === 429 ? Math.max(delay, (e.retryAfter || 5) * 1000) : 3000;
    }
    S.timers.set(id, setTimeout(step, delay));
  };
  S.timers.set(id, setTimeout(step, 0));
}

function tick() {                                  // once a second: count down the "deleted in" labels
  const now = Date.now();
  for (const job of S.jobs) {
    if (job.status !== 'done' || !job.expiresAt) continue;
    if (job.expiresAt <= now) { job.status = 'expired'; persist(); paintJob(job); } else paintStatus(job);
  }
}

async function removeJob(job) {
  clearTimeout(S.timers.get(job.id));
  S.timers.delete(job.id);
  if (job.status !== 'expired') { try { await api(`/api/jobs/${job.id}`, { method: 'DELETE' }); } catch { /* already gone */ } }
  S.jobs = S.jobs.filter((j) => j.id !== job.id);
  persist();
  nodes.get(job.id)?.li.remove();
  nodes.delete(job.id);
  $('#jobs-empty').hidden = S.jobs.length > 0;
}

async function cancelJob(job) {
  try { Object.assign(job, fromView(await api(`/api/jobs/${job.id}/cancel`, { method: 'POST' }))); persist(); paintJob(job); } catch { /* ignore */ }
}

async function retryJob(job) {
  try {
    const view = await api('/api/jobs', { method: 'POST', body: job.req });
    const title = job.title;
    await removeJob(job);
    addJob(view, job.req, title);
  } catch (e) {
    showNotice('error', errorText(e, ctx()));
  }
}

// ------------------------------------------------------------------ the list of downloads
const nodes = new Map();

function renderJobs(force = false) {
  const list = $('#joblist');
  $('#jobs-empty').hidden = S.jobs.length > 0;
  for (const [id, node] of nodes) if (!S.jobs.some((j) => j.id === id)) { node.li.remove(); nodes.delete(id); }
  for (const job of S.jobs) {
    if (force) nodes.get(job.id)?.li.remove(), nodes.delete(job.id);
    paintJob(job);
  }
  [...S.jobs].reverse().forEach((job) => list.prepend(nodes.get(job.id).li));
}

function statusText(job) {
  switch (job.status) {
    case 'queued': return t('st.queued', { n: job.queue_position || 1 });
    case 'running': {
      if (job.stage === 'downloading') {
        const extra = [job.speed ? fmtRate(job.speed) : '', job.eta ? t('eta', { time: fmtDuration(job.eta) }) : ''].filter(Boolean);
        return [t('st.downloading', { pct: Math.round((job.progress || 0) * 100) }), ...extra].join(' · ');
      }
      return t(job.stage === 'processing' ? 'st.processing' : 'st.preparing');
    }
    case 'done': return job.expiresAt ? `${t('st.done')} · ${t('expires', { time: fmtDuration(Math.max(0, (job.expiresAt - Date.now()) / 1000)) })}` : t('st.done');
    case 'error':
    case 'cancelled': return errorText(job.error || { code: job.status === 'cancelled' ? 'cancelled' : 'failed' }, ctx());
    default: return t('st.expired');
  }
}

function paintStatus(job) {
  const node = nodes.get(job.id);
  if (node) node.status.textContent = statusText(job);
}

function paintJob(job) {
  let node = nodes.get(job.id);
  if (!node) {
    const title = el('div', { class: 'job-title', dir: 'auto' }), meta = el('div', { class: 'job-meta' });
    const status = el('div', { class: 'job-status', 'aria-live': 'polite' });
    const fill = el('i'), bar = el('div', { class: 'bar-progress', role: 'progressbar', 'aria-valuemin': '0', 'aria-valuemax': '100' }, fill);
    const actions = el('div', { class: 'job-actions' });
    const li = el('li', { class: 'job card' }, el('div', { class: 'job-head' }, el('div', { class: 'job-main' }, title, meta), actions), status, bar);
    node = { li, title, meta, status, bar, actions, key: '' };
    nodes.set(job.id, node);
    $('#joblist').prepend(li);
  }
  node.li.dataset.status = job.status;
  node.title.textContent = job.title || t('untitled');
  const bits = [t(`kind.${job.req.kind}`), ltr((job.ext || job.req.format || '').toUpperCase())];
  if (job.req.kind === 'video' && job.req.height) bits.push(ltr(`${job.req.height}p`));
  if (job.size) bits.push(fmtBytes(job.size));
  node.meta.textContent = bits.filter(Boolean).join(' · ');
  paintStatus(job);
  const pct = Math.round((job.status === 'done' ? 1 : job.progress || 0) * 100);
  node.bar.style.setProperty('--p', `${pct}%`);
  node.bar.setAttribute('aria-valuenow', String(pct));
  node.bar.hidden = !(job.status === 'queued' || job.status === 'running' || job.status === 'done');
  if (node.key !== job.status) {                     // rebuild the buttons only when they change, so focus is never stolen
    node.key = job.status;
    const buttons = [];
    if (job.status === 'queued' || job.status === 'running') buttons.push(el('button', { class: 'btn sm ghost', type: 'button', onclick: () => cancelJob(job) }, icon('x'), t('btn.cancel')));
    if (job.status === 'done') buttons.push(el('a', { class: 'btn sm primary', href: `/api/jobs/${job.id}/file`, download: job.filename || '' }, icon('download'), t('btn.save')));
    if (job.status === 'error') buttons.push(el('button', { class: 'btn sm', type: 'button', onclick: () => retryJob(job) }, icon('retry'), t('btn.retry')));
    if (FINAL.includes(job.status)) buttons.push(el('button', { class: 'btn sm ghost', type: 'button', onclick: () => removeJob(job) }, icon('x'), t('btn.remove')));
    node.actions.replaceChildren(...buttons);
  }
}

// ------------------------------------------------------------------ private instance: access code and sharing
const locked = () => S.auth.required && !S.auth.ok;

function applyAuth() {
  const lock = locked();
  document.body.toggleAttribute('data-locked', lock);
  $('#login').hidden = !lock;
  $('#signout').hidden = !(S.auth.required && S.auth.ok);
  if (lock) $('#code').focus({ preventScroll: true });
}

function resumeJobs() {
  S.jobs.forEach((job) => { if (!FINAL.includes(job.status) || job.status === 'done') poll(job.id); });
}

function wireAuth() {
  $('#login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const message = $('#login-error');
    message.textContent = '';
    try {
      await api('/api/login', { method: 'POST', body: { code: $('#code').value } });
      $('#code').value = '';
      S.health = await api('/api/health');
      S.auth = S.health.auth;
      renderStatic();
      applyAuth();
      resumeJobs();
      openShared();
    } catch (err) {
      message.textContent = errorText(err, ctx());
    }
  });
  $('#signout').addEventListener('click', async () => {
    try { await api('/api/logout', { method: 'POST' }); } catch { /* already signed out */ }
    S.auth.ok = false;
    for (const timer of S.timers.values()) clearTimeout(timer);
    S.timers.clear();
    S.jobs = [];                                     // a shared phone shouldn't keep the list
    persist();
    for (const node of nodes.values()) node.li.remove();
    nodes.clear();
    S.info = null;
    $('#result').hidden = true;
    $('#jobs-empty').hidden = false;
    applyAuth();
  });
}

// When the page is installed on a phone it shows up in the share sheet: sharing a link from another app opens it here.
function openShared() {
  const query = new URLSearchParams(location.search);
  if (!['url', 'text', 'title'].some((k) => query.has(k))) return;
  const link = extractUrl(query.get('url') || query.get('text') || query.get('title') || '');
  history.replaceState(null, '', location.pathname);
  if (link) { $('#url').value = link; analyze(link); } else showNotice('error', t('err.bad_url'));
}

boot();
