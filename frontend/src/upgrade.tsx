import {Fragment, useEffect, useMemo, useRef, useState} from 'react'
import {Language} from './i18n'
import {Icon} from './visuals'

// English / Arabic strings for the 0.7 interface upgrade.
const words = {
  palette: ['Search or run a command…', 'ابحث أو نفّذ أمرًا…'],
  paletteTitle: ['Command palette', 'لوحة الأوامر'],
  noResults: ['No matching commands', 'لا توجد أوامر مطابقة'],
  downloadLink: ['Download this link', 'تنزيل هذا الرابط'],
  downloadLinks: ['Download these links', 'تنزيل هذه الروابط'],
  dropTitle: ['Drop to add download', 'أفلت لإضافة تنزيل'],
  dropHint: ['Links, text or a browser tab can be dropped here.', 'يمكنك إفلات الروابط أو النص أو علامة تبويب المتصفح هنا.'],
  shortcuts: ['Keyboard shortcuts', 'اختصارات لوحة المفاتيح'],
  close: ['Close', 'إغلاق'],
  total: ['Total saved', 'إجمالي المحفوظ'],
  running: ['running', 'قيد العمل'],
  files: ['files', 'ملفات'],
  idle: ['Idle', 'خامل'],
  live: ['Live', 'مباشر'],
  addedFromClipboard: ['Link added from clipboard', 'تمت إضافة الرابط من الحافظة'],
  copiedLinks: ['links copied', 'روابط تم نسخها'],
  group_actions: ['Actions', 'الإجراءات'],
  group_navigate: ['Go to', 'انتقال'],
  group_appearance: ['Appearance', 'المظهر'],
  group_link: ['Link', 'الرابط'],
  kNew: ['New download', 'تنزيل جديد'],
  kPalette: ['Open command palette', 'فتح لوحة الأوامر'],
  kSearch: ['Focus queue search', 'التركيز على بحث القائمة'],
  kHelp: ['Show this help', 'عرض هذه المساعدة'],
  kClose: ['Close dialogs', 'إغلاق النوافذ'],
  kPaste: ['Paste a link anywhere to add it', 'الصق رابطًا في أي مكان لإضافته'],
  kDrop: ['Drag a link onto the window', 'اسحب رابطًا إلى النافذة'],
} as const
export type UxKey = keyof typeof words
export const ux = (lang: Language, key: UxKey) => words[key][lang === 'ar' ? 1 : 0]

export type Command = {id: string; label: string; group: UxKey; icon: string; hint?: string; keywords?: string; run: () => void}

const URL_PATTERN = /https?:\/\/[^\s<>"'`]+/gi
export function extractUrls(text: string): string[] {
  const found = (text.match(URL_PATTERN) || []).map(u => u.replace(/[),.;]+$/, ''))
  return [...new Set(found)].filter(u => { try {return !!new URL(u).hostname} catch {return false} })
}

const editable = (target: EventTarget | null) => {
  const el = target as HTMLElement | null
  if (!el || !el.tagName) return false
  return el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT' || el.isContentEditable
}

