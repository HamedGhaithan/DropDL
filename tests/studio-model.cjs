// Clip Studio 3.0 smart-edit model: ripple cuts, scene splits, dissolves, captions and looks.
const assert=require('assert/strict'),path=require('path'),Module=require('module'),{createRequire}=Module
const frontend=path.resolve(__dirname,'../frontend'),load=createRequire(path.join(frontend,'package.json'))
function bundle(file){const code=load('esbuild').buildSync({entryPoints:[path.join(frontend,'src',file)],bundle:true,write:false,format:'cjs',platform:'node',jsx:'automatic',external:['react','react/jsx-runtime']}).outputFiles[0].text;const m=new Module(path.join(frontend,file+'.check.cjs'),module);m.paths=Module._nodeModulePaths(frontend);m._compile(code,path.join(frontend,file+'.check.cjs'));return m.exports}
const {keepRanges,removeRanges,splitAtTimes,crossDissolve,dipToBlack,transcriptCues,chunks,withCaptions,currentLine,previousNeighbour,clipExtrasValid}=bundle('studioModel.ts')
const {lookMatrix,LOOKS,clipAlpha,clipFadeGain,fullFrame,lookFilter}=bundle('looks.tsx')
const near=(a,b,e=1e-9)=>assert(Math.abs(a-b)<e,`${a} != ${b}`)
const base={ratio:'original',rotate:0,flip:false,brightness:0,contrast:1,saturation:1,volume:1,fadeIn:0,fadeOut:0}
const project={...base,segments:[
 {source_job_id:'A',start:0,end:10,speed:1,offset:0,track:0,fade_in:.5,fade_out:.5},
 {source_job_id:'B',start:2,end:6,speed:2,offset:10,track:0},
 {source_job_id:'C',start:0,end:4,speed:1,offset:3,track:1}],
 texts:[{start:1,end:2,text:'before cut',kind:'caption'},{start:4.5,end:5.5,text:'inside cut',kind:'caption'},{start:8,end:9,text:'after cut',kind:'caption'},{start:11,end:11.5,text:'next clip',kind:'title'}]}
const frozen=JSON.stringify(project)

// Removing 4..6 from clip A: two pieces back to back, the next clip on V1 moves up, V2 stays, captions follow.
let r=removeRanges(project,0,[[4,6]])
assert.deepEqual(r.project.segments.slice(0,2).map(s=>[s.start,s.end,s.offset]),[[0,4,0],[6,10,4]])
near(r.removed,2);assert.equal(r.project.segments[2].offset,8);assert.equal(r.project.segments[3].offset,3)
assert.equal(r.project.segments[0].fade_in,.5);assert.equal(r.project.segments[0].fade_out,undefined)
assert.equal(r.project.segments[1].fade_in,undefined);assert.equal(r.project.segments[1].fade_out,.5)
assert.deepEqual(r.project.texts.map(t=>[t.text,t.start,t.end]),[['before cut',1,2],['inside cut',4,4],['after cut',6,7],['next clip',9,9.5]].filter(([,a,b])=>b-a>=.05))
assert.equal(JSON.stringify(project),frozen)
// Kept ranges outside the clip are clipped, overlapping ranges merge, and nothing-removed is a no-op.
r=keepRanges(project,1,[[0,3],[2.5,4],[5,9]])
assert.deepEqual(r.project.segments.slice(1,3).map(s=>[s.start,s.end]),[[2,4],[5,6]]);near(r.removed,.5)
assert.equal(keepRanges(project,0,[[0,10]]),null);assert.equal(keepRanges(project,0,[]),null);assert.equal(keepRanges(project,9,[[0,1]]),null)
// Locked tracks refuse every tool.
const locked={...project,tracks:[{locked:true}]}
assert.equal(removeRanges(locked,0,[[1,2]]),null);assert.equal(splitAtTimes(locked,0,[5]),null);assert.equal(crossDissolve(locked,1,.5),null)
console.log('Ripple cuts passed: pieces, fades on the outer edges, same-track ripple, captions remapped, inputs untouched.')

