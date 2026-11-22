import {LookName,Segment} from './editorProject'
/** Colour looks. The numbers match LOOKS in backend/app/editor.py exactly: the preview uses an SVG colour matrix
 * plus CSS contrast and brightness, the export uses FFmpeg's colorchannelmixer and eq with the same values. */
type Look={sat?:number;gains?:[number,number,number];sepia?:number;contrast?:number;brightness?:number;vignette?:boolean}
export const LOOKS:Record<LookName,Look>={
 vivid:{sat:1.35,contrast:1.06},
 warm:{gains:[1.08,1,.86],sat:1.06,brightness:.015},
 cool:{gains:[.9,.99,1.1],sat:.96},
 cinematic:{gains:[1.04,1,.95],sat:.86,contrast:1.14,brightness:-.02,vignette:true},
 punch:{sat:1.2,contrast:1.2,brightness:-.01},
 mono:{sat:0,contrast:1.05},
 noir:{sat:0,contrast:1.38,brightness:-.04,vignette:true},
 vintage:{sepia:.6,sat:.92,contrast:.9,brightness:.03,vignette:true},
 fade:{sat:.82,contrast:.8,brightness:.05},
 dream:{gains:[1.04,.98,1.06],sat:1.1,contrast:.9,brightness:.04},
}
export const LOOK_NAMES:Record<LookName,[string,string]>={vivid:['Vivid','زاهٍ'],warm:['Warm','دافئ'],cool:['Cool','بارد'],cinematic:['Cinematic','سينمائي'],punch:['Punch','قوي'],mono:['Mono','أبيض وأسود'],noir:['Noir','نوار'],vintage:['Vintage','كلاسيكي'],fade:['Faded','باهت'],dream:['Dream','حالم']}
const LUMA=[.2126,.7152,.0722],SEPIA=[[.393,.769,.189],[.349,.686,.168],[.272,.534,.131]]
export function lookMatrix(look:Look){
 const s=look.sat??1,k=look.sepia??0,g=look.gains??[1,1,1]
 const sat=[0,1,2].map(r=>[0,1,2].map(c=>LUMA[c]*(1-s)+(r===c?s:0)))
 const sepia=[0,1,2].map(r=>[0,1,2].map(c=>(1-k)*(r===c?1:0)+k*SEPIA[r][c]))
 const mixed=[0,1,2].map(r=>[0,1,2].map(c=>[0,1,2].reduce((n,m)=>n+sepia[r][m]*sat[m][c],0)))
 return mixed.map((row,r)=>row.map(v=>v*g[r]))
}
/** Hidden SVG filters the preview's CSS refers to (rendered once per window). */
export function LookFilters(){
 return <svg width="0" height="0" style={{position:'absolute',pointerEvents:'none'}} aria-hidden="true" focusable="false"><defs>{(Object.keys(LOOKS) as LookName[]).map(name=>{const m=lookMatrix(LOOKS[name]);return <filter key={name} id={`dropdl-look-${name}`} colorInterpolationFilters="sRGB"><feColorMatrix type="matrix" values={`${m[0].map(v=>v.toFixed(4)).join(' ')} 0 0 ${m[1].map(v=>v.toFixed(4)).join(' ')} 0 0 ${m[2].map(v=>v.toFixed(4)).join(' ')} 0 0 0 0 0 1 0`}/></filter>})}</defs></svg>
}
/** CSS filter for a clip's look (empty when it has none). */
export function lookFilter(name?:LookName){
 const look=name&&LOOKS[name];if(!look)return ''
 return `url(#dropdl-look-${name})${look.contrast&&look.contrast!==1?` contrast(${look.contrast})`:''}${look.brightness?` brightness(${1+look.brightness})`:''}`
}
export const hasVignette=(name?:LookName)=>!!(name&&LOOKS[name]?.vignette)
/** How visible a clip is at `t` sequence seconds: its opacity times its fades. */
export function clipAlpha(s:Segment,t:number,length:number){
 const local=t-(s.offset||0),fadeIn=Math.min(s.fade_in||0,length/2),fadeOut=Math.min(s.fade_out||0,length/2)
 let alpha=s.opacity??1
 if(fadeIn>0)alpha*=Math.max(0,Math.min(1,local/fadeIn))
 if(fadeOut>0)alpha*=Math.max(0,Math.min(1,(length-local)/fadeOut))
 return alpha
}
/** Audio follows the clip's fades (not its opacity). */
export function clipFadeGain(s:Segment,t:number,length:number){
 const local=t-(s.offset||0),fadeIn=Math.min(s.fade_in||0,length/2),fadeOut=Math.min(s.fade_out||0,length/2)
 let gain=1
 if(fadeIn>0)gain*=Math.max(0,Math.min(1,local/fadeIn))
 if(fadeOut>0)gain*=Math.max(0,Math.min(1,(length-local)/fadeOut))
 return gain
}
export const fullFrame=(s:Segment)=>(s.scale??1)>=1&&(s.x??.5)===.5&&(s.y??.5)===.5
/** Ken Burns movement at `t` sequence seconds, as a CSS transform for the clip's picture (matches the export). */
export function motionTransform(s:Segment,t:number,length:number){
 if(!s.motion||length<=0)return ''
 const amount=s.motion_amount??.12,p=Math.max(0,Math.min(1,(t-(s.offset||0))/length))
 if(s.motion==='zoom-in')return `scale(${1+amount*p})`
 if(s.motion==='zoom-out')return `scale(${1+amount*(1-p)})`
 const edge=amount/2*100,travel=s.motion==='pan-right'?edge-2*edge*p:-edge+2*edge*p
 return `translateX(${travel.toFixed(3)}%) scale(${1+amount})`
}
export const MOTION_NAMES:Record<string,[string,string]>={'zoom-in':['Zoom in','تكبير'],'zoom-out':['Zoom out','تصغير'],'pan-left':['Pan left','تحريك لليسار'],'pan-right':['Pan right','تحريك لليمين']}
