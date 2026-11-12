import {MediaFile} from './api'
import {isEditedMedia} from './editorMedia'
export type LibraryFilters={query:string;kind:string;site:string;collection:string;favorites:boolean;availability:string;origin:string;sort:string}
export function filterLibrary(files:MediaFile[],f:LibraryFilters){
 const q=f.query.trim().toLocaleLowerCase()
 const results=files.filter(file=>(f.kind==='all'||file.kind===f.kind)&&(f.site==='all'||file.site===f.site)&&(!f.favorites||file.favorite)&&(f.collection==='all'||(f.collection==='unfiled'?!file.collection_id:file.collection_id===f.collection))&&(f.availability==='all'||(f.availability==='missing'?!file.exists:file.exists))&&(f.origin==='all'||(f.origin==='original'?!file.owned:f.origin==='edited'?isEditedMedia(file):f.origin==='converted'?file.metadata.purpose==='conversion':file.owned&&file.metadata.purpose!=='conversion'&&!isEditedMedia(file)))&&`${file.title} ${file.site} ${file.filename} ${file.collection_name||''}`.toLocaleLowerCase().includes(q))
 return results.sort((a,b)=>{let value=0;switch(f.sort){case 'oldest':value=a.created-b.created;break;case 'title':value=a.title.localeCompare(b.title,undefined,{numeric:true,sensitivity:'base'});break;case 'size':value=b.size-a.size;break;case 'duration':{const ad=Number(a.metadata.duration),bd=Number(b.metadata.duration);const av=Number.isFinite(ad)&&ad>0,bv=Number.isFinite(bd)&&bd>0;value=av&&bv?bd-ad:av?-1:bv?1:0;break}default:value=b.created-a.created}return value||a.id.localeCompare(b.id)})
}
export const mediaClock=(value:unknown)=>{const n=Number(value);return Number.isFinite(n)&&n>0?[Math.floor(n/3600),Math.floor(n%3600/60),Math.floor(n%60)].map(v=>String(v).padStart(2,'0')).join(':'):''}