// Scene splits cut at each time without moving anything; duplicates and edge times are ignored.
r=splitAtTimes(project,0,[7,2,2,0.01,9.99])
assert.deepEqual(r.project.segments.slice(0,3).map(s=>[s.start,s.end,s.offset]),[[0,2,0],[2,7,2],[7,10,7]]);assert.equal(r.cuts,2)
assert.equal(r.project.segments[3].offset,10)
assert.equal(splitAtTimes(project,0,[0,10]),null)
console.log('Scene splits passed.')

// A dissolve overlaps the previous clip, fades in, and pulls the rest of the track back.
assert.equal(previousNeighbour(project,1),0);assert.equal(previousNeighbour(project,0),-1);assert.equal(previousNeighbour(project,2),-1)
r=crossDissolve(project,1,1)
assert.equal(r.project.segments[1].offset,9);assert.equal(r.project.segments[1].fade_in,1);assert.equal(r.index,1)
assert.equal(crossDissolve(project,1,99).project.segments[1].fade_in,1)                 // capped at half the shorter clip
const reversed={...project,segments:[project.segments[1],project.segments[0]]}
r=crossDissolve(reversed,0,1)
assert.deepEqual(r.project.segments.map(s=>s.source_job_id),['A','B']);assert.equal(r.index,1)  // incoming clip draws on top
const dip=dipToBlack(project,1,1);assert.equal(dip.segments[0].fade_out,.5);assert.equal(dip.segments[1].fade_in,.5)
console.log('Transitions passed: overlap, cap, stacking order and dip to black.')

// Transcript lines become captions on the finished timeline, speed included.
const lines=[{start:1,end:3,text:'one two three four five six seven'},{start:5,end:7,text:'tail'},{start:20,end:21,text:'elsewhere'}]
let cues=transcriptCues(project,1,lines)
assert.deepEqual(cues.map(c=>[c.start,c.end,c.text]),[[10,10.5,'one two three four five six seven'],[11.5,12,'tail']])
cues=transcriptCues(project,0,lines,3)
assert.deepEqual(cues.slice(0,3).map(c=>c.text),['one two three','four five six','seven']);near(cues[0].start,1);near(cues[2].end,3)
assert(cues[0].end<=cues[1].start+1e-9)
assert.equal(chunks('a b',4,0,1).length,1)
const captioned=withCaptions(project,0,[{start:2,end:3,text:'new',kind:'caption'}])
assert.deepEqual(captioned.texts.map(t=>t.text),['new','next clip'])
assert.equal(currentLine(lines,5.5),1);assert.equal(currentLine(lines,4),-1)
console.log('Captions passed: clip mapping, speed, short phrases, replacement under the clip.')

// Looks match the backend's matrices; fades and opacity drive the preview.
const mono=lookMatrix(LOOKS.mono);for(const row of mono){near(row[0],.2126,1e-6);near(row[1],.7152,1e-6);near(row[2],.0722,1e-6)}
const warm=lookMatrix(LOOKS.warm);near(warm[0][0],1.08*(.2126*(1-1.06)+1.06),1e-9)
assert.equal(lookFilter(),'');assert(lookFilter('noir').startsWith('url(#dropdl-look-noir) contrast(1.38)'))
const clip={start:0,end:4,speed:1,offset:10,fade_in:1,fade_out:2,opacity:.8}
near(clipAlpha(clip,10.5,4),.4);near(clipAlpha(clip,11.5,4),.8);near(clipAlpha(clip,13,4),.4);near(clipFadeGain(clip,10.5,4),.5)
assert(fullFrame({start:0,end:1,speed:1}));assert(!fullFrame({start:0,end:1,speed:1,scale:.5}))
assert(clipExtrasValid({start:0,end:1,speed:1,look:'warm',scale:.3,x:1,y:0,opacity:.2}));assert(!clipExtrasValid({start:0,end:1,speed:1,look:'neon'}));assert(!clipExtrasValid({start:0,end:1,speed:1,scale:0}))
console.log('Looks and layers passed: matrices match the export, alpha and fade gain, validation.')

