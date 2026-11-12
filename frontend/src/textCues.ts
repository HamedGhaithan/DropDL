import {TextCue} from './editorProject'
export function parseSrt(raw:string):TextCue[]{
 const cues:TextCue[]=[]
 for(const block of raw.replace(/^\uFEFF/,'').replace(/\r/g,'').trim().split(/\n\s*\n/)){
  const lines=block.split('\n'),index=lines.findIndex(s=>s.includes('-->'));if(index<0)continue
  const match=lines[index].match(/^(\d{1,3}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{1,3}):(\d{2}):(\d{2})[,.](\d{3})/);if(!match)throw Error('Invalid SRT timecode.')
  const seconds=(offset:number)=>Number(match[offset])*3600+Number(match[offset+1])*60+Number(match[offset+2])+Number(match[offset+3])/1000
  const start=seconds(1),end=seconds(5),text=lines.slice(index+1).join('\n').replace(/<[^>]*>/g,'');if(end<=start||text.length>2000)throw Error('Invalid SRT cue.');cues.push({start,end,text,kind:'caption'})
 }
 if(!cues.length)throw Error('No SRT captions found.');return cues
}
const stamp=(n:number)=>{const milliseconds=Math.round(n*1000);return `${String(Math.floor(milliseconds/3600000)).padStart(2,'0')}:${String(Math.floor(milliseconds/60000)%60).padStart(2,'0')}:${String(Math.floor(milliseconds/1000)%60).padStart(2,'0')},${String(milliseconds%1000).padStart(3,'0')}`}
export const toSrt=(texts:TextCue[])=>texts.filter(t=>t.kind==='caption').sort((a,b)=>a.start-b.start).map((t,i)=>`${i+1}\n${stamp(t.start)} --> ${stamp(t.end)}\n${t.text}\n`).join('\n')