/** Paste a link anywhere or drop one onto the window to start a download. */
export function useUrlIntake(onUrls: (urls: string[]) => void, enabled: boolean) {
  const [dragging, setDragging] = useState(false)
  const handler = useRef(onUrls)
  handler.current = onUrls
  useEffect(() => {
    if (!enabled) {setDragging(false); return}
    let depth = 0
    const hasPayload = (e: DragEvent) => !!e.dataTransfer && ['text/uri-list', 'text/plain', 'text/x-moz-url'].some(t => e.dataTransfer!.types.includes(t))
    const paste = (e: ClipboardEvent) => {
      if (editable(e.target)) return
      const urls = extractUrls(e.clipboardData?.getData('text') || '')
      if (urls.length) {e.preventDefault(); handler.current(urls)}
    }
    const enter = (e: DragEvent) => {if (hasPayload(e)) {depth++; setDragging(true)}}
    const over = (e: DragEvent) => {if (hasPayload(e)) {e.preventDefault(); if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy'}}
    const leave = () => {depth = Math.max(0, depth - 1); if (!depth) setDragging(false)}
    const drop = (e: DragEvent) => {
      depth = 0; setDragging(false)
      if (!e.dataTransfer || editable(e.target)) return
      const text = e.dataTransfer.getData('text/uri-list') || e.dataTransfer.getData('text/plain')
      const urls = extractUrls(text)
      if (urls.length) {e.preventDefault(); handler.current(urls)}
    }
    window.addEventListener('paste', paste)
    window.addEventListener('dragenter', enter)
    window.addEventListener('dragover', over)
    window.addEventListener('dragleave', leave)
    window.addEventListener('drop', drop)
    return () => {
      window.removeEventListener('paste', paste); window.removeEventListener('dragenter', enter)
      window.removeEventListener('dragover', over); window.removeEventListener('dragleave', leave); window.removeEventListener('drop', drop)
    }
  }, [enabled])
  return dragging
}

export function DropOverlay({lang}: {lang: Language}) {
  return <div className="drop-overlay" role="presentation"><div className="drop-card"><span><Icon name="down" size={34}/></span><strong>{ux(lang, 'dropTitle')}</strong><p>{ux(lang, 'dropHint')}</p></div></div>
}

export function Sparkline({values, active}: {values: number[]; active: boolean}) {
  const width = 132, height = 38
  const data = values.length > 1 ? values : [0, 0]
  const max = Math.max(...data, 1)
  const step = width / (data.length - 1)
  const points = data.map((v, i) => [i * step, height - 3 - (v / max) * (height - 8)] as const)
  const line = points.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`).join(' ')
  const area = `${line} L${width} ${height} L0 ${height} Z`
  return <svg className={`sparkline ${active ? 'live' : ''}`} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden="true">
    <defs><linearGradient id="spark-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="currentColor" stopOpacity=".38"/><stop offset="1" stopColor="currentColor" stopOpacity="0"/></linearGradient></defs>
    <path d={area} fill="url(#spark-fill)"/><path d={line} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke"/>
  </svg>
}

export function CommandPalette({lang, commands, onClose, onUrls}: {lang: Language; commands: Command[]; onClose: () => void; onUrls: (urls: string[]) => void}) {
  const [query, setQuery] = useState('')
  const [index, setIndex] = useState(0)
  const input = useRef<HTMLInputElement>(null)
  const list = useRef<HTMLUListElement>(null)
  const urls = useMemo(() => extractUrls(query), [query])
  const items = useMemo(() => {
    const terms = query.toLowerCase().split(/\s+/).filter(Boolean)
    const matched = urls.length ? [] : commands.filter(c => {
      const hay = `${c.label} ${c.keywords || ''} ${ux(lang, c.group)}`.toLowerCase()
      return terms.every(term => hay.includes(term))
    })
    const link: Command[] = urls.length ? [{id: 'url', group: 'group_link', icon: 'down', label: urls.length > 1 ? `${ux(lang, 'downloadLinks')} (${urls.length})` : ux(lang, 'downloadLink'), hint: urls.length === 1 ? urls[0] : undefined, run: () => onUrls(urls)}] : []
    return [...link, ...matched]
  }, [query, commands, urls, lang, onUrls])
  useEffect(() => {input.current?.focus()}, [])
  useEffect(() => setIndex(0), [query])
  useEffect(() => {list.current?.querySelector<HTMLElement>('[aria-selected="true"]')?.scrollIntoView({block: 'nearest'})}, [index])
  const run = (command?: Command) => {if (!command) return; onClose(); command.run()}
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {e.preventDefault(); setIndex(i => Math.min(items.length - 1, i + 1))}
    else if (e.key === 'ArrowUp') {e.preventDefault(); setIndex(i => Math.max(0, i - 1))}
    else if (e.key === 'Enter') {e.preventDefault(); run(items[index])}
    else if (e.key === 'Escape') {e.preventDefault(); onClose()}
    else if (e.key === 'Tab') {e.preventDefault(); input.current?.focus()}
  }
  let lastGroup = ''
  return <div className="palette-backdrop" onMouseDown={e => {if (e.target === e.currentTarget) onClose()}}>
    <div className="palette" role="dialog" aria-modal="true" aria-label={ux(lang, 'paletteTitle')} onKeyDown={onKey}>
      <div className="palette-input"><Icon name="search" size={18}/><input ref={input} role="combobox" aria-expanded="true" aria-controls="palette-list" aria-activedescendant={items[index] ? `cmd-${items[index].id}` : undefined} value={query} onChange={e => setQuery(e.target.value)} placeholder={ux(lang, 'palette')} spellCheck={false} autoComplete="off"/><kbd>Esc</kbd></div>
      <ul id="palette-list" role="listbox" ref={list}>
        {items.length === 0 && <li className="palette-empty">{ux(lang, 'noResults')}</li>}
        {items.map((c, i) => {
          const heading = c.group !== lastGroup ? (lastGroup = c.group, <li className="palette-group" role="presentation" key={`g-${c.group}`}>{ux(lang, c.group)}</li>) : null
          return <Fragment key={c.id}>{heading}<li id={`cmd-${c.id}`} role="option" aria-selected={i === index} className={i === index ? 'active' : ''} onMouseMove={() => setIndex(i)} onClick={() => run(c)}><span className="palette-icon"><Icon name={c.icon} size={16}/></span><span className="palette-label" dir="auto">{c.label}</span>{c.hint && <small dir="ltr">{c.hint}</small>}</li></Fragment>
        })}
      </ul>
    </div>
  </div>
}

export function ShortcutsSheet({lang, onClose}: {lang: Language; onClose: () => void}) {
  useEffect(() => {
    const key = (e: KeyboardEvent) => {if (e.key === 'Escape') onClose()}
    window.addEventListener('keydown', key); return () => window.removeEventListener('keydown', key)
  }, [onClose])
  const rows: [string[], UxKey][] = [[['Ctrl', 'K'], 'kPalette'], [['Ctrl', 'N'], 'kNew'], [['/'], 'kSearch'], [['?'], 'kHelp'], [['Esc'], 'kClose'], [['Ctrl', 'V'], 'kPaste'], [['⇲'], 'kDrop']]
  return <div className="palette-backdrop" onMouseDown={e => {if (e.target === e.currentTarget) onClose()}}>
    <div className="shortcuts-sheet" role="dialog" aria-modal="true" aria-label={ux(lang, 'shortcuts')}>
      <header><strong>{ux(lang, 'shortcuts')}</strong><button className="icon-button" aria-label={ux(lang, 'close')} onClick={onClose}><Icon name="close"/></button></header>
      <ul>{rows.map(([keys, label]) => <li key={label}><span>{ux(lang, label)}</span><span dir="ltr">{keys.map(k => <kbd key={k}>{k}</kbd>)}</span></li>)}</ul>
    </div>
  </div>
}
