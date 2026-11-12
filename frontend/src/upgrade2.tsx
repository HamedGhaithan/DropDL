import {useEffect, useRef, useState} from 'react'
import {Language} from './i18n'
import {Job} from './api'
import {Icon} from './visuals'
import {extractUrls} from './upgrade'

const W = {
  overall: ['Overall progress', 'التقدم الإجمالي'], left: ['left', 'متبقي'], tasks: ['active', 'نشطة'],
  allDone: ['All downloads finished', 'اكتملت كل التنزيلات'], linkFound: ['Link copied — download it?', 'تم نسخ رابط — هل تريد تنزيله؟'],
  download: ['Download', 'تنزيل'], ignore: ['Ignore', 'تجاهل'], doneN: ['finished', 'منتهية']
} as const
export const ux2 = (l: Language, k: keyof typeof W) => W[k][l === 'ar' ? 1 : 0]

/** Eased count-up for stat numbers. */
export function useCountUp(value: number, ms = 650) {
  const [shown, setShown] = useState(value), from = useRef(value)
  useEffect(() => {
    const start = from.current, t0 = performance.now(); let raf = 0
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) {setShown(value); from.current = value; return}
    const tick = (now: number) => {
      const p = Math.min(1, (now - t0) / ms), e = 1 - Math.pow(1 - p, 3)
      const v = start + (value - start) * e; setShown(v); from.current = v
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick); return () => cancelAnimationFrame(raf)
  }, [value, ms])
  return shown
}
export function Count({value, fmt}: {value: number; fmt?: (n: number) => string}) {const v = useCountUp(value); return <>{fmt ? fmt(v) : Math.round(v)}</>}

export function OverallBar({lang, jobs}: {lang: Language; jobs: Job[]}) {
  const live = jobs.filter(j => !['completed', 'failed', 'cancelled', 'paused'].includes(j.status) && j.purpose !== 'preview')
  if (!live.length) return null
  const pct = live.reduce((s, j) => s + Math.min(100, Math.max(0, j.percent || 0)), 0) / live.length
  const eta = Math.max(0, ...live.map(j => j.eta || 0)), fmt = (n: number) => [n / 3600, n % 3600 / 60, n % 60].map(x => String(Math.floor(x)).padStart(2, '0')).join(':')
  return <div className="overall" role="status"><div className="overall-text"><strong>{ux2(lang, 'overall')}</strong><span dir="ltr">{pct.toFixed(0)}% · {live.length} {ux2(lang, 'tasks')}{eta > 0 && ` · ${fmt(eta)} ${ux2(lang, 'left')}`}</span></div><div className="overall-track"><div style={{width: `${pct}%`}}/></div></div>
}

/** Canvas confetti burst when the queue empties. */
export function Confetti({lang}: {lang: Language}) {
  const ref = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const c = ref.current!, x = c.getContext('2d')!; c.width = innerWidth; c.height = innerHeight
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const cols = ['#60e7d3', '#62a7ff', '#ac81ff', '#ffd166', '#ff7ab8']
    const ps = Array.from({length: 130}, () => ({x: c.width / 2 + (Math.random() - .5) * 240, y: c.height * .72, vx: (Math.random() - .5) * 15, vy: -Math.random() * 17 - 6, s: 5 + Math.random() * 7, r: Math.random() * 6, vr: (Math.random() - .5) * .4, c: cols[Math.floor(Math.random() * cols.length)]}))
    let raf = 0, f = 0
    const tick = () => {
      x.clearRect(0, 0, c.width, c.height); f++
      for (const p of ps) {p.vy += .42; p.vx *= .99; p.x += p.vx; p.y += p.vy; p.r += p.vr; x.save(); x.globalAlpha = Math.max(0, 1 - f / 150); x.translate(p.x, p.y); x.rotate(p.r); x.fillStyle = p.c; x.fillRect(-p.s / 2, -p.s / 4, p.s, p.s / 2); x.restore()}
      if (f < 150) raf = requestAnimationFrame(tick)
    }
    tick(); return () => cancelAnimationFrame(raf)
  }, [])
  return <><canvas ref={ref} className="confetti" aria-hidden="true"/><div className="celebrate" role="status"><Icon name="completed" size={22}/>{ux2(lang, 'allDone')}</div></>
}

