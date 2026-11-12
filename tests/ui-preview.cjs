// Behavioral UI checks without a native Windows runtime or live downloads.
const assert = require('node:assert/strict')
const path = require('node:path')
const Module = require('node:module')
const {createRequire} = Module
const frontend = path.resolve(__dirname, '../frontend')
const load = createRequire(path.join(frontend, 'package.json'))
const {JSDOM} = load('jsdom')
const dom = new JSDOM('<div id="root"></div>', {url:'http://localhost/', pretendToBeVisual:true})
for (const key of ['window','document','localStorage','HTMLElement','Event','MouseEvent','requestAnimationFrame','cancelAnimationFrame']) {
  global[key] = typeof dom.window[key] === 'function' && key.includes('AnimationFrame') ? dom.window[key].bind(dom.window) : dom.window[key]
}
Object.defineProperty(global,'navigator',{value:dom.window.navigator,configurable:true})
// Browser globals used by the user's 0.8 productivity hooks.
dom.window.matchMedia=global.matchMedia=()=>({matches:true,addEventListener(){},removeEventListener(){}})
for(const key of ['addEventListener','removeEventListener'])global[key]=dom.window[key].bind(dom.window)
localStorage.setItem('dropdl-sound','0');localStorage.setItem('dropdl-notify','0')
global.innerWidth=1024;global.innerHeight=768
dom.window.HTMLCanvasElement.prototype.getContext=()=>({clearRect(){},fillRect(){},save(){},restore(){},translate(){},rotate(){}})
global.IS_REACT_ACT_ENVIRONMENT = true
HTMLElement.prototype.scrollIntoView = function() {}
dom.window.HTMLMediaElement.prototype.pause=function(){}
const React = load('react')
const {act} = React
const {createRoot} = load('react-dom/client')
const bundled = load('esbuild').buildSync({
  entryPoints:[path.join(frontend,'src/App.tsx')],bundle:true,write:false,format:'cjs',platform:'node',
  jsx:'automatic',external:['react','react/jsx-runtime'],define:{'import.meta.env':'{}','__DROPDL_VERSION__':JSON.stringify(require(path.join(frontend,'package.json')).version)},logLevel:'silent'
}).outputFiles[0].text
const compiled = new Module(path.join(frontend,'ui-check.cjs'), module)
compiled.filename = path.join(frontend,'ui-check.cjs')
compiled.paths = Module._nodeModulePaths(frontend)
compiled._compile(bundled, compiled.filename)
const App = compiled.exports.default
const base = {url:'https://example.com/video',kind:'video',container:'mp4',quality:'1080p',percent:40,eta:125,speed:1024,preview_ready:false}
let conversionPayload=null,libraryFiles=[{id:'local-media',title:'Local editing source',filename:'source.mp4',path:'C:/media/source.mp4',kind:'video',site:'Local',owned:false,exists:true,size:2048,created:1700000000,metadata:{}}]
let settingsPayload=null,preferencesSnapshot={download_directory:'C:/Downloads',native_folder_picker:false,group_by_site:true,speed_limit_kbps:0,folder_rule:'none',name_rule:'original'}
let selectionRequests=[], selectedActions=[], jobs, calls, playlistFailure=false, playlistRequests=0, videoInspections=0
global.fetch = async (url,options) => {
  let result
  if (url.endsWith('/api/engine-update')) result={current:'2026.08.19',checking:false,pending:null,error:null}
  else if (url.endsWith('/api/library')) result={files:libraryFiles}
  else if (url.endsWith('/api/collections')) result={collections:[]}
  else if (url.endsWith('/api/storage')) result={free:10000000000,total:20000000000,temporary_bytes:0,directory:'C:/Downloads',low_space:false}
  else if (url.endsWith('/api/cookies')) result={configured:false}
  else if (url.endsWith('/api/subscriptions')) result={subscriptions:[]}
  else if (url.endsWith('/api/browser/inbox')) result={links:[]}
  else if (url.endsWith('/api/convert/presets')) result={presets:{device:{label:'Universal MP4',ar:'MP4 متوافق',container:'mp4',kind:'video'},wav:{label:'WAV for editing',ar:'WAV للمونتاج',container:'wav',kind:'audio'}},custom:[]}
  else if (url.endsWith('/api/convert')) {conversionPayload=JSON.parse(options.body);result={batch_id:'conversion-batch',jobs:[]}}
  else if (url.endsWith('/api/queue/remove')) {const ids=JSON.parse(options.body).ids;selectionRequests.push(ids);jobs=jobs.filter(j=>!ids.includes(j.id));result={removed:ids,missing:[],stopped:0}}
  else if (url.endsWith('/api/library/selection/remove')) {const payload=JSON.parse(options.body);selectionRequests.push(payload);libraryFiles=libraryFiles.filter(f=>!payload.ids.includes(f.id));result={removed:payload.ids,errors:[]}}
  else if (url.endsWith('/api/queue/control')) result={paused:JSON.parse(options.body).action==='pause'}
  else if (url.endsWith('/api/support/status')) result={version:'2.3.0',checks:[{id:'backend',ok:true,detail:'2.3.0'}],findings:['port_in_use'],failures:[],repair_available:false}
  else if (url.endsWith('/api/diagnostics')) result={ok:true}
  else if (url.endsWith('/api/health')) result={ok:true,version:"2.3.0",ffmpeg:true,ffprobe:true,max_concurrent_downloads:2}
  else if (url.endsWith('/api/settings')) {if(options?.body){settingsPayload=JSON.parse(options.body);preferencesSnapshot={...preferencesSnapshot,...settingsPayload}}result=preferencesSnapshot}
  else if (url.endsWith('/api/playlist')) {
    playlistRequests++
    if(playlistFailure)return {ok:false,status:422,json:async()=>({detail:'Playlist unavailable'})}
    result={title:'Large playlist',total:100000,has_more:true,next_start:101,entries:Array.from({length:100},(_,i)=>({index:i+1,title:`Playlist video ${i+1}`,url:i===1?null:`https://youtube.com/watch?v=video${i}`,duration:30}))}
  }
  else if (url.endsWith('/api/info')) {videoInspections++;throw new Error('Playlist was sent to Single URL inspector')}
  else if (url.endsWith('/api/batch')) {
    const payload=JSON.parse(options.body)
    assert.equal(payload.urls.length,99)
    const queued=[]
    for(const [i,url] of payload.urls.entries())for(const kind of payload.mode==='both'?['video','audio']:[payload.mode])queued.push({...base,id:`queued-${i}-${kind}`,url,kind,title:`Queued ${i} ${kind}`,purpose:'download',status:'queued',batch_id:'playlist-batch'})
    jobs=[...queued,...jobs];result={batch_id:'playlist-batch',jobs:queued}
  }
  else if (url.endsWith('/api/jobs')) result={jobs:structuredClone(jobs)}
  else if (url.endsWith('/retry')||url.endsWith('/pause')) {const id=url.split('/').at(-2);selectedActions.push([id,url.endsWith('/retry')?'retry':'pause']);const job=jobs.find(j=>j.id===id);job.status=url.endsWith('/retry')?'queued':'paused';result={...job}}
  else if (url.endsWith('/cancel')) {
    const id=url.split('/').at(-2);calls.push(id)
    const job=jobs.find(j=>j.id===id);job.status='cancelled';result={...job}
  } else throw new Error(`Unexpected API call: ${url}`)
  return {ok:true,json:async()=>result}
}
const settle = () => new Promise(resolve=>setTimeout(resolve,20))
async function click(element) {assert(element,'Missing control');await act(async()=>{element.click();await settle()})}
async function run(lang) {
  localStorage.clear();localStorage.setItem('dropdl-language',lang);localStorage.setItem('dropdl-tour-v1','done')
  calls=[];jobs=[
    {...base,id:'download',title:'Real download',purpose:'download',status:'downloading'},
    {...base,id:'preview',title:'Preview source',purpose:'preview',status:'downloading'},
    {...base,id:'old-preview',title:'Old preview',purpose:'preview',status:'completed',preview_ready:true},
    {...base,id:'failed-preview',title:'Failed preview',purpose:'preview',status:'failed'}
  ]
  const root=createRoot(document.getElementById('root'))
  await act(async()=>{root.render(React.createElement(App));await settle()})
  assert.equal(document.documentElement.dir,lang==='ar'?'rtl':'ltr')
  assert.equal(document.querySelectorAll('.task-card').length,1)
  assert(!document.querySelector('.download-workspace').textContent.includes('Preview source'))
  assert.equal(document.querySelector('.overview strong').firstChild.textContent,'1')
  assert.equal(document.querySelector('.preview-toast-source').textContent,'Preview source')
  assert.equal(document.querySelector('.preview-toast .numeric').textContent,'40% · 00:02:05')
  assert.equal(document.querySelector('.row-actions .cancel-button').textContent,lang==='ar'?'إلغاء':'Cancel')
  // 2.2 command center: the smart bar searches tasks or detects links; cards open the inspector.
  const smartInput=document.getElementById('queue-search')
  const typeSmart=async value=>act(async()=>{Object.getOwnPropertyDescriptor(Object.getPrototypeOf(smartInput),'value').set.call(smartInput,value);smartInput.dispatchEvent(new Event('input',{bubbles:true}));await settle()})
  await typeSmart('zzz-no-match')
  assert.equal(document.querySelectorAll('.task-card').length,0)
  await typeSmart('https://example.com/a https://example.com/b')
  assert.equal(document.querySelectorAll('.task-card').length,1,'A pasted link must not filter the queue')
  assert(document.querySelector('.smart-bar .primary').textContent.includes('2'),'Several links offer a batch add')
  await typeSmart('')
  assert.equal(document.querySelector('.cc-inspector .inspector-detail'),null)
  await click(document.querySelector('.task-card .file-title'))
  assert(document.querySelector('.cc-inspector .inspector-detail h3').textContent.includes('Real download'))
  await click(document.querySelector('.cc-inspector .inspector-heading .icon-button'))
  assert(document.querySelector('.cc-inspector .overview'))
  // Open modal: popup remains within the dialog and its cancel control remains reachable.
  await click(document.getElementById('tour-add'))
  assert(document.querySelector('[role=dialog] .preview-notifications'))
  await click(document.querySelector('.preview-toast .cancel-button'))
  assert.deepEqual(calls,['preview'])
  assert.equal(document.querySelector('.preview-notifications'),null)
  assert.equal(document.querySelector('[role=alert]'),null)
  assert.equal(document.querySelectorAll('.task-card').length,1)
  await click(document.querySelector('.drawer-header .icon-button'))
  await click(document.querySelector('.row-actions .cancel-button'))
  assert.equal(document.querySelectorAll('.task-card').length,1)
  assert.equal(document.querySelector('.status-badge').textContent,lang==='ar'?'ملغاة':'Cancelled')
  // Unknown-length downloads animate, then completion opens the actual media via native bridge.
  jobs.push({...base,id:'unknown-size',title:'Unknown total',purpose:'download',status:'downloading',percent:0,total_bytes:null,downloaded_bytes:2048})
  await act(async()=>{await new Promise(resolve=>setTimeout(resolve,1300))})
  const unknownRow=[...document.querySelectorAll('.task-card')].find(r=>r.textContent.includes('Unknown total'))
  assert(unknownRow.querySelector('.progress').classList.contains('indeterminate'))
  const opened=[]
  dom.window.pywebview={api:{open_downloaded:async id=>{opened.push(id);return true}}}
  jobs.find(j=>j.id==='unknown-size').status='completed'
  await act(async()=>{await new Promise(resolve=>setTimeout(resolve,1300))})
  const notification=document.querySelector('.completion-toast')
  assert(notification)
  assert.equal(notification.querySelector('button.primary').textContent,lang==='ar'?'فتح الملف المُنزّل':'Open downloaded')
  await click(notification.querySelector('button.primary'))
  assert.deepEqual(opened,['unknown-size'],'Completion popup opens the Windows player')
  assert.equal(document.querySelector('.mini-player'),null)
  assert.equal(document.querySelector('.completion-toast'),null,'Completion popup must dismiss after opening')
  opened.length=0
  const completedRow=[...document.querySelectorAll('.task-card')].find(r=>r.textContent.includes('Unknown total'))
  localStorage.setItem('dropdl-playback',JSON.stringify({'job:unknown-size':35}))
  const playButton=completedRow.querySelector('.play-button')
  assert.equal(playButton.textContent,lang==='ar'?'تشغيل':'Play')
  await click(playButton)
  assert.deepEqual(opened,['unknown-size'],'Play defaults to Windows player')
  assert.equal(document.querySelector('.mini-player'),null)
  opened.length=0
  await click(completedRow.querySelector('.mini-play-button'))
  assert.equal(document.querySelector('.mini-player header strong').textContent,'Unknown total')
  const media=document.querySelector('.mini-player video')
  assert.equal(media.autoplay,false,'Explicit mini player opens paused')
  Object.defineProperty(media,'duration',{value:120,configurable:true})
  await act(async()=>{media.dispatchEvent(new Event('loadedmetadata'));await settle()})
  assert.equal(media.currentTime,35,'Playback resumes from its saved position')
  await click(document.querySelector('.mini-player .player-tools button:last-of-type'))
  assert.equal(media.currentTime,45)
  const rate=document.querySelector('.player-tools select')
  await act(async()=>{rate.value='1.5';rate.dispatchEvent(new Event('change',{bubbles:true}));await settle()})
  assert.equal(media.playbackRate,1.5)
  await click(document.querySelector('.mini-player header button'))
  assert(document.querySelector('.mini-player-content').hidden)
  await click(document.querySelector('.mini-player header button'))
  assert(!document.querySelector('.mini-player-content').hidden)
  media.currentTime=67
  await act(async()=>{media.dispatchEvent(new Event('timeupdate'));await settle()})
  assert.equal(JSON.parse(localStorage.getItem('dropdl-playback'))['job:unknown-size'],67)
  await click(document.querySelector('.mini-player .secondary'))
  assert.deepEqual(opened,['unknown-size'])
  assert.equal(document.querySelector('.completion-toast'),null)
  // A failed media open reports the failure and retains the completed task for retry.
  dom.window.pywebview.api.open_downloaded=async()=>false
  await click(completedRow.querySelector('.play-button'))
  assert.equal(document.querySelector('.mini-player'),null)
  assert(document.querySelector('[role=alert]').textContent.includes(lang==='ar'?'تعذر فتح الوسائط':'The media could not be opened'))
  assert.equal(completedRow.querySelector('.status-badge').textContent,lang==='ar'?'مكتملة':'Completed')
  dom.window.pywebview.api.open_downloaded=async id=>{opened.push(id);return true}
  await click(completedRow.querySelector('.play-button'))
  assert.equal(document.querySelector('[role=alert]'),null)
  assert.equal(document.querySelector('.mini-player'),null)
  // Audio uses the same native player action.
  jobs.push({...base,id:'completed-audio',kind:'audio',container:'mp3',title:'Finished audio',purpose:'download',status:'completed'})
  await act(async()=>{await new Promise(resolve=>setTimeout(resolve,1300))})
  const audioRow=[...document.querySelectorAll('.task-card')].find(r=>r.textContent.includes('Finished audio'))
  await click(audioRow.querySelector('.play-button'))
  assert.equal(document.querySelector('.mini-player'),null)
  await click(audioRow.querySelector('.mini-play-button'))
  assert(document.querySelector('.mini-player audio'))
  assert.equal(document.querySelector('.mini-player audio').autoplay,false)
  await click(document.querySelector('.mini-player .secondary'))
  assert.equal(opened.at(-1),'completed-audio')
  jobs=jobs.filter(j=>j.id!=='completed-audio')
  jobs=jobs.filter(j=>j.id!=='unknown-size')
  await act(async()=>{await new Promise(resolve=>setTimeout(resolve,1300))})
  delete dom.window.pywebview
  // Manual task selection: selected removal affects only chosen records.
  selectionRequests=[]
  jobs.push({...base,id:'keep-task',title:'Keep this task',purpose:'download',status:'completed'})
  await act(async()=>{await new Promise(resolve=>setTimeout(resolve,1300))})
  const taskCheckbox=[...document.querySelectorAll('.selection-cell input')].find(x=>x.getAttribute('aria-label').includes('Real download'))
  await click(taskCheckbox)
  assert.equal(document.querySelector('.selection-bar strong').textContent,lang==='ar'?'1 محددة':'1 selected')
  selectedActions=[]
  await click([...document.querySelectorAll('.selection-bar button')].find(b=>b.textContent===(lang==='ar'?'استئناف / إعادة محاولة المحدد':'Resume / retry selected')))
  await click([...document.querySelectorAll('.selection-bar button')].find(b=>b.textContent===(lang==='ar'?'إيقاف المحدد مؤقتًا':'Pause selected')))
  assert.deepEqual(selectedActions,[['download','retry'],['download','pause']])
  await click([...document.querySelectorAll('.selection-bar button')].find(b=>b.textContent===(lang==='ar'?'إلغاء المهام المحددة':'Cancel selected')))
  assert.equal(jobs.find(j=>j.id==='download').status,'cancelled')
  await click(document.querySelector('.selection-bar button.danger'))
  await click(document.querySelector('.selection-confirm button.danger'))
  assert.deepEqual(selectionRequests,[['download']])
  assert(!document.querySelector('.task-table').textContent.includes('Real download'))
  assert(document.querySelector('.task-table').textContent.includes('Keep this task'))
  const keepBox=[...document.querySelectorAll('.selection-cell input')].find(x=>x.getAttribute('aria-label').includes('Keep this task'))
  await click(keepBox)
  assert(document.querySelector('.selection-bar a').href.includes('ids=keep-task'))
  await click([...document.querySelectorAll('.selection-bar button')].find(b=>b.textContent===(lang==='ar'?'إلغاء التحديد':'Clear selection')))
  jobs=jobs.filter(j=>j.id!=='keep-task');jobs.push({...base,id:'download',title:'Real download',purpose:'download',status:'cancelled'})
  await act(async()=>{await new Promise(resolve=>setTimeout(resolve,1300))})
  // Preferences expose diagnostics and persist the new organization rules.
  await click([...document.querySelectorAll('.nav-tool')].at(-2))
  assert(document.querySelector('.support-panel').textContent.includes(lang==='ar'?'التشخيص والإصلاح':'Diagnostics & repair'))
  assert(document.querySelector('.support-panel a').href.endsWith('/api/support/bundle'))
  const folderRule=document.querySelector('.organization-panel select')
  const nameRule=document.querySelectorAll('.organization-panel select')[1]
  await act(async()=>{folderRule.value='creator';folderRule.dispatchEvent(new Event('change',{bubbles:true}));await settle();nameRule.value='date_title';nameRule.dispatchEvent(new Event('change',{bubbles:true}));await settle()})
  await click(document.querySelector('.drawer-body .primary.full'))
  assert.equal(settingsPayload.folder_rule,'creator');assert.equal(settingsPayload.name_rule,'date_title')
  // Every tour step has a different, localized title and retains navigation focus.
  await click([...document.querySelectorAll('.nav-tool')].at(-1))
  const titles=[]
  for(let step=0;step<6;step++) {
    titles.push(document.getElementById('tour-title').textContent)
    assert(document.querySelector('.tour-card').contains(document.activeElement))
    await click(document.querySelector('.tour-actions .primary'))
  }
  assert.equal(new Set(titles).size,6)
  assert.equal(titles[1],lang==='ar'?'اختر المصدر':'Choose a source')
  assert.equal(document.querySelector('.tour-overlay'),null)
  // A playlist pasted into the default tab is routed to flat playlist loading.
  await click(document.getElementById('tour-add'))
  Object.defineProperty(navigator,'clipboard',{value:{readText:async()=> 'https://www.youtube.com/watch?v=sample&list=PLsample'},configurable:true})
  await click(document.querySelector('.source-form button[type=button]'))
  assert.equal(document.querySelector('.mode-tabs button.active').textContent,lang==='ar'?'قائمة تشغيل':'Playlist')
  playlistRequests=0;videoInspections=0
  await act(async()=>{document.querySelector('.source-form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));await settle()})
  assert.equal(playlistRequests,1);assert.equal(videoInspections,0)
  assert.equal(document.querySelectorAll('.playlist-list label').length,100)
  assert(document.querySelectorAll('.playlist-list input')[1].disabled)
  assert.equal(document.querySelector('[role=alert]'),null)
  playlistFailure=true
  await act(async()=>{document.querySelector('.source-form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));await settle()})
  assert(document.querySelector('[role=alert]').textContent.includes('Playlist unavailable'))
  assert(document.getElementById('tour-add'))
  assert(!document.querySelector('.source-form .primary').disabled)
  playlistFailure=false
  await act(async()=>{document.querySelector('.source-form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));await settle()})
  await click(document.querySelectorAll('#tour-output .mode-tabs button')[2])
  await click(document.querySelector('.drawer-footer .primary'))
  assert.equal(document.querySelector('[role=dialog]'),null)
  assert.equal(document.querySelectorAll('.task-card').length,100)
  assert.equal(document.querySelector('.filter-nav button b').textContent,'199')
  await click(document.querySelector('.queue-pagination button:last-child'))
  assert.equal(document.querySelectorAll('.task-card').length,99)
  assert(document.querySelector('.queue-pagination button:last-child').disabled)
  assert.equal(document.querySelector('[role=alert]'),null)
  // Desktop workspace: library originals, converter selection, native import and localized controls.
  const converterButton=document.querySelectorAll('.workspace-nav button')[0]
  await click(converterButton)
  assert.equal(document.querySelector('.manager-header h1').textContent,lang==='ar'?'تحويل':'Convert')
  assert.equal(document.querySelectorAll('.media-card').length,1)
  assert(!document.querySelector('.media-card .danger-text'),'Imported original exposed a delete action')
  await click(document.querySelector('.media-select input'))
  assert.equal(document.querySelector('.converter-panel .button-row .primary').disabled,false)
  await click(document.querySelector('.converter-panel .button-row .primary'))
  assert.deepEqual(conversionPayload.media_ids,['local-media'])
  assert.equal(conversionPayload.preset,'device')
  assert.equal(conversionPayload.sample,false)
  await click(document.querySelector('.converter-panel .button-row .secondary'))
  assert.equal(conversionPayload.sample,true)
  dom.window.pywebview={api:{choose_media_files:async()=>({files:libraryFiles,errors:[]})}}
  await click(document.querySelector('.workspace-intro .primary'))
  assert.equal(document.querySelector('[role=alert]'),null)
  assert(document.querySelector('.browser-inbox'))
  await click(document.querySelectorAll('.workspace-nav button')[2])
  assert.equal(document.querySelector('.manager-header h1').textContent,lang==='ar'?'مكتبة الوسائط':'Media library')
  assert.equal(document.querySelector('.converter-panel'),null)
  assert(document.querySelector('.storage-panel'))
  // Media selection exports originals, but offers deletion only for owned outputs.
  libraryFiles.push({id:'output-media',title:'Finished output',filename:'output.mp4',path:'C:/Downloads/output.mp4',kind:'video',site:'Example',owned:true,exists:true,size:1024,created:1700000000,metadata:{}})
  await click(document.querySelector('.workspace-intro button.secondary'))
  await click(document.querySelector('.library-toolbar button.ghost'))
  assert(document.querySelector('.selection-bar a').href.includes('local-media'))
  const deleteButton=document.querySelector('.selection-bar .danger')
  assert(deleteButton.textContent.includes('(1)'))
  await click(deleteButton)
  await click(document.querySelector('.deletion-dialog button.secondary'))
  assert(!document.querySelector('.deletion-dialog'))
  await click(document.querySelector('.selection-bar button.secondary'))
  assert.deepEqual(selectionRequests.at(-1),{ids:['local-media','output-media'],delete_file:false})
  assert.equal(document.querySelectorAll('.media-card').length,0)
  // A library item can detach even after its original task was removed from the queue.
  libraryFiles=[{id:'persisted-media',title:'Retained output',filename:'retained.mp4',path:'C:/Downloads/retained.mp4',kind:'video',site:'Local',owned:true,exists:true,size:2048,created:1700000000,metadata:{job_id:'removed-task'}}]
  await click(document.querySelector('.workspace-intro button.secondary'))
  const detached=[];dom.window.pywebview={api:{open_player:async(...args)=>{detached.push(args);return true}}}
  await click(document.querySelector('.media-card .mini-play-button'))
  await click(document.querySelector('.detach-player-button'))
  assert.equal(detached[0][0],'library:persisted-media')
  assert.equal(document.querySelector('.mini-player'),null)
  // Restore fixtures for the next language.
  libraryFiles=[{id:'local-media',title:'Local editing source',filename:'source.mp4',path:'C:/media/source.mp4',kind:'video',site:'Local',owned:false,exists:true,size:2048,created:1700000000,metadata:{}}]
  delete dom.window.pywebview
  await act(async()=>root.unmount())
}
async function checkSidebarClips(lang) {
  const previousFetch=global.fetch;const payloads=[],trayCalls=[],editorCalls=[]
  jobs=[];localStorage.clear();localStorage.setItem('dropdl-language',lang);localStorage.setItem('dropdl-tour-v1','done')
  dom.window.pywebview={api:{configure_tray:async(...args)=>{trayCalls.push(args);return true},open_editor:async()=>{editorCalls.push(true);return true}}}
  global.fetch=async(url,options)=>{
    let result
    if(url.endsWith('/api/info'))result={title:'Sidebar source',duration:900,suggested_qualities:['1080p']}
    else if(url.endsWith('/api/preview')){const j={...base,id:'inline-preview',purpose:'preview',status:'downloading',preview_ready:false,filename:'source.mp4'};jobs.push(j);result={...j};setTimeout(()=>{j.status='completed';j.preview_ready=true},50)}
    else if(url.endsWith('/api/batch')||url.endsWith('/clip')){payloads.push([url,JSON.parse(options.body)]);result={batch_id:'clipped',jobs:[]}}
    else return previousFetch(url,options)
    return {ok:true,json:async()=>result}
  }
  const root=createRoot(document.getElementById('root'))
  const input=async(el,value)=>{assert(el);await act(async()=>{Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype,'value').set.call(el,value);el.dispatchEvent(new Event('input',{bubbles:true}));await settle()})}
  const prepare=async()=>{
    await click(document.getElementById('tour-add'))
    await input(document.querySelector('.source-form input'),'https://example.com/video')
    await act(async()=>{document.querySelector('.source-form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));await settle()})
    const toggle=document.querySelector('#tour-clip input');if(!toggle.checked)await click(toggle)
    await input(document.querySelector('.range-grid input[type=text]'),'00:00:29.9')
    await input(document.querySelectorAll('.range-grid input[type=text]')[1],'00:12:54.6')
    assert.equal(document.querySelector('.range-grid input[type=text]').value,'00:00:29.9')
  }
  try {
    await act(async()=>{root.render(React.createElement(App));await settle()})
    await prepare();await click(document.querySelector('.drawer-footer .primary'))
    assert.equal(payloads[0][1].clip_enabled,true);assert.equal(payloads[0][1].clip_start,29.9);assert.equal(payloads[0][1].clip_end,774.6)
    await prepare()
    await input(document.querySelector('.range-grid input[type=text]'),'00:90:00')
    assert(document.querySelector('.drawer-footer .primary').disabled,'Invalid timestamp silently accepted')
    await input(document.querySelector('.range-grid input[type=text]'),'00:00:29.9')
    await click(document.querySelector('.preview-overlay .primary'))
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,1300))})
    assert(document.querySelector('[role=dialog]'),'Preview closed sidebar')
    assert(document.querySelector('.clip-panel video'),'No inline preview')
    assert.equal(editorCalls.length,0,'Sidebar preview unexpectedly opens editor')
    assert.equal(document.querySelector('.range-grid input[type=text]').value,'00:00:29.9')
    await click(document.querySelector('.drawer-footer .primary'))
    assert(payloads[1][0].endsWith('/clip'));assert.equal(payloads[1][1].clip_end,774.6);assert.equal(payloads[1][1].show_in_downloads,true)
    await click([...document.querySelectorAll('.nav-tool')].at(-2))
    const toggle=[...document.querySelectorAll('input[type=checkbox]')].find(x=>x.parentElement.textContent.includes(lang==='ar'?'علبة النظام':'system tray'))
    assert(toggle&&!toggle.disabled);if(!toggle.checked)await click(toggle)
    await click(document.querySelector('.drawer-body .primary.full'))
    assert.equal(settingsPayload.keep_in_tray,true);assert(trayCalls.some(([enabled,l])=>enabled&&l===lang))
  } finally {await act(async()=>root.unmount());global.fetch=previousFetch;delete dom.window.pywebview}
}
async function checkRecovery() {
  const code=load('esbuild').buildSync({entryPoints:[path.join(frontend,'src/ErrorBoundary.tsx')],bundle:true,write:false,format:'cjs',platform:'node',jsx:'automatic',external:['react','react/jsx-runtime'],define:{'import.meta.env':'{}'},logLevel:'silent'}).outputFiles[0].text
  const mod=new Module(path.join(frontend,'recovery-check.cjs'),module)
  mod.filename=path.join(frontend,'recovery-check.cjs');mod.paths=Module._nodeModulePaths(frontend);mod._compile(code,mod.filename)
  const root=createRoot(document.getElementById('root'))
  const before=console.error;console.error=()=>{}
  try {
    function Broken(){throw new Error('Test rendering failure')}
    await act(async()=>{root.render(React.createElement(mod.exports.default,null,React.createElement(Broken)));await settle()})
    assert(document.querySelector('.ui-recovery').textContent.includes('Test rendering failure'))
    assert.equal(document.querySelector('.ui-recovery').dir,'rtl')
    assert(localStorage.getItem('dropdl-last-ui-error').includes('Test rendering failure'))
  } finally {console.error=before;await act(async()=>root.unmount())}
}
(async()=>{await run('en');await run('ar');await checkSidebarClips('en');await checkSidebarClips('ar');await checkRecovery();console.log('UI checks passed: hidden preview rows/counts, popup cancellation, same-row cancellation, modal access, six tour titles, playlist paste/loading/errors, 198-task queue and pagination, converter/library/native import, selected task pause/resume/cancel/remove/export, media selection and original protection, render recovery, English/Arabic.');dom.window.close()})().catch(error=>{console.error(error);process.exit(1)})
