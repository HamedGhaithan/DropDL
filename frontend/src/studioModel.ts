import {EditProject,Segment,TextCue,positioned,clipLength,clipLocked} from './editorProject'
/** Pure timeline operations behind Clip Studio's smart tools. Every function returns a new project (or null when
 * nothing would change) and leaves the input untouched, so each tool is one undo step. */
export type Line={start:number;end:number;text:string;words?:number[]}
const MIN=.05

function pieces(s:Segment,bounds:[number,number][]):Segment[]{
 const {fade_in,fade_out,...rest}=s;let at=s.offset!
 return bounds.map(([a,b],n)=>{const piece:Segment={...rest,start:a,end:b,offset:at};if(n===0&&fade_in)piece.fade_in=fade_in;if(n===bounds.length-1&&fade_out)piece.fade_out=fade_out;at+=(b-a)/s.speed;return piece})
}

/** Keep only `ranges` (source seconds) of clip `index`, placed back to back. Later clips on the same track and
 * text cues move left by the time removed (a ripple edit), so no gap opens and captions stay in sync. */
export function keepRanges(p:EditProject,index:number,ranges:[number,number][]):{project:EditProject;index:number;removed:number}|null{
 const base=positioned(p),s=base.segments[index];if(!s||clipLocked(p,s))return null
 const parts=ranges.map(([a,b])=>[Math.max(s.start,a),Math.min(s.end,b)] as [number,number]).filter(([a,b])=>b-a>=MIN).sort((x,y)=>x[0]-y[0])
 const merged:[number,number][]=[];for(const [a,b] of parts){const last=merged[merged.length-1];if(last&&a<=last[1]+1e-6)last[1]=Math.max(last[1],b);else merged.push([a,b])}
 if(!merged.length)return null
 const kept=merged.reduce((n,[a,b])=>n+(b-a)/s.speed,0),removed=clipLength(s)-kept
 if(removed<.01)return null
 if(base.segments.length-1+merged.length>100)throw Error('The timeline supports up to 100 clips.')
 const replacement=pieces(s,merged),end=s.offset!+clipLength(s),track=s.track||0
 const segments=base.segments.flatMap((part,i)=>i===index?replacement:[(part.track||0)===track&&part.offset!>=end-1e-6?{...part,offset:Math.max(0,part.offset!-removed)}:part])
 // Old sequence time -> new sequence time; times inside removed stretches snap to the next kept moment.
 const remap=(t:number)=>{if(t<=s.offset!)return t;if(t>=end)return t-removed;const source=s.start+(t-s.offset!)*s.speed;for(const piece of replacement){if(source<piece.start)return piece.offset!;if(source<=piece.end)return piece.offset!+(source-piece.start)/s.speed}return end-removed}
 const texts=p.texts?.map(c=>({...c,start:remap(c.start),end:remap(c.end)})).filter(c=>c.end-c.start>=MIN)
 return {project:{...base,segments,...(p.texts?{texts}:{})},index,removed}
}

/** The complement of `remove` (source seconds) inside clip `index`, kept with keepRanges. */
export function removeRanges(p:EditProject,index:number,remove:[number,number][]){
 const s=positioned(p).segments[index];if(!s)return null
 const keep:[number,number][]=[];let cursor=s.start
 for(const [a,b] of [...remove].sort((x,y)=>x[0]-y[0])){if(a>cursor)keep.push([cursor,Math.min(a,s.end)]);cursor=Math.max(cursor,b)}
 if(cursor<s.end)keep.push([cursor,s.end])
 return keepRanges(p,index,keep)
}

/** Cut clip `index` at each of `times` (source seconds) without moving anything. */
export function splitAtTimes(p:EditProject,index:number,times:number[]):{project:EditProject;index:number;cuts:number}|null{
 const base=positioned(p),s=base.segments[index];if(!s||clipLocked(p,s))return null
 const cuts=[...new Set(times)].filter(t=>t>s.start+MIN&&t<s.end-MIN).sort((a,b)=>a-b)
 if(!cuts.length)return null
 if(base.segments.length+cuts.length>100)throw Error('The timeline supports up to 100 clips.')
 const bounds=[s.start,...cuts,s.end],ranges=bounds.slice(0,-1).map((a,n)=>[a,bounds[n+1]] as [number,number])
 return {project:{...base,segments:base.segments.flatMap((part,i)=>i===index?pieces(s,ranges):[part])},index,cuts:cuts.length}
}

/** The clip that ends exactly where clip `index` starts, on the same track (or -1). */
export function previousNeighbour(p:EditProject,index:number){
 const base=positioned(p),s=base.segments[index];if(!s)return -1
 return base.segments.findIndex((part,i)=>i!==index&&(part.track||0)===(s.track||0)&&Math.abs(part.offset!+clipLength(part)-s.offset!)<.02)
}

