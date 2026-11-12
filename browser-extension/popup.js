const base='http://127.0.0.1:17321/api/browser';let token
const status=document.getElementById('status')
async function request(path,data,auth){const response=await fetch(base+path,{method:'POST',headers:{'content-type':'application/json',...(auth?{Authorization:'Bearer '+auth}:{})},body:JSON.stringify(data)});const result=await response.json();if(!response.ok)throw Error(typeof result.detail==='string'?result.detail:'Check the pairing code.');return result}
function update(){document.getElementById('pairing').hidden=!!token;document.getElementById('send').hidden=!token;document.getElementById('disconnect').hidden=!token}
chrome.storage.local.get('token').then(data=>{token=data.token;update()})
document.getElementById('pair').onclick=async()=>{try{const result=await request('/pair',{code:document.getElementById('code').value.trim()});token=result.token;await chrome.storage.local.set({token});update();status.textContent='Connected.'}catch(error){status.textContent=error.message}}
document.getElementById('send').onclick=async()=>{try{const [tab]=await chrome.tabs.query({active:true,currentWindow:true});if(!/^https?:\/\//.test(tab.url||''))throw Error('Open a video or playlist webpage first.');await request('/inbox',{url:tab.url,title:tab.title||''},token);status.textContent='Sent. Open the browser inbox in DropDL to choose output options.'}catch(error){status.textContent=error.message}}
document.getElementById('disconnect').onclick=async()=>{await chrome.storage.local.remove('token');token=null;update()}
