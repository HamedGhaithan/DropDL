import {EditProject,Segment,positioned,clipLength,trackState} from './editorProject'
import {MediaFile} from './api'
export const isEditedMedia=(file:MediaFile)=>file.metadata?.purpose==='clip'||!!file.metadata?.edited||file.metadata?.clip_start!=null||file.metadata?.clip_end!=null
export const MEDIA_DRAG='application/x-dropdl-media'
export function insertSegments(project:EditProject,clips:Segment[],seconds:number,track=0){
 if(trackState(project,track).locked)throw Error('This track is locked. Unlock it before inserting clips.')
 const base=positioned(project);let at=Math.max(0,seconds)
 const added=clips.map(s=>{const item={...s,offset:at,track};at+=clipLength(s);return item})
 if(base.segments.length+added.length>100)throw Error('The timeline supports up to 100 clips.')
 return {project:{...base,segments:[...base.segments,...added]},index:base.segments.length}
}
