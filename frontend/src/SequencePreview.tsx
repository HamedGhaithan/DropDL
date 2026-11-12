import {useEffect,useRef} from 'react'
import {EditProject,positioned,clipLength,outputDuration,trackState} from './editorProject'
import {API_BASE,downloadUrl} from './api'
import {AUDIO_LEVEL_EVENT} from './proEditor'
/** Paused startup uses a still image; one video decoder supplies the visible layer. */
export default function SequencePreview({project,sourceId,time,playing,onTime,onStop,previews,sources,enabled,onSourceError}:{project:EditProject;sourceId:string;time:number;playing:boolean;onTime:(n:number)=>void;onStop:()=>void;previews:Record<string,string>;sources:Record<string,{video?:boolean}>;enabled:boolean;onSourceError:(id:string)=>void}){
 const mixer=useRef<{context:AudioContext;limiter:DynamicsCompressorNode;meters?:AnalyserNode[];samples?:Float32Array<ArrayBuffer>;nodes:Map<HTMLMediaElement,{source:MediaElementAudioSourceNode;gain:GainNode}>}|null>(null)
 const players=useRef<Record<number,HTMLMediaElement|null>>({}),clock=useRef(time),callback=useRef({onTime,onStop});callback.current={onTime,onStop}
 const timelineClips=positioned(project).segments,total=outputDuration(project),bed=project.soundtrack
 const clips=[...timelineClips,...(bed?[{start:bed.start,end:bed.start+Math.max(0,total-bed.offset),speed:1,offset:bed.offset,track:-1,source_job_id:bed.source_job_id,gain:bed.muted?0:bed.gain}]:[])]
 const active=clips.map((s,i)=>({s,i})).filter(({s})=>time>=s.offset!&&time<s.offset!+clipLength(s))
 const visible=[...active].filter(({s})=>(s.track??0)>=0&&!trackState(project,s.track||0).hidden&&sources[s.source_job_id||sourceId]?.video!==false).sort((a,b)=>(b.s.track||0)-(a.s.track||0)||b.i-a.i)[0]?.i
 const visibleSource=visible===undefined?null:clips[visible].source_job_id||sourceId
 useEffect(()=>()=>{void mixer.current?.context.close()},[])
 useEffect(()=>{clock.current=time},[time])
 useEffect(()=>{
  let frame=0,previous=performance.now(),published=0
  const tick=(now:number)=>{
   if(playing)clock.current=Math.min(total,clock.current+(now-previous)/1000);previous=now
   const t=clock.current,fade=Math.max(0,Math.min(1,project.fadeIn?t/Math.min(project.fadeIn,total/2):1,project.fadeOut?(total-t)/Math.min(project.fadeOut,total/2):1))
   if(playing&&!mixer.current){try{const context=new AudioContext(),limiter=context.createDynamicsCompressor();limiter.connect(context.destination);let meters:AnalyserNode[]|undefined;try{const splitter=context.createChannelSplitter(2);limiter.connect(splitter);meters=[0,1].map(channel=>{const analyser=context.createAnalyser();analyser.fftSize=1024;splitter.connect(analyser,channel);return analyser})}catch{meters=undefined}mixer.current={context,limiter,meters,samples:new Float32Array(1024),nodes:new Map()};void context.resume()}catch{}}
   const mix=mixer.current;if(mix){const live=new Set(Object.values(players.current));for(const [node,wiring] of mix.nodes)if(!live.has(node)){wiring.source.disconnect();wiring.gain.disconnect();mix.nodes.delete(node)}}
   Object.entries(players.current).forEach(([key,v])=>{const s=clips[Number(key)];if(!v||!s)return
    const desired=s.start+Math.max(0,t-s.offset!)*s.speed,inside=t>=s.offset!&&t<s.offset!+clipLength(s)&&(!Number.isFinite(v.duration)||desired<v.duration),gain=(s.track??0)>=0&&trackState(project,s.track||0).muted?0:Math.max(0,(s.gain??1)*project.volume*fade)
    if(v.playbackRate!==s.speed)v.playbackRate=s.speed
    if(mix){let wiring=mix.nodes.get(v);if(!wiring){try{const source=mix.context.createMediaElementSource(v),node=mix.context.createGain();source.connect(node);node.connect(mix.limiter);wiring={source,gain:node};mix.nodes.set(v,wiring)}catch{}}if(wiring){wiring.gain.gain.value=gain;v.volume=1}else v.volume=Math.min(1,gain)}else v.volume=Math.min(1,gain)
    if(inside){if(v.readyState>=1&&!v.seeking&&Math.abs(v.currentTime-desired)>(playing?.2:.02))v.currentTime=desired;if(playing&&v.paused)void v.play().catch(()=>{});if(!playing&&!v.paused)v.pause()}else if(!v.paused)v.pause()
   })
   if(playing){if(now-published>=40){callback.current.onTime(t);published=now;const levels=mix?.meters&&mix.samples?mix.meters.map(analyser=>{analyser.getFloatTimeDomainData(mix.samples!);let peak=0;for(const value of mix.samples!)peak=Math.max(peak,Math.abs(value));return peak}):null;if(levels)window.dispatchEvent(new CustomEvent(AUDIO_LEVEL_EVENT,{detail:{left:levels[0],right:levels[1]}}))}if(t>=total){callback.current.onTime(total);callback.current.onStop();return}frame=requestAnimationFrame(tick)}
  }
  tick(performance.now())
  return()=>{cancelAnimationFrame(frame);Object.values(players.current).forEach(v=>v?.pause())}
 },[playing,project,total,enabled,time===0,visible,previews])
 // Seek once after metadata arrives when paused. No continuous idle animation loop.
 function ready(i:number){const v=players.current[i],s=clips[i];if(v&&s)v.currentTime=Math.max(s.start,Math.min(s.end,s.start+(time-s.offset!)*s.speed))}
 useEffect(()=>{if(!playing)Object.keys(players.current).forEach(i=>ready(Number(i)))},[time,playing,enabled,project])
 const fade=Math.max(0,Math.min(1,project.fadeIn?time/Math.min(project.fadeIn,total/2):1,project.fadeOut?(total-time)/Math.min(project.fadeOut,total/2):1))
 return <div className="sequence-preview" aria-label="Timeline composition">
  {!enabled&&visibleSource&&<img className="sequence-still" src={`${API_BASE}/api/jobs/${visibleSource}/frame/0`} alt="" onError={e=>{e.currentTarget.style.visibility='hidden'}}/>}
  {enabled&&active.filter(({i})=>playing||i===visible).map(({s,i})=>{const props={crossOrigin:'anonymous' as const,preload:'metadata','data-track':s.track,src:downloadUrl(previews[s.source_job_id||sourceId]||s.source_job_id||sourceId,true),onLoadedMetadata:()=>ready(i),onError:()=>onSourceError(s.source_job_id||sourceId)}
   return i===visible?<video key={`v-${i}-${s.source_job_id||sourceId}`} ref={v=>{players.current[i]=v}} {...props} playsInline style={{opacity:fade,filter:`brightness(${1+project.brightness}) contrast(${project.contrast}) saturate(${project.saturation})`,transform:`rotate(${project.rotate}deg) scaleX(${project.flip?-1:1})`,objectFit:project.ratio==='original'?'contain':'cover'}}/>:<audio key={`a-${i}-${s.source_job_id||sourceId}`} ref={v=>{players.current[i]=v}} {...props}/>
  })}
  {visible===undefined&&<span className="preview-gap">{time.toFixed(2)}s</span>}
 </div>
}
