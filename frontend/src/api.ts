export type MediaInfo = {
  id?: string; title: string; uploader?: string; duration?: number; thumbnail?: string
  webpage_url?: string; extractor?: string; heights: number[]; suggested_qualities: string[]
  sizes?: Record<string, number>; audio_size?: number|null; is_live?: boolean; live_status?: string|null; has_h264?: boolean; chapters?: number; subtitles?: string[]
}
export type DownloadExtras = {codec?: 'auto'|'compatible'|'any'; sponsorblock?: 'off'|'mark'|'remove'; embed_thumbnail?: boolean; embed_subtitles?: boolean; audio_quality?: 'best'|'320'|'256'|'192'|'128'}
export type Job = {
  id: string; url: string; site?:string; destination?:string; output_path?:string; attempt?:number; created_at?:number; speed_limit_kbps?:number; kind: 'video' | 'audio'; container: string; quality: string
  priority?:number;scheduled_at?:number;conversion_options?:ConversionOptions;download_options?:DownloadExtras;retry_at?:number;auto_retries?:number;
  thumbnail?:string; purpose: string; preview_ready: boolean; title: string; batch_id?: string; clip_start?: number; clip_end?: number
  phase?:string;interrupted?:boolean;error_code?:string;status: string; percent: number; downloaded_bytes?: number; total_bytes?: number
  speed?: number; eta?: number; filename?: string; error?: string
}
export type Entry = { index: number; title: string; url: string | null; duration?: number }
export type Playlist = { title: string; entries: Entry[]; total?: number; has_more: boolean; next_start: number }
export type OutputOptions = {
  collection?:string;
  mode: 'video' | 'audio' | 'both'; video_container: string; audio_container: string
  quality: string; clip_enabled?:boolean;show_in_downloads?:boolean; clip_start?: number; clip_end?: number;skip_duplicates?:boolean;scheduled_at?:number;subtitle_languages?:string[];embed_metadata?:boolean;download_options?:DownloadExtras
}
export type Health = {revision?:number;disk_free?:number|null;engine_version?:string|null;max_parallel?:number;queue_checkpoint_ok?:boolean;recovered_count?:number;restored_from_backup?:boolean;ok: boolean; version?:string; ffmpeg: boolean; ffprobe: boolean; max_concurrent_downloads: number}
const isTauri = '__TAURI_INTERNALS__' in window
export const API_BASE = import.meta.env.VITE_API_BASE || (isTauri ? 'http://127.0.0.1:17321' : '')
async function request<T>(path: string, data?: unknown, timeout=0): Promise<T> {
  const controller=new AbortController()
  const timer=timeout?setTimeout(()=>controller.abort(),timeout):undefined
  let response:Response
  try {
    response = await fetch(API_BASE + path, {...(data === undefined ? {} : {
      method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(data)
    }),signal:controller.signal})
    const body = await response.json()
    if (!response.ok) {
      const detail = typeof body.detail === 'string' ? body.detail : Array.isArray(body.detail) ? body.detail.map((x: {msg:string}) => x.msg).join('; ') : `Request failed (${response.status})`
      throw new Error(detail)
    }
    return body as T
  } catch(error) {
    if(controller.signal.aborted){const timeoutError=new Error('Request timed out.');timeoutError.name='RequestTimeout';throw timeoutError}
    throw error
  } finally {if(timer)clearTimeout(timer)}
}
export const inspectUrl = (url: string) => request<MediaInfo>('/api/info', {url},60000)
export const inspectPlaylist = (url: string, start = 1) => request<Playlist>('/api/playlist', {url, start, limit: 100},60000)
export const getHealth = () => request<Health>('/api/health',undefined,6000)
export const getJobs = () => request<{jobs: Job[]; revision?: number}>('/api/jobs',undefined,6000)
// Cheap poll: the backend answers {unchanged:true} when the queue revision is current.
export const getJobsSince = (revision?: number) => request<{jobs?: Job[]; revision: number; unchanged?: boolean}>(`/api/jobs${revision===undefined?'':`?revision=${revision}`}`,undefined,6000)
export const createBatch = (urls: string[], options: OutputOptions) => request<{batch_id: string; jobs: Job[];skipped?:number}>('/api/batch', {urls, ...options})
export const createClip = (id: string, options: OutputOptions) => request<{batch_id: string; jobs: Job[]}>(`/api/jobs/${id}/clip`, options)
export const cancelDownload = (id: string) => request<Job>(`/api/jobs/${id}/cancel`, {})
export const downloadUrl = (id: string, preview = false) => `${API_BASE}/api/jobs/${id}/file${preview ? '?preview=true' : ''}`
export const archiveUrl = (id: string) => `${API_BASE}/api/batches/${id}/archive`

export const retryDownload = (id: string) => request<Job>(`/api/jobs/${id}/retry`, {})

export const preparePreview = (payload: {url?: string; source_job_id?: string; quality?: string; force_transcode?: boolean;proxy?:boolean}) => request<Job>('/api/preview', payload)

export const clearQueue = (include_active = false) => request<{removed:number; stopped:number; remaining:number}>('/api/queue/clear', {include_active})

export type Preferences = {download_directory:string;export_directory?:string;keep_in_tray?:boolean; group_by_site:boolean; speed_limit_kbps:number; native_folder_picker:boolean;global_speed_limit_kbps?:number;auto_recover?:boolean;auto_cleanup?:boolean;skip_duplicates?:boolean;folder_rule?:string;name_rule?:string
  max_concurrent_downloads?:number;max_auto_retries?:number;stall_timeout?:number;concurrent_fragments?:number;proxy?:string;force_ipv4?:boolean;impersonate?:'auto'|'always';cookies_browser?:string}