/** Overlap clip `index` with the clip before it by `seconds` and fade it in, so one shot melts into the next.
 * The clip and everything after it on its track move back by the overlap. */
export function crossDissolve(p:EditProject,index:number,seconds:number):{project:EditProject;index:number}|null{
 const base=positioned(p),s=base.segments[index],previous=previousNeighbour(p,index)
 if(!s||previous<0||clipLocked(p,s))return null
 const d=Math.min(seconds,clipLength(base.segments[previous])/2,clipLength(s)/2);if(d<.1)return null
 const track=s.track||0,start=s.offset!
 const segments=base.segments.map((part,i)=>{if(i===index)return {...part,offset:start-d,fade_in:+d.toFixed(3)};if(i!==previous&&(part.track||0)===track&&part.offset!>=start-1e-6)return {...part,offset:part.offset!-d};return part})
 // On one track a later clip draws over an earlier one, so the incoming clip must come after the outgoing clip.
 if(index<previous){const [moved]=segments.splice(index,1);segments.splice(previous,0,moved);return {project:{...base,segments},index:previous}}
 return {project:{...base,segments},index}
}

/** Fade the previous clip out to black and this clip in from black, half of `seconds` each. */
export function dipToBlack(p:EditProject,index:number,seconds:number):EditProject|null{
 const base=positioned(p),s=base.segments[index],previous=previousNeighbour(p,index);if(!s||clipLocked(p,s))return null
 const half=+(seconds/2).toFixed(3)
 return {...base,segments:base.segments.map((part,i)=>i===index?{...part,fade_in:Math.min(half,clipLength(part)/2)}:i===previous?{...part,fade_out:Math.min(half,clipLength(part)/2)}:part)}
}

/** Transcript lines that fall inside clip `index`, as text cues on the finished timeline. Lines that carry word
 * timings (YouTube's automatic captions) keep them, so word-by-word caption styles follow the speech exactly. */
export function transcriptCues(p:EditProject,index:number,lines:Line[],maxWords=0):TextCue[]{
 const s=positioned(p).segments[index];if(!s)return []
 const at=(t:number)=>s.offset!+(t-s.start)/s.speed,cues:TextCue[]=[]
 for(const line of lines){
  const a=Math.max(line.start,s.start),b=Math.min(line.end,s.end);if(b-a<MIN)continue
  const words=line.text.split(/\s+/).filter(Boolean)
  if(line.words&&line.words.length===words.length){
   const kept=words.map((w,i)=>({w,t:line.words![i]})).filter(x=>x.t>=a-1e-6&&x.t<b);if(!kept.length)continue
   const size=maxWords||kept.length
   for(let i=0;i<kept.length;i+=size){const group=kept.slice(i,i+size),next=kept[i+size],from=i===0?a:group[0].t,to=next?next.t:b
    if(to-from<MIN)continue
    cues.push({start:at(from),end:at(to),text:group.map(x=>x.w).join(' '),kind:'caption',words:group.map((x,n)=>at(n===0?from:x.t))})}
  }else for(const chunk of chunks(line.text,maxWords,at(a),at(b)))cues.push(chunk)
 }
 return cues.slice(0,500)
}

/** Split a caption into phrases of at most `maxWords` words, timed by their share of the characters. */
export function chunks(text:string,maxWords:number,start:number,end:number):TextCue[]{
 const words=text.split(/\s+/).filter(Boolean);if(!maxWords||words.length<=maxWords)return [{start,end,text,kind:'caption'}]
 const groups:string[]=[];for(let i=0;i<words.length;i+=maxWords)groups.push(words.slice(i,i+maxWords).join(' '))
 const total=groups.reduce((n,g)=>n+g.length,0);let at=start
 return groups.map((g,i)=>{const next=i===groups.length-1?end:at+(end-start)*g.length/total,cue={start:at,end:next,text:g,kind:'caption' as const};at=next;return cue})
}

/** Replace the captions under clip `index` with `cues`, keeping titles and captions elsewhere. */
export function withCaptions(p:EditProject,index:number,cues:TextCue[]):EditProject{
 const s=positioned(p).segments[index];if(!s)return p
 const from=s.offset!,to=from+clipLength(s)
 const kept=(p.texts||[]).filter(t=>t.kind!=='caption'||t.end<=from+1e-6||t.start>=to-1e-6)
 return {...p,texts:[...kept,...cues].sort((a,b)=>a.start-b.start).slice(0,500)}
}

/** Index of the transcript line playing at `source` seconds (or -1). */
export const currentLine=(lines:Line[],source:number)=>lines.findIndex(l=>source>=l.start&&source<l.end)

