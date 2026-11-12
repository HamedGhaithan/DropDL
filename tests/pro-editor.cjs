// 2.3 pro editor: SMPTE timecode formatting used by the monitor, ruler and timeline.
const assert=require('node:assert/strict'),path=require('node:path'),{createRequire}=require('node:module')
const frontend=path.resolve(__dirname,'../frontend'),load=createRequire(path.join(frontend,'package.json'))
const code=load('esbuild').buildSync({entryPoints:[path.join(frontend,'src/proEditor.tsx')],bundle:true,write:false,format:'cjs',platform:'node',jsx:'automatic',external:['react','react/jsx-runtime']}).outputFiles[0].text
const m={exports:{}};new Function('module','exports','require',code)(m,m.exports,load)
const {timecode}=m.exports
for(const [seconds,fps,expected] of [[0,30,'00:00:00:00'],[1,30,'00:00:01:00'],[1.5,30,'00:00:01:15'],[59.99,24,'00:01:00:00'],[3661+12/25,25,'01:01:01:12'],[4.0833,24,'00:00:04:02'],[-3,30,'00:00:00:00'],[NaN,30,'00:00:00:00'],[10,29.97,'00:00:10:00']])assert.equal(timecode(seconds,fps),expected,`${seconds}s @ ${fps}`)
console.log('Pro editor timecode passed: frames, hours, rounding, 24/25/29.97/30 fps, invalid input')
