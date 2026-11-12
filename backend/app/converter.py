"""Validated FFmpeg conversions. Originals are never modified."""
import json
import math
import os
import shutil
import subprocess
import time
from pathlib import Path
from .downloader import _tool,DownloadCancelled
from .jobs import jobs

PRESETS={
 'device':{'label':'Universal MP4','ar':'MP4 متوافق','container':'mp4','kind':'video','codec':'libx264','crf':22},
 'compact':{'label':'Small mobile video','ar':'فيديو صغير للهاتف','container':'mp4','kind':'video','codec':'libx264','crf':28,'height':720},
 'quality':{'label':'High quality video','ar':'فيديو عالي الجودة','container':'mp4','kind':'video','codec':'libx264','crf':18},
 'webm':{'label':'WebM / VP9','ar':'WebM / VP9','container':'webm','kind':'video','codec':'libvpx-vp9','crf':32},
 'mp3':{'label':'MP3 audio','ar':'صوت MP3','container':'mp3','kind':'audio','codec':'libmp3lame'},
 'm4a':{'label':'AAC / M4A audio','ar':'صوت AAC / M4A','container':'m4a','kind':'audio','codec':'aac'},
 'wav':{'label':'WAV for editing','ar':'WAV للمونتاج','container':'wav','kind':'audio','codec':'pcm_s24le'},
 'flac':{'label':'Lossless FLAC','ar':'FLAC دون فقد','container':'flac','kind':'audio','codec':'flac'},
 'prores':{'label':'ProRes 422 editing','ar':'ProRes 422 للمونتاج','container':'mov','kind':'video','codec':'prores_ks'},
 'dnxhr':{'label':'DNxHR HQ editing','ar':'DNxHR HQ للمونتاج','container':'mov','kind':'video','codec':'dnxhd'},
 'remux':{'label':'Fast container change','ar':'تغيير الحاوية بسرعة','container':'mkv','kind':'video','codec':'copy'},
}

def eval_rate(value):
    try:
        numerator,denominator=value.split('/');return float(numerator)/float(denominator) if float(denominator) else 0
    except (ValueError,TypeError):return 0

