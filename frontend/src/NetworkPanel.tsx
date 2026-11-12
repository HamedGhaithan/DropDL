import {Preferences} from './api'

const PROXY = /^(https?|socks4a?|socks5h?):\/\/([^\s/?#@]+@)?[^\s/?#@]+(:\d{1,5})?\/?$/i
export const proxyValid = (value?: string) => !value?.trim() || PROXY.test(value.trim())

type Props = {lang: string; value: Preferences; onChange: (next: Preferences) => void}

/** Network & reliability preferences (2.0). Saved with the main Save button. */
export default function NetworkPanel({lang, value, onChange}: Props) {
  const w = (en: string, ar: string) => lang === 'ar' ? ar : en
  const set = <K extends keyof Preferences>(key: K, next: Preferences[K]) => onChange({...value, [key]: next})
  const int = (raw: string, low: number, high: number) => Math.max(low, Math.min(high, Math.round(Number(raw) || 0)))
  const stall = value.stall_timeout ?? 90
  return <section className="panel network-panel" data-testid="network-panel">
    <h3>{w('Network & reliability', 'الشبكة والموثوقية')} <span className="new-pill">2.0</span></h3>
    <div className="settings-grid">
      <label>{w('Parallel downloads', 'التنزيلات المتزامنة')}
        <select value={value.max_concurrent_downloads ?? 2} onChange={e => set('max_concurrent_downloads', Number(e.target.value))}>
          {[1, 2, 3, 4, 5, 6, 8].map(n => <option key={n} value={n}>{n}</option>)}
        </select></label>
      <label>{w('Connections per download', 'الاتصالات لكل تنزيل')}
        <select value={value.concurrent_fragments ?? 4} onChange={e => set('concurrent_fragments', Number(e.target.value))}>
          {[1, 2, 4, 8, 12, 16].map(n => <option key={n} value={n}>{n}</option>)}
        </select></label>
      <label>{w('Automatic retries', 'إعادة المحاولة التلقائية')}
        <input type="number" min={0} max={10} value={value.max_auto_retries ?? 4} onChange={e => set('max_auto_retries', int(e.target.value, 0, 10))}/></label>
      <label>{w('Restart stalled transfers after', 'إعادة تشغيل التنزيل المتوقف بعد')}
        <select value={stall} onChange={e => set('stall_timeout', Number(e.target.value))}>
          {[0, 45, 90, 180, 300].map(n => <option key={n} value={n}>{n === 0 ? w('Never', 'أبدًا') : `${n} ${w('seconds', 'ثانية')}`}</option>)}
        </select></label>
    </div>
    <p className="muted">{w('Network errors, rate limits and stalls retry with growing pauses (10 s → 5 min). Partial data is kept, so retries continue where they stopped. Unavailable or private media is not retried.', 'تُعاد محاولة أخطاء الشبكة وحدود المعدل والتوقفات بفواصل متزايدة (١٠ ث ← ٥ د). تُحفظ البيانات الجزئية فتستكمل المحاولات من حيث توقفت. لا تُعاد محاولة الوسائط غير المتاحة أو الخاصة.')}</p>
    <label>{w('Proxy (optional)', 'الوكيل (اختياري)')}
      <input dir="ltr" type="text" spellCheck={false} placeholder="socks5h://127.0.0.1:1080" aria-invalid={!proxyValid(value.proxy)} value={value.proxy || ''} onChange={e => set('proxy', e.target.value)}/></label>
    {!proxyValid(value.proxy) && <p className="job-error">{w('Use http://, https://, socks4://, socks5:// or socks5h:// followed by host:port.', 'استخدم http:// أو https:// أو socks4:// أو socks5:// أو socks5h:// متبوعًا بالمضيف:المنفذ.')}</p>}
    <label>{w('Use cookies from browser', 'استخدام ملفات تعريف الارتباط من المتصفح')}
      <select value={value.cookies_browser || ''} onChange={e => set('cookies_browser', e.target.value)}>
        <option value="">{w('Off', 'إيقاف')}</option>
        {['firefox', 'edge', 'chrome', 'brave', 'opera', 'vivaldi', 'chromium'].map(b => <option key={b} value={b}>{b[0].toUpperCase() + b.slice(1)}</option>)}
      </select></label>
    {value.cookies_browser && value.cookies_browser !== 'firefox' && <p className="muted">{w('Chromium browsers lock and encrypt cookies while open; Firefox is the most reliable. If reading fails, DropDL continues without them.', 'تقفل متصفحات Chromium ملفات الارتباط وتشفرها أثناء التشغيل؛ Firefox هو الأكثر موثوقية. إذا فشلت القراءة يتابع DropDL بدونها.')}</p>}
    <label className="toggle"><input type="checkbox" checked={!!value.force_ipv4} onChange={e => set('force_ipv4', e.target.checked)}/>{w('Force IPv4 (fixes slow or stuck IPv6 routes)', 'فرض IPv4 (يعالج مسارات IPv6 البطيئة)')}</label>
    <label className="toggle"><input type="checkbox" checked={value.impersonate === 'always'} onChange={e => set('impersonate', e.target.checked ? 'always' : 'auto')}/>{w('Always present as a desktop browser', 'الظهور دائمًا كمتصفح سطح مكتب')}</label>
    <p className="muted">{w('Off by default: DropDL switches to browser impersonation automatically when a site answers 403 Forbidden.', 'معطل افتراضيًا: يتحول DropDL تلقائيًا إلى محاكاة المتصفح عندما يرد الموقع بخطأ 403.')}</p>
  </section>
}