const LOOK_IDS=['vivid','warm','cool','cinematic','punch','mono','noir','vintage','fade','dream']
const within=(v:unknown,min:number,max:number)=>v===undefined||typeof v==='number'&&Number.isFinite(v)&&v>=min&&v<=max
/** The 3.0 per-clip fields of a saved or loaded project are in range (mirrors the backend's EditSegment). */
export const clipExtrasValid=(s:Segment)=>(s.motion===undefined||['zoom-in','zoom-out','pan-left','pan-right'].includes(s.motion))&&within(s.motion_amount,.03,.5)&&within(s.focus_x,0,1)&&within(s.focus_y,0,1)&&(s.look===undefined||LOOK_IDS.includes(s.look))&&within(s.fade_in,0,10)&&within(s.fade_out,0,10)&&within(s.opacity,0,1)&&within(s.scale,.1,1)&&within(s.x,0,1)&&within(s.y,0,1)&&(s.denoise===undefined||typeof s.denoise==='boolean')&&(s.voice===undefined||typeof s.voice==='boolean')


// ---------------------------------------------------------------- music: beats and the montage
/** Beat times found in a piece of music (its own seconds), placed on the timeline the way that music plays. */
export function beatsOnTimeline(beats:number[],music:{start:number;end?:number;offset:number;speed?:number},total:number){
 const speed=music.speed||1
 return beats.filter(b=>b>=music.start-1e-6&&(music.end===undefined||b<=music.end+1e-6)).map(b=>+(music.offset+(b-music.start)/speed).toFixed(3)).filter(t=>t>=0&&t<=total+30)
}

/** Re-time the clips on V1, in order, so every cut lands on a beat. `every` is how many beats each clip lasts, or
 * 'nearest' to keep each clip close to its current length. Clips may grow into unused source (up to `durations`). */
export function cutToBeats(p:EditProject,beats:number[],every:number|'nearest',durations:Record<string,number>={}):{project:EditProject;changed:number}|null{
 const base=positioned(p),grid=[...new Set(beats)].filter(Number.isFinite).sort((a,b)=>a-b)
 const order=base.segments.map((s,i)=>({s,i})).filter(({s})=>(s.track||0)===0).sort((a,b)=>a.s.offset!-b.s.offset!)
 if(grid.length<2||!order.length||order.some(({s})=>clipLocked(p,s)))return null
 let b=grid.findIndex(t=>t>=order[0].s.offset!-1e-6);if(b<0)return null
 let cursor=grid[b],changed=0
 const segments=base.segments.map(s=>({...s}))
 for(const {s,i} of order){
  const room=((durations[s.source_job_id||'']??s.end)-s.start)/s.speed,current=clipLength(s)
  let k=-1
  if(every==='nearest'){const want=cursor+current;for(let n=b+1;n<grid.length&&grid[n]-cursor<=room+1e-6;n++)if(k<0||Math.abs(grid[n]-want)<Math.abs(grid[k]-want))k=n}
  else{const n=b+every;if(n<grid.length&&grid[n]-cursor<=room+1e-6)k=n;else for(let m=b+1;m<grid.length&&grid[m]-cursor<=room+1e-6;m++)k=m}
  if(k<0||grid[k]-cursor<MIN){segments[i]={...segments[i],offset:cursor};cursor+=current;b=grid.findIndex(t=>t>=cursor-1e-6);if(b<0)b=grid.length-1;continue}
  const length=grid[k]-cursor
  segments[i]={...segments[i],offset:+cursor.toFixed(3),end:+(s.start+length*s.speed).toFixed(3)};changed++
  cursor=grid[k];b=k
 }
 return changed?{project:{...base,segments},changed}:null
}

// ---------------------------------------------------------------- markers and chapters
export function addMarker(p:EditProject,t:number,label=''):EditProject{
 const markers=[...(p.markers||[]).filter(m=>Math.abs(m.t-t)>.05),{t:+Math.max(0,t).toFixed(3),label:label||`Marker ${(p.markers?.length||0)+1}`}].sort((a,b)=>a.t-b.t).slice(0,200)
 return {...p,markers}
}
const stamp=(n:number)=>{const s=Math.max(0,Math.floor(n));return s>=3600?`${Math.floor(s/3600)}:${String(Math.floor(s%3600/60)).padStart(2,'0')}:${String(s%60).padStart(2,'0')}`:`${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}`}
/** A YouTube description chapter list: it must start at 0:00, so a "Start" chapter is added when needed. */
export function chaptersText(markers:{t:number;label:string}[],intro='Start'){
 const list=[...markers].sort((a,b)=>a.t-b.t);if(!list.length)return ''
 if(list[0].t>=1)list.unshift({t:0,label:intro})
 return list.map(m=>`${stamp(m.t)} ${m.label}`).join('\n')
}
