"""Read-only multi-source timeline rendering, normalized video and mixed audio.

3.0 adds, per clip: looks (colour presets), fades that dissolve over lower tracks, opacity, picture-in-picture
position and size, voice cleanup and noise reduction. Per sequence: a blurred-background frame fill, loudness
normalization, GPU encoding with automatic CPU fallback, H.265 output, a target file size and animated GIFs.
"""
import os
from pathlib import Path
from functools import lru_cache
import subprocess
from .downloader import _tool

AUDIO_FORMATS = ('mp3', 'm4a', 'wav')

# Looks are colour matrices plus a little contrast and brightness, so the editor preview (an SVG colour matrix
# and CSS filters) shows the same picture the export renders. Keep in step with LOOKS in frontend/src/looks.ts.
LOOKS = {
    'vivid': {'sat': 1.35, 'contrast': 1.06},
    'warm': {'gains': (1.08, 1.0, .86), 'sat': 1.06, 'brightness': .015},
    'cool': {'gains': (.9, .99, 1.1), 'sat': .96},
    'cinematic': {'gains': (1.04, 1.0, .95), 'sat': .86, 'contrast': 1.14, 'brightness': -.02, 'vignette': True},
    'punch': {'sat': 1.2, 'contrast': 1.2, 'brightness': -.01},
    'mono': {'sat': 0, 'contrast': 1.05},
    'noir': {'sat': 0, 'contrast': 1.38, 'brightness': -.04, 'vignette': True},
    'vintage': {'sepia': .6, 'sat': .92, 'contrast': .9, 'brightness': .03, 'vignette': True},
    'fade': {'sat': .82, 'contrast': .8, 'brightness': .05},
    'dream': {'gains': (1.04, .98, 1.06), 'sat': 1.1, 'contrast': .9, 'brightness': .04},
}
LUMA = (.2126, .7152, .0722)
SEPIA = ((.393, .769, .189), (.349, .686, .168), (.272, .534, .131))


def look_matrix(look):
    """3x3 RGB matrix: gains x sepia blend x saturation."""
    s = look.get('sat', 1)
    saturation = [[LUMA[c] * (1 - s) + (s if r == c else 0) for c in range(3)] for r in range(3)]
    k = look.get('sepia', 0)
    sepia = [[(1 - k) * (1 if r == c else 0) + k * SEPIA[r][c] for c in range(3)] for r in range(3)]
    mixed = [[sum(sepia[r][m] * saturation[m][c] for m in range(3)) for c in range(3)] for r in range(3)]
    gains = look.get('gains', (1, 1, 1))
    return [[gains[r] * mixed[r][c] for c in range(3)] for r in range(3)]


def look_filters(name):
    look = LOOKS.get(name or '')
    if not look:
        return []
    m = look_matrix(look)
    names = ('r', 'g', 'b')
    mixer = 'colorchannelmixer=' + ':'.join(f'{names[r]}{names[c]}={m[r][c]:.4f}' for r in range(3) for c in range(3))
    filters = [mixer]
    if look.get('contrast', 1) != 1 or look.get('brightness', 0):
        filters.append(f"eq=contrast={look.get('contrast', 1)}:brightness={look.get('brightness', 0)}")
    if look.get('vignette'):
        filters.append('vignette=angle=PI/4.5')
    return filters


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


def clip_audio_filters(part, length):
    """Cleanup and fades for one clip's sound, after speed changes (so fade times are timeline seconds)."""
    filters = []
    if part.get('denoise'):
        filters.append('afftdn=nf=-25:tn=1')
    if part.get('voice'):
        filters += ['highpass=f=85', 'equalizer=f=250:t=q:w=1:g=-2', 'equalizer=f=3200:t=q:w=1.2:g=3',
                    'acompressor=threshold=0.1:ratio=3:attack=15:release=250:makeup=2']
    fade_in, fade_out = min(part.get('fade_in', 0), length / 2), min(part.get('fade_out', 0), length / 2)
    if fade_in > 0:
        filters.append(f'afade=t=in:st=0:d={fade_in:.3f}')
    if fade_out > 0:
        filters.append(f'afade=t=out:st={length - fade_out:.3f}:d={fade_out:.3f}')
    return filters


