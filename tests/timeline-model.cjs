const assert=require('assert/strict'),path=require('path'),Module=require('module'),{createRequire}=Module;
const frontend=path.resolve(__dirname,'../frontend'),load=createRequire(path.join(frontend,'package.json'));
const code=load('esbuild').buildSync({entryPoints:[path.join(frontend,'src/timelineModel.ts')],bundle:true,write:false,format:'cjs',platform:'node'}).outputFiles[0].text;
const mod=new Module(path.join(frontend,'timeline-model-check.cjs'),module);mod._compile(code,path.join(frontend,'timeline-model-check.cjs'));
const {trimClip,moveClip,length}=mod.exports;
const p={segments:[{source_job_id:'A',start:2,end:6,speed:2},{source_job_id:'B',start:1,end:5,speed:.5},{source_job_id:'C',start:0,end:3,speed:1}],fps:30};
const duration=p=>p.segments.reduce((n,s)=>n+length(s),0);
// Moving forward/backward and either no-op boundary retain the same clip ranges.
let result=moveClip(p,0,3);assert.deepEqual(result.project.segments.map(s=>s.source_job_id),['B','C','A']);assert.equal(result.index,2);assert.deepEqual(result.project.segments[2],p.segments[0]);assert.equal(moveClip(p,0,1).project,p);assert.equal(moveClip(p,1,1).project,p);
result=moveClip(p,2,0);assert.deepEqual(result.project.segments.map(s=>s.source_job_id),['C','A','B']);
// A timeline-second trim honors source speed and bounds; extremes remain valid.
let trimmed=trimClip(p,0,'end',.5,12);assert.equal(trimmed.segments[0].end,7);
trimmed=trimClip(p,0,'start',999,12);assert.equal(trimmed.segments[0].start,5.95);
trimmed=trimClip(p,0,'end',-999,12);assert.equal(trimmed.segments[0].end,2.05);
trimmed=trimClip(p,0,'end',999,12);assert.equal(trimmed.segments[0].end,12);
// Rolling trim conserves total output length, including different clip speeds.
for(const delta of [-999,-.25,.5,999]){trimmed=trimClip(p,0,'end',delta,12,'roll');assert(Math.abs(duration(trimmed)-duration(p))<1e-9);assert(trimmed.segments[0].end-trimmed.segments[0].start>=.049999);assert(trimmed.segments[1].end-trimmed.segments[1].start>=.049999);assert(trimmed.segments[1].start>=0)}
// Slip changes content only and stays inside the original duration.
for(const delta of [-999,.4,999]){trimmed=trimClip(p,0,'start',delta,12,'slip');assert.equal(length(trimmed.segments[0]),length(p.segments[0]));assert(trimmed.segments[0].start>=0&&trimmed.segments[0].end<=12)}
assert.deepEqual(p.segments.map(s=>[s.start,s.end]),[[2,6],[1,5],[0,3]]);
console.log('Timeline model passed: reorder boundaries, speed-aware trim, extreme bounds, rolling duration and slip invariants; originals unchanged.');
const mediaCode=load('esbuild').buildSync({entryPoints:[path.join(frontend,'src/editorMedia.ts')],bundle:true,write:false,format:'cjs',platform:'node'}).outputFiles[0].text;
const mediaModule=new Module(path.join(frontend,'editor-media-check.cjs'),module);mediaModule._compile(mediaCode,path.join(frontend,'editor-media-check.cjs'));
const {insertSegments,isEditedMedia}=mediaModule.exports;
const original={segments:[{source_job_id:'A',start:2,end:10,speed:2}]};
const inserted=insertSegments(original,[{source_job_id:'B',start:0,end:3,speed:1},{source_job_id:'C',start:1,end:2,speed:1}],2);
assert.equal(inserted.index,1);assert.deepEqual(inserted.project.segments.map(s=>s.source_job_id),['A','B','C']);assert.equal(inserted.project.segments[0].end,10);assert.equal(inserted.project.segments[1].offset,2);assert.equal(inserted.project.segments[2].offset,5);
assert.deepEqual(original.segments,[{source_job_id:'A',start:2,end:10,speed:2}]);assert.equal(insertSegments(original,[{start:0,end:1,speed:1}],99,2).project.segments[1].offset,99);assert.equal(insertSegments(original,[{start:0,end:1,speed:1}],99,2).project.segments[1].track,2);
const positionedProject={...p,segments:p.segments.map((s,i)=>({...s,offset:[0,3,12][i],track:i}))};
const gapTrim=trimClip(positionedProject,0,'end',-.5,12);assert.equal(gapTrim.segments[1].offset,3);assert.equal(gapTrim.segments[2].offset,12);
const startTrim=trimClip(positionedProject,1,'start',1,12);assert.equal(startTrim.segments[1].offset,4);assert.equal(startTrim.segments[2].offset,12);
assert(isEditedMedia({metadata:{purpose:'clip'}}));assert(!isEditedMedia({metadata:{purpose:'download'}}));assert(isEditedMedia({metadata:{purpose:'download',clip_start:0,clip_end:4}}));
console.log('Media drop model passed: absolute placement with gaps and overlap, multiple-file order, boundaries, immutable originals and edited classification.');
// 0.14: only touching neighbours on the same track roll; outer positions stay fixed.
const {rollNeighbor,placeClip,snapPosition}=mod.exports;
const tracks={...p,segments:[{...p.segments[0],offset:0,track:0},{...p.segments[2],offset:2,track:1},{...p.segments[1],offset:2,track:0}]};
assert.equal(rollNeighbor(tracks,0,'end'),2);
const rolled=trimClip(tracks,0,'end',.5,12,'roll');assert.equal(rolled.segments[2].offset,2.5);assert.equal(rolled.segments[2].offset+length(rolled.segments[2]),10);assert.deepEqual(rolled.segments[1],tracks.segments[1]);
const back=trimClip(rolled,2,'start',-.25,12,'roll',false,{A:12});assert.equal(back.segments[2].offset,2.25);assert.equal(back.segments[0].offset,0);assert.equal(back.segments[2].offset+length(back.segments[2]),10);
const gap={...tracks,segments:tracks.segments.map((s,i)=>i===2?{...s,offset:3}:s)};assert.equal(trimClip(gap,0,'end',.5,12,'roll'),gap);
const ambiguous={...tracks,segments:[...tracks.segments,{...tracks.segments[2]}]};assert.equal(rollNeighbor(ambiguous,0,'end'),-1);
const locked={...tracks,tracks:[{locked:true},{}]};assert.equal(trimClip(locked,0,'end',.5,12),locked);assert.equal(placeClip(locked,0,8,1),locked);assert.equal(placeClip(locked,1,8,0),locked);assert.equal(moveClip(locked,0,3).project,locked);assert.throws(()=>insertSegments(locked,[{start:0,end:1,speed:1}],2,0),/locked/);
const free=placeClip(tracks,1,7.3,2);assert.equal(free.segments[1].offset,7.3);assert.equal(free.segments[1].track,2);assert.deepEqual(free.segments[0],tracks.segments[0]);
assert.equal(snapPosition(tracks,2.06,1,1,9,100,false).value,2.06);assert.equal(snapPosition(tracks,2.06,1,1,9,100,true).value,2);assert.equal(snapPosition(tracks,1.04,1,1,9,100,true).value,1);assert.equal(snapPosition(tracks,8.94,1,1,9,100,true).value,9);assert.equal(snapPosition(tracks,7.23,1,1,9,100,false,true).value,Math.round(7.23*30)/30);
console.log('0.14 passed: same-track Roll adjacency and both edges, fixed outer bounds, gaps, ambiguous overlaps, locked source/target and optional nearest-edge snapping.');