export const getPreferences = () => request<Preferences>('/api/settings')
export const savePreferences = (payload: Pick<Preferences,'group_by_site'|'speed_limit_kbps'> & Partial<Preferences>) => request<Preferences>('/api/settings',payload)
declare global {
  interface Window {pywebview?: {api: {configure_tray?:(enabled:boolean,language:string)=>Promise<boolean>;choose_folder: () => Promise<Preferences|null>;choose_export_folder?:()=>Promise<Preferences|null>; open_folder: (id?:string) => Promise<boolean>;open_downloaded?: (id:string)=>Promise<boolean>;export_diagnostics?:()=>Promise<boolean>;close_editor?:()=>Promise<boolean>;open_player?:(key:string,language:string,time:number,rate:number)=>Promise<boolean>;close_player?:()=>Promise<boolean>;dock_player?:(time:number,rate:number)=>Promise<boolean>;open_editor?: (id:string,language:string)=>Promise<boolean>;open_library?: (id:string)=>Promise<boolean>;locate_media?:(id:string)=>Promise<MediaFile|null>;reveal_library?:(id:string)=>Promise<boolean>;launch_repair?:()=>Promise<boolean>;choose_media_files?:()=>Promise<{files:MediaFile[];errors:{name:string;error:string}[]}>;choose_cookies?:()=>Promise<{configured:boolean}|null>}}}
}

// Local diagnostic reporting must never block app actions.
export function reportDiagnostic(event:string,message='') {
  void fetch(API_BASE+'/api/diagnostics',{method:'POST',headers:{'content-type':'application/json'},
    body:JSON.stringify({event:event.slice(0,80),message:message.slice(0,6000)}),keepalive:true}).catch(()=>{})
}

export type MediaFile={favorite?:boolean;collection_id?:string|null;collection_name?:string|null;id:string;path:string;title:string;kind:string;site:string;url:string;owned:boolean;created:number;metadata:Record<string,unknown>;exists:boolean;size:number;filename:string}
export type ConversionOptions={preset:string;container?:string;height?:number;fps?:number;rotate?:number;normalize?:boolean;target_mb?:number;start?:number;finish?:number;sample?:boolean;crop?:{width:number;height:number;x:number;y:number}}
export type ConversionPreset={label:string;ar:string;container:string;kind:string}
export const getLibrary=()=>request<{files:MediaFile[]}>('/api/library')
export const getConversionPresets=()=>request<{presets:Record<string,ConversionPreset>;custom:{name:string;options:ConversionOptions}[]}>('/api/convert/presets')
export const convertMedia=(media_ids:string[],options:ConversionOptions)=>request<{jobs:Job[];batch_id:string}>('/api/convert',{media_ids,...options})
export const saveConversionPreset=(name:string,options:ConversionOptions)=>request('/api/convert/presets',{name,options})
export const libraryFileUrl=(id:string)=>API_BASE+`/api/library/${id}/file`
export const thumbnailUrl=(id:string)=>API_BASE+`/api/library/${id}/thumbnail`
export const previewLibrary=(id:string)=>request<Job>(`/api/library/${id}/preview`,{})
export const removeMedia=(id:string,delete_file=false)=>request(`/api/library/${id}/remove`,{delete_file})
export const pauseDownload=(id:string)=>request<Job>(`/api/jobs/${id}/pause`,{})
export const queueControl=(action:'pause'|'resume')=>request('/api/queue/control',{action})
export const setPriority=(id:string,priority:number,scheduled_at=0)=>request(`/api/jobs/${id}/priority`,{priority,scheduled_at})
export const reorderQueue=(ids:string[])=>request('/api/queue/reorder',{ids})
export type Storage={free:number;total:number;temporary_bytes:number;directory:string;low_space:boolean}
export const getStorage=()=>request<Storage>('/api/storage')
export const cleanupStorage=()=>request<{removed:number}>('/api/storage/cleanup',{})
export const getCookieStatus=()=>request<{configured:boolean}>('/api/cookies')
export const removeCookies=()=>request('/api/cookies/remove',{})

export const removeSelectedTasks=(ids:string[])=>request<{removed:string[];missing:string[];stopped:number}>('/api/queue/remove',{ids})
export const selectedArchiveUrl=(ids:string[])=>API_BASE+'/api/queue/archive?ids='+encodeURIComponent(ids.join(','))
export const selectedMediaArchiveUrl=(ids:string[])=>API_BASE+'/api/library/selection/archive?ids='+encodeURIComponent(ids.join(','))
export const removeSelectedMedia=(ids:string[],delete_file=false)=>request<{removed:string[];errors:{id:string;error:string}[]}>('/api/library/selection/remove',{ids,delete_file})

export type SupportStatus={session?:{previous_unclean_exit:boolean};recovery?:{interrupted:number;restored_from_backup:boolean};version:string;checks:{id:string;ok:boolean;detail:string}[];findings:string[];failures:{id:string;error:string}[];repair_available:boolean}
export const getSupportStatus=()=>request<SupportStatus>('/api/support/status',undefined,6000)

export type MediaCollection={id:string;name:string;count:number;created:number}
export const getCollections=()=>request<{collections:MediaCollection[]}>('/api/collections')
export const saveCollection=(name:string,id?:string)=>request<MediaCollection>(id?`/api/collections/${id}/rename`:'/api/collections',{name})
export const removeCollection=(id:string)=>request(`/api/collections/${id}/remove`,{})
export const organizeMedia=(ids:string[],patch:{favorite?:boolean;collection_id?:string|null;title?:string})=>request<{files:MediaFile[]}>('/api/library/selection/organize',{ids,...patch})
export const getLibraryInfo=(id:string)=>request<{file:MediaFile;info:Record<string,unknown>}>(`/api/library/${id}/info`,undefined,30000)