// ---------------------------------------------------------------- second wave: beats, words, markers, motion
const M2=bundle('studioModel.ts'),L2=bundle('looks.tsx'),T2=bundle('TextOverlay.tsx')
const grid=Array.from({length:40},(_,i)=>i*.5)
const montage={...base,segments:[{source_job_id:'A',start:0,end:1.3,speed:1,offset:0,track:0},{source_job_id:'B',start:2,end:2.9,speed:1,offset:1.3,track:0},{source_job_id:'C',start:0,end:3,speed:1,offset:0,track:1}]}
let cut=M2.cutToBeats(montage,grid,2,{A:10,B:3})
assert.deepEqual(cut.project.segments.map(s=>[s.offset,s.end]),[[0,1],[1,3],[0,3]]);assert.equal(cut.changed,2)  // end is a source time: B starts at 2
cut=M2.cutToBeats(montage,grid,'nearest',{A:10,B:10})
assert.deepEqual(cut.project.segments.slice(0,2).map(s=>[s.offset,s.end]),[[0,1.5],[1.5,3]])
cut=M2.cutToBeats(montage,grid,4,{A:10,B:3})                                    // B only has 1 s of source: it takes the beats that fit
assert.deepEqual(cut.project.segments.slice(0,2).map(s=>[s.offset,s.end]),[[0,2],[2,3]])
assert.equal(M2.cutToBeats(montage,[1],2),null);assert.equal(M2.cutToBeats({...montage,tracks:[{locked:true}]},grid,2),null)
assert.deepEqual(M2.beatsOnTimeline([0,1,2,3],{start:1,offset:10,speed:2,end:2.5},60),[10,10.5])
console.log('Beat montage passed: every-N, nearest, short sources, guards and beat placement.')
const timed=[{start:10,end:13,text:'alpha beta gamma delta',words:[10,10.5,11.5,12.5]}]
const clipW={...base,segments:[{source_job_id:'A',start:10,end:13,speed:1,offset:5,track:0}]}
let wc=M2.transcriptCues(clipW,0,timed,2)
assert.deepEqual(wc.map(c=>[c.text,c.start,c.end,c.words]),[['alpha beta',5,6.5,[5,5.5]],['gamma delta',6.5,8,[6.5,7.5]]])
wc=M2.transcriptCues({...base,segments:[{source_job_id:'A',start:11,end:13,speed:2,offset:0,track:0}]},0,timed)
assert.deepEqual(wc.map(c=>[c.text,c.start,c.end,c.words]),[['gamma delta',0,1,[0,.75]]])
const wt=T2.wordTimes({start:0,end:2,text:'aa bb',kind:'caption'});assert.deepEqual(wt.words,['aa','bb']);near(wt.times[1],1)
assert.deepEqual(T2.wordTimes({start:0,end:2,text:'aa bb',kind:'caption',words:[0,.2]}).times,[0,.2])
console.log('Word timing passed: kept through clips, chunks and speed; shared out when missing.')
let mk=M2.addMarker(base,12.3456);mk=M2.addMarker(mk,3,'Hook');mk=M2.addMarker(mk,3.02,'Dup')
assert.deepEqual(mk.markers.map(m=>[m.t,m.label]),[[3.02,'Dup'],[12.346,'Marker 1']])
assert.equal(M2.chaptersText([{t:65,label:'Main'},{t:3700,label:'Late'}]),'0:00 Start\n1:05 Main\n1:01:40 Late')
assert.equal(M2.chaptersText([{t:0,label:'Intro'}]),'0:00 Intro');assert.equal(M2.chaptersText([]),'')
assert(!M2.clipExtrasValid({start:0,end:1,speed:1,motion:'spin'}));assert(M2.clipExtrasValid({start:0,end:1,speed:1,motion:'zoom-in',motion_amount:.2,focus_x:0}))
console.log('Markers and chapters passed.')
const mv={start:0,end:4,speed:1,offset:2,motion:'zoom-in',motion_amount:.2}
assert.equal(L2.motionTransform(mv,2,4),'scale(1)');assert.equal(L2.motionTransform(mv,6,4),'scale(1.2)')
assert.equal(L2.motionTransform({...mv,motion:'pan-right'},2,4),'translateX(10.000%) scale(1.2)');assert.equal(L2.motionTransform({...mv,motion:'pan-right'},6,4),'translateX(-10.000%) scale(1.2)')
assert.equal(L2.motionTransform({...mv,motion:undefined},3,4),'')
console.log('Motion preview passed: zoom and pan match the export over the clip.')
