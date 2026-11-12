const assert=require('node:assert/strict'),path=require('node:path'),Module=require('node:module')
const frontend=path.resolve(__dirname,'../frontend'),load=Module.createRequire(path.join(frontend,'package.json'))
const result=load('esbuild').buildSync({entryPoints:[path.join(frontend,'src/ClipTimeInput.tsx')],bundle:true,write:false,format:'cjs',platform:'node',jsx:'automatic',external:['react','react/jsx-runtime']}).outputFiles[0].text
const mod=new Module(path.join(frontend,'clip-check.cjs'));mod.filename=path.join(frontend,'clip-check.cjs');mod.paths=Module._nodeModulePaths(frontend);mod._compile(result,mod.filename)
const {parseClipTime,clipClock}=mod.exports
for(const [value,seconds] of [['00:00:29.9',29.9],['00:12:54.6',774.6],['29.9',29.9],['12:54.6',774.6],['٠٠:١٢:٥٤٫٦',774.6],['01:00:00',3600],['0',0]])assert.equal(parseClipTime(value),seconds)
for(const value of ['', '00:61:00', '1:99','-2','NaN','1.2:3','1::3'])assert.equal(parseClipTime(value),null)
assert.equal(clipClock(59.96),'00:01:00.0');assert.equal(clipClock(774.6),'00:12:54.6');assert.equal(clipClock(3600),'01:00:00.0')
console.log('Clip timestamp parsing/formatting passed')