def probe_media(path):
    process=subprocess.run([_tool('ffprobe'),'-v','error','-show_format','-show_streams','-of','json',str(path)],capture_output=True,text=True,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    if process.returncode:raise ValueError('This file could not be read as media.')
    data=json.loads(process.stdout);streams=data.get('streams',[])
    video=next((x for x in streams if x.get('codec_type')=='video' and not x.get('disposition',{}).get('attached_pic')),None)
    audio=next((x for x in streams if x.get('codec_type')=='audio'),None)
    if not video and not audio:raise ValueError('No playable video or audio stream was found.')
    duration=float(data.get('format',{}).get('duration') or 0)
    return {'duration':duration if math.isfinite(duration) else 0,'width':video.get('width',0) if video else 0,'height':video.get('height',0) if video else 0,'fps':(eval_rate(video.get('avg_frame_rate','0/1')) if video else 0),'video_codec':video.get('codec_name') if video else None,'audio_codec':audio.get('codec_name') if audio else None,'kind':'video' if video else 'audio','streams':streams}

def build_command(source,target,options,metadata):
    if options.get('edit'):
        from .editor import build_edit_command
        return build_edit_command(source,target,options['edit'],metadata)
    preset=PRESETS[options.get('preset','device')];duration=metadata['duration'];start=options.get('start',0) or 0;finish=options.get('finish')
    if start and start>=duration:raise ValueError('Start is outside the source duration.')
    if finish is not None and (finish<=start or finish>duration+.1):raise ValueError('Finish must be after start and within the source duration.')
    if preset['kind']=='video' and not metadata['video_codec']:raise ValueError('This source has no video stream. Choose an audio preset.')
    if preset['kind']=='audio' and not metadata['audio_codec']:raise ValueError('This source has no audio stream.')
    command=[_tool('ffmpeg'),'-nostdin','-y','-v','error','-i',str(source)]
    if start:command+=['-ss',str(start)]
    if finish is not None:command+=['-t',str(min(10,finish-start) if options.get('sample') else finish-start)]
    elif options.get('sample'):command+=['-t',str(min(10,max(.1,duration-start)))]
    command+=['-map_metadata','0','-map_chapters','0']
    if preset['codec']=='copy':
        if any(options.get(k) for k in ('height','fps','rotate','normalize','target_mb','crop')):raise ValueError('Fast container changes cannot resize, rotate, normalize or target a file size.')
        command+=['-map','0:v:0','-map','0:a?','-map','0:s?','-c','copy']
    elif preset['kind']=='audio':
        if any(options.get(k) for k in ('height','fps','rotate','target_mb','crop')):raise ValueError('Resize, frame rate, rotation, crop and target video size apply to video presets only.')
        command+=['-vn','-map','0:a:0','-c:a',preset['codec']]
        if preset['codec'] in {'aac','libmp3lame'}:command+=['-b:a','192k']
        if options.get('normalize'):command+=['-af','loudnorm=I=-16:TP=-1.5:LRA=11']
    else:
        filters=[];crop=options.get('crop')
        if crop and (crop['x']+crop['width']>metadata['width'] or crop['y']+crop['height']>metadata['height']):raise ValueError('Crop rectangle exceeds the source dimensions.')
        if crop:filters.append('crop='+':'.join(str(int(crop[k])) for k in ('width','height','x','y')))
        rotation=options.get('rotate',0)
        if rotation==90:filters.append('transpose=1')
        elif rotation==180:filters+=['hflip','vflip']
        elif rotation==270:filters.append('transpose=2')
        height=options.get('height') or preset.get('height')
        if height:filters.append(f"scale=-2:'trunc(min({height},ih)/2)*2'")
        if filters:command+=['-vf',','.join(filters)]
        command+=['-map','0:v:0','-map','0:a:0?','-c:v',preset['codec']]
        if preset['codec']=='prores_ks':command+=['-profile:v','2','-pix_fmt','yuv422p10le','-c:a','pcm_s24le']
        elif preset['codec']=='dnxhd':command+=['-profile:v','dnxhr_hq','-pix_fmt','yuv422p','-c:a','pcm_s24le']
        else:
            command+=['-pix_fmt','yuv420p','-c:a','libopus' if preset['container']=='webm' else 'aac','-b:a','128k']
            if options.get('target_mb'):
                length=min(10,(finish or duration)-start) if options.get('sample') else (finish or duration)-start
                rate=int(options['target_mb']*1024*1024*8/max(.1,length)*.95-128000)
                if rate<50000:raise ValueError('Target size is too small for this duration.')
                command+=['-b:v',str(rate)]
            else:command+=['-crf',str(preset['crf'])]
            if preset['codec']=='libx264':command+=['-preset','fast']
            else:command+=['-b:v','0'] if not options.get('target_mb') else []
        if options.get('fps'):command+=['-r',str(options['fps'])]
        if options.get('normalize'):command+=['-af','loudnorm=I=-16:TP=-1.5:LRA=11']
    if target.suffix in {'.mp4','.m4a','.mov'}:command+=['-movflags','+faststart']
    command+=['-threads','2','-progress','pipe:1','-nostats',str(target)]
    return command

def run_conversion(job):
    source=Path(job.source_filename or '');directory=Path(job.directory);directory.mkdir(parents=True,exist_ok=True)
    temporary=directory/('converted.tmp.'+job.container)
    process=None
    try:
        if job.cancel_event.is_set():raise DownloadCancelled()
        metadata=probe_media(source);options=job.conversion_options;command=build_command(source,temporary,options,metadata)
        jobs.update_attempt(job,status='converting',percent=0,eta=None,error=None)
        began=time.monotonic();duration=(options.get('finish') or metadata['duration'])-(options.get('start') or 0)
        if options.get('sample'):duration=min(10,duration)
        if options.get('edit'):
            from .editor import timeline_duration
            duration=timeline_duration(options['edit']['segments'])
        with (directory/'conversion.log').open('w+b') as errors:
            process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=errors,text=True,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            # A monitor terminates silent FFmpeg processes as soon as cancellation is requested.
            from threading import Thread
            def watch():
                while process.poll() is None:
                    if job.cancel_event.wait(.15):
                        process.terminate()
                        try:process.wait(timeout=3)
                        except subprocess.TimeoutExpired:process.kill()
                        return
            Thread(target=watch,daemon=True).start()
            for line in process.stdout:
                if line.startswith('out_time_us='):
                    try:done=float(line.split('=',1)[1])/1e6
                    except ValueError:continue
                    elapsed=time.monotonic()-began;percent=min(99,done/max(.1,duration)*100)
                    jobs.update_attempt(job,percent=round(percent,1),eta=int(max(0,duration-done)*elapsed/done) if done>0 else None)
            process.wait()
            if job.cancel_event.is_set():raise DownloadCancelled()
            if process.returncode:
                errors.seek(0);raise RuntimeError('Conversion failed: '+errors.read().decode(errors='replace')[-2000:])
        destination=Path(job.destination or directory);destination.mkdir(parents=True,exist_ok=True)
        final=destination/(source.stem[:130]+' ['+job.id[:8]+(' sample' if options.get('sample') else ' edited' if options.get('edit') else ' converted')+'].'+job.container)
        if final.resolve()==source.resolve() or final.exists():raise ValueError('Output path already exists; the original is preserved.')
        shutil.move(str(temporary),str(final))
        preview=None
        if options.get('sample'):
            from .downloader import prepare_preview
            preview=prepare_preview(job,final)
        jobs.update_attempt(job,status='completed',percent=100,eta=0,filename=str(final),preview_filename=str(preview) if preview else None)
    except DownloadCancelled:jobs.update_attempt(job,status='cancelled',error=None)
    except Exception as exc:jobs.update_attempt(job,status='failed',error=str(exc))
    finally:
        if process and process.poll() is None:process.kill();process.wait()
        temporary.unlink(missing_ok=True)
        temporary.with_suffix('.filters.txt').unlink(missing_ok=True)
        temporary.with_suffix('.captions.ass').unlink(missing_ok=True)
