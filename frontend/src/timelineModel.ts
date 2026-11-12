import {EditProject,Segment,positioned,trackState,clipLocked} from './editorProject'
export const length=(s:Segment)=>(s.end-s.start)/s.speed
export const minimumClip=.05
export function moveClip(p:EditProject,from:number,boundary:number){
 const index=Math.max(0,Math.min(p.segments.length-1,boundary-(from<boundary?1:0)))
 if(index===from||!p.segments[from]||clipLocked(p,p.segments[from])||clipLocked(p,p.segments[index]))return {project:p,index:from}
 if(p.segments.some(s=>s.offset!==undefined)){const base=positioned(p),segments=base.segments.map(s=>({...s})),a=segments[from],b=segments[index];[a.offset,b.offset]=[b.offset,a.offset];[a.track,b.track]=[b.track,a.track];return {project:{...base,segments},index:from}}
 const segments=[...p.segments],item=segments.splice(from,1)[0];segments.splice(index,0,item)
 return {project:{...p,segments},index}
}
export function rollNeighbor(p:EditProject,index:number,edge:'start'|'end'){
 const base=positioned(p),s=base.segments[index];if(!s)return -1
 const boundary=s.offset!+(edge==='end'?length(s):0),tolerance=1e-6
 const matches=base.segments.map((part,i)=>({part,i})).filter(({part,i})=>i!==index&&(part.track||0)===(s.track||0)&&Math.abs((part.offset!+(edge==='start'?length(part):0))-boundary)<tolerance)
 // Ambiguous overlaps must never silently select a neighbour.
 return matches.length===1?matches[0].i:-1
}
export function trimClip(p:EditProject,index:number,edge:'start'|'end',delta:number,duration:number,mode:'trim'|'roll'|'slip'='trim',snap=false,sourceDurations:Record<string,number>={}){
 const original=p;p=positioned(p);const source=p.segments[index];if(!source||clipLocked(p,source)||!Number.isFinite(delta)||!Number.isFinite(duration))return original
 const step=1/(p.fps||30),frame=(n:number)=>snap?Math.round(n/step)*step:n
 const segments=p.segments.map(s=>({...s})),s=segments[index]
 if(mode==='slip'){
  const shift=Math.max(-source.start,Math.min(duration-source.end,frame(delta)*source.speed));s.start=source.start+shift;s.end=source.end+shift
 }else if(mode==='roll'){
  const neighborIndex=rollNeighbor(p,index,edge);if(neighborIndex<0||clipLocked(p,segments[neighborIndex]))return original
  const next=segments[neighborIndex],offset=source.offset!,boundary=offset+(edge==='end'?length(source):0)
  let shift=frame(boundary+delta)-boundary
  if(edge==='end'){
   shift=Math.max(Math.max((source.start+minimumClip-source.end)/source.speed,-next.start/next.speed),Math.min((duration-source.end)/source.speed,(next.end-next.start-minimumClip)/next.speed,shift))
   s.end=source.end+shift*source.speed;next.start+=shift*next.speed;next.offset=boundary+shift
  }else{
   const otherDuration=sourceDurations[next.source_job_id||'default']??next.end
   shift=Math.max(Math.max(-source.start/source.speed,(next.start+minimumClip-next.end)/next.speed,-offset),Math.min((source.end-source.start-minimumClip)/source.speed,(otherDuration-next.end)/next.speed,shift))
   s.start=source.start+shift*source.speed;s.offset=offset+shift;next.end+=shift*next.speed
  }
 }else if(edge==='start'){
  s.start=Math.max(0,source.start-source.offset!*source.speed,Math.min(source.end-minimumClip,source.start+(frame(source.offset!+delta)-source.offset!)*source.speed))
  s.offset=source.offset!+(s.start-source.start)/source.speed
 }else s.end=Math.max(source.start+minimumClip,Math.min(duration,source.end+(frame(source.offset!+length(source)+delta)-source.offset!-length(source))*source.speed))
 if(s.start===source.start&&s.end===source.end)return original
 return {...p,segments}
}
export function snapPosition(p:EditProject,seconds:number,clipDuration:number,index:number,playhead:number,pixelsPerSecond:number,enabled:boolean,frames=false){
 let value=Math.max(0,seconds);if(frames)value=Math.round(value*(p.fps||30))/(p.fps||30)
 if(!enabled)return {value,target:null as number|null}
 const targets=[0,playhead,...positioned(p).segments.flatMap((s,i)=>i===index?[]:[s.offset!,s.offset!+length(s)])]
 const proposed=value;let best=8/Math.max(.001,pixelsPerSecond),target:number|null=null
 for(const candidate of targets)for(const correction of [candidate-proposed,candidate-(proposed+clipDuration)])if(Math.abs(correction)<best&&proposed+correction>=0){best=Math.abs(correction);target=candidate;value=Math.max(0,proposed+correction)}
 return {value,target}
}
export function placeClip(p:EditProject,index:number,offset:number,track:number){
 if(!p.segments[index]||clipLocked(p,p.segments[index])||trackState(p,track).locked)return p
 const base=positioned(p);return {...base,segments:base.segments.map((s,i)=>i===index?{...s,offset:Math.max(0,Math.min(86400,offset)),track:Math.max(0,Math.min(7,track))}:s)}
}