/** Title-bar speed, completion chime and desktop notification. */
export function useSystemFeedback(jobs: Job[], speed: number, sound: boolean, notify: boolean) {
  const seen = useRef<Map<string, string> | null>(null)
  useEffect(() => {
    const active = jobs.filter(j => !['completed', 'failed', 'cancelled', 'paused'].includes(j.status) && j.purpose !== 'preview').length
    const rate = speed > 0 ? `${(speed / 1048576).toFixed(1)} MB/s · ` : ''
    document.title = active ? `↓ ${rate}${active} — DropDL Studio` : 'DropDL Studio'
  }, [jobs, speed])
  useEffect(() => {
    const prev = seen.current; seen.current = new Map(jobs.map(j => [j.id, j.status]))
    if (!prev) return
    const fresh = jobs.filter(j => j.status === 'completed' && prev.has(j.id) && prev.get(j.id) !== 'completed' && j.purpose !== 'preview' && j.purpose !== 'conversion_sample')
    if (!fresh.length) return
    if (sound) try {
      const a = new AudioContext(); [660, 880, 1320].forEach((f, i) => {const o = a.createOscillator(), g = a.createGain(); o.frequency.value = f; o.type = 'sine'; o.connect(g); g.connect(a.destination); const t = a.currentTime + i * .11; g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(.12, t + .02); g.gain.exponentialRampToValueAtTime(.0001, t + .5); o.start(t); o.stop(t + .55)})
    } catch {/* audio unavailable */}
    if (notify && 'Notification' in window && document.hidden) try {
      const show = () => new Notification('DropDL Studio', {body: fresh.length > 1 ? `${fresh.length} downloads finished` : fresh[0].title || fresh[0].filename || ''})
      if (Notification.permission === 'granted') show(); else if (Notification.permission === 'default') void Notification.requestPermission().then(p => {if (p === 'granted') show()})
    } catch {/* notifications unavailable */}
  }, [jobs, sound, notify])
}

/** Offer to download a link that was just copied (opt-in). */
export function useClipboardWatch(enabled: boolean, onFound: (url: string) => void) {
  const last = useRef('')
  useEffect(() => {
    if (!enabled) return
    const check = async () => {
      try {
        const [url] = extractUrls(await navigator.clipboard.readText())
        if (url && url !== last.current) {last.current = url; onFound(url)}
      } catch {/* permission denied */}
    }
    addEventListener('focus', check); return () => removeEventListener('focus', check)
  }, [enabled, onFound])
}
export function ClipToast({lang, url, onYes, onNo}: {lang: Language; url: string; onYes: () => void; onNo: () => void}) {
  return <div className="clip-toast" role="alert"><span className="ct-icon"><Icon name="link" size={18}/></span><div><strong>{ux2(lang, 'linkFound')}</strong><small dir="ltr">{url}</small></div><button className="primary compact" onClick={onYes}>{ux2(lang, 'download')}</button><button className="ghost compact" onClick={onNo}>{ux2(lang, 'ignore')}</button></div>
}

/** Cursor-follow glow on cards. */
export function useSpotlight() {
  useEffect(() => {
    const move = (e: PointerEvent) => {const el = (e.target as HTMLElement).closest?.('.stat,.panel,.download-workspace,.detail-panel') as HTMLElement | null; if (el) {const r = el.getBoundingClientRect(); el.style.setProperty('--mx', `${e.clientX - r.left}px`); el.style.setProperty('--my', `${e.clientY - r.top}px`)}}
    addEventListener('pointermove', move, {passive: true}); return () => removeEventListener('pointermove', move)
  }, [])
}

export function exportCsv(jobs: Job[]) {
  const q = (v: unknown) => `"${String(v ?? '').replace(/"/g, '""')}"`
  const rows = [['title', 'url', 'site', 'status', 'kind', 'container', 'quality', 'bytes', 'file'], ...jobs.map(j => [j.title, j.url, j.site, j.status, j.kind, j.container, j.quality, j.total_bytes || j.downloaded_bytes || 0, j.filename])]
  const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob(['\ufeff' + rows.map(r => r.map(q).join(',')).join('\r\n')], {type: 'text/csv'}))
  a.download = `dropdl-history-${new Date().toISOString().slice(0, 10)}.csv`; document.body.appendChild(a); a.click(); a.remove()
}
