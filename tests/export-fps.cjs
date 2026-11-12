// Export frame rate follows the source instead of always 30 (2.1).
const assert=require('node:assert/strict'),path=require('node:path'),{createRequire}=require('node:module')
const frontend=path.resolve(__dirname,'../frontend'),load=createRequire(path.join(frontend,'package.json'))
const code=load('esbuild').buildSync({entryPoints:[path.join(frontend,'src/editorProject.ts')],bundle:true,write:false,format:'cjs',platform:'node'}).outputFiles[0].text
const m={exports:{}};new Function('module','exports','require',code)(m,m.exports,load)
const {exportFps}=m.exports
for(const [source,expected] of [[24,24],[23.976,24],[25,25],[29.97,30],[30,30],[48,50],[59.94,60],[60,60],[undefined,30],[NaN,30],[120,60]])assert.equal(exportFps(source),expected,`source ${source}`)
console.log('Export frame-rate defaults passed: 23.976→24, 29.97→30, 59.94→60, unknown→30')