def motion_filters(part, length, width, height):
    """Ken Burns movement over the clip's own length, on its source picture (before framing)."""
    kind = part.get('motion')
    if not kind or length <= 0 or width < 2 or height < 2:
        return []
    amount, span = part.get('motion_amount', .12), f'{length:.3f}'
    if kind in ('zoom-in', 'zoom-out'):
        progress = f't/{span}' if kind == 'zoom-in' else f'(1-t/{span})'
        return [f"scale=w='trunc(iw*(1+{amount}*min(1,{progress}))/2)*2':h=-2:eval=frame", f'crop={width}:{height}']
    travel = f'min(1,t/{span})' if kind == 'pan-right' else f'(1-min(1,t/{span}))'
    return [f"scale=w='trunc(iw*{1 + amount}/2)*2':h=-2", f"crop={width}:{height}:x='(iw-ow)*{travel}':y='(ih-oh)/2'"]


def chapters_file(path, markers, duration):
    """FFmpeg metadata with one chapter per marker (a chapter at 0:00 is added when the first marker is later)."""
    points = sorted((max(0.0, min(duration, m['t'])), m.get('label') or 'Chapter') for m in markers)
    if not points:
        return None
    if points[0][0] > .5:
        points.insert(0, (0.0, 'Start'))
    clean = lambda text: ''.join('\\' + c if c in '=;#\\\n' else c for c in text.replace('\n', ' '))
    lines = [';FFMETADATA1']
    for index, (start, label) in enumerate(points):
        end = points[index + 1][0] if index + 1 < len(points) else duration
        if end - start < .05:
            continue
        lines += ['[CHAPTER]', 'TIMEBASE=1/1000', f'START={int(start * 1000)}', f'END={int(end * 1000)}', f'title={clean(label)}']
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return path


