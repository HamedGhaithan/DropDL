"""Read-only multi-source timeline rendering, normalized video and mixed audio."""
from pathlib import Path
from functools import lru_cache
import subprocess
from .downloader import _tool

@lru_cache(maxsize=8)
def filter_script_option(executable,modified=0):
    """Probe syntax rather than assuming a version; retain old FFmpeg support."""
    try:
        result=subprocess.run([executable,'-nostdin','-v','error','-/filter_complex'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=5)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise RuntimeError('Could not check FFmpeg export support. Repair FFmpeg and retry.') from exc
    message=(result.stderr or '')+(result.stdout or '')
    if 'Missing argument' in message and 'filter_complex' in message:return '-/filter_complex'
    if 'Unrecognized option' in message and '/filter_complex' in message:return '-filter_complex_script'
    raise RuntimeError('FFmpeg could not start or report its filter support. Repair FFmpeg and retry: '+message[-600:])

def timeline_duration(segments):
    cursor=total=0
    for part in segments:
        cursor=part.get('offset',cursor)+(part['end']-part['start'])/part['speed']
        total=max(total,cursor)
    return total

def tempo(speed):
    filters=[]
    while speed>2:filters.append('atempo=2');speed/=2
    while speed<.5:filters.append('atempo=0.5');speed/=.5
    return filters+[f'atempo={speed}']

def build_edit_command(source,target,edit,metadata):
    from .converter import probe_media
    default=edit.get('_default_source','default')
    sources=edit.get('_sources') or {default:{'path':str(source),'metadata':metadata}}
    # Re-probe at export time so moved/changed files fail cleanly before encoding.
    sources={k:{'path':v['path'],'metadata':probe_media(v['path'])} for k,v in sources.items()}
    segments=edit['segments'];ids=[s.get('source_job_id') or default for s in segments]
    video=edit.get('export_format') not in ('mp3','m4a','wav') and any(sources[k]['metadata']['video_codec'] for k in ids)
    tracks=edit.get('tracks') or []
    def track(part):
        lane=part.get('track',0)
        return tracks[lane] if lane<len(tracks) else {}
    visible=lambda i:not track(segments[i]).get('hidden',False)
    audio=any(sources[k]['metadata']['audio_codec'] for k in ids) or bool(edit.get('soundtrack'))
    if not video and not audio:raise ValueError('No media stream.')
    first=next((sources[k]['metadata'] for k in ids if sources[k]['metadata']['video_codec']),metadata)
    width,height=first['width'],first['height'];rotation=edit.get('rotate',0)
    if rotation in (90,270):width,height=height,width
    ratio=edit.get('ratio','original')
    if ratio!='original':
        rw,rh=map(float,ratio.split(':'));width=min(width,height*rw/rh);height=min(height,width*rh/rw)
    requested=edit.get('height',0)
    if video:
        if requested:width=width/height*requested;height=requested
        width=max(2,int(width)//2*2);height=max(2,int(height)//2*2)
    fps=edit.get('fps',30);graph=[];labels=[];command=[_tool('ffmpeg'),'-nostdin','-y','-v','error']
    indices={k:i for i,k in enumerate(sources)}
    for entry in sources.values():command+=['-i',str(entry['path'])]
    for key,index in indices.items():
        uses=[i for i,k in enumerate(ids) if k==key];info=sources[key]['metadata']
        video_uses=[i for i in uses if visible(i)]
        if video_uses and info['video_codec'] and video:graph.append(f'[{index}:v]split={len(video_uses)}'+''.join(f'[vin{i}]' for i in video_uses))
        if uses and info['audio_codec'] and audio:graph.append(f'[{index}:a]asplit={len(uses)}'+''.join(f'[ain{i}]' for i in uses))
    duration=0;offsets=[];cursor=0
    for i,part in enumerate(segments):
        a,b,speed=part['start'],part['end'],part['speed'];info=sources[ids[i]]['metadata']
        if a<0 or b<=a or b>info['duration']+.05:raise ValueError('A segment is outside its source duration.')
        length=(b-a)/speed;offset=part.get("offset",cursor);cursor=offset+length;offsets.append(offset);duration=max(duration,cursor)
        effects=[]
        if rotation==90:effects.append('transpose=1')
        elif rotation==180:effects+=['hflip','vflip']
        elif rotation==270:effects.append('transpose=2')
        if edit.get('flip'):effects.append('hflip')
        if ratio!='original':
            rw,rh=map(float,ratio.split(':'));r=rw/rh
            effects.append(f"crop=w='trunc(min(iw,ih*{r})/2)*2':h='trunc(min(ih,iw/{r})/2)*2'")
        effects += [f"eq=brightness={edit.get('brightness',0)}:contrast={edit.get('contrast',1)}:saturation={edit.get('saturation',1)}",f'scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2',f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2','setsar=1','format=yuv420p',f'fps={fps}']
        if video:
            if info['video_codec'] and visible(i):graph.append(f'[vin{i}]trim=start={a}:end={b},setpts=(PTS-STARTPTS)/{speed},'+','.join(effects)+f'[v{i}]')

        if audio:
            if info['audio_codec']:graph.append(f'[ain{i}]atrim=start={a}:end={b},asetpts=PTS-STARTPTS,'+','.join(tempo(speed))+f",volume={0 if track(part).get('muted') else part.get('gain',1)},aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,apad,atrim=duration={length}[a{i}]")
            else:graph.append(f'anullsrc=r=48000:cl=stereo,atrim=duration={length}[a{i}]')
        if video:labels.append(f'[v{i}]')
        if audio:labels.append(f'[a{i}]')
    # Full-frame higher tracks cover lower tracks; every clip's audio is mixed.
    if video:
        graph.append(f'color=c=black:s={width}x{height}:r={fps}:d={duration},setsar=1[canvas0]')
        order=sorted([i for i in range(len(segments)) if visible(i) and sources[ids[i]]['metadata']['video_codec']],key=lambda i:(segments[i].get('track',0),i))
        if not order:graph.append('[canvas0]null[joinedv]')
        for layer,i in enumerate(order):
            offset=offsets[i];length=(segments[i]['end']-segments[i]['start'])/segments[i]['speed']
            graph.append(f'[v{i}]setpts=PTS+{offset}/TB[placed{i}]')
            label='joinedv' if layer==len(order)-1 else f'canvas{layer+1}'
            graph.append(f"[canvas{layer}][placed{i}]overlay=eof_action=pass:repeatlast=0:enable='gte(t,{offset})*lt(t,{offset+length})'[{label}]")
    if audio:
        graph.append(f'anullsrc=r=48000:cl=stereo,atrim=duration={duration}[silence]')
        for i,offset in enumerate(offsets):graph.append(f'[a{i}]adelay={round(offset*1000)}:all=1[placed_a{i}]')
        graph.append('[silence]'+''.join(f'[placed_a{i}]' for i in range(len(segments)))+f'amix=inputs={len(segments)+1}:duration=first:normalize=0:dropout_transition=0[joineda]')
    fade_in=min(edit.get('fadeIn',0),duration/2);fade_out=min(edit.get('fadeOut',0),duration/2)
    if video:
        vf=[]
        if edit.get('texts'):
            captions=Path(target).with_suffix('.captions.ass');write_text_track(captions,edit['texts'],width,height,duration)
            def escape(value,special):return ''.join(chr(92)+c if c in special else c for c in value)
            # FFmpeg parses option values and then the enclosing filter graph.
            escaped=escape(escape(str(captions.resolve()).replace(chr(92),'/'),chr(92)+chr(39)+':'),chr(92)+chr(39)+'[],;')
            vf.append('subtitles=filename='+escaped)
        if fade_in:vf.append(f'fade=t=in:st=0:d={fade_in}')
        if fade_out:vf.append(f'fade=t=out:st={duration-fade_out}:d={fade_out}')
        graph.append('[joinedv]'+','.join(vf or ['null'])+'[outv]')
    if audio:
        joined='joineda';bed=edit.get('soundtrack')
        if bed:
            index=indices[bed['source_job_id']]
            graph.append(f"[{index}:a]atrim=start={bed.get('start',0)},asetpts=PTS-STARTPTS,aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,volume={0 if bed.get('muted') else bed.get('gain',.3)},adelay={int(bed.get('offset',0)*1000)}:all=1,apad,atrim=duration={duration}[bed]")
            graph.append('[joineda][bed]amix=inputs=2:duration=first:normalize=0:dropout_transition=0[mixed]');joined='mixed'
        af=[f"volume={edit.get('volume',1)}"]
        if fade_in:af.append(f'afade=t=in:st=0:d={fade_in}')
        if fade_out:af.append(f'afade=t=out:st={duration-fade_out}:d={fade_out}')
        # Limiter protects a combined soundtrack from digital clipping.
        af.append('alimiter=limit=0.95:level=false:latency=true')
        graph.append(f'[{joined}]'+','.join(af)+'[outa]')
    filters=Path(target).with_suffix('.filters.txt');filters.write_text(';'.join(graph),encoding='utf-8')
    executable=command[0]
    modified=Path(executable).stat().st_mtime_ns if Path(executable).is_file() else 0
    command+=['-filter_complex_threads','1',filter_script_option(executable,modified),str(filters)]
    prores=edit.get('export_format')=='prores'
    if video:
        command+=['-map','[outv]']
        command+=['-c:v','prores_ks','-profile:v','2','-pix_fmt','yuv422p10le'] if prores else ['-c:v','libx264','-preset','medium','-crf',str(edit.get('crf',18)),'-pix_fmt','yuv420p']
    if audio:
        codec='pcm_s24le' if (prores and video) or edit.get('export_format')=='wav' else 'aac' if video or edit.get('export_format')=='m4a' else 'libmp3lame'
        command+=['-map','[outa]','-c:a',codec]
        if codec!='pcm_s24le':command+=['-b:a',str(edit.get('audio_bitrate',256))+'k']
    if video:command+=['-movflags','+faststart']
    return command+['-t',str(duration),'-threads','2','-progress','pipe:1','-nostats',str(target)]


def write_text_track(path,texts,width,height,duration):
    """Render literal user text with libass (including bidirectional Arabic shaping)."""
    def clock(value):
        centiseconds=round(value*100)
        return f'{centiseconds//360000}:{centiseconds//6000%60:02}:{centiseconds//100%60:02}.{centiseconds%100:02}'
    header=f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: caption,Arial,{max(12,int(height*.045))},&H00FFFFFF,&H00FFFFFF,&H70000000,&H70000000,0,0,0,0,100,100,0,0,3,2,0,2,20,20,{max(10,int(height*.07))},1
Style: title,Arial,{max(18,int(height*.07))},&H00FFFFFF,&H00FFFFFF,&H00000000,&H70000000,-1,0,0,0,100,100,0,0,1,2,1,8,20,20,{max(10,int(height*.14))},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines=[]
    for cue in texts:
        if cue['start']>=duration:continue
        # Remove ASS override control syntax; content cannot inject filters or styles.
        text=cue['text'].replace('\\','／').replace('{','｛').replace('}','｝').replace('\r','').replace('\n',r'\N')
        lines.append(f"Dialogue: 0,{clock(cue['start'])},{clock(min(cue['end'],duration))},{cue['kind']},,0,0,0,,{text}")
    path.write_text(header+'\n'.join(lines)+'\n',encoding='utf-8')
