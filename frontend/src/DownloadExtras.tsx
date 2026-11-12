import {useEffect, useState} from 'react'
import {DownloadExtras as Extras, MediaInfo} from './api'

const KEY = 'dropdl-download-extras-v2'
export const DEFAULT_EXTRAS: Required<Extras> = {codec: 'auto', sponsorblock: 'off', embed_thumbnail: true, embed_subtitles: false, audio_quality: 'best'}

/** Last-used extras are remembered per viewer; the backend validates them again. */
export function useDownloadExtras(): [Required<Extras>, (next: Required<Extras>) => void] {
  const [value, setValue] = useState<Required<Extras>>(() => {
    try { return {...DEFAULT_EXTRAS, ...JSON.parse(localStorage.getItem(KEY) || '{}')} } catch { return DEFAULT_EXTRAS }
  })
  useEffect(() => { try { localStorage.setItem(KEY, JSON.stringify(value)) } catch { /* storage unavailable */ } }, [value])
  return [value, setValue]
}

type Props = {lang: string; value: Required<Extras>; onChange: (next: Required<Extras>) => void; mode: string; videoFormat: string; audioFormat: string; info?: MediaInfo | null; hasSubtitles: boolean}

export default function DownloadExtras({lang, value, onChange, mode, videoFormat, audioFormat, info, hasSubtitles}: Props) {
  const w = (en: string, ar: string) => lang === 'ar' ? ar : en
  const set = <K extends keyof Extras>(key: K, next: Required<Extras>[K]) => onChange({...value, [key]: next})
  const video = mode !== 'audio'
  const audio = mode !== 'video'
  const lossless = ['flac', 'wav'].includes(audioFormat)
  const youtube = !info || /youtube/i.test(info.extractor || '') || /youtu\.?be/i.test(info.webpage_url || '')
  return <div className="dl-extras" data-testid="download-extras">
    <h4>{w('Smart extras', 'إضافات ذكية')} <span className="new-pill">2.0</span></h4>
    <div className="settings-grid">
      {video && <label>{w('Video codec', 'ترميز الفيديو')}
        <select value={value.codec} onChange={e => set('codec', e.target.value as Required<Extras>['codec'])}>
          <option value="auto">{w('Automatic', 'تلقائي')}{videoFormat === 'mp4' ? w(' (plays everywhere)', ' (يعمل في كل مكان)') : ''}</option>
          <option value="compatible">{w('H.264 — maximum compatibility', 'H.264 — أقصى توافق')}</option>
          <option value="any">{w('Best quality (AV1/VP9 allowed)', 'أفضل جودة (يسمح AV1/VP9)')}</option>
        </select></label>}
      {audio && <label>{w('Audio quality', 'جودة الصوت')}
        <select value={lossless ? 'best' : value.audio_quality} disabled={lossless} onChange={e => set('audio_quality', e.target.value as Required<Extras>['audio_quality'])}>
          <option value="best">{lossless ? w('Lossless', 'بدون فقدان') : w('Best available', 'أفضل جودة متاحة')}</option>
          {['320', '256', '192', '128'].map(rate => <option key={rate} value={rate}>{rate} kbps</option>)}
        </select></label>}
      <label>{w('SponsorBlock', 'SponsorBlock')}
        <select value={value.sponsorblock} onChange={e => set('sponsorblock', e.target.value as Required<Extras>['sponsorblock'])}>
          <option value="off">{w('Off', 'إيقاف')}</option>
          <option value="mark">{w('Mark sponsors as chapters', 'تمييز الرعاة كفصول')}</option>
          <option value="remove">{w('Remove sponsors & self-promo', 'حذف الرعاة والترويج الذاتي')}</option>
        </select></label>
    </div>
    {value.sponsorblock !== 'off' && !youtube && <p className="muted">{w('SponsorBlock data exists for YouTube videos only; other sites are downloaded normally.', 'تتوفر بيانات SponsorBlock لفيديوهات YouTube فقط؛ تُنزّل المواقع الأخرى بشكل عادي.')}</p>}
    <label className="toggle"><input type="checkbox" checked={value.embed_thumbnail} onChange={e => set('embed_thumbnail', e.target.checked)}/>{w('Embed cover art / thumbnail', 'تضمين صورة الغلاف')}</label>
    {video && <label className="toggle"><input type="checkbox" checked={value.embed_subtitles} disabled={!hasSubtitles} onChange={e => set('embed_subtitles', e.target.checked)}/>{w('Embed subtitles inside the video', 'تضمين الترجمة داخل الفيديو')}{!hasSubtitles && <small className="muted"> — {w('set subtitle languages first', 'حدد لغات الترجمة أولًا')}</small>}</label>}
    {info && video && info.has_h264 === false && value.codec === 'compatible' && <p className="muted">{w('This source has no H.264 stream; the closest compatible format will be used.', 'لا يحتوي هذا المصدر على H.264؛ سيُستخدم أقرب تنسيق متوافق.')}</p>}
  </div>
}
