import {useEffect,useRef,useState,RefObject} from 'react'
import {EditProject,outputDuration} from './editorProject'
import {downloadUrl} from './api'
export default function SoundtrackPreview({project,time,playing,video,lang}:{project:EditProject;time:number;playing:boolean;video:RefObject<HTMLVideoElement|null>;lang:string}){
 const audio=useRef<HTMLAudioElement>(null),[error,setError]=useState(''),mix=useRef<{context:AudioContext;video:GainNode;bed:GainNode}|null>(null)
 useEffect(()=>{if(!playing||mix.current||!video.current||!audio.current)return;try{const context=new AudioContext(),main=context.createGain(),bed=context.createGain(),limiter=context.createDynamicsCompressor();context.createMediaElementSource(video.current).connect(main);context.createMediaElementSource(audio.current).connect(bed);main.connect(limiter);bed.connect(limiter);limiter.connect(context.destination);mix.current={context,video:main,bed};void context.resume()}catch(e){setError(String(e))}},[playing])
 useEffect(()=>{const node=audio.current,main=video.current;if(!node||!main)return;const duration=outputDuration(project),fadeIn=Math.min(project.fadeIn,duration/2),fadeOut=Math.min(project.fadeOut,duration/2),fade=Math.min(1,fadeIn?time/fadeIn:1,fadeOut?(duration-time)/fadeOut:1),master=Math.max(0,project.volume*fade),track=project.soundtrack,at=track?time-track.offset+track.start:0,enabled=!!track&&time>=track.offset&&at<node.duration;
 const active=project.segments.find((_,i)=>time<project.segments.slice(0,i+1).reduce((n,s)=>n+(s.end-s.start)/s.speed,0))||project.segments[project.segments.length-1];
 if(mix.current){main.volume=1;node.volume=1;mix.current.video.gain.value=master*(active.gain??1);mix.current.bed.gain.value=master*(track?.muted?0:track?.gain??0);if(playing)void mix.current.context.resume()}else{main.volume=Math.min(1,master*(active.gain??1));node.volume=Math.min(1,master*(track?.muted?0:track?.gain??0))}
 if(track&&Number.isFinite(at)&&at>=0&&node.readyState>=1&&(Math.abs(node.currentTime-at)>.2||!playing))node.currentTime=Math.min(at,node.duration||at);node.playbackRate=1;
 if(playing&&enabled){if(node.paused)void node.play().catch(e=>{if(e.name!=='AbortError')setError(String(e))})}else node.pause()
 },[project,time,playing])
 useEffect(()=>()=>{audio.current?.pause();void mix.current?.context.close()},[])
 return <><audio ref={audio} crossOrigin="anonymous" preload="metadata" src={project.soundtrack?downloadUrl(project.soundtrack.source_job_id,true):undefined} onError={()=>{if(project.soundtrack)setError(lang==='ar'?'تعذر تشغيل المسار الصوتي.':'Soundtrack preview could not play.')}}/>{error&&<button className="audio-preview-error" onClick={()=>setError('')}>{error} ×</button>}</>
}