def export_threads():
    return str(max(2, min(16, (os.cpu_count() or 4) // 2)))


def target_bitrate(target_mb, duration, audio_kbps):
    """Video bits per second that keep the whole file under `target_mb` (with a safety margin)."""
    total = target_mb * 1024 * 1024 * 8 * .93
    rate = int(total / max(.1, duration) - audio_kbps * 1000)
    if rate < 80_000:
        raise ValueError('The target size is too small for this length. Shorten the timeline or choose a larger size.')
    return rate


def build_edit_command(source,target,edit,metadata):
    from .converter import probe_media
    default=edit.get('_default_source','default')
    sources=edit.get('_sources') or {default:{'path':str(source),'metadata':metadata}}
    # Re-probe at export time so moved/changed files fail cleanly before encoding.
    sources={k:{'path':v['path'],'metadata':probe_media(v['path'])} for k,v in sources.items()}
    segments=edit['segments'];ids=[s.get('source_job_id') or default for s in segments]
    if not segments:raise ValueError('Add a clip to the timeline before exporting.')
    export_format=edit.get('export_format','mp4');gif=export_format=='gif'
    video=export_format not in AUDIO_FORMATS and any(sources[k]['metadata']['video_codec'] for k in ids)
    if gif and not video:raise ValueError('An animated GIF needs at least one video clip.')
    tracks=edit.get('tracks') or []
    def track(part):
        lane=part.get('track',0)
        return tracks[lane] if lane<len(tracks) else {}
    visible=lambda i:not track(segments[i]).get('hidden',False)
    audio=not gif and (any(sources[k]['metadata']['audio_codec'] for k in ids) or bool(edit.get('soundtrack')))
    if not video and not audio:raise ValueError('No media stream.')
    first=next((sources[k]['metadata'] for k in ids if sources[k]['metadata']['video_codec']),metadata)
    width,height=first['width'],first['height'];rotation=edit.get('rotate',0)
    if rotation in (90,270):width,height=height,width
    ratio=edit.get('ratio','original');fit=edit.get('fit','crop')
    if ratio!='original':
        rw,rh=map(float,ratio.split(':'));width=min(width,height*rw/rh);height=min(height,width*rh/rw)
    requested=edit.get('height',0)
    if gif:
        # GIFs grow fast with size: keep the long side at most 640 pixels unless a smaller height was chosen.
        limit=min(requested or 640,640)/max(width,height)
        if limit<1:width,height=width*limit,height*limit
        requested=0
    if video:
        if requested:width=width/height*requested;height=requested
        width=max(2,int(width)//2*2);height=max(2,int(height)//2*2)
    fps=min(edit.get('fps',30),15) if gif else edit.get('fps',30);graph=[];labels=[];command=[_tool('ffmpeg'),'-nostdin','-y','-v','error']
    indices={k:i for i,k in enumerate(sources)}
    for entry in sources.values():command+=['-i',str(entry['path'])]
    for key,index in indices.items():
        uses=[i for i,k in enumerate(ids) if k==key];info=sources[key]['metadata']
        video_uses=[i for i in uses if visible(i)]
        if video_uses and info['video_codec'] and video:graph.append(f'[{index}:v]split={len(video_uses)}'+''.join(f'[vin{i}]' for i in video_uses))
        if uses and info['audio_codec'] and audio:graph.append(f'[{index}:a]asplit={len(uses)}'+''.join(f'[ain{i}]' for i in uses))
    duration=0;offsets=[];cursor=0;positions={}
    for i,part in enumerate(segments):
        a,b,speed=part['start'],part['end'],part['speed'];info=sources[ids[i]]['metadata']
        if a<0 or b<=a or b>info['duration']+.05:raise ValueError('A segment is outside its source duration.')
        length=(b-a)/speed;offset=part.get("offset",cursor);cursor=offset+length;offsets.append(offset);duration=max(duration,cursor)
        effects=[]
        if rotation==90:effects.append('transpose=1')
        elif rotation==180:effects+=['hflip','vflip']
        elif rotation==270:effects.append('transpose=2')
        if edit.get('flip'):effects.append('hflip')
        effects+=look_filters(part.get('look'))
        effects.append(f"eq=brightness={edit.get('brightness',0)}:contrast={edit.get('contrast',1)}:saturation={edit.get('saturation',1)}")
        # After framing: size and position (picture-in-picture), opacity and fades that reveal the tracks below.
        scale=part.get('scale',1);cx=part.get('x',.5);cy=part.get('y',.5);opacity=part.get('opacity',1)
        fade_in=min(part.get('fade_in',0),length/2);fade_out=min(part.get('fade_out',0),length/2)
        tail=['setsar=1',f'fps={fps}']
        if opacity<1 or fade_in>0 or fade_out>0:
            tail.append('format=yuva420p')
            if opacity<1:tail.append(f'colorchannelmixer=aa={opacity}')
            if fade_in>0:tail.append(f'fade=t=in:st=0:d={fade_in:.3f}:alpha=1')
            if fade_out>0:tail.append(f'fade=t=out:st={length-fade_out:.3f}:d={fade_out:.3f}:alpha=1')
        else:tail.append('format=yuv420p')
        if scale<1 or cx!=.5 or cy!=.5:positions[i]=(cx,cy)
        if video and info['video_codec'] and visible(i):
            sw,sh=(info['height'],info['width']) if rotation in (90,270) else (info['width'],info['height'])
            head=f'[vin{i}]trim=start={a}:end={b},setpts=(PTS-STARTPTS)/{speed},'+','.join(effects+motion_filters(part,length,sw//2*2,sh//2*2))
            if scale<1:
                # Picture-in-picture keeps the clip's own shape, sized to fit its share of the frame.
                box=f'{max(2,int(width*scale)//2*2)}:{max(2,int(height*scale)//2*2)}'
                graph.append(head+f',scale={box}:force_original_aspect_ratio=decrease:force_divisible_by=2,'+','.join(tail)+f'[v{i}]')
            elif fit=='blur':
                # The clip fits inside the frame over a soft, darkened, enlarged copy of itself.
                small=f'{max(2,width//4//2*2)}:{max(2,height//4//2*2)}'
                graph.append(head+f',split[fg{i}][bs{i}]')
                graph.append(f'[bs{i}]scale={small}:force_original_aspect_ratio=increase,crop={small},gblur=sigma=6,eq=brightness=-0.07:saturation=0.85,scale={width}:{height}[bg{i}]')
                graph.append(f'[fg{i}]scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2[ff{i}]')
                graph.append(f'[bg{i}][ff{i}]overlay=(W-w)/2:(H-h)/2,'+','.join(tail)+f'[v{i}]')
            else:
                frame=[]
                if ratio!='original' and fit=='crop':
                    rw,rh=map(float,ratio.split(':'));r=rw/rh
                    fx,fy=part.get('focus_x',.5),part.get('focus_y',.5)
                    frame.append(f"crop=w='trunc(min(iw,ih*{r})/2)*2':h='trunc(min(ih,iw/{r})/2)*2'"+(f":x='(iw-ow)*{fx}':y='(ih-oh)*{fy}'" if (fx,fy)!=(.5,.5) else ''))
                frame+=[f'scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2',f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2']
                graph.append(head+','+','.join(frame+tail)+f'[v{i}]')

        if audio:
            if info['audio_codec']:graph.append(f'[ain{i}]atrim=start={a}:end={b},asetpts=PTS-STARTPTS,'+','.join(tempo(speed))+f",volume={0 if track(part).get('muted') else part.get('gain',1)},"+''.join(f+',' for f in clip_audio_filters(part,length))+f"aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,apad,atrim=duration={length}[a{i}]")
            else:graph.append(f'anullsrc=r=48000:cl=stereo,atrim=duration={length}[a{i}]')
        if video:labels.append(f'[v{i}]')
        if audio:labels.append(f'[a{i}]')
    # Higher tracks cover lower tracks (later clips cover earlier ones on a track); every clip's audio is mixed.
    if video:
        graph.append(f'color=c=black:s={width}x{height}:r={fps}:d={duration},setsar=1[canvas0]')
        order=sorted([i for i in range(len(segments)) if visible(i) and sources[ids[i]]['metadata']['video_codec']],key=lambda i:(segments[i].get('track',0),i))
        if not order:graph.append('[canvas0]null[joinedv]')
        for layer,i in enumerate(order):
            offset=offsets[i];length=(segments[i]['end']-segments[i]['start'])/segments[i]['speed']
            graph.append(f'[v{i}]setpts=PTS+{offset}/TB[placed{i}]')
            label='joinedv' if layer==len(order)-1 else f'canvas{layer+1}'
            place=f"x='{positions[i][0]}*W-w/2':y='{positions[i][1]}*H-h/2':" if i in positions else ''
            graph.append(f"[canvas{layer}][placed{i}]overlay={place}eof_action=pass:repeatlast=0:enable='gte(t,{offset})*lt(t,{offset+length})'[{label}]")
    if audio:
        graph.append(f'anullsrc=r=48000:cl=stereo,atrim=duration={duration}[silence]')
        for i,offset in enumerate(offsets):graph.append(f'[a{i}]adelay={round(offset*1000)}:all=1[placed_a{i}]')
        graph.append('[silence]'+''.join(f'[placed_a{i}]' for i in range(len(segments)))+f'amix=inputs={len(segments)+1}:duration=first:normalize=0:dropout_transition=0[joineda]')
    fade_in=min(edit.get('fadeIn',0),duration/2);fade_out=min(edit.get('fadeOut',0),duration/2)
    if video:
        vf=[]
        if edit.get('texts'):
            captions=Path(target).with_suffix('.captions.ass');write_text_track(captions,edit['texts'],width,height,duration,edit.get('caption_style','classic'))
            def escape(value,special):return ''.join(chr(92)+c if c in special else c for c in value)
            # FFmpeg parses option values and then the enclosing filter graph.
            escaped=escape(escape(str(captions.resolve()).replace(chr(92),'/'),chr(92)+chr(39)+':'),chr(92)+chr(39)+'[],;')
            vf.append('subtitles=filename='+escaped)
        if fade_in:vf.append(f'fade=t=in:st=0:d={fade_in}')
        if fade_out:vf.append(f'fade=t=out:st={duration-fade_out}:d={fade_out}')
        if gif:
            graph.append('[joinedv]'+','.join(vf+['split'])+'[gifa][gifb]')
            graph.append('[gifa]palettegen=max_colors=192:stats_mode=diff[palette]')
            graph.append('[gifb][palette]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle[outv]')
        else:graph.append('[joinedv]'+','.join(vf or ['null'])+'[outv]')
    if audio:
        joined='joineda';bed=edit.get('soundtrack')
        if bed:
            index=indices[bed['source_job_id']]
            graph.append(f"[{index}:a]atrim=start={bed.get('start',0)},asetpts=PTS-STARTPTS,aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,volume={0 if bed.get('muted') else bed.get('gain',.3)},adelay={int(bed.get('offset',0)*1000)}:all=1,apad,atrim=duration={duration}[bed]")
            if edit.get('duck'):
                # The music dips whenever the clips speak (sidechain compression keyed by the clips' own sound).
                graph.append('[joineda]asplit=2[voice][key]')
                graph.append('[bed][key]sidechaincompress=threshold=0.025:ratio=9:attack=25:release=550:makeup=1[ducked]')
                graph.append('[voice][ducked]amix=inputs=2:duration=first:normalize=0:dropout_transition=0[mixed]')
            else:graph.append('[joineda][bed]amix=inputs=2:duration=first:normalize=0:dropout_transition=0[mixed]')
            joined='mixed'
        af=[f"volume={edit.get('volume',1)}"]
        if fade_in:af.append(f'afade=t=in:st=0:d={fade_in}')
        if fade_out:af.append(f'afade=t=out:st={duration-fade_out}:d={fade_out}')
        if edit.get('loudness'):
            # EBU R128 loudness to the platform target (-14 LUFS streaming, -16 podcasts, -23 broadcast).
            af+=[f"loudnorm=I={edit['loudness']}:TP=-1.5:LRA=11",'aresample=48000']
        # Limiter protects a combined soundtrack from digital clipping.
        af.append('alimiter=limit=0.95:level=false:latency=true')
        graph.append(f'[{joined}]'+','.join(af)+'[outa]')
    filters=Path(target).with_suffix('.filters.txt');filters.write_text(';'.join(graph),encoding='utf-8')
    executable=command[0]
    modified=Path(executable).stat().st_mtime_ns if Path(executable).is_file() else 0
    threads=export_threads()
    command+=['-filter_complex_threads',threads,filter_script_option(executable,modified),str(filters)]
    chapter_input=None
    if edit.get('markers') and export_format in ('mp4','prores','m4a'):
        if chapters_file(Path(target).with_suffix('.chapters.txt'),edit['markers'],duration):
            command+=['-f','ffmetadata','-i',str(Path(target).with_suffix('.chapters.txt'))];chapter_input=len(sources)
    prores=export_format=='prores'
    if video:
        command+=['-map','[outv]']
        if prores:command+=['-c:v','prores_ks','-profile:v','2','-pix_fmt','yuv422p10le']
        elif gif:command+=['-c:v','gif','-loop','0']
        else:
            from . import hardware
            family='hevc' if edit.get('codec')=='hevc' else 'h264'
            encoder=hardware.SOFTWARE[family] if edit.get('encoder')=='cpu' else hardware.choose(family)
            audio_kbps=edit.get('audio_bitrate',256) if audio else 0
            bitrate=target_bitrate(edit['target_mb'],duration,audio_kbps) if edit.get('target_mb') else None
            command+=hardware.video_flags(encoder,edit.get('crf',18),edit.get('speed','balanced'),bitrate=bitrate)
            if family=='hevc':command+=['-tag:v','hvc1']
    if audio:
        codec='pcm_s24le' if (prores and video) or export_format=='wav' else 'aac' if video or export_format=='m4a' else 'libmp3lame'
        command+=['-map','[outa]','-c:a',codec]
        if codec!='pcm_s24le':command+=['-b:a',str(edit.get('audio_bitrate',256))+'k']
    if chapter_input is not None:command+=['-map_chapters',str(chapter_input)]
    if video and not gif:command+=['-movflags','+faststart']
    return command+['-t',str(duration),'-threads',threads,'-progress','pipe:1','-nostats',str(target)]


CAPTION_STYLES = {
    # name: (font size as a share of height, primary, outline, back colour, border style, outline width, bold, margin share)
    'classic': (.045, '&H00FFFFFF', '&H70000000', '&H70000000', 3, 2, 0, .07),
    'bold': (.06, '&H00FFFFFF', '&H00000000', '&H00000000', 1, 4, -1, .12),
    'highlight': (.055, '&H0000E8FF', '&H00000000', '&H00000000', 1, 4, -1, .12),
    'boxed': (.045, '&H00FFFFFF', '&H00000000', '&HC0000000', 3, 8, 0, .08),
    # Karaoke: words fill from white to yellow as they are said. Pop: the word being said grows and turns yellow.
    'karaoke': (.058, '&H0000E8FF', '&H00000000', '&H00000000', 1, 4, -1, .12),
    'pop': (.064, '&H00FFFFFF', '&H00000000', '&H00000000', 1, 5, -1, .14),
}
TITLE_PLACES = {'top': (8, .5, .14), 'center': (5, .5, .5), 'bottom': (2, .5, .86), 'lower': (1, .06, .84)}


def _ass_escape(text):
    # Remove ASS override control syntax; content cannot inject filters or styles.
    return text.replace('\\', '／').replace('{', '｛').replace('}', '｝').replace('\r', '').replace('\n', r'\N')


def word_times(cue):
    """Start time of each word: real timings when the cue carries them, else shared out by word length."""
    words = cue['text'].split()
    times = cue.get('words')
    if times and len(times) == len(words) and all(cue['start'] - .01 <= t <= cue['end'] + .01 for t in times):
        return words, [max(cue['start'], min(cue['end'], t)) for t in times]
    total = sum(len(w) + 1 for w in words) or 1
    span, moment, result = cue['end'] - cue['start'], cue['start'], []
    for word in words:
        result.append(moment)
        moment += span * (len(word) + 1) / total
    return words, result


def _title_text(cue, width, height):
    animation, place = cue.get('animation') or 'none', cue.get('position') or 'top'
    align, fx, fy = TITLE_PLACES.get(place, TITLE_PLACES['top'])
    x, y = int(width * fx), int(height * fy)
    body = _ass_escape(cue['text'])
    if animation == 'slide':
        start = (x - int(width * .08), y) if place == 'lower' else (x, y + int(height * .04))
        tags = f'\\an{align}\\move({start[0]},{start[1]},{x},{y},0,450)\\fad(200,250)'
    elif animation == 'pop':
        tags = f'\\an{align}\\pos({x},{y})\\fad(90,200)\\fscx30\\fscy30\\t(0,220,\\fscx112\\fscy112)\\t(220,340,\\fscx100\\fscy100)'
    elif animation == 'fade':
        tags = f'\\an{align}\\pos({x},{y})\\fad(350,350)'
    elif animation == 'typewriter':
        characters = list(cue['text'])[:160]
        step = min(60, int(1400 / max(1, len(characters))))
        body = ''.join(_ass_escape(c) if c.isspace() else f'{{\\alpha&HFF&\\t({n * step},{n * step + 1},\\alpha&H00&)}}{_ass_escape(c)}'
                       for n, c in enumerate(characters)) + _ass_escape(cue['text'][160:])
        tags = f'\\an{align}\\pos({x},{y})'
    else:
        tags = f'\\an{align}\\pos({x},{y})'
    return '{' + tags + '}' + body


def write_text_track(path,texts,width,height,duration,style='classic'):
    """Render literal user text with libass (including bidirectional Arabic shaping)."""
    def clock(value):
        centiseconds=round(value*100)
        return f'{centiseconds//360000}:{centiseconds//6000%60:02}:{centiseconds//100%60:02}.{centiseconds%100:02}'
    size,primary,outline,back,border,outline_width,bold,margin=CAPTION_STYLES.get(style,CAPTION_STYLES['classic'])
    secondary='&H00FFFFFF'
    short=min(width,height)
    header=f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: caption,Arial,{max(12,int(short*size*16/9 if height>width else height*size))},{primary},{secondary},{outline},{back},{bold},0,0,0,100,100,0,0,{border},{outline_width if style!='classic' else 2},0,2,{max(20,int(width*.06))},{max(20,int(width*.06))},{max(10,int(height*margin))},1
Style: title,Arial,{max(18,int(height*.07))},&H00FFFFFF,&H00FFFFFF,&H00000000,&H70000000,-1,0,0,0,100,100,0,0,1,2,1,8,20,20,{max(10,int(height*.14))},1
Style: lower,Arial,{max(14,int(short*.05))},&H00FFFFFF,&H00FFFFFF,&H00000000,&H30E07A1F,-1,0,0,0,100,100,0,0,3,{max(6,int(short*.016))},0,1,20,20,20,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines=[]
    for cue in texts:
        if cue['start']>=duration:continue
        end=min(cue['end'],duration)
        if cue['kind']=='title':
            name='lower' if cue.get('position')=='lower' else 'title'
            lines.append(f"Dialogue: 0,{clock(cue['start'])},{clock(end)},{name},,0,0,0,,{_title_text(cue,width,height)}")
            continue
        if style=='karaoke':
            words,times=word_times(cue);parts=[]
            lead=times[0]-cue['start'] if times else 0
            if lead>.01:parts.append(f'{{\\k{round(lead*100)}}}')
            for n,word in enumerate(words):
                stop=times[n+1] if n+1<len(times) else cue['end']
                parts.append(f'{{\\kf{max(1,round((stop-times[n])*100))}}}{_ass_escape(word)}'+(' ' if n+1<len(words) else ''))
            lines.append(f"Dialogue: 0,{clock(cue['start'])},{clock(end)},caption,,0,0,0,,{''.join(parts)}")
        elif style=='pop':
            words,times=word_times(cue)
            for n in range(len(words)):
                begin=cue['start'] if n==0 else times[n];stop=times[n+1] if n+1<len(times) else cue['end']
                if stop<=begin or begin>=duration:continue
                shown=' '.join('{\\c&H00E8FF&\\fscx116\\fscy116}'+_ass_escape(w)+'{\\r}' if k==n else _ass_escape(w) for k,w in enumerate(words))
                lines.append(f"Dialogue: 0,{clock(begin)},{clock(min(stop,duration))},caption,,0,0,0,,{shown}")
        else:
            lines.append(f"Dialogue: 0,{clock(cue['start'])},{clock(end)},{cue['kind']},,0,0,0,,{_ass_escape(cue['text'])}")
    path.write_text(header+'\n'.join(lines)+'\n',encoding='utf-8')
