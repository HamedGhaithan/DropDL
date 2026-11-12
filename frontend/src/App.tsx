import {DARK_ACCENTS,LIGHT_ACCENTS,DEFAULT_ACCENT} from './theme'
import {taskPhase,taskAdvice} from './reliability'
import EngineUpdate from './EngineUpdate'
import ClipTimeInput,{clipClock} from './ClipTimeInput'
import { FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import { API_BASE, archiveUrl, cancelDownload, createBatch, createClip, downloadUrl, Entry, getHealth, getJobs, getJobsSince, Health, inspectPlaylist, inspectUrl, Job, MediaInfo, OutputOptions, Playlist, retryDownload, preparePreview, clearQueue, getPreferences, savePreferences, Preferences, reportDiagnostic } from './api'
import DownloadExtras, {useDownloadExtras} from './DownloadExtras'
import NetworkPanel, {proxyValid} from './NetworkPanel'
import {Language, TextKey, translate} from './i18n'
import {Logo, Icon} from './visuals'
import RightClickLayer from './RightClickLayer'
import {openEditor} from './editorProject'
import {AppearancePanel,designText} from './StudioDesign'
import Tour from './Tour'
import ClipTimeline from './ClipTimeline'
import Workspace,{WorkspaceTab,workText} from './Workspace'
import {QueueTools,PriorityControls,qText} from './QueueTools'
import {pauseDownload,reorderQueue,queueControl} from './api'
import {Confetti,ClipToast,Count,OverallBar,exportCsv,useClipboardWatch,useSpotlight,useSystemFeedback,ux2} from './upgrade2'
import {CommandPalette,Command,DropOverlay,ShortcutsSheet,Sparkline,useUrlIntake,ux} from './upgrade'
import TaskSelection,{selectionText} from './TaskSelection'
import MiniPlayer,{PlayingMedia} from './MiniPlayer'
import Organization from './Organization'
import SupportPanel from './SupportPanel'
import {isYouTubePlaylist} from './source'

const terminal = (job: Job) => ['completed', 'failed', 'cancelled','paused'].includes(job.status)
const clock = clipClock
const bytes = (value?: number) => {
  if (!value) return '—'
  const units = ['B','KB','MB','GB']; let i = 0
  while (value >= 1024 && i < 3) {value /= 1024; i++}
  return `${value.toFixed(i > 1 ? 1 : 0)} ${units[i]}`
}

const accents = DARK_ACCENTS
const lightAccents = LIGHT_ACCENTS
type Accent = keyof typeof accents
function readPreference(key: string, fallback: string) {
  try {return localStorage.getItem(key) || fallback} catch {return fallback}
}
const etaClock = (seconds: number) => {
  const n = Number.isFinite(seconds) ? Math.max(0, Math.floor(seconds)) : 0
  return [Math.floor(n / 3600), Math.floor(n % 3600 / 60), n % 60].map(x => String(x).padStart(2,'0')).join(':')
}
export default function App() {
  const [lang, setLang] = useState<Language>(() => readPreference('dropdl-language','en') === 'ar' ? 'ar' : 'en')
  const t = (key:TextKey) => translate(lang,key)
  const d=(key:Parameters<typeof designText>[1])=>designText(lang,key)
  const sw=(key:Parameters<typeof selectionText>[1])=>selectionText(lang,key)
  const [taskSelection,setTaskSelection]=useState<Set<string>>(new Set())
  const refreshTasks=async()=>setJobs((await getJobs()).jobs)
  const [playback,setPlayback]=useState<{media:PlayingMedia;external?:()=>Promise<unknown>}|null>(null)
  const [workspace,setWorkspace]=useState<WorkspaceTab>('downloads')
  const [scheduled,setScheduled]=useState('')
  const [subtitles,setSubtitles]=useState('')
  const [metadata,setMetadata]=useState(false)
  const [extras,setExtras]=useDownloadExtras()
  const [,setTick]=useState(0)
  const [duplicateSkip,setDuplicateSkip]=useState(false)
  const [globalLimit,setGlobalLimit]=useState('0')
  const [dragged,setDragged]=useState<string|null>(null)
  const [view,setView] = useState('all')
  const [composer,setComposer] = useState(false)
  const [settingsOpen,setSettingsOpen] = useState(false)
  const [search,setSearch] = useState('')
  const [smart,setSmart] = useState('')
  const [sort,setSort] = useState('newest')
  const [queuePage,setQueuePage] = useState(0)
  const [recoveryDismissed,setRecoveryDismissed]=useState(false)
  const [connectionLost,setConnectionLost] = useState(false)
  const hasConnected=useRef(false)
  useEffect(()=>setQueuePage(0),[view,search,sort])
  const [detailId,setDetailId] = useState<string|null>(null)
  const [preferences,setPreferences] = useState<Preferences|null>(null)
  const [limit,setLimit] = useState('0')
  const [tour,setTour] = useState(() => readPreference('dropdl-tour-v1','') ? -1 : 0)
  const modal = useRef<HTMLDivElement>(null)
  const [theme, setTheme] = useState(() => readPreference('dropdl-theme','dark') === 'light' ? 'light' : 'dark')
  const [accent, setAccent] = useState<Accent>(() => {const a=readPreference('dropdl-accent',DEFAULT_ACCENT); return a in accents ? a as Accent : DEFAULT_ACCENT})
  const [motion,setMotion] = useState(()=>readPreference('dropdl-motion','smooth')==='reduced'?'reduced':'smooth')
  useEffect(()=>{document.documentElement.dataset.motion=motion;try{localStorage.setItem('dropdl-motion',motion)}catch{}},[motion])
  const [showClear, setShowClear] = useState(false)
  const [queueMessage, setQueueMessage] = useState('')
  const [dismissedClips,setDismissedClips]=useState<Set<string>>(new Set())
  const [tab, setTab] = useState<'single'|'playlist'|'batch'>('single')
  const [url, setUrl] = useState('')
  const [batchText, setBatchText] = useState('')
  const [info, setInfo] = useState<MediaInfo | null>(null)
  const [playlist, setPlaylist] = useState<Playlist | null>(null)
  const [playlistURL, setPlaylistURL] = useState('')
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [mode, setMode] = useState<OutputOptions['mode']>('video')
  const [videoFormat, setVideoFormat] = useState('mp4')
  const [audioFormat, setAudioFormat] = useState('mp3')
  const [quality, setQuality] = useState('1080p')
  const [health, setHealth] = useState<Health | null>(null)
  const [jobs, setJobs] = useState<Job[]>([])
  const [palette,setPalette]=useState(false)
  const flag=(k:string,d='0')=>readPreference('dropdl-'+k,d)==='1'
  const [pref,setPref]=useState(()=>({sound:flag('sound','1'),notify:flag('notify','1'),clip:flag('clipwatch'),compact:flag('compact'),collapsed:flag('collapsed')}))
  const togglePref=(k:keyof typeof pref)=>setPref(p=>({...p,[k]:!p[k]}))
  useEffect(()=>{document.documentElement.dataset.density=pref.compact?'compact':'comfortable';try{localStorage.setItem('dropdl-sound',pref.sound?'1':'0');localStorage.setItem('dropdl-notify',pref.notify?'1':'0');localStorage.setItem('dropdl-clipwatch',pref.clip?'1':'0');localStorage.setItem('dropdl-compact',pref.compact?'1':'0');localStorage.setItem('dropdl-collapsed',pref.collapsed?'1':'0')}catch{}},[pref])
  const [celebrate,setCelebrate]=useState(false)
  const [clipUrl,setClipUrl]=useState('')
  const wasActive=useRef(0)
  const wasDone=useRef(-1)
  useSpotlight()
  const [shortcuts,setShortcuts]=useState(false)
  const [speedHistory,setSpeedHistory]=useState<number[]>(()=>Array(40).fill(0))
  useEffect(()=>{const total=jobs.filter(j=>j.status==='downloading').reduce((sum,j)=>sum+(j.speed||0),0);setSpeedHistory(h=>[...h.slice(-39),total])},[jobs])
  useEffect(()=>{const ids=new Set(jobs.map(j=>j.id));setTaskSelection(old=>{const next=new Set([...old].filter(id=>ids.has(id)));return next.size===old.size?old:next})},[jobs])
  const previousStates=useRef<Map<string,string>>(new Map())
  const [notifications,setNotifications]=useState<Job[]>([])
  useEffect(()=>{const fresh=jobs.filter(j=>j.status==='completed'&&previousStates.current.has(j.id)&&previousStates.current.get(j.id)!=='completed'&&j.purpose!=='preview'&&j.purpose!=='conversion_sample');if(fresh.length)setNotifications(old=>[...fresh,...old].slice(0,3));previousStates.current=new Map(jobs.map(j=>[j.id,j.status]))},[jobs])
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [clip, setClip] = useState(false)
  const [startTimeValid,setStartTimeValid]=useState(true),[endTimeValid,setEndTimeValid]=useState(true)
  const [ranges,setRanges]=useState<[number,number][]>([])
  const [start, setStart] = useState(0)
  const [end, setEnd] = useState(30)
  const [duration, setDuration] = useState(0)
  const [source, setSource] = useState<Job | null>(null)
  useEffect(()=>setRanges([]),[source?.id])
  const [pendingPreview, setPendingPreview] = useState<{id:string; preserveRange:boolean} | null>(null)
  const [rangeOnly, setRangeOnly] = useState(true)
  const [position, setPosition] = useState(0)
  const player = useRef<HTMLVideoElement>(null)
  const failedPreviews=useRef(new Set<string>())
  const previewing = useRef(false)
  const stopLoading = useRef(false)

  useEffect(() => {
    document.documentElement.lang = lang
    document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr'
    try {localStorage.setItem('dropdl-language',lang)} catch {}
  },[lang])
  useEffect(() => {void getPreferences().then(p=>{setPreferences(p);setLimit(String(p.speed_limit_kbps));setGlobalLimit(String(p.global_speed_limit_kbps||0));setDuplicateSkip(p.skip_duplicates===true)}).catch(()=>{})},[])
  useEffect(() => {
    const keys = (e:KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase()==='n') {e.preventDefault();setComposer(true)}
      if(e.key==='Escape' && tour < 0) {setComposer(false);setSettingsOpen(false)}
      const target=e.target as HTMLElement|null
      const typing=!!target&&(['INPUT','TEXTAREA','SELECT'].includes(target.tagName)||target.isContentEditable)
      if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'&&tour<0){e.preventDefault();setPalette(open=>!open)}
      else if(!typing&&!e.ctrlKey&&!e.metaKey&&!e.altKey&&tour<0){
        if(e.key==='/'){e.preventDefault();setComposer(false);setSettingsOpen(false);setWorkspace('downloads');setTimeout(()=>document.getElementById('queue-search')?.focus(),0)}
        else if(e.key==='?'){e.preventDefault();setShortcuts(true)}
        else if(e.key==='['){e.preventDefault();togglePref('collapsed')}
      }
    }
    window.addEventListener('keydown',keys);return()=>window.removeEventListener('keydown',keys)
  },[tour])
  useEffect(() => {
    if(!(composer || settingsOpen) || tour>=0) return
    const before=document.activeElement as HTMLElement
    const frame=requestAnimationFrame(()=>modal.current?.querySelector<HTMLElement>('button,input,select')?.focus())
    const trap=(e:KeyboardEvent)=>{if(e.key!=='Tab')return;const items=[...modal.current?.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href]')||[]];const first=items[0],last=items[items.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus()}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus()}}
    document.addEventListener('keydown',trap)
    return()=>{cancelAnimationFrame(frame);document.removeEventListener('keydown',trap);before?.focus()}
  },[composer,settingsOpen,tour])

  useEffect(()=>{void window.pywebview?.api.configure_tray?.(!!preferences?.keep_in_tray,lang).catch(()=>{});},[lang])

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    document.documentElement.style.setProperty('--accent', (theme==='light'?lightAccents:accents)[accent])
    document.documentElement.style.colorScheme = theme
    try {localStorage.setItem('dropdl-theme', theme); localStorage.setItem('dropdl-accent', accent)} catch { /* Preferences remain usable in this session. */ }
  }, [theme, accent])

  const revision = useRef<number|undefined>(undefined)
  // Live countdown for tasks waiting on an automatic retry.
  useEffect(()=>{if(!jobs.some(j=>j.retry_at&&j.retry_at*1000>Date.now()))return;const id=setInterval(()=>setTick(n=>n+1),1000);return()=>clearInterval(id)},[jobs])
  useEffect(() => {
    let active = true; let timer: ReturnType<typeof setTimeout>
    async function update() {
      try {
        const [h, list] = await Promise.all([getHealth(), getJobsSince(revision.current)])
        if (active) {hasConnected.current=true;setConnectionLost(false);setHealth(h);if(list.jobs){revision.current=list.revision;setJobs(list.jobs)}}
      } catch (error) {if (active) {setHealth(null);if(hasConnected.current)setConnectionLost(true);reportDiagnostic('queue-refresh-error',String(error))}}
      if (active) timer = setTimeout(update, 1200)
    }
    void update()
    return () => {active = false; clearTimeout(timer); stopLoading.current = true}
  }, [])

  useEffect(() => {
    if (!pendingPreview) return
    const job = jobs.find(item => item.id === pendingPreview.id)
    if (!job) return
    if (job.status === 'completed' && job.preview_ready) {
      setSource(job); setQuality(job.quality); setPosition(0); setRangeOnly(true)
      if (!pendingPreview.preserveRange) {setStart(0); setEnd(30); setDuration(0)}
      if (job.kind === 'audio') setMode('audio')
      setPendingPreview(null)
    } else if (job.status === 'failed') {
      setError(job.error || t('previewFail')); setPendingPreview(null)
    } else if (job.status === 'cancelled') {
      setPendingPreview(null)
    }
  }, [jobs, pendingPreview])

  const qualities = useMemo(() => ['best', ...new Set(info?.suggested_qualities?.length ? info.suggested_qualities : ['2160p','1440p','1080p','720p','480p','360p'])], [info])
  const batchURLs = [...new Set(batchText.split(/\r?\n/).map(x => x.trim()).filter(Boolean))]
  const urls = tab === 'playlist' ? (playlist?.entries.filter(e => selected.has(e.index) && e.url).map(e => e.url!) || []) : tab === 'batch' ? batchURLs : url.trim() ? [url.trim()] : []
  const downloadJobs = jobs.filter(j => j.purpose !== 'preview'&&j.purpose!=='conversion_sample'&&j.purpose!=='clip')
  const previewJobs = jobs.filter(j => j.purpose === 'preview' && !terminal(j))
  const activeJobs = downloadJobs.filter(j => !terminal(j))
  const completed = jobs.filter(j => j.status === 'completed' && j.purpose !== 'preview')
  const batches = [...new Set(completed.map(j => j.batch_id).filter((id): id is string => !!id))]
  const totalSpeed = activeJobs.reduce((sum,j)=>sum+(j.speed||0),0)
  useSystemFeedback(jobs,totalSpeed,pref.sound,pref.notify)
  useClipboardWatch(pref.clip&&tour<0,setClipUrl)
  useEffect(()=>{const n=activeJobs.length;if(wasActive.current>0&&n===0&&completed.length>wasDone.current){wasDone.current=completed.length;setCelebrate(true);const id=setTimeout(()=>setCelebrate(false),3600);wasActive.current=n;return()=>clearTimeout(id)}wasDone.current=Math.max(wasDone.current,completed.length>0&&wasActive.current===0?completed.length:wasDone.current);wasActive.current=n},[activeJobs.length])
  const totalSaved = completed.reduce((sum,j)=>sum+(j.total_bytes||j.downloaded_bytes||0),0)
  const sliderMax = duration || Math.max(60, end, start + 1)
  const validClip = startTimeValid && endTimeValid && Number.isFinite(start) && Number.isFinite(end) && start >= 0 && end > start && (!duration || end <= duration)

  useEffect(() => {
    const media = player.current
    if (!media || !rangeOnly || !validClip) return
    let frame = 0
    const tick = () => {
      if (media.paused) return
      if (media.currentTime >= end) {
        media.pause(); media.currentTime = end; previewing.current = false
        return
      }
      frame = window.requestAnimationFrame(tick)
    }
    const watch = () => {window.cancelAnimationFrame(frame); frame = window.requestAnimationFrame(tick)}
    media.addEventListener('play', watch)
    if (!media.paused) watch()
    return () => {media.removeEventListener('play', watch); window.cancelAnimationFrame(frame)}
  }, [source?.id, start, end, rangeOnly, validClip])

  async function act(name: string, action: () => Promise<void>) {
    setBusy(name); setError('')
    try {await action()} catch (e) {reportDiagnostic('operation-error',`${name}: ${e instanceof Error?e.message:String(e)}`);setError(e instanceof Error ? e.name==='RequestTimeout'?t('requestTimeout'):e.message : t('operationFail'))} finally {setBusy('')}
  }
  function acceptURL(value:string) {
    stopLoading.current = true
    setUrl(value); resetSource(); setInfo(null); setDuration(0)
    setPlaylist(null); setSelected(new Set())
    if(isYouTubePlaylist(value)){setTab('playlist');setClip(false)}
  }
  function resetSource() { setPlayback(null); player.current?.pause(); setSource(null); setPendingPreview(null); setDuration(info?.duration || 0); previewing.current = false }
  async function analyze(event: FormEvent) {
    event.preventDefault()
    resetSource()
    await act('Analyze', async () => {
      if (tab === 'playlist') {
        reportDiagnostic('load-playlist-click')
        const data = await inspectPlaylist(url.trim()); setPlaylist(data); setPlaylistURL(url.trim()); setSelected(new Set(data.entries.filter(e => e.url).map(e => e.index)))
        setInfo(null); setDuration(0); setClip(false)
        reportDiagnostic('playlist-render-ready',`${data.entries.length} entries`)
      } else {
        const data = await inspectUrl(url.trim()); setInfo(data); setDuration(data.duration || 0)
        setStart(0); setEnd(Math.min(30, data.duration || 30)); setQuality(data.suggested_qualities?.includes('1080p') ? '1080p' : 'best')
      }
    })
  }
  async function more(all = false) {
    if (!playlist || !playlist.has_more) return
    stopLoading.current = false
    await act(all ? 'Load all' : 'Load more', async () => {
      let next = playlist.next_start
      let hasMore = true
      do {
        const data = await inspectPlaylist(playlistURL, next)
        setPlaylist(previous => previous ? {...data, entries: [...previous.entries, ...data.entries.filter(e => !previous.entries.some(old => old.index === e.index))]} : data)
        setSelected(previous => new Set([...previous, ...data.entries.filter(e => e.url).map(e => e.index)]))
        if (data.next_start <= next) break
        next = data.next_start; hasMore = data.has_more
      } while (all && hasMore && !stopLoading.current)
    })
  }
  function options(): OutputOptions {
    return {collection:tab==='playlist'?playlist?.title.slice(0,200):undefined,mode, video_container: videoFormat, audio_container: audioFormat, quality,skip_duplicates:duplicateSkip,scheduled_at:scheduled?new Date(scheduled).getTime()/1000:0,subtitle_languages:subtitles.split(',').map(s=>s.trim()).filter(Boolean),embed_metadata:metadata,download_options:extras,
      clip_enabled:clip, ...(clip ? {clip_start: start, clip_end: end} : {})}
  }
  async function download() {
    await act(source ? 'Export clip' : 'Queue downloads', async () => {
      reportDiagnostic('queue-click',`${urls.length} sources, mode=${mode}`)
      if (clip && !validClip) throw new Error(t('invalidClip'))
      if (source && clip) {
        for(const [a,b] of (ranges.length?ranges:[[start,end]])) await createClip(source.id, {...options(),clip_start:a,clip_end:b,show_in_downloads:true})
      } else {
        for (let i = 0; i < urls.length; i += 500) {const result=await createBatch(urls.slice(i, i + 500), options());if(result.skipped)setQueueMessage(`${result.skipped} ${lang==='ar'?'ملفات مكررة تم تخطيها':'duplicate outputs skipped'}`)}
      }
      setJobs((await getJobs()).jobs);setQueuePage(0); setComposer(false);setView('all');setWorkspace('downloads')
    })
  }
  async function loadPreview(job?: Job, forceTranscode=false) {
    await act('Prepare preview', async () => {
      if (!job && !url.trim()) throw new Error(t('enterUrl'))
      setPlayback(null); player.current?.pause(); setSource(null)
      const next = await preparePreview(job ? {source_job_id:job.id,force_transcode:forceTranscode} : {url:url.trim(), quality})
      if(forceTranscode)failedPreviews.current.add(next.id)
      if(next.status==='completed'&&next.preview_ready){setSource(next);setQuality(next.quality);setPosition(0);setRangeOnly(true);setPendingPreview(null);if(next.kind==='audio')setMode('audio')}else setPendingPreview({id:next.id, preserveRange:forceTranscode||!job})
      setJobs((await getJobs()).jobs)
      document.getElementById('clip-editor')?.scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth', block:'center'})
    })
  }
  function selectSource(job: Job) { setPlayback(null);void act('Open editor',()=>openEditor(job.id,lang)) }
  function updateStart(value: number) {
    player.current?.pause(); previewing.current = false
    setStart(value); seek(Math.max(0,value))
  }
  function updateEnd(value: number) {
    player.current?.pause(); previewing.current = false
    setEnd(value); seek(Math.max(0,value - .05))
  }
  function seek(seconds: number) {
    if (player.current) player.current.currentTime = seconds
  }
  function playRange() {
    if (!player.current) return
    setRangeOnly(true); previewing.current = true; player.current.currentTime = start
    void player.current.play().catch(() => setError(t('previewFail')))
  }
  async function retry(job: Job) {
    await act('Retry', async () => {
      await retryDownload(job.id)
      setJobs((await getJobs()).jobs)
    })
  }

  async function clearTasks(includeActive: boolean) {
    await act('Clear queue', async () => {
      const result = await clearQueue(includeActive)
      if (includeActive || source && terminal(source)) {resetSource(); setClip(false)}
      setJobs((await getJobs()).jobs); setShowClear(false)
      setQueueMessage(`${result.removed} · ${t('cleared')}`)
    })
  }

  const filtered = downloadJobs.filter(j => (view==='all' || view==='active' && !terminal(j) || view==='completed' && j.status==='completed' || view==='attention' && ['failed','cancelled'].includes(j.status) || view==='video' && j.kind==='video' || view==='audio' && j.kind==='audio') && `${j.title} ${j.url} ${j.site||''} ${j.filename||''}`.toLocaleLowerCase().includes(search.toLocaleLowerCase())).sort((a,b)=>sort==='priority'?(b.priority||0)-(a.priority||0)||((a.created_at||0)-(b.created_at||0)):sort==='name'?(a.title||a.url).localeCompare(b.title||b.url):sort==='oldest'?(a.created_at||0)-(b.created_at||0):(b.created_at||0)-(a.created_at||0))
  const page=Math.min(queuePage,Math.max(0,Math.ceil(filtered.length/100)-1))
  const pageJobs=filtered.slice(page*100,(page+1)*100)
  const detail=downloadJobs.find(j=>j.id===detailId)
  const statusText=(status:string)=>['paused','pausing','converting'].includes(status)?qText(lang,status as 'paused'|'pausing'|'converting'):t(({queued:'taskQueued',starting:'taskStarting',downloading:'taskDownloading',processing:'taskProcessing',clipping:'taskClipping',preparing_preview:'taskPreparing',completed:'completed',failed:'taskFailed',cancelled:'taskCancelled',cancelling:'taskCancelling'} as Record<string,TextKey>)[status]||'taskQueued')
  function finishTour(){setTour(-1);setComposer(false);try{localStorage.setItem('dropdl-tour-v1','done')}catch{};document.getElementById('tour-add')?.focus()}
  function moveTour(step:number){setWorkspace('downloads');setComposer(step>0&&step<5);setSettingsOpen(false);setTour(step)}
  async function chooseFolder(){await act('Folder',async()=>{if(!window.pywebview?.api)throw Error(t('folderFail'));const p=await window.pywebview.api.choose_folder();if(p){setPreferences(p);setLimit(String(p.speed_limit_kbps))}})}
  async function setGrouping(enabled:boolean){if(!preferences)return;await act('Preferences',async()=>setPreferences(await savePreferences({...preferences,group_by_site:enabled})))}
  async function saveSettings(){if(!preferences)return;await act('Preferences',async()=>{const value=Number(limit);if(!Number.isInteger(value)||value<0||value>1000000)throw Error(t('speedHint'));if(!proxyValid(preferences.proxy))throw Error(lang==='ar'?'عنوان الوكيل غير صالح.':'The proxy address is not valid.');setPreferences(await savePreferences({...preferences,speed_limit_kbps:value,global_speed_limit_kbps:Number(globalLimit),skip_duplicates:duplicateSkip}));await window.pywebview?.api.configure_tray?.(!!preferences.keep_in_tray,lang);setQueueMessage(t('settingsSaved'));setSettingsOpen(false)})}
  async function paste(){await act('Paste',async()=>{try{const text=await navigator.clipboard.readText();if(tab==='batch')setBatchText(text);else acceptURL(text.trim())}catch{throw Error(t('pasteFail'))}})}
  const miniLabel=lang==='ar'?'فتح المشغل المصغر':'Open mini player'
  async function playMedia(media:PlayingMedia,external?:()=>Promise<unknown>,mini=false){
    setPlayback(null)
    if(mini){setPlayback({media,external});return}
    await act('Open media',async()=>{if(!external)throw Error(t('openDownloadedUnavailable'));if(!await external())throw Error(t('openDownloadedFailed'))})
  }
  useEffect(()=>{const dock=(event:Event)=>{const {key,time,rate}=(event as CustomEvent).detail||{};if(typeof key!=='string'||!Number.isFinite(time)||time<0)return;try{const saved=JSON.parse(localStorage.getItem('dropdl-playback')||'{}');saved[key]=time;localStorage.setItem('dropdl-playback',JSON.stringify(saved));localStorage.setItem('dropdl-playback-rate',String(rate))}catch{}const [type,id]=key.split(':');if(!['job','library'].includes(type)||!id||!/^[a-zA-Z0-9_-]+$/.test(id))return;void fetch(API_BASE+`/api/${type==='job'?'jobs':'library'}/${id}`).then(async response=>{if(!response.ok)throw Error('The media is unavailable');const record=await response.json();setPlayback({media:{key,url:API_BASE+`/api/${type==='job'?'jobs':'library'}/${id}/file?inline=true`,title:record.title||record.filename,kind:record.kind},external:window.pywebview?.api[type==='job'?'open_downloaded':'open_library']?()=>window.pywebview!.api[type==='job'?'open_downloaded':'open_library']!(id):undefined})}).catch(e=>setError(String(e.message||e)))};window.addEventListener('dropdl-player-docked',dock);return()=>window.removeEventListener('dropdl-player-docked',dock)},[])
  async function openDownloaded(id:string,mini=false){
    setNotifications(old=>old.filter(job=>job.id!==id))
    const job=jobs.find(j=>j.id===id&&j.status==='completed')
    if(!job){setError(t('openDownloadedFailed'));return}
    await playMedia({key:'job:'+id,url:downloadUrl(id)+'?inline=true',title:job.title||job.filename||job.url,kind:job.kind},window.pywebview?.api.open_downloaded?()=>window.pywebview!.api.open_downloaded!(id):undefined,mini)
  }

  async function openFolder(id?:string){await act('Folder',async()=>{if(!window.pywebview?.api)throw Error(t('folderFail'));await window.pywebview.api.open_folder(id)})}
  async function copyLink(job:Job){await act('Copy',async()=>{await navigator.clipboard.writeText(job.url);setQueueMessage(t('copied'))})}
  function intake(found:string[]){
    setSettingsOpen(false);setPalette(false);setWorkspace('downloads')
    if(found.length>1){resetSource();setClip(false);setInfo(null);setPlaylist(null);setTab('batch');setBatchText(found.join('\n'))}
    else{setTab('single');acceptURL(found[0]);if(!isYouTubePlaylist(found[0]))void quickAnalyze(found[0])}
    setComposer(true)
  }
  async function quickAnalyze(u:string){await act('Analyze',async()=>{const data=await inspectUrl(u);setInfo(data);setDuration(data.duration||0);setStart(0);setEnd(Math.min(30,data.duration||30));setQuality(data.suggested_qualities?.includes('1080p')?'1080p':'best')})}
  const dragging=useUrlIntake(intake,tour<0&&!palette)
  async function copyLinks(list:Job[]){await act('Copy',async()=>{await navigator.clipboard.writeText(list.map(j=>j.url).join('\n'));setQueueMessage(`${list.length} ${ux(lang,'copiedLinks')}`)})}
  const L=(en:string,ar:string)=>lang==='ar'?ar:en
  const selectedJobs=downloadJobs.filter(j=>taskSelection.has(j.id))
  const commands:Command[]=[
    {id:'new',group:'group_actions',icon:'plus',label:t('newDownload'),hint:'Ctrl N',keywords:'add url link download',run:()=>{setWorkspace('downloads');setSettingsOpen(false);setComposer(true)}},
    {id:'pause',group:'group_actions',icon:'pause',label:qText(lang,'pauseAll'),keywords:'queue stop hold',run:()=>void act('Pause',async()=>{await queueControl('pause');await refreshTasks()})},
    {id:'resume',group:'group_actions',icon:'bolt',label:qText(lang,'resumeAll'),keywords:'queue start continue',run:()=>void act('Resume',async()=>{await queueControl('resume');await refreshTasks()})},
    ...(downloadJobs.some(j=>j.status==='failed')?[{id:'retry-failed',group:'group_actions' as const,icon:'retry',label:t('retryAll'),keywords:'failed again',run:()=>void act('Retry',async()=>{for(const job of downloadJobs.filter(j=>j.status==='failed'))await retryDownload(job.id);await refreshTasks()})}]:[]),
    ...(downloadJobs.some(terminal)?[{id:'clear-finished',group:'group_actions' as const,icon:'close',label:t('clearFinished'),keywords:'remove history clean',run:()=>void clearTasks(false)}]:[]),
    ...(selectedJobs.length?[{id:'copy-selected',group:'group_actions' as const,icon:'copy',label:L(`Copy links of ${selectedJobs.length} selected`,`نسخ روابط ${selectedJobs.length} محددة`),keywords:'url clipboard',run:()=>void copyLinks(selectedJobs)}]:[]),
    ...(downloadJobs.length?[{id:'copy-visible',group:'group_actions' as const,icon:'copy',label:L(`Copy links of ${filtered.length} shown tasks`,`نسخ روابط ${filtered.length} مهمة معروضة`),keywords:'url clipboard export',run:()=>void copyLinks(filtered)}]:[]),
    ...(preferences?.native_folder_picker?[{id:'folder',group:'group_actions' as const,icon:'folder',label:L('Open download folder','فتح مجلد التنزيل'),keywords:'explorer directory',run:()=>void openFolder()}]:[]),
    ...['all','active','completed','attention','video','audio'].map(v=>({id:`view-${v}`,group:'group_navigate' as const,icon:v,label:t(v as TextKey),keywords:'queue list',run:()=>{setWorkspace('downloads');setView(v)}})),
    ...(['convert','studio','library'] as const).map(section=>({id:`tool-${section}`,group:'group_navigate' as const,icon:section==='library'?'folder':section==='convert'?'convert':'scissors',label:workText(lang,section),keywords:'tool workspace',run:()=>{setComposer(false);setSettingsOpen(false);setWorkspace(section)}})),
    {id:'prefs',group:'group_navigate',icon:'settings',label:t('preferences'),keywords:'settings options',run:()=>{setComposer(false);setSettingsOpen(true)}},
    {id:'theme',group:'group_appearance',icon:theme==='dark'?'sun':'moon',label:theme==='dark'?L('Switch to light theme','التبديل إلى السمة الفاتحة'):L('Switch to dark theme','التبديل إلى السمة الداكنة'),keywords:'appearance mode',run:()=>setTheme(theme==='dark'?'light':'dark')},
    {id:'lang',group:'group_appearance',icon:'globe',label:lang==='ar'?'Switch to English':'التبديل إلى العربية',keywords:'language arabic english rtl',run:()=>setLang(lang==='ar'?'en':'ar')},
    ...(Object.keys(accents) as Accent[]).filter(a=>a!==accent).map(a=>({id:`accent-${a}`,group:'group_appearance' as const,icon:'bolt',label:`${t('accent')}: ${t(a)}`,keywords:'color theme',run:()=>setAccent(a)})),
    {id:'export-csv',group:'group_actions',icon:'down',label:L('Export history as CSV','تصدير السجل بصيغة CSV'),keywords:'spreadsheet excel report',run:()=>exportCsv(downloadJobs)},
    ...[[0,L('Total bandwidth: unlimited','إجمالي النطاق: بلا حد')],[5120,L('Total bandwidth: 5 MB/s','إجمالي النطاق: 5 ميغابايت/ث')],[1024,L('Total bandwidth: 1 MB/s (eco)','إجمالي النطاق: 1 ميغابايت/ث (اقتصادي)')]].map(([kbps,label])=>({id:`speed-${kbps}`,group:'group_actions' as const,icon:'bolt',label:String(label),keywords:'bandwidth throttle limit network',run:()=>{if(preferences)void act('Preferences',async()=>{setPreferences(await savePreferences({...preferences,global_speed_limit_kbps:Number(kbps)}));setGlobalLimit(String(kbps));setQueueMessage(String(label))})}})),
    {id:'t-collapse',group:'group_appearance',icon:'all',label:pref.collapsed?L('Expand sidebar','توسيع الشريط الجانبي'):L('Collapse sidebar','طي الشريط الجانبي'),hint:'[',keywords:'navigation menu',run:()=>togglePref('collapsed')},
    {id:'t-density',group:'group_appearance',icon:'all',label:pref.compact?L('Comfortable density','كثافة مريحة'):L('Compact density','كثافة مدمجة'),keywords:'rows table spacing',run:()=>togglePref('compact')},
    {id:'t-sound',group:'group_appearance',icon:'audio',label:pref.sound?L('Turn off completion sound','إيقاف صوت الاكتمال'):L('Turn on completion sound','تشغيل صوت الاكتمال'),keywords:'chime audio',run:()=>togglePref('sound')},
    {id:'t-notify',group:'group_appearance',icon:'attention',label:pref.notify?L('Turn off desktop notifications','إيقاف إشعارات سطح المكتب'):L('Turn on desktop notifications','تشغيل إشعارات سطح المكتب'),keywords:'alerts popup',run:()=>togglePref('notify')},
    {id:'t-clip',group:'group_appearance',icon:'clipboard',label:pref.clip?L('Stop watching clipboard for links','إيقاف مراقبة الحافظة'):L('Watch clipboard for links','مراقبة الحافظة بحثًا عن الروابط'),keywords:'copy detect paste auto',run:()=>togglePref('clip')},
    {id:'shortcuts',group:'group_appearance',icon:'keyboard',label:ux(lang,'shortcuts'),hint:'?',keywords:'keys help',run:()=>setShortcuts(true)},
    {id:'guide',group:'group_appearance',icon:'help',label:t('guide'),keywords:'tour tutorial',run:()=>moveTour(0)},
  ]
  const previewIndicator = (previewJobs.length>0||notifications.length>0) && <aside className={`preview-notifications ${playback?'with-player':''}`} aria-label={t('previewActivity')}>
    {previewJobs.map(job=><section className="preview-toast" key={job.id}>
      <div className="preview-toast-heading"><span className="preview-pulse"><Icon name="video" size={18}/></span><div role="status"><strong>{t('preparing')}</strong><span>{statusText(job.status)}</span></div></div>
      <p className="preview-toast-source" dir="auto" title={job.title||job.url}>{job.title||job.url}</p>
      <div className={`progress ${['queued','starting','processing','preparing_preview','cancelling'].includes(job.status)?'indeterminate':''}`} role="progressbar" aria-label={t('preparing')} aria-valuemin={0} aria-valuemax={100} aria-valuenow={job.status==='downloading'?Math.min(100,Math.max(0,job.percent)):undefined}><div style={{width:`${Math.min(100,Math.max(0,job.percent))}%`}}/></div>
      <div className="preview-toast-footer"><span className="numeric" dir="ltr">{job.status==='downloading'?`${Math.min(100,Math.max(0,job.percent)).toFixed(0)}%`:''}{job.eta!=null&&job.status==='downloading'?` · ${etaClock(job.eta)}`:''}</span><button className="cancel-button" aria-label={`${t('cancel')}: ${job.title||job.url}`} disabled={!!busy||job.status==='cancelling'} onClick={()=>void act('Cancel',async()=>{await cancelDownload(job.id);setJobs((await getJobs()).jobs)})}><Icon name="close" size={14}/>{t(job.status==='cancelling'?'taskCancelling':'cancel')}</button></div>
    </section>)}
    {notifications.map(job=><section className="preview-toast completion-toast" key={job.id} role="status"><div className="section-row"><strong>{t('completed')}</strong><button className="ghost compact" aria-label={t('dismiss')} onClick={()=>setNotifications(old=>old.filter(j=>j.id!==job.id))}><Icon name="close" size={15}/></button></div><p className="preview-toast-source" dir="auto">{job.title||job.filename}</p><button className="primary compact" disabled={!!busy} onClick={()=>void openDownloaded(job.id)}><Icon name="video" size={15}/>{t('openDownloaded')}</button></section>)}
  </aside>
  const folderControls = <div id="tour-destination" className="destination-block"><div className="section-label"><Icon name="folder"/><strong>{t('destination')}</strong><button className="ghost compact" disabled={!!busy||!preferences?.native_folder_picker} onClick={()=>void chooseFolder()}>{t('chooseFolder')}</button></div><div className="path" dir="ltr" title={preferences?.download_directory}>{preferences?.download_directory||'…'}</div><label className="toggle"><input type="checkbox" checked={preferences?.group_by_site||false} disabled={!!busy||!preferences} onChange={e=>void setGrouping(e.target.checked)}/>{t('groupSite')}</label><p className="muted">{preferences?.native_folder_picker?t('folderHint'):t('desktopFolder')}</p></div>
  const filterViews=['all','active','completed','attention','video','audio']
  const viewCount=(v:string)=>downloadJobs.filter(j=>v==='all'||v==='active'&&!terminal(j)||v==='completed'&&j.status==='completed'||v==='attention'&&['failed','cancelled'].includes(j.status)||v==='video'&&j.kind==='video'||v==='audio'&&j.kind==='audio').length
  const hostOf=(job:Job)=>job.site||(()=>{try{return new URL(job.url).hostname}catch{return ''}})()
  const smartUrls=(text:string)=>[...new Set(text.match(/https?:\/\/[^\s<>"']+/g)||[])]
  function changeSmart(value:string){setSmart(value);if(smartUrls(value).length){setSearch('')}else{setSearch(value);if(value&&workspace!=='downloads')setWorkspace('downloads')}}
  function submitSmart(event:FormEvent){event.preventDefault();const found=smartUrls(smart);if(found.length){setSmart('');setSearch('');intake(found)}else if(!smart.trim())setPalette(true)}
  const pageTitle=workspace==='downloads'?t(view as TextKey):workText(lang,workspace)
  const queuedCount=downloadJobs.filter(j=>j.status==='queued').length
  const thumbFor=(job:Job)=>job.thumbnail||(job.status==='completed'?`${API_BASE}/api/jobs/${job.id}/poster`:'')
  const taskActions=(job:Job,wide=false)=><>{job.purpose==='download'&&['queued','starting','downloading'].includes(job.status)&&<button className="secondary compact" onClick={()=>void act('Pause',async()=>{await pauseDownload(job.id);setJobs((await getJobs()).jobs)})}><Icon name="pause" size={14}/>{qText(lang,'pause')}</button>}{!['completed','failed','cancelled'].includes(job.status)&&<button className="cancel-button" aria-label={`${t('cancel')}: ${job.title||job.url}`} title={t('cancel')} disabled={!!busy||job.status==='cancelling'} onClick={()=>void act('Cancel',async()=>{await cancelDownload(job.id);setJobs((await getJobs()).jobs)})}><Icon name="close" size={15}/>{t(job.status==='cancelling'?'taskCancelling':'cancel')}</button>}{job.status==='paused'&&<button className="secondary compact" onClick={()=>void retry(job)}><Icon name="play" size={14}/>{qText(lang,'resume')}</button>}{['failed','cancelled'].includes(job.status)&&(wide?<button className="primary compact inspector-retry" disabled={!!busy} onClick={()=>void retry(job)}><Icon name="retry" size={16}/>{t('retry')}</button>:<button className="icon-button" aria-label={`${t('retry')}: ${job.title||job.url}`} title={t('retry')} disabled={!!busy} onClick={()=>void retry(job)}><Icon name="retry" size={17}/></button>)}{job.status==='completed'&&<><button className="secondary compact play-button" aria-label={`${t('playMedia')}: ${job.title||job.filename||job.url}`} title={t('playMedia')} disabled={!!busy} onClick={()=>void openDownloaded(job.id)}><Icon name="play" size={16}/>{t('playMedia')}</button><button className="icon-button mini-play-button" aria-label={`${miniLabel}: ${job.title||job.url}`} title={miniLabel} disabled={!!busy} onClick={()=>void openDownloaded(job.id,true)}><Icon name="video" size={17}/></button><button className="icon-button" aria-label={`${t('makeClip')}: ${job.title||job.url}`} title={t('makeClip')} disabled={!!busy} onClick={()=>selectSource(job)}><Icon name="scissors" size={17}/></button>{preferences?.native_folder_picker?<button className="icon-button" title={t('openFolder')} aria-label={`${t('openFolder')}: ${job.title||job.url}`} onClick={()=>void openFolder(job.id)}><Icon name="folder" size={17}/></button>:<a className="icon-button" title={t('save')} aria-label={`${t('save')}: ${job.title||job.url}`} href={downloadUrl(job.id)}><Icon name="down" size={17}/></a>}</>}</>
  const progressOf=(job:Job)=>{const pct=Math.min(100,Math.max(0,job.percent));return <div className="progress-cell"><div className={`progress ${job.status==='downloading'?'live ':''}${(['queued','starting','processing','clipping','preparing_preview','cancelling','pausing'].includes(job.status)||job.status==='downloading'&&!job.total_bytes)?'indeterminate':''}`}><div style={{width:`${pct}%`}}/></div><small dir="ltr">{job.status==='downloading'&&!job.total_bytes?'—':`${pct.toFixed(0)}%`} · {bytes(job.downloaded_bytes)} / {bytes(job.total_bytes)}</small><small className="compact-metrics" dir="ltr">{job.speed?`${bytes(job.speed)}/s`:'—'} · ETA {job.eta!=null&&!terminal(job)?etaClock(job.eta):'—'}</small></div>}
  const taskCard=(job:Job)=><article key={job.id} className={`task-card ${detailId===job.id?'focused':''} ${taskSelection.has(job.id)?'selected':''}`} data-job-id={job.id} data-status={job.status} tabIndex={0} draggable={job.status==='queued'} onDragStart={()=>setDragged(job.id)} onDragOver={e=>{if(job.status==='queued')e.preventDefault()}} onDrop={e=>{e.preventDefault();if(dragged&&job.status==='queued'){const ids=filtered.filter(j=>j.status==='queued').map(j=>j.id).filter(id=>id!==dragged);ids.splice(ids.indexOf(job.id),0,dragged);void act('Reorder',async()=>{await reorderQueue(ids);setSort('priority');setJobs((await getJobs()).jobs)})}setDragged(null)}} onClick={e=>{if(!(e.target as HTMLElement).closest('button,a,input,label'))setDetailId(job.id)}} onKeyDown={e=>{if(e.key==='Enter'&&e.target===e.currentTarget)setDetailId(job.id)}}>
    <label className="selection-cell task-select"><input type="checkbox" aria-label={`${sw('select')}: ${job.title||job.url}`} checked={taskSelection.has(job.id)} disabled={!taskSelection.has(job.id)&&taskSelection.size>=500} onChange={e=>setTaskSelection(old=>{const next=new Set(old);e.target.checked?next.add(job.id):next.delete(job.id);return next})}/></label>
    <div className={`task-thumb ${job.kind}`}><Icon name={job.kind} size={22}/>{thumbFor(job)&&<img loading="lazy" draggable={false} referrerPolicy="no-referrer" src={thumbFor(job)} alt="" onError={e=>{if(job.status==='completed'&&!e.currentTarget.dataset.fallback){e.currentTarget.dataset.fallback='1';e.currentTarget.src=`${API_BASE}/api/jobs/${job.id}/poster`}else e.currentTarget.style.display='none'}}/>}<span className="task-kind"><Icon name={job.kind} size={11}/></span></div>
    <div className="task-main"><button className="file-title" dir="auto" title={job.title||job.url} onClick={()=>setDetailId(job.id)}>{job.title||job.filename||job.url}</button><small className="task-meta" dir="auto">{hostOf(job)}<span> · {job.container.toUpperCase()} · {job.purpose==='preview'?t('preview'):job.quality==='best'?t('best'):job.quality}</span></small>{!terminal(job)&&job.phase!=='downloading'&&taskPhase(job,lang)&&<small className="task-phase">{taskPhase(job,lang)}</small>}{job.interrupted&&<small className="task-phase">{L('Recovered; ready to resume','تمت الاستعادة؛ جاهز للاستئناف')}</small>}</div>
    <div className="task-status"><span className={`status-badge ${job.status}`}>{statusText(job.status)}</span></div>
    <div className="task-progress">{progressOf(job)}</div>
    <div className="row-actions">{taskActions(job)}</div>
  </article>
  const overviewPanel=<div className="inspector-overview">
    <div className="inspector-heading"><span className="eyebrow">{L('Overview','نظرة عامة')}</span><h2>{L('Session','الجلسة')}</h2></div>
    <section className="overview"><div className="stat"><div className="stat-head"><i><Icon name="active" size={15}/></i><span>{t('active')}</span></div><strong><Count value={activeJobs.length}/><small>{t('downloads')}</small></strong></div><div className="stat"><div className="stat-head"><i><Icon name="completed" size={15}/></i><span>{t('completed')}</span></div><strong><Count value={completed.length}/><small>{t('downloads')}</small></strong></div><div className="stat stat-speed"><div className="stat-head"><i><Icon name="bolt" size={15}/></i><span>{t('speed')}</span><em className={totalSpeed>0?'live':''}>{ux(lang,totalSpeed>0?'live':'idle')}</em></div><strong dir="ltr"><Count value={totalSpeed} fmt={bytes}/><small>/s</small></strong><Sparkline values={speedHistory} active={totalSpeed>0}/></div><div className="stat"><div className="stat-head"><i><Icon name="drive" size={15}/></i><span>{ux(lang,'total')}</span></div><strong dir="ltr"><Count value={totalSaved} fmt={bytes}/><small>{completed.length} {ux(lang,'files')}</small></strong></div></section>
    <OverallBar lang={lang} jobs={downloadJobs}/>
    <div className="inspector-section"><span className="eyebrow">{L('Tools','الأدوات')}</span><div className="tool-list">{(['convert','studio','library'] as const).map(section=><button key={section} className={`tool-row tool-${section}`} onClick={()=>{setComposer(false);setSettingsOpen(false);setWorkspace(section)}}><span className="tool-symbol"><Icon name={section==='library'?'folder':section==='convert'?'convert':'scissors'} size={18}/></span><span><strong>{workText(lang,section)}</strong><small>{section==='convert'?L('Change format, size or codec','تغيير الصيغة أو الحجم أو الترميز'):section==='studio'?L('Trim and edit on a timeline','القص والتحرير على خط زمني'):L('Everything you have saved','كل ما حفظته')}</small></span><Icon name="arrow" size={15}/></button>)}</div></div>
    {batches.length>0&&<details className="batch-archives"><summary>{t('batches')} ({batches.length})</summary>{batches.map((id,i)=><a className="secondary link-button" key={id} href={archiveUrl(id)}>{t('batchArchive')} {batches.length-i} · {completed.filter(j=>j.batch_id===id).length}</a>)}</details>}
    <p className="inspector-tip"><Icon name="link" size={14}/>{L('Tip: paste or drop a link anywhere in the window to start a download.','تلميح: الصق رابطًا أو اسحبه إلى أي مكان في النافذة لبدء التنزيل.')}</p>
  </div>
  const detailPanel=detail&&<div className="inspector-detail detail-panel">
    <div className="inspector-heading row"><div><span className="eyebrow">{t('details')}</span></div><button className="icon-button" aria-label={t('close')} onClick={()=>setDetailId(null)}><Icon name="close"/></button></div>
    <div className={`inspector-poster ${detail.kind}`}><Icon name={detail.kind} size={36}/>{thumbFor(detail)&&<img src={thumbFor(detail)} alt="" referrerPolicy="no-referrer" onError={e=>{e.currentTarget.style.display='none'}}/>}</div>
    <h3 dir="auto">{detail.title||detail.filename||detail.url}</h3>
    <p className="inspector-meta" dir="auto">{hostOf(detail)} · {detail.container.toUpperCase()} · {detail.quality==='best'?t('best'):detail.quality}</p>
    <div className="inspector-state"><span className={`status-badge ${detail.status}`}>{statusText(detail.status)}</span>{!terminal(detail)&&taskPhase(detail,lang)&&<small className="task-phase">{taskPhase(detail,lang)}</small>}</div>
    {detail.status!=='completed'&&progressOf(detail)}
    <div className="inspector-actions">{taskActions(detail,true)}</div>
    <dl className="detail-grid"><div><dt>{t('url')}</dt><dd dir="ltr">{detail.url}</dd></div><div><dt>{t('destination')}</dt><dd dir="ltr">{detail.output_path||detail.destination||'—'}</dd></div><div><dt>{t('status')}</dt><dd>{statusText(detail.status)} · {detail.attempt||1} {t('attempts')}</dd></div><div><dt>{L('Size','الحجم')}</dt><dd dir="ltr">{bytes(detail.total_bytes||detail.downloaded_bytes)}</dd></div></dl>
    {['queued','paused'].includes(detail.status)&&<PriorityControls key={detail.id} job={detail} lang={lang} refresh={()=>void getJobs().then(data=>setJobs(data.jobs))} onError={setError}/>}
    {taskAdvice(detail,lang)&&<p className="recovery-note">{taskAdvice(detail,lang)}</p>}
    {detail.error&&<p className="job-error" dir="auto">{detail.error==='Interrupted by an app restart. Retry to continue.'?t('restartError'):detail.error.replace(/\x1b\[[0-9;]*m/g,'')}</p>}
    <div className="button-row"><button className="secondary" onClick={()=>void copyLink(detail)}><Icon name="link" size={16}/>{t('copyLink')}</button>{detail.status==='completed'&&<a className="secondary link-button" href={downloadUrl(detail.id)}><Icon name="down" size={16}/>{t('save')}</a>}</div>
  </div>
  return <div className={`cc-app ${pref.collapsed?'collapsed':''}`} dir={lang==='ar'?'rtl':'ltr'}>
    <nav className="cc-rail" aria-label={L('Main navigation','التنقل الرئيسي')}>
      <div className="rail-logo" title="DropDL Studio"><Logo/></div>
      <button className={`rail-item ${workspace==='downloads'?'selected':''}`} onClick={()=>{setComposer(false);setSettingsOpen(false);setWorkspace('downloads')}}><span className="rail-icon"><Icon name="down"/>{activeJobs.length>0&&<b className="rail-badge">{activeJobs.length}</b>}</span><span className="rail-label">{t('downloads')}</span></button>
      <div className="workspace-nav">{(['convert','studio','library'] as const).map(section=><button key={section} className={`rail-item nav-tool ${workspace===section?'selected':''}`} onClick={()=>{setComposer(false);setSettingsOpen(false);setWorkspace(section)}}><span className="rail-icon"><Icon name={section==='library'?'folder':section==='convert'?'convert':'scissors'}/></span><span className="rail-label">{section==='library'?L('Library','المكتبة'):section==='studio'?L('Studio','الاستوديو'):workText(lang,section)}</span></button>)}</div>
      <div className="rail-spacer"/>
      <button className="rail-item" aria-label={t('appearance')} title={t('appearance')} onClick={()=>setTheme(theme==='dark'?'light':'dark')}><span className="rail-icon"><Icon name={theme==='dark'?'sun':'moon'}/></span><span className="rail-label">{theme==='dark'?L('Light','فاتح'):L('Dark','داكن')}</span></button>
      <button className={`rail-item nav-tool ${settingsOpen?'selected':''}`} onClick={()=>{setComposer(false);setSettingsOpen(true)}}><span className="rail-icon"><Icon name="settings"/></span><span className="rail-label">{t('preferences')}</span></button>
      <button className="rail-item nav-tool" onClick={()=>moveTour(0)}><span className="rail-icon"><Icon name="help"/></span><span className="rail-label">{t('guide')}</span></button>
    </nav>
    <div className="cc-main">
      <header className="cc-topbar">
        <div className="manager-header"><h1>{pageTitle}</h1><small>DropDL Studio</small></div>
        <form className="smart-bar" onSubmit={submitSmart} role="search">
          <Icon name={smartUrls(smart).length?'link':'search'} size={17}/>
          <input id="queue-search" aria-label={L('Paste a link, search downloads, or press Enter for commands','الصق رابطًا أو ابحث في التنزيلات أو اضغط Enter للأوامر')} placeholder={L('Paste a link to download, or search…','الصق رابطًا للتنزيل أو ابحث…')} value={smart} onChange={e=>changeSmart(e.target.value)} onKeyDown={e=>{if(e.key==='Escape'&&smart){e.stopPropagation();changeSmart('')}}} dir="auto" autoComplete="off" spellCheck={false}/>
          {smartUrls(smart).length>0?<button className="primary compact" type="submit"><Icon name="down" size={15}/>{smartUrls(smart).length>1?L(`Add ${smartUrls(smart).length} links`,`إضافة ${smartUrls(smart).length} روابط`):L('Download','تنزيل')}</button>:<button type="button" className="smart-commands" onClick={()=>setPalette(true)} aria-label={ux(lang,'paletteTitle')}><kbd>Ctrl K</kbd></button>}
        </form>
        <div className="header-tools"><EngineUpdate lang={lang}/><select aria-label={t('language')} value={lang} onChange={e=>setLang(e.target.value as Language)}><option value="en">EN</option><option value="ar">ع</option></select><button id="tour-add" className="primary new-download" onClick={()=>{setWorkspace('downloads');setSettingsOpen(false);setComposer(true)}}><Icon name="plus" size={17}/><span>{t('newDownload')}</span></button></div>
      </header>
      <div className="cc-banners">
      {error&&!(composer||settingsOpen)&&<div className="error-card" role="alert"><div><strong>{t('error')}</strong><p dir="auto">{error.replace(/\x1b\[[0-9;]*m/g,'')}</p></div><button className="ghost compact" onClick={()=>setError('')}>{t('dismiss')}</button></div>}
      {connectionLost&&!(composer||settingsOpen)&&<div className="error-card" role="alert"><strong>{t('backendUnavailable')}</strong><p>{lang==='ar'?'لا تُحذف قائمة المهام. أعد تشغيل التطبيق لاستعادة آخر نقطة حفظ.':'Your queue is retained. Restart DropDL to recover the last saved checkpoint.'}</p><button className="secondary" onClick={()=>setSettingsOpen(true)}>{lang==='ar'?'التشخيص':'Diagnostics'}</button></div>}
      {health?.queue_checkpoint_ok===false&&<div className="error-card" role="alert">{lang==='ar'?'تعذر حفظ قائمة المهام. تحقق من مساحة القرص وصلاحيات مجلد بيانات التطبيق قبل إغلاقه.':'Queue checkpoints cannot be saved. Check disk space and profile permissions before closing.'}</div>}
      {!recoveryDismissed&&((health?.recovered_count||0)>0||health?.restored_from_backup)&&<div className="recovery-note" role="status"><div className="section-row"><strong>{lang==='ar'?'استعادة العمل بعد إعادة التشغيل':'Work recovered after restart'}</strong><button className="icon-button" aria-label={t('dismiss')} onClick={()=>setRecoveryDismissed(true)}><Icon name="close" size={14}/></button></div><p>{lang==='ar'?'تم الاحتفاظ بقائمة المهام والملفات الجزئية. التنزيلات المتوقفة تُستأنف وفق إعداد الاستعادة. راجع عمليات التصدير المتوقفة وأعد تشغيلها يدويًا.':'Your queue and partial files were retained. Interrupted downloads follow your recovery setting; review interrupted exports and retry them manually.'}</p>{jobs.some(j=>j.purpose==='download'&&j.interrupted&&j.status==='paused')&&<button className="secondary compact" onClick={()=>void act('Resume recovered downloads',async()=>{for(const j of jobs.filter(j=>j.purpose==='download'&&j.interrupted&&j.status==='paused'))await retryDownload(j.id);await refreshTasks()})}>{lang==='ar'?'استئناف التنزيلات المستعادة':'Resume recovered downloads'}</button>}</div>}
      {health&&(!health.ffmpeg||!health.ffprobe)&&<p className="notice">{t('ffmpegMissing')}</p>}
      </div>
      {workspace==='downloads'?<div className={`cc-downloads ${detail?'has-detail':''}`}>
        <section id="tour-queue" className="download-workspace cc-list">
          <div className="cc-list-head">
            <nav className="filter-nav" aria-label={t('downloads')}>{filterViews.map(v=><button key={v} className={view===v?'selected':''} onClick={()=>setView(v)}><Icon name={v} size={15}/><span>{t(v as TextKey)}</span><b>{viewCount(v)}</b></button>)}</nav>
            <div className="list-toolbar"><select aria-label={t('sort')} value={sort} onChange={e=>setSort(e.target.value)}><option value="priority">{qText(lang,'priority')}</option><option value="newest">{t('newest')}</option><option value="oldest">{t('oldest')}</option><option value="name">{t('name')}</option></select>{activeJobs.length>0&&<button className="ghost compact" disabled={!!busy} onClick={()=>void act('Cancel',async()=>{await Promise.all(activeJobs.map(j=>cancelDownload(j.id)));setJobs((await getJobs()).jobs)})}>{t('stopAll')}</button>}{downloadJobs.some(j=>j.status==='failed')&&<button className="secondary compact" disabled={!!busy} onClick={()=>void act('Retry',async()=>{for(const job of downloadJobs.filter(j=>j.status==='failed'))await retryDownload(job.id);setJobs((await getJobs()).jobs)})}>{t('retryAll')}</button>}<button className="ghost compact" disabled={!!busy||!downloadJobs.length} onClick={()=>setShowClear(!showClear)}>{t('clearQueue')}</button></div>
          </div>
          <QueueTools lang={lang} refresh={()=>void getJobs().then(data=>setJobs(data.jobs))} onError={setError}/>
          {showClear&&<div className="clear-panel"><strong>{t('clearQueue')}</strong><p className="muted">{t('clearHint')}</p><div className="button-row"><button className="secondary" disabled={!!busy} onClick={()=>void clearTasks(false)}>{t('clearFinished')}</button><button className="danger" disabled={!!busy} onClick={()=>void clearTasks(true)}>{t('clearAll')}</button><button className="ghost" onClick={()=>setShowClear(false)}>{t('keep')}</button></div></div>}
          {queueMessage&&<div className="inline-status" role="status">{queueMessage}<button aria-label={t('dismiss')} onClick={()=>setQueueMessage('')}><Icon name="close" size={15}/></button></div>}
          {filtered.length>0&&<div className="selection-tools"><label className="select-page"><input type="checkbox" aria-label={sw('page')} checked={pageJobs.length>0&&pageJobs.every(j=>taskSelection.has(j.id))} ref={node=>{if(node)node.indeterminate=pageJobs.some(j=>taskSelection.has(j.id))&&!pageJobs.every(j=>taskSelection.has(j.id))}} onChange={e=>setTaskSelection(old=>{const next=new Set(old);for(const job of pageJobs){if(e.target.checked&&next.size<500)next.add(job.id);else if(!e.target.checked)next.delete(job.id)}return next})}/></label><button className="ghost compact" onClick={()=>setTaskSelection(new Set(filtered.slice(0,500).map(j=>j.id)))}>{sw('all')}</button><button className="ghost compact" onClick={()=>setTaskSelection(new Set([...taskSelection,...pageJobs.map(j=>j.id)].slice(0,500)))}>{sw('page')}</button>{taskSelection.size>=500&&<small>{sw('limit')}</small>}<span className="list-count">{filtered.length} / {downloadJobs.length}</span></div>}
          <TaskSelection lang={lang} jobs={downloadJobs} selected={taskSelection} setSelected={setTaskSelection} refresh={refreshTasks} onError={setError}/>
          {filtered.length>0?<div className="task-list task-table">{pageJobs.map(taskCard)}</div>:<div className="queue-empty"><div className="empty-symbol"><Logo/></div><h2>{t(downloadJobs.length?'noMatches':'emptyTitle')}</h2><p>{downloadJobs.length?t('emptyHint'):L('Paste a link in the bar above, drop one onto the window, or start a new download.','الصق رابطًا في الشريط أعلاه أو اسحبه إلى النافذة أو ابدأ تنزيلًا جديدًا.')}</p><button className="primary" onClick={()=>setComposer(true)}><Icon name="plus" size={18}/>{t('newDownload')}</button></div>}
          {filtered.length>100&&<div className="list-bottom"><div className="queue-pagination"><button className="secondary compact" disabled={page===0} onClick={()=>setQueuePage(page-1)}>{t('previousPage')}</button><span dir="ltr">{page*100+1}–{Math.min((page+1)*100,filtered.length)}</span><button className="secondary compact" disabled={(page+1)*100>=filtered.length} onClick={()=>setQueuePage(page+1)}>{t('nextPage')}</button></div></div>}
        </section>
        <aside className="cc-inspector" aria-label={L('Inspector','لوحة التفاصيل')}>{detailPanel||overviewPanel}</aside>
      </div>:<div className="cc-workspace"><Workspace onPlay={playMedia} tab={workspace} setTab={setWorkspace} lang={lang} jobs={jobs} onLink={link=>{acceptURL(link);setWorkspace('downloads');setComposer(true)}} onQueued={()=>void getJobs().then(data=>setJobs(data.jobs))} onPreview={job=>{setPlayback(null);void act('Open editor',()=>openEditor(job.id,lang))}}/></div>}
      <footer className="cc-status" role="contentinfo">
        <span className={`status-engine ${health?'connected':''}`}><i/>{t(health?'connected':'connecting')}</span>
        <span dir="ltr" className={totalSpeed>0?'live':''}><Icon name="down" size={13}/>{totalSpeed>0?`${bytes(totalSpeed)}/s`:L('Idle','خامل')}</span>
        <span>{activeJobs.length} {L('active','نشطة')} · {queuedCount} {L('queued','بالانتظار')}</span>
        {health?<span>{health.max_parallel??health.max_concurrent_downloads} {t('parallel')}</span>:null}
        {health?.disk_free!=null&&<span dir="ltr"><Icon name="drive" size={13}/>{bytes(health.disk_free)} {L('free','متاحة')}</span>}
        <span className="status-spacer"/>
        <span className="status-version">DropDL {__DROPDL_VERSION__}{health?.engine_version?` · yt-dlp ${health.engine_version}`:''}{health&&health.version!==__DROPDL_VERSION__&&<b className="version-warning">{lang==='ar'?' · إصدار المحرك مختلف؛ أعد تشغيل التطبيق.':' · Engine version differs; restart the app.'}</b>}</span>
      </footer>
    </div>
    <RightClickLayer onLibraryMini={playMedia} jobs={jobs} lang={lang} onPlay={openDownloaded} onClip={selectSource} onDetails={setDetailId} onNew={()=>setComposer(true)} onRefresh={refreshTasks} onError={setError}/>
    {playback&&<MiniPlayer key={playback.media.key} media={playback.media} lang={lang} onClose={()=>setPlayback(null)} onExternal={playback.external}/>}
    {!(composer||settingsOpen)&&previewIndicator}
    {jobs.some(j=>j.purpose==='clip'&&j.status!=='completed'&&!dismissedClips.has(j.id))&&<div className="clip-export-indicator" role="status">{jobs.filter(j=>j.purpose==='clip'&&j.status!=='completed'&&!dismissedClips.has(j.id)).slice(0,3).map(j=><section className="preview-toast" key={j.id}><div className="section-row"><strong>{terminal(j)?statusText(j.status):lang==='ar'?'تصدير المقطع':'Exporting clip'}</strong>{terminal(j)&&<button className="ghost compact" aria-label={t('dismiss')} onClick={()=>setDismissedClips(old=>new Set([...old,j.id]))}><Icon name="close" size={15}/></button>}</div><p dir="auto">{j.title}</p>{j.error&&<p className="job-error" dir="auto">{j.error}</p>}<div className={`progress ${!terminal(j)&&j.percent===0?'indeterminate':''}`}><div style={{width:`${j.percent}%`}}/></div>{terminal(j)?<button className="secondary compact" disabled={!!busy} onClick={()=>void retry(j)}>{t('retry')}</button>:<button className="cancel-button" onClick={()=>void act('Cancel clip',async()=>{await cancelDownload(j.id);await refreshTasks()})}>{t('cancel')}</button>}</section>)}</div>}
    {(composer||settingsOpen)&&<div className="modal-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget&&tour<0){setComposer(false);setSettingsOpen(false)}}}><div className={`drawer ${settingsOpen?'preferences-drawer':''}`} role="dialog" aria-modal={tour<0} aria-labelledby="drawer-title" ref={modal}><header className="drawer-header"><div><span className="eyebrow">DropDL Studio</span><h2 id="drawer-title">{t(settingsOpen?'preferences':'newDownload')}</h2></div><button className="icon-button" aria-label={t('close')} onClick={()=>{if(tour>=0)finishTour();setComposer(false);setSettingsOpen(false)}}><Icon name="close"/></button></header>
    {connectionLost&&<div className="error-card drawer-error" role="alert"><strong>{t('backendUnavailable')}</strong></div>}
    {error&&<div className="error-card drawer-error" role="alert"><div><strong>{t('error')}</strong><p dir="auto">{error.replace(/\x1b\[[0-9;]*m/g,'')}</p></div><button className="ghost compact" onClick={()=>setError('')}>{t('dismiss')}</button></div>}
    {settingsOpen?<div className="drawer-body"><AppearancePanel lang={lang} theme={theme} setTheme={setTheme} accent={accent} setAccent={value=>setAccent(value as Accent)} motion={motion} setMotion={setMotion} density={pref.compact?'compact':'comfortable'} setDensity={value=>setPref(p=>({...p,compact:value==='compact'}))} colors={theme==='light'?lightAccents:accents}/><section className="panel"><label>{t('language')}<select value={lang} onChange={e=>setLang(e.target.value as Language)}><option value="en">English</option><option value="ar">العربية</option></select></label></section>{folderControls}{preferences&&<Organization lang={lang} value={preferences} onChange={setPreferences}/>}<section className="panel"><label className="toggle"><input type="checkbox" disabled={!window.pywebview?.api.configure_tray} checked={preferences?.keep_in_tray||false} onChange={e=>preferences&&setPreferences({...preferences,keep_in_tray:e.target.checked})}/>{lang==='ar'?'إبقاء التطبيق في علبة النظام عند إغلاق النافذة':'Keep in system tray when closing the window'}</label><p className="muted">{lang==='ar'?'تستمر التنزيلات. انقر مرتين على أيقونة التطبيق لفتحه، أو اختر خروج من قائمة الأيقونة.':'Downloads continue. Double-click the tray icon to reopen, or choose Exit from its menu.'}</p></section><SupportPanel lang={lang}/>{preferences&&<NetworkPanel lang={lang} value={preferences} onChange={setPreferences}/>}<section className="panel"><h3>{t('speedLimit')}</h3><label className="input-label" htmlFor="speed-limit">{t('speedHint')}</label><input id="speed-limit" dir="ltr" type="number" min="0" max="1000000" value={limit} onChange={e=>setLimit(e.target.value)}/></section><section className="panel"><label>{lang==='ar'?'حد السرعة الإجمالي (كيلوبايت/ثانية)':'Global bandwidth limit (KB/s)'}<input type="number" min={0} max={1000000} value={globalLimit} onChange={e=>setGlobalLimit(e.target.value)}/></label><p className="muted">{lang==='ar'?'يُقسم الحد على مهام التنزيل المتزامنة ويطبق عند بدء المهمة.':'Divided across download slots; applies when each task starts.'}</p><label className="toggle"><input type="checkbox" checked={preferences?.auto_recover!==false} onChange={e=>preferences&&setPreferences({...preferences,auto_recover:e.target.checked})}/>{lang==='ar'?'استعادة المهام التي توقفت عند إغلاق التطبيق':'Recover tasks interrupted by an app restart'}</label><label className="toggle"><input type="checkbox" checked={preferences?.auto_cleanup!==false} onChange={e=>preferences&&setPreferences({...preferences,auto_cleanup:e.target.checked})}/>{lang==='ar'?'تنظيف الملفات المؤقتة غير المستخدمة بعد ٧ أيام':'Clean unused temporary files after 7 days'}</label></section><button className="primary full" disabled={!!busy||!preferences} onClick={()=>void saveSettings()}>{t('saveSettings')}</button></div>:<>
    <div className="drawer-body composer-body"><div className="sheet-col"><section id="tour-source" className="panel"><h3><span className="step">01</span>{t('chooseSource')}</h3><div className="mode-tabs">{(['single','playlist','batch'] as const).map(tabName=><button key={tabName} disabled={!!busy} className={tab===tabName?'active':''} onClick={()=>{setTab(tabName);resetSource();setDuration(tabName==='single'?info?.duration||0:0)}}>{t(tabName)}</button>)}</div>{tab==='batch'?<><label className="input-label" htmlFor="batch-urls">{t('batchLabel')}</label><textarea id="batch-urls" dir="ltr" value={batchText} onChange={e=>setBatchText(e.target.value)} rows={4} placeholder={'https://site.com/video-one\nhttps://site.com/video-two'}/><div className="section-row"><span className="muted">{batchURLs.length} {t('unique')}</span><button className="ghost compact" disabled={!!busy} onClick={()=>void paste()}><Icon name="clipboard" size={15}/>{t('paste')}</button></div></>:<form onSubmit={analyze} className="source-form"><input dir="ltr" aria-label={t(tab==='playlist'?'playlistUrl':'url')} type="url" value={url} required placeholder={t(tab==='playlist'?'pastePlaylist':'pasteUrl')} onChange={e=>acceptURL(e.target.value)}/><div className="button-row"><button type="button" className="secondary compact" disabled={!!busy} onClick={()=>void paste()}><Icon name="clipboard" size={15}/>{t('paste')}</button><button className="primary compact" disabled={!!busy||!url.trim()}>{busy==='Analyze'?t('loading'):t(tab==='playlist'?'loadPlaylist':'analyze')}</button></div></form>}
    {tab==='single'&&info&&<div className="source-preview">{info.thumbnail&&<img src={info.thumbnail} alt=""/>}<div><span className="source">{info.extractor}</span><h4 dir="auto">{info.title}</h4><p dir="auto">{info.uploader} · <bdi>{info.duration?clock(info.duration):'—'}</bdi></p></div></div>}
    {tab==='playlist'&&playlist&&<><div className="playlist-head"><h4 dir="auto">{playlist.title}</h4><p>{selected.size} {t('selected')} / {playlist.entries.length} {t('loaded')}</p><div className="button-row"><button type="button" className="ghost compact" onClick={()=>setSelected(new Set(playlist.entries.filter(e=>e.url).map(e=>e.index)))}>{t('selectAll')}</button><button type="button" className="ghost compact" onClick={()=>setSelected(new Set())}>{t('clear')}</button></div></div><div className="playlist-list">{playlist.entries.map((entry:Entry)=><label key={entry.index}><input type="checkbox" disabled={!entry.url} checked={selected.has(entry.index)} onChange={e=>setSelected(old=>{const next=new Set(old);e.target.checked?next.add(entry.index):next.delete(entry.index);return next})}/><span className="entry-title" dir="auto">{entry.index}. {entry.title}</span><small><bdi>{entry.duration?clock(entry.duration):!entry.url?t('unavailable'):''}</bdi></small></label>)}</div>{playlist.has_more&&<div className="button-row"><button className="secondary" disabled={!!busy} onClick={()=>void more()}>{t('more')}</button><button className="secondary" disabled={!!busy} onClick={()=>void more(true)}>{t('loadAll')}</button></div>}</>}
    </section>
    <section className="panel"><label>{lang==='ar'?'إعداد سريع':'Quick preset'}<select defaultValue="custom" onChange={e=>{if(e.target.value==='mobile'){setMode('video');setVideoFormat('mp4');setQuality('720p')}else if(e.target.value==='quality'){setMode('video');setVideoFormat('mkv');setQuality('best')}else if(e.target.value==='audio'){setMode('audio');setAudioFormat('mp3');setQuality('best')}else if(e.target.value==='both'){setMode('both');setVideoFormat('mp4');setAudioFormat('mp3');setQuality('1080p')}}}><option value="custom">{lang==='ar'?'مخصص':'Custom'}</option><option value="mobile">{lang==='ar'?'فيديو للهاتف':'Mobile video'}</option><option value="quality">{lang==='ar'?'أفضل جودة':'Best quality'}</option><option value="audio">{lang==='ar'?'صوت فقط':'Audio only'}</option><option value="both">{lang==='ar'?'فيديو وصوت':'Video and audio'}</option></select></label><details><summary>{lang==='ar'?'خيارات التنزيل المتقدمة':'Advanced download options'}</summary><div className="settings-grid"><label>{qText(lang,'schedule')}<input type="datetime-local" value={scheduled} onChange={e=>setScheduled(e.target.value)}/></label><label>{lang==='ar'?'لغات الترجمة (مثل ar,en)':'Subtitle languages (e.g. ar,en)'}<input dir="ltr" value={subtitles} onChange={e=>setSubtitles(e.target.value)} placeholder="ar,en"/></label></div><label className="toggle"><input type="checkbox" checked={metadata} onChange={e=>setMetadata(e.target.checked)}/>{lang==='ar'?'تضمين البيانات والفصول':'Embed metadata and chapters'}</label><label className="toggle"><input type="checkbox" checked={duplicateSkip} onChange={e=>setDuplicateSkip(e.target.checked)}/>{lang==='ar'?'تخطي المخرجات المكررة':'Skip duplicate outputs'}</label><DownloadExtras lang={lang} value={extras} onChange={setExtras} mode={mode} videoFormat={videoFormat} audioFormat={audioFormat} info={info} hasSubtitles={subtitles.trim().length>0}/></details></section></div><div className="sheet-col"><section id="tour-output" className="panel"><h3><span className="step">02</span>{t('chooseOutput')}</h3><div className="mode-tabs">{(['video','audio','both'] as const).map(m=><button key={m} disabled={source?.kind==='audio'&&m!=='audio'} className={mode===m?'active':''} onClick={()=>setMode(m)}>{t(m)}</button>)}</div><div className="settings-grid">{mode!=='audio'&&<><label>{t('videoFormat')}<select value={videoFormat} onChange={e=>setVideoFormat(e.target.value)}>{['mp4','webm','mkv'].map(f=><option key={f}>{f}</option>)}</select></label><label>{t('quality')}<select disabled={!!source||!!pendingPreview} value={quality} onChange={e=>setQuality(e.target.value)}>{qualities.map(q=><option key={q} value={q}>{q==='best'?t('best'):q}{q!=='best'&&info?.sizes?.[q]?` · ~${bytes(info.sizes[q])}`:''}</option>)}</select></label></>}{mode!=='video'&&<label>{t('audioFormat')}<select value={audioFormat} onChange={e=>setAudioFormat(e.target.value)}>{['mp3','m4a','opus','flac','wav'].map(f=><option key={f} value={f}>{f.toUpperCase()}</option>)}</select></label>}</div>{mode==='both'&&<p className="notice">{t('twoFiles')}</p>}</section>
    {folderControls}
    <section className="panel clip-panel" id="clip-editor"><div id="tour-clip" className="section-row"><h3><span className="step">03</span>{t('clipMaker')}</h3><label className="toggle"><input type="checkbox" checked={clip} onChange={e=>{setClip(e.target.checked);if(!e.target.checked){if(pendingPreview)void cancelDownload(pendingPreview.id);resetSource()}}}/>{t('enableClip')}</label></div>{!clip?<p className="muted">{t('clipOff')}</p>:<>{source?<div className="clip-source"><span>{t('existingSource')} · <bdi>{source.quality}</bdi></span><button className="ghost compact" onClick={resetSource}>{t('useUrl')}</button></div>:<div className="preview-stage">{info?.thumbnail&&<img src={info.thumbnail} alt=""/>}<div className="preview-overlay"><Icon name="video" size={30}/><strong>{t(pendingPreview?'preparing':'clipMaker')}</strong><span>{t('previewHint')}</span>{!pendingPreview&&<button className="primary" disabled={!!busy||!url.trim()||tab!=='single'||!health?.ffmpeg||!health?.ffprobe} onClick={()=>void loadPreview()}>{t('preview')}</button>}</div></div>}
    {source&&<><video key={source.id} ref={player} controls playsInline preload="metadata" src={downloadUrl(source.id,true)} onLoadedMetadata={e=>{const d=e.currentTarget.duration;if(Number.isFinite(d)){setDuration(d);const a=Math.min(Math.max(0,start),Math.max(0,d-.1));const b=Math.min(Math.max(end,a+.1),d);setStart(a);setEnd(b);e.currentTarget.currentTime=a}}} onPlay={e=>{if(rangeOnly&&validClip){previewing.current=true;if(e.currentTarget.currentTime<start||e.currentTarget.currentTime>=end)e.currentTarget.currentTime=start}}} onTimeUpdate={e=>{const cur=e.currentTarget.currentTime;setPosition(cur);if(previewing.current&&cur>=end){e.currentTarget.pause();e.currentTarget.currentTime=end;previewing.current=false}}} onSeeking={e=>{if(rangeOnly&&validClip){if(e.currentTarget.currentTime<start)e.currentTarget.currentTime=start;else if(e.currentTarget.currentTime>end)e.currentTarget.currentTime=Math.max(start,end-.05)}}} onError={()=>{if(source&&!busy&&!pendingPreview&&!failedPreviews.current.has(source.id)){failedPreviews.current.add(source.id);void loadPreview(source,true)}else setError(t('previewFail'))}}/><div className="preview-transport"><button className="primary compact" disabled={!validClip} onClick={playRange}>{t('playClip')}</button><button className="secondary compact" onClick={()=>{player.current?.pause();previewing.current=false;seek(start)}}>{t('backStart')}</button><label className="toggle"><input type="checkbox" checked={rangeOnly} onChange={e=>{setRangeOnly(e.target.checked);previewing.current=e.target.checked&&!!player.current&&!player.current.paused}}/>{t('rangeOnly')}</label></div></>}
    {source&&<ClipTimeline job={source} lang={lang} start={start} end={end} seek={seconds=>{player.current?.pause();previewing.current=false;seek(seconds);setPosition(seconds)}} position={position} ranges={ranges} setRanges={setRanges}/>}<div className="timeline"><div className="timeline-selection" style={{left:`${start/sliderMax*100}%`,width:`${Math.max(0,end-start)/sliderMax*100}%`}}/><div className="timeline-marker" style={{left:`${start/sliderMax*100}%`}}>{t('start')}</div><div className="timeline-marker" style={{left:`${end/sliderMax*100}%`}}>{t('finish')}</div></div><div className="range-grid"><label>{t('start')} · <bdi>{clock(start)}</bdi><input aria-label={t('start')} type="range" min={0} max={sliderMax} step={.1} value={start} onChange={e=>updateStart(Math.min(Number(e.target.value),Math.max(0,end-.1)))}/><ClipTimeInput label={lang==='ar'?'وقت البداية':'Start timestamp'} value={start} onChange={updateStart} lang={lang} onValid={setStartTimeValid}/></label><label>{t('finish')} · <bdi>{clock(end)}</bdi><input aria-label={t('finish')} type="range" min={0} max={sliderMax} step={.1} value={end} onChange={e=>updateEnd(Math.max(Number(e.target.value),start+.1))}/><ClipTimeInput label={lang==='ar'?'وقت النهاية':'Finish timestamp'} value={end} onChange={updateEnd} lang={lang} onValid={setEndTimeValid}/></label></div><p className="muted">{t('selectedLength')}: <bdi>{clock(Math.max(0,end-start))}</bdi></p>{source&&<div className="button-row"><button className="secondary compact" onClick={()=>updateStart(position)}>{t('setStart')}</button><button className="secondary compact" onClick={()=>updateEnd(position)}>{t('setFinish')}</button></div>}{!validClip&&<p className="job-error">{t('invalidClip')}</p>}</>}</section><p className="support-note">{t('support')}</p></div></div>
    <div className="drawer-footer"><span>{clip?<><bdi>{clock(start)} – {clock(end)}</bdi></>:t('completeMedia')} · {urls.length} {t('queuedSources')}</span><button className="primary" disabled={!!busy||!!pendingPreview||!health?.ffmpeg||((clip||source)&&!health?.ffprobe)||(!source&&!urls.length)||(clip&&!validClip)} onClick={()=>void download()}><Icon name="down" size={18}/>{busy==='Queue downloads'||busy==='Export clip'?t('adding'):t(source?'export':'queue')}</button></div></>}
    {previewIndicator}</div></div>}
    {palette&&<CommandPalette lang={lang} commands={commands} onClose={()=>setPalette(false)} onUrls={intake}/>}
    {shortcuts&&<ShortcutsSheet lang={lang} onClose={()=>setShortcuts(false)}/>}
    {dragging&&<DropOverlay lang={lang}/>}
    {celebrate&&<Confetti lang={lang}/>}
    {clipUrl&&!composer&&<ClipToast lang={lang} url={clipUrl} onNo={()=>setClipUrl('')} onYes={()=>{intake([clipUrl]);setClipUrl('')}}/>}
    {tour>=0&&<Tour lang={lang} step={tour} move={moveTour} finish={finishTour}/>}
  </div>
}
