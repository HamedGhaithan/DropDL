import {useEffect,useRef} from 'react'
import {EditProject,Segment,positioned,clipLength,outputDuration,trackState} from './editorProject'
import {API_BASE,downloadUrl} from './api'
import {AUDIO_LEVEL_EVENT} from './proEditor'
import {clipAlpha,clipFadeGain,fullFrame,hasVignette,lookFilter,motionTransform} from './looks'
type Clip=Segment&{offset:number}
/** Live composition of the timeline. Visible layers are stacked bottom to top (picture-in-picture, opacity and
 * dissolves show through); decoding stops at the first opaque full-frame layer, so a plain cut uses one decoder.
 * Paused startup uses a still image. */
export default function SequencePreview({project,sourceId,time,playing,onTime,onStop,previews,sources,enabled,onSourceError}:{project:EditProject;sourceId:string;time:number;playing:boolean;onTime:(n:number)=>void;onStop:()=>void;previews:Record<string,string>;sources:Record<string,{video?:boolean;audio?:boolean}>;enabled:boolean;onSourceError:(id:string)=>void}){
 const mixer=useRef<{context:AudioContext;limiter:DynamicsCompressorNode;meters?:AnalyserNode[];samples?:Float32Array<ArrayBuffer>;nodes:Map<HTMLMediaElement,{source:MediaElementAudioSourceNode;gain:GainNode}>}|null>(null)
 const duck=useRef(1),players=useRef<Record<number,HTMLMediaElement|null>>({}),backdrops=useRef<Record<number,HTMLCanvasElement|null>>({}),boxes=useRef<Record<number,HTMLDivElement|null>>({}),clock=useRef(time),callback=useRef({onTime,onStop});callback.current={onTime,onStop}
 const timelineClips=positioned(project).segments as Clip[],total=outputDuration(project),bed=project.soundtrack
 const clips:Clip[]=[...timelineClips,...(bed?[{start:bed.start,end:bed.start+Math.max(0,total-bed.offset),speed:1,offset:bed.offset,track:-1,source_job_id:bed.source_job_id,gain:bed.muted?0:bed.gain}]:[])]
 const idOf=(s:Segment)=>s.source_job_id||sourceId
 const activeAt=(t:number)=>clips.map((s,i)=>({s,i})).filter(({s})=>t>=s.offset&&t<s.offset+clipLength(s))
 const active=activeAt(time)
 // Bottom-to-top visible layers at `t`, skipping what an opaque full-frame layer hides.
 function layersAt(t:number){
  const stack=activeAt(t).filter(({s})=>(s.track??0)>=0&&!trackState(project,s.track||0).hidden&&sources[idOf(s)]?.video!==false).sort((a,b)=>(a.s.track||0)-(b.s.track||0)||a.i-b.i)
  const kept:number[]=[]
  for(let n=stack.length-1;n>=0;n--){const {s,i}=stack[n];kept.unshift(i);if(fullFrame(s)&&clipAlpha(s,t,clipLength(s))>=.999)break}
  return kept
 }
 const layers=layersAt(time),visible=layers[layers.length-1],visibleSource=visible===undefined?null:idOf(clips[visible])
 const fit=project.fit||'crop',objectFit=project.ratio==='original'||fit!=='crop'?'contain':'cover'
 const base=`brightness(${1+project.brightness}) contrast(${project.contrast}) saturate(${project.saturation})`
 useEffect(()=>()=>{void mixer.current?.context.close()},[])
 useEffect(()=>{clock.current=time},[time])
 useEffect(()=>{
  let frame=0,previous=performance.now(),published=0
  const tick=(now:number)=>{
   if(playing)clock.current=Math.min(total,clock.current+(now-previous)/1000);previous=now
   const t=clock.current,fade=Math.max(0,Math.min(1,project.fadeIn?t/Math.min(project.fadeIn,total/2):1,project.fadeOut?(total-t)/Math.min(project.fadeOut,total/2):1))
   if(playing&&!mixer.current){try{const context=new AudioContext(),limiter=context.createDynamicsCompressor();limiter.connect(context.destination);let meters:AnalyserNode[]|undefined;try{const splitter=context.createChannelSplitter(2);limiter.connect(splitter);meters=[0,1].map(channel=>{const analyser=context.createAnalyser();analyser.fftSize=1024;splitter.connect(analyser,channel);return analyser})}catch{meters=undefined}mixer.current={context,limiter,meters,samples:new Float32Array(1024),nodes:new Map()};void context.resume()}catch{}}
   const mix=mixer.current;if(mix){const live=new Set(Object.values(players.current));for(const [node,wiring] of mix.nodes)if(!live.has(node)){wiring.source.disconnect();wiring.gain.disconnect();mix.nodes.delete(node)}}
   const speaking=!!project.duck&&clips.some(c=>(c.track??0)>=0&&t>=c.offset&&t<c.offset+clipLength(c)&&sources[idOf(c)]?.audio!==false&&(c.gain??1)>0&&!trackState(project,c.track||0).muted)
   duck.current+=((speaking?.32:1)-duck.current)*(speaking?.35:.04)
   Object.entries(players.current).forEach(([key,v])=>{const s=clips[Number(key)];if(!v||!s)return
    const length=clipLength(s),desired=s.start+Math.max(0,t-s.offset)*s.speed,inside=t>=s.offset&&t<s.offset+length&&(!Number.isFinite(v.duration)||desired<v.duration),gain=(s.track??0)>=0&&trackState(project,s.track||0).muted?0:Math.max(0,(s.gain??1)*project.volume*fade*((s.track??0)>=0?clipFadeGain(s,t,length):duck.current))
    if(v.playbackRate!==s.speed)v.playbackRate=s.speed
    if(mix){let wiring=mix.nodes.get(v);if(!wiring){try{const source=mix.context.createMediaElementSource(v),node=mix.context.createGain();source.connect(node);node.connect(mix.limiter);wiring={source,gain:node};mix.nodes.set(v,wiring)}catch{}}if(wiring){wiring.gain.gain.value=gain;v.volume=1}else v.volume=Math.min(1,gain)}else v.volume=Math.min(1,gain)
    if(inside){if(v.readyState>=1&&!v.seeking&&Math.abs(v.currentTime-desired)>(playing?.2:.02))v.currentTime=desired;if(playing&&v.paused)void v.play().catch(()=>{});if(!playing&&!v.paused)v.pause()}else if(!v.paused)v.pause()
    // Per-clip fades and opacity change every frame, so they are written straight to the layer.
    const box=boxes.current[Number(key)];if(box)box.style.opacity=String(clipAlpha(s,t,length)*fade)
    drawBackdrop(Number(key))
    if(s.motion&&v instanceof HTMLVideoElement)v.style.transform=`rotate(${project.rotate}deg) scaleX(${project.flip?-1:1}) ${motionTransform(s,t,length)}`
   })
   if(playing){if(now-published>=40){callback.current.onTime(t);published=now;const levels=mix?.meters&&mix.samples?mix.meters.map(analyser=>{analyser.getFloatTimeDomainData(mix.samples!);let peak=0;for(const value of mix.samples!)peak=Math.max(peak,Math.abs(value));return peak}):null;if(levels)window.dispatchEvent(new CustomEvent(AUDIO_LEVEL_EVENT,{detail:{left:levels[0],right:levels[1]}}))}if(t>=total){callback.current.onTime(total);callback.current.onStop();return}frame=requestAnimationFrame(tick)}
  }
  tick(performance.now())
  return()=>{cancelAnimationFrame(frame);Object.values(players.current).forEach(v=>v?.pause())}
 },[playing,project,total,enabled,time===0,layers.join(','),previews])
 // The blurred fill is a tiny copy of the layer's own frame, redrawn per frame while playing and after each seek.
 function drawBackdrop(i:number){const canvas=backdrops.current[i],v=players.current[i];if(canvas&&v instanceof HTMLVideoElement&&v.readyState>=2){try{canvas.getContext('2d')?.drawImage(v,0,0,canvas.width,canvas.height)}catch{}}}
 // Seek once after metadata arrives when paused. No continuous idle animation loop.
 function ready(i:number){const v=players.current[i],s=clips[i];if(v&&s)v.currentTime=Math.max(s.start,Math.min(s.end,s.start+(time-s.offset)*s.speed))}
 useEffect(()=>{if(!playing)Object.keys(players.current).forEach(i=>ready(Number(i)))},[time,playing,enabled,project])
 const fade=Math.max(0,Math.min(1,project.fadeIn?time/Math.min(project.fadeIn,total/2):1,project.fadeOut?(total-time)/Math.min(project.fadeOut,total/2):1))
 const shown=new Set(layers)
 return <div className="sequence-preview" aria-label="Timeline composition">
  {!enabled&&visibleSource&&<img className="sequence-still" src={`${API_BASE}/api/jobs/${visibleSource}/frame/0`} alt="" style={{opacity:fade,filter:`${lookFilter(clips[visible!].look)} ${base}`.trim()}} onError={e=>{e.currentTarget.style.visibility='hidden'}}/>}
  {enabled&&active.filter(({i})=>playing||shown.has(i)).map(({s,i})=>{const id=idOf(s),props={crossOrigin:'anonymous' as const,preload:'metadata','data-track':s.track,src:downloadUrl(previews[id]||id,true),onLoadedMetadata:()=>ready(i),onError:()=>onSourceError(id)}
   if(!shown.has(i))return <audio key={`a-${i}-${id}`} ref={v=>{players.current[i]=v}} {...props}/>
   const scale=s.scale??1,x=s.x??.5,y=s.y??.5,layer=layers.indexOf(i)
   return <div key={`v-${i}-${id}`} ref={node=>{boxes.current[i]=node}} className={`sequence-layer ${scale<1?'pip':''}`} style={{zIndex:layer+1,opacity:clipAlpha(s,time,clipLength(s))*fade,left:`${(x-scale/2)*100}%`,top:`${(y-scale/2)*100}%`,width:`${scale*100}%`,height:`${scale*100}%`}}>
    {fit==='blur'&&project.ratio!=='original'&&scale>=1&&<canvas className="sequence-backdrop" width={48} height={27} ref={node=>{backdrops.current[i]=node}} aria-hidden="true"/>}
    <video ref={v=>{players.current[i]=v}} {...props} onSeeked={()=>drawBackdrop(i)} onLoadedData={()=>drawBackdrop(i)} playsInline data-layer={layer} style={{filter:`${lookFilter(s.look)} ${base}`.trim(),transform:`rotate(${project.rotate}deg) scaleX(${project.flip?-1:1}) ${motionTransform(s,time,clipLength(s))}`.trim(),objectFit:scale<1?'contain':objectFit,objectPosition:`${(s.focus_x??.5)*100}% ${(s.focus_y??.5)*100}%`}}/>
    {hasVignette(s.look)&&<i className="sequence-vignette" aria-hidden="true"/>}
   </div>
  })}
  {visible===undefined&&<span className="preview-gap">{project.segments.length?`${time.toFixed(2)}s`:''}</span>}
 </div>
}
