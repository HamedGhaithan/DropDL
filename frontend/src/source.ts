export function isYouTubePlaylist(value:string):boolean {
  try {
    const url=new URL(value.trim())
    const host=url.hostname.toLowerCase()
    return ['http:','https:'].includes(url.protocol) && (host==='youtu.be'||host==='youtube.com'||host.endsWith('.youtube.com')) && !!url.searchParams.get('list')
  } catch {return false}
}
