"""Clip Studio 3.0: projects without a source clip, smart tools, transcripts and the new export engine.

Render tests make real files with FFmpeg and read pixels and loudness back, so every effect is checked by what
it actually produces, not by the command text.
"""
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from fastapi.testclient import TestClient

import app.main as main
from app import analysis, hardware, studio, transcripts
from app.converter import probe_media, run_conversion
from app.editor import LOOKS, build_edit_command, look_matrix, target_bitrate, write_text_track
from app.jobs import jobs

client = TestClient(main.app)
NL = chr(10)


def ffmpeg(*args):
    result = subprocess.run(['ffmpeg', '-v', 'error', '-y', *map(str, args)], capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stderr
    return result


def pixel(path, at, x, y):
    """RGB of one pixel (x, y as fractions of the frame) at `at` seconds."""
    info = probe_media(path)
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(at), '-i', str(path), '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1'],
                         capture_output=True, timeout=30).stdout
    width, height = info['width'], info['height']
    offset = (int(y * (height - 1)) * width + int(x * (width - 1))) * 3
    return tuple(raw[offset:offset + 3])


def render(tmp_path, edit, name='out.mp4', sources=None):
    first = next(iter(sources.values()))['path']
    edit = {'_sources': sources, '_default_source': next(iter(sources)), 'encoder': 'cpu', **edit}
    target = tmp_path / name
    result = subprocess.run(build_edit_command(first, target, edit, probe_media(first)), capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    return target


@pytest.fixture(scope='module')
def clips(tmp_path_factory):
    folder = tmp_path_factory.mktemp('studio-media')
    blue = folder / 'blue.mp4'
    ffmpeg('-f', 'lavfi', '-i', 'color=0x1030e0:size=320x180:rate=25', '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000',
           '-t', '3', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', blue)
    red = folder / 'red.mp4'
    ffmpeg('-f', 'lavfi', '-i', 'color=0xe01010:size=320x180:rate=25', '-f', 'lavfi', '-i', 'sine=frequency=660:sample_rate=48000',
           '-t', '3', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', red)
    talk = folder / 'talk.wav'                    # tone, 1.5 s of silence, tone
    ffmpeg('-f', 'lavfi', '-i', 'sine=frequency=300:sample_rate=48000:duration=1', '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=mono:d=1.5',
           '-f', 'lavfi', '-i', 'sine=frequency=300:sample_rate=48000:duration=1', '-filter_complex', '[0][1][2]concat=n=3:v=0:a=1', talk)
    shots = folder / 'shots.mp4'                  # a hard cut from blue to red at 1.5 s
    ffmpeg('-f', 'lavfi', '-i', 'color=blue:size=320x180:rate=25:d=1.5', '-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=25:d=1.5',
           '-filter_complex', '[0][1]concat=n=2:v=1', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', shots)
    return {'blue': blue, 'red': red, 'talk': talk, 'shots': shots}


def sources_for(clips, *names):
    return {name: {'path': str(clips[name]), 'metadata': probe_media(clips[name])} for name in names}


# ---------------------------------------------------------------- transcripts
# YouTube's own files put a line holding one space inside each cue; <SP> keeps that space visible here.
ROLLING = """WEBVTT
Kind: captions
Language: en

00:00:00.320 --> 00:00:02.869 align:start position:0%
<SP>
hello<00:00:00.640><c> everyone</c><00:00:01.120><c> and</c><00:00:01.360><c> welcome</c>

00:00:02.869 --> 00:00:02.879 align:start position:0%
hello everyone and welcome
<SP>

00:00:02.879 --> 00:00:05.150 align:start position:0%
hello everyone and welcome
to<00:00:03.120><c> the</c><00:00:03.360><c> show</c>
""".replace('<SP>', ' ')


def test_rolling_auto_captions_become_clean_sentences():
    expected = [{'start': .32, 'end': 2.869, 'text': 'hello everyone and welcome'}, {'start': 2.879, 'end': 5.15, 'text': 'to the show'}]
    plain = lambda text: [{k: v for k, v in s.items() if k != 'words'} for s in transcripts.parse(text)]
    assert plain(ROLLING) == expected
    assert plain(ROLLING.replace(NL + ' ' + NL, NL + NL)) == expected      # also when an editor stripped the spaces


def test_srt_with_sloppy_separators_and_markup():
    text = '﻿1\r\n00:00:01,000 --> 00:00:03,500\r\n<i>First</i> line\r\n \r\n2\r\n00:00:04,000 --> 00:00:06,000\r\nSecond &amp; last\r\n'
    segments = transcripts.parse(text)
    assert segments == [{'start': 1.0, 'end': 3.5, 'text': 'First line'}, {'start': 4.0, 'end': 6.0, 'text': 'Second & last'}]
    assert transcripts.parse(transcripts.to_srt(segments)) == segments
    assert transcripts.parse('not a subtitle file') == []


def test_transcripts_are_stored_searched_and_exported(clips):
    job = jobs.create(url='https://example.com/watch?v=1', kind='video', container='mp4', quality='best', directory=str(clips['blue'].parent),
                      status='completed', filename=str(clips['blue']), title='Blue talk')
    assert client.get(f'/api/studio/transcript/{job.id}').json() == {'segments': [], 'source': None, 'language': '', 'can_fetch': True}
    srt = '1\n00:00:00,500 --> 00:00:01,500\nThe quick brown fox\n\n2\n00:00:02,000 --> 00:00:02,800\nجملة عربية\n'
    view = client.post(f'/api/studio/transcript/{job.id}/import', json={'text': srt}).json()
    assert [s['text'] for s in view['segments']] == ['The quick brown fox', 'جملة عربية'] and view['source'] == 'import'
    found = client.get('/api/studio/transcripts/search', params={'q': 'fox quick'}).json()['results']
    assert found and found[0]['job_id'] == job.id and found[0]['start'] == .5 and found[0]['title'] == 'Blue talk'
    assert client.get('/api/studio/transcripts/search', params={'q': 'عربية'}).json()['results'][0]['text'] == 'جملة عربية'
    exported = client.get(f'/api/studio/transcript/{job.id}/export', params={'format': 'txt'})
    assert exported.text == 'The quick brown fox\nجملة عربية' and 'attachment' in exported.headers['content-disposition']
    assert client.post(f'/api/studio/transcript/{job.id}/import', json={'text': 'nothing timed'}).status_code == 422
    assert client.post(f'/api/studio/transcript/{job.id}/remove').json()['segments'] == []


def test_subtitles_saved_next_to_a_download_are_found(tmp_path, clips):
    media = tmp_path / 'Talk [abc].mp4'
    media.write_bytes(clips['blue'].read_bytes())
    (tmp_path / 'Talk [abc].en.vtt').write_text(ROLLING, encoding='utf-8')
    job = jobs.create(url='local://x', kind='video', container='mp4', quality='best', directory=str(tmp_path), status='completed', filename=str(media))
    view = client.get(f'/api/studio/transcript/{job.id}').json()
    assert view['source'] == 'file' and view['language'] == 'en' and len(view['segments']) == 2 and view['can_fetch'] is False
    assert client.post(f'/api/studio/transcript/{job.id}/fetch').status_code == 422     # a local file has no online captions


def test_caption_tracks_are_chosen_in_the_spoken_language():
    calls = []

    class FakeYDL:
        def __init__(self, options): calls.append(options)
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def extract_info(self, url, download):
            assert download is False
            return {'language': 'ar', 'subtitles': {'live_chat': [{'ext': 'json', 'url': 'x'}]},
                    'automatic_captions': {'en': [{'ext': 'vtt', 'url': 'https://c/en'}], 'ar-orig': [{'ext': 'json3', 'url': 'https://c/j'}, {'ext': 'vtt', 'url': 'https://c/ar'}]}}
        def urlopen(self, url):
            assert url == 'https://c/ar'
            return type('R', (), {'read': lambda self: '1\n00:00:01,000 --> 00:00:02,000\nمرحبا\n'.encode()})()
    with patch('yt_dlp.YoutubeDL', FakeYDL):
        segments, language, kind = transcripts.fetch_captions('https://www.youtube.com/watch?v=x')
    assert segments[0]['text'] == 'مرحبا' and language == 'ar' and kind == 'auto'
    assert calls[0]['skip_download'] is True


# ---------------------------------------------------------------- smart analysis
def test_silences_are_found_and_turned_into_kept_ranges(clips):
    quiet = analysis.silences(clips['talk'], -40, .5, 3.5)
    assert len(quiet) == 1 and quiet[0][0] == pytest.approx(1.0, abs=.05) and quiet[0][1] == pytest.approx(2.5, abs=.05)
    keep = analysis.keep_ranges(quiet, 0, 3.5, padding=.1)
    assert [[round(a, 1), round(b, 1)] for a, b in keep] == [[0, 1.1], [2.4, 3.5]]
    assert analysis.keep_ranges([[0, 1], [1.05, 2]], 0, 3, padding=0, minimum_keep=.2) == [[2, 3]]      # a blip is dropped
    assert analysis.keep_ranges([], 1, 2) == [[1, 2]]


def test_scene_cuts_are_detected(clips):
    cuts = analysis.scenes(clips['shots'], .3)
    assert len(cuts) == 1 and cuts[0] == pytest.approx(1.5, abs=.05)


def test_smart_tool_routes(clips):
    talk = jobs.create(url='local://t', kind='audio', container='wav', quality='best', directory=str(clips['talk'].parent), status='completed', filename=str(clips['talk']))
    result = client.post('/api/studio/analyze/silence', json={'source_job_id': talk.id, 'start': .5, 'end': 3.5, 'threshold': -40, 'minimum': .5, 'padding': .1}).json()
    assert result['removed'] == pytest.approx(1.3, abs=.08) and result['keep'][0][0] == .5
    shots = jobs.create(url='local://s', kind='video', container='mp4', quality='best', directory=str(clips['shots'].parent), status='completed', filename=str(clips['shots']))
    assert client.post('/api/studio/analyze/scenes', json={'source_job_id': shots.id, 'end': 3}).json()['cuts'] == [pytest.approx(1.5, abs=.05)]
    assert client.post('/api/studio/analyze/scenes', json={'source_job_id': talk.id, 'end': 3}).status_code == 422          # no picture
    assert client.post('/api/studio/analyze/silence', json={'source_job_id': 'missing', 'end': 3}).status_code == 409
    level = client.post('/api/studio/analyze/loudness', json={'source_job_id': talk.id, 'end': 3.5}).json()
    assert -40 < level['integrated'] < 0


# ---------------------------------------------------------------- projects without a source clip
def test_an_empty_project_is_created_saved_and_listed(clips):
    created = client.post('/api/studio/projects', json={'aspect': '9:16'})
    assert created.status_code == 201
    record = created.json()
    assert record['name'].startswith('Untitled project') and record['clips'] == 0 and record['aspect'] == '9:16'
    opened = client.get(f"/api/studio/projects/{record['id']}").json()
    assert opened['project']['segments'] == [] and opened['project']['ratio'] == '9:16' and opened['missing'] == []
    blue = jobs.create(url='local://b', kind='video', container='mp4', quality='best', directory=str(clips['blue'].parent), status='completed', filename=str(clips['blue']), title='Blue')
    project = {**opened['project'], 'segments': [{'source_job_id': blue.id, 'start': .5, 'end': 2.5, 'speed': 1, 'offset': 0, 'track': 0, 'look': 'warm'}]}
    assert client.put(f"/api/editor/projects/{record['id']}", json={'project': project}).status_code == 200
    card = next(p for p in client.get('/api/studio/projects').json()['projects'] if p['id'] == record['id'])
    assert card['clips'] == 1 and card['duration'] == 2 and card['media'][blue.id]['path'] == str(clips['blue']) and card['missing'] == 0
    assert client.get(f"/api/studio/projects/{record['id']}/poster").headers['content-type'] == 'image/jpeg'
    renamed = client.post(f"/api/studio/projects/{record['id']}/rename", json={'name': '  My   vertical\u0007 cut  '}).json()
    assert renamed['name'] == 'My vertical cut'
    assert client.post(f"/api/studio/projects/{record['id']}/rename", json={'name': '   '}).status_code == 422
    copy = client.post(f"/api/studio/projects/{record['id']}/duplicate").json()
    assert copy['name'] == 'My vertical cut (copy)' and client.get(f"/api/studio/projects/{copy['id']}").json()['project']['segments'][0]['look'] == 'warm'
    assert client.post(f"/api/studio/projects/{copy['id']}/remove").json() == {'ok': True}
    assert client.get(f"/api/studio/projects/{copy['id']}").status_code == 404


def test_a_project_can_start_from_files_and_relinks_cleared_tasks(clips):
    blue = jobs.create(url='local://b', kind='video', container='mp4', quality='best', directory=str(clips['blue'].parent), status='completed', filename=str(clips['blue']), title='Blue')
    red = jobs.create(url='local://r', kind='video', container='mp4', quality='best', directory=str(clips['red'].parent), status='completed', filename=str(clips['red']), title='Red')
    record = client.post('/api/studio/projects', json={'media': [blue.id, red.id]}).json()
    assert record['name'] == 'Blue' and record['clips'] == 2 and record['duration'] == pytest.approx(6, abs=.1)
    segments = client.get(f"/api/studio/projects/{record['id']}").json()['project']['segments']
    assert [s['offset'] for s in segments] == [0, pytest.approx(3, abs=.05)]
    jobs.remove_selected([red.id])
    reopened = client.get(f"/api/studio/projects/{record['id']}").json()
    assert reopened['relinked'] == 1 and reopened['missing'] == []
    replacement = reopened['project']['segments'][1]['source_job_id']
    assert replacement != red.id and jobs.get(replacement).filename == str(clips['red'])
    assert client.post('/api/studio/projects', json={'media': ['nope']}).status_code == 409


def test_project_routes_refuse_unknown_and_malformed_ids():
    for identity in ('p' + '0' * 20, '../../x', 'pXYZ'):
        assert client.get(f'/api/studio/projects/{identity}').status_code == 404
    assert client.put('/api/editor/projects/p' + '1' * 20, json={'project': {'segments': [], 'ratio': 'original', 'rotate': 0, 'flip': False,
                      'brightness': 0, 'contrast': 1, 'saturation': 1, 'volume': 1, 'fadeIn': 0, 'fadeOut': 0}}).status_code == 404


def test_export_rules_for_projects(clips):
    blue = jobs.create(url='local://b', kind='video', container='mp4', quality='best', directory=str(clips['blue'].parent), status='completed', filename=str(clips['blue']))
    base = {'ratio': 'original', 'rotate': 0, 'flip': False, 'brightness': 0, 'contrast': 1, 'saturation': 1, 'volume': 1, 'fadeIn': 0, 'fadeOut': 0}
    assert client.post('/api/editor/export', json={'source_job_id': blue.id, 'project': {**base, 'segments': []}}).status_code == 422
    clip = {'source_job_id': blue.id, 'start': 0, 'end': 1, 'speed': 1}
    for bad in ({'segments': [{**clip, 'look': 'neon'}]}, {'segments': [{**clip, 'scale': 2}]}, {'segments': [clip], 'loudness': -5},
                {'segments': [clip], 'fit': 'stretch'}, {'segments': [clip], 'encoder': 'nvenc'}, {'segments': [clip], 'target_mb': .2}):
        assert client.post('/api/editor/export', json={'source_job_id': blue.id, 'project': {**base, **bad}}).status_code == 422, bad
    record = client.post('/api/studio/projects', json={'name': 'Night/Drive: "final"'}).json()
    with patch.object(main.editor, 'submit'):
        started = client.post('/api/editor/export', json={'source_job_id': blue.id, 'project_id': record['id'],
                                                           'project': {**base, 'segments': [clip], 'export_format': 'gif', 'ratio': '4:5'}})
    assert started.status_code == 202 and started.json()['container'] == 'gif' and started.json()['title'] == 'Night/Drive: "final"'
    client.post(f"/api/jobs/{started.json()['id']}/cancel")


# ---------------------------------------------------------------- the export engine
def test_picture_in_picture_sits_where_it_was_placed(tmp_path, clips):
    out = render(tmp_path, {'segments': [{'source_job_id': 'blue', 'start': 0, 'end': 2, 'speed': 1, 'offset': 0, 'track': 0},
                                         {'source_job_id': 'red', 'start': 0, 'end': 2, 'speed': 1, 'offset': 0, 'track': 1, 'scale': .4, 'x': .75, 'y': .25}]},
                 sources=sources_for(clips, 'blue', 'red'))
    r, g, b = pixel(out, 1, .75, .25)
    assert r > 150 and b < 90                                             # the small red picture, top right
    r, g, b = pixel(out, 1, .2, .8)
    assert b > 150 and r < 90                                             # the blue clip below it everywhere else


def test_fades_dissolve_over_the_track_below_and_from_black_on_the_first_track(tmp_path, clips):
    out = render(tmp_path, {'segments': [{'source_job_id': 'blue', 'start': 0, 'end': 3, 'speed': 1, 'offset': 0, 'track': 0, 'fade_in': 1},
                                         {'source_job_id': 'red', 'start': 0, 'end': 2, 'speed': 1, 'offset': 1, 'track': 1, 'fade_in': 1}]},
                 sources=sources_for(clips, 'blue', 'red'))
    assert max(pixel(out, .04, .5, .5)) < 40                               # fades in from black
    r, g, b = pixel(out, 1.5, .5, .5)
    assert 60 < r < 200 and 60 < b < 200                                  # halfway through the dissolve: both colours
    r, g, b = pixel(out, 2.6, .5, .5)
    assert r > 180 and b < 60                                             # the red clip fully covers


def test_opacity_and_looks_change_the_picture(tmp_path, clips):
    plain = render(tmp_path, {'segments': [{'source_job_id': 'blue', 'start': 0, 'end': 1, 'speed': 1}]}, 'plain.mp4', sources_for(clips, 'blue'))
    mono = render(tmp_path, {'segments': [{'source_job_id': 'blue', 'start': 0, 'end': 1, 'speed': 1, 'look': 'mono'}]}, 'mono.mp4', sources_for(clips, 'blue'))
    r, g, b = pixel(mono, .5, .5, .5)
    assert max(r, g, b) - min(r, g, b) < 12                                # black and white
    assert pixel(plain, .5, .5, .5)[2] > 180
    faint = render(tmp_path, {'segments': [{'source_job_id': 'blue', 'start': 0, 'end': 1, 'speed': 1, 'opacity': .5}]}, 'faint.mp4', sources_for(clips, 'blue'))
    assert 80 < pixel(faint, .5, .5, .5)[2] < 150                          # half-transparent over black


def test_every_look_renders_and_matches_its_matrix(tmp_path, clips):
    for name in LOOKS:
        matrix = look_matrix(LOOKS[name])
        assert len(matrix) == 3 and all(len(row) == 3 for row in matrix)
    edit = {'segments': [{'source_job_id': 'blue', 'start': i * .2, 'end': i * .2 + .2, 'speed': 1, 'look': name} for i, name in enumerate(LOOKS)]}
    out = render(tmp_path, edit, 'looks.mp4', sources_for(clips, 'blue'))
    assert probe_media(out)['duration'] == pytest.approx(.2 * len(LOOKS), abs=.1)


def test_blurred_background_fills_a_vertical_frame(tmp_path, clips):
    shots = sources_for(clips, 'shots')
    out = render(tmp_path, {'segments': [{'source_job_id': 'shots', 'start': 1.6, 'end': 2.6, 'speed': 1}], 'ratio': '9:16', 'fit': 'blur', 'height': 640}, sources=shots)
    info = probe_media(out)
    assert (info['width'], info['height']) == (360, 640)
    assert max(pixel(out, .5, .5, .03)) > 40                                # the top is a blurred picture, not black bars
    bars = render(tmp_path, {'segments': [{'source_job_id': 'shots', 'start': 1.6, 'end': 2.6, 'speed': 1}], 'ratio': '9:16', 'fit': 'fit', 'height': 640}, 'bars.mp4', shots)
    assert max(pixel(bars, .5, .5, .03)) < 20


def test_loudness_normalization_reaches_the_target(tmp_path, clips):
    out = render(tmp_path, {'segments': [{'source_job_id': 'talk', 'start': 0, 'end': 3.5, 'speed': 1, 'gain': .3}], 'export_format': 'm4a', 'loudness': -16},
                 'loud.m4a', sources_for(clips, 'talk'))
    assert analysis.loudness(out)['integrated'] == pytest.approx(-16, abs=2.5)


def test_clip_cleanup_and_audio_fades_render(tmp_path, clips):
    out = render(tmp_path, {'segments': [{'source_job_id': 'blue', 'start': 0, 'end': 2, 'speed': 1, 'denoise': True, 'voice': True, 'fade_in': .5, 'fade_out': .5}]},
                 'clean.mp4', sources_for(clips, 'blue'))
    assert probe_media(out)['audio_codec'] == 'aac'


def test_gif_hevc_and_target_size_exports(tmp_path, clips):
    sources = sources_for(clips, 'shots')
    gif = render(tmp_path, {'segments': [{'source_job_id': 'shots', 'start': 0, 'end': 3, 'speed': 1}], 'export_format': 'gif'}, 'loop.gif', sources)
    info = probe_media(gif)
    assert info['video_codec'] == 'gif' and info['audio_codec'] is None and max(info['width'], info['height']) <= 640
    hevc = render(tmp_path, {'segments': [{'source_job_id': 'shots', 'start': 0, 'end': 3, 'speed': 1}], 'codec': 'hevc'}, 'small.mp4', sources)
    assert probe_media(hevc)['video_codec'] == 'hevc'
    sized = render(tmp_path, {'segments': [{'source_job_id': 'shots', 'start': 0, 'end': 3, 'speed': 1}], 'target_mb': 1, 'audio_bitrate': 128}, 'sized.mp4', sources)
    assert sized.stat().st_size < 1024 * 1024
    with pytest.raises(ValueError):
        target_bitrate(1, 3600, 256)


def test_caption_styles(tmp_path):
    target = tmp_path / 'c.ass'
    write_text_track(target, [{'start': 0, 'end': 1, 'text': 'Hi {\\b1}', 'kind': 'caption'}], 1080, 1920, 2, 'highlight')
    text = target.read_text(encoding='utf-8')
    assert '&H0000E8FF' in text and 'Hi ｛／b1｝' in text
    write_text_track(target, [], 1920, 1080, 2)
    assert 'Style: caption,Arial,48,' in target.read_text(encoding='utf-8')


def test_gpu_failures_fall_back_to_the_cpu(tmp_path, clips):
    sources = sources_for(clips, 'blue')
    job = jobs.create(url='local://b', kind='video', container='mp4', quality='best', directory=str(tmp_path / 'work'), source_filename=str(clips['blue']),
                      purpose='clip', destination=str(tmp_path / 'exports'),
                      conversion_options={'preset': 'device', 'edit': {'_sources': sources, '_default_source': 'blue', '_name': 'GPU test',
                                                                       'segments': [{'source_job_id': 'blue', 'start': 0, 'end': 1, 'speed': 1}]}})
    with patch.object(hardware, 'choose', return_value='h264_imaginary_nvenc'):
        run_conversion(job)
    done = jobs.get(job.id)
    assert done.status == 'completed', done.error
    assert Path(done.filename).name.startswith('GPU test [') and probe_media(done.filename)['video_codec'] == 'h264'


def test_encoder_flags_follow_the_measured_mapping():
    assert hardware.video_flags('h264_nvenc', 18)[hardware.video_flags('h264_nvenc', 18).index('-cq') + 1] == '25'
    amf = hardware.video_flags('h264_amf', 18)
    assert amf[amf.index('-qp_i') + 1] == '18' and amf[amf.index('-qp_p') + 1] == '20'
    assert '-crf' not in hardware.video_flags('libx264', 18, bitrate=2_000_000) and '2000000' in hardware.video_flags('libx264', 18, bitrate=2_000_000)
    assert hardware.video_flags('libx265', 18)[hardware.video_flags('libx265', 18).index('-crf') + 1] == '23'
    assert hardware.is_hardware('hevc_amf') and not hardware.is_hardware('libx264')
    with patch.object(hardware, 'detect', return_value={'encoders': {'h264': []}}):
        assert hardware.choose('h264') == 'libx264'
    with patch.object(hardware, 'detect', return_value={'encoders': {'hevc': ['hevc_nvenc']}}):
        assert hardware.choose('hevc') == 'hevc_nvenc' and hardware.choose('hevc', prefer_hardware=False) == 'libx265'


def test_hardware_summary_route():
    with patch.object(hardware, 'detect', return_value={'encoders': {'h264': ['h264_nvenc'], 'hevc': []}, 'gpu': 'NVIDIA', 'checked_at': 1}):
        assert client.get('/api/hardware').json() == {'gpu': 'NVIDIA', 'h264': 'h264_nvenc', 'hevc': None, 'av1': None, 'checked_at': 1, 'error': None}


# ---------------------------------------------------------------- chapter files
def test_downloads_can_also_be_split_into_chapters(tmp_path):
    from app.downloader import build_options, publish_chapters
    job = jobs.create(url='https://example.com/v', kind='video', container='mp4', quality='best', directory=str(tmp_path),
                      download_options={'split_chapters': True})
    options = build_options(job, tmp_path)
    assert options['outtmpl']['default'].endswith('[%(id)s].%(ext)s') and 'chapters' in options['outtmpl']['chapter']
    assert options['postprocessors'][-1]['key'] == 'FFmpegSplitChapters'
    clipped = jobs.create(url='https://example.com/v', kind='video', container='mp4', quality='best', directory=str(tmp_path),
                          clip_start=1.0, clip_end=4.0, download_options={'split_chapters': True})
    assert isinstance(build_options(clipped, tmp_path)['outtmpl'], str)               # a clip is never split
    plain = jobs.create(url='https://example.com/v', kind='video', container='mp4', quality='best', directory=str(tmp_path))
    assert isinstance(build_options(plain, tmp_path)['outtmpl'], str)
    (tmp_path / 'chapters').mkdir()
    for name in ('001 Intro.mp4', '002 Main part.mp4', 'notes.txt'):
        (tmp_path / 'chapters' / name).write_bytes(b'x')
    exports = tmp_path / 'out'
    exports.mkdir()
    final = exports / 'Talk [abc].mp4'
    final.write_bytes(b'video')
    folder = publish_chapters(tmp_path, final)
    assert folder == exports / 'Talk [abc] - chapters'
    assert sorted(p.name for p in folder.iterdir()) == ['001 Intro.mp4', '002 Main part.mp4']
    assert not (tmp_path / 'chapters').exists() and publish_chapters(tmp_path, final) is None
    assert client.post('/api/batch', json={'urls': ['https://example.com/a'], 'mode': 'video', 'video_container': 'mp4', 'audio_container': 'mp3',
                                           'quality': 'best', 'download_options': {'split_chapters': 'yes please'}}).status_code == 422



# ---------------------------------------------------------------- 3.0 second wave: motion, focus, ducking, chapters, beats, words
@pytest.fixture(scope='module')
def target(tmp_path_factory):
    """A red square in the middle of a blue frame, with a steady tone; and a frame with a red bar on its left edge."""
    folder = tmp_path_factory.mktemp('target')
    path = folder / 'target.mp4'
    ffmpeg('-f', 'lavfi', '-i', 'color=0x1030e0:size=320x180:rate=25', '-f', 'lavfi', '-i', 'sine=frequency=500:sample_rate=48000',
           '-vf', 'drawbox=x=140:y=70:w=40:h=40:color=red:t=fill', '-t', '3', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', path)
    edge = folder / 'edge.mp4'
    ffmpeg('-f', 'lavfi', '-i', 'color=0x1030e0:size=320x180:rate=25', '-vf', 'drawbox=x=0:y=0:w=30:h=180:color=red:t=fill',
           '-t', '2', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', edge)
    return {'target': path, 'edge': edge}


def red_share(path, at):
    """(share of red pixels, mean x of red pixels as a share of the width) in one frame."""
    info = probe_media(path)
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(at), '-i', str(path), '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1'],
                         capture_output=True, timeout=30).stdout
    w, h = info['width'], info['height']
    reds = [(i // 3) % w for i in range(0, len(raw) - 2, 3) if raw[i] > 160 and raw[i + 2] < 90]
    return len(reds) / (w * h), (sum(reds) / len(reds) / w if reds else None)


def test_ken_burns_motion_zooms_and_pans(tmp_path, target):
    sources = {'t': {'path': str(target['target']), 'metadata': probe_media(target['target'])}}
    clip = {'source_job_id': 't', 'start': 0, 'end': 3, 'speed': 1}
    zoom = render(tmp_path, {'segments': [{**clip, 'motion': 'zoom-in', 'motion_amount': .4}]}, 'zoom.mp4', sources)
    assert red_share(zoom, 2.8)[0] > red_share(zoom, .1)[0] * 1.5
    out = render(tmp_path, {'segments': [{**clip, 'motion': 'zoom-out', 'motion_amount': .4}]}, 'out.mp4', sources)
    assert red_share(out, .1)[0] > red_share(out, 2.8)[0] * 1.5
    pan = render(tmp_path, {'segments': [{**clip, 'motion': 'pan-right', 'motion_amount': .4}]}, 'pan.mp4', sources)
    assert red_share(pan, .1)[1] > red_share(pan, 2.8)[1] + .05                    # the picture slides left as the camera pans right
    assert probe_media(pan)['width'] == 320 and probe_media(zoom)['height'] == 180


def test_reframe_focus_chooses_the_kept_side(tmp_path, target):
    sources = {'e': {'path': str(target['edge']), 'metadata': probe_media(target['edge'])}}
    base = {'start': 0, 'end': 1, 'speed': 1, 'source_job_id': 'e'}
    left = render(tmp_path, {'segments': [{**base, 'focus_x': 0}], 'ratio': '9:16'}, 'left.mp4', sources)
    right = render(tmp_path, {'segments': [{**base, 'focus_x': 1}], 'ratio': '9:16'}, 'right.mp4', sources)
    assert red_share(left, .5)[0] > .1 and red_share(right, .5)[0] == 0


def test_music_ducks_under_voices(tmp_path, clips, target):
    sources = {**sources_for(clips, 'talk'), 't': {'path': str(target['target']), 'metadata': probe_media(target['target'])}}
    edit = {'segments': [{'source_job_id': 't', 'start': 0, 'end': 3, 'speed': 1, 'gain': 1}], 'soundtrack': {'source_job_id': 'talk', 'start': 0, 'offset': 0, 'gain': 1},
            'export_format': 'm4a'}
    plain = render(tmp_path, edit, 'plain.m4a', sources)
    ducked = render(tmp_path, {**edit, 'duck': True}, 'ducked.m4a', sources)
    # In the first second both play: the music must sit well under the voice when ducking is on.
    def rms(path):
        subprocess.run(['ffmpeg', '-v', 'error', '-ss', '0.3', '-t', '0.6', '-i', str(path), '-af',
                        'astats=metadata=1:reset=0,ametadata=print:key=lavfi.astats.Overall.RMS_level:file=level.txt', '-f', 'null', '-'],
                       capture_output=True, cwd=str(tmp_path), check=True)
        return float((tmp_path / 'level.txt').read_text().strip().splitlines()[-1].split('=')[-1])
    assert rms(ducked) < rms(plain) - 2


def test_markers_become_chapters(tmp_path, clips):
    out = render(tmp_path, {'segments': [{'source_job_id': 'blue', 'start': 0, 'end': 3, 'speed': 1}],
                            'markers': [{'t': 1, 'label': 'Main = part; #1'}, {'t': 2.2, 'label': 'Outro'}]}, 'chapters.mp4', sources_for(clips, 'blue'))
    chapters = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-show_chapters', '-of', 'json', str(out)], capture_output=True, text=True).stdout)['chapters']
    assert [c['tags']['title'] for c in chapters] == ['Start', 'Main = part; #1', 'Outro']
    assert float(chapters[1]['start_time']) == pytest.approx(1, abs=.01) and float(chapters[2]['end_time']) == pytest.approx(3, abs=.05)


def test_word_by_word_captions_and_animated_titles(tmp_path, clips):
    cues = [{'start': 0, 'end': 2, 'text': 'one two three', 'kind': 'caption', 'words': [0, .5, 1.2]},
            {'start': 2, 'end': 3, 'text': 'four five', 'kind': 'caption'},
            {'start': 0, 'end': 2.5, 'text': 'Big {title}', 'kind': 'title', 'animation': 'slide', 'position': 'lower'},
            {'start': .5, 'end': 2.5, 'text': 'Typed', 'kind': 'title', 'animation': 'typewriter', 'position': 'center'}]
    karaoke = tmp_path / 'k.ass'
    write_text_track(karaoke, cues, 1080, 1920, 3, 'karaoke')
    text = karaoke.read_text(encoding='utf-8')
    assert '{\\kf50}one {\\kf70}two {\\kf80}three' in text and '\\move(' in text and '｛title｝' in text and '\\alpha&HFF&' in text
    pop = tmp_path / 'p.ass'
    write_text_track(pop, cues, 1080, 1920, 3, 'pop')
    events = [line for line in pop.read_text(encoding='utf-8').splitlines() if line.startswith('Dialogue') and ',caption,' in line]
    assert len(events) == 5 and '{\\c&H00E8FF&\\fscx116\\fscy116}two{\\r}' in events[1]
    for style in ('karaoke', 'pop'):
        out = render(tmp_path, {'segments': [{'source_job_id': 'blue', 'start': 0, 'end': 3, 'speed': 1}], 'texts': cues, 'caption_style': style},
                     f'{style}.mp4', sources_for(clips, 'blue'))
        assert probe_media(out)['duration'] == pytest.approx(3, abs=.1)


def test_new_project_fields_are_validated(clips):
    blue = jobs.create(url='local://b', kind='video', container='mp4', quality='best', directory=str(clips['blue'].parent), status='completed', filename=str(clips['blue']))
    base = {'ratio': 'original', 'rotate': 0, 'flip': False, 'brightness': 0, 'contrast': 1, 'saturation': 1, 'volume': 1, 'fadeIn': 0, 'fadeOut': 0}
    project = {**base, 'segments': [{'source_job_id': blue.id, 'start': 0, 'end': 1, 'speed': 1, 'motion': 'zoom-in', 'focus_x': .2}],
               'texts': [{'start': 0, 'end': 1, 'text': 'two words', 'kind': 'caption', 'words': [0, .2, .4]}], 'markers': [{'t': .5, 'label': 'Hook'}],
               'beats': [.5, 1.0], 'bpm': 120, 'duck': True, 'caption_style': 'pop'}
    record = client.post('/api/studio/projects', json={}).json()
    saved = client.put(f"/api/editor/projects/{record['id']}", json={'project': project}).json()['history'][0]['project']
    assert 'words' not in saved['texts'][0] and saved['segments'][0]['motion'] == 'zoom-in' and saved['markers'][0]['label'] == 'Hook'
    for bad in ({'segments': [{**project['segments'][0], 'motion': 'spin'}]}, {'caption_style': 'neon'}, {'markers': [{'t': -1}]}):
        assert client.put(f"/api/editor/projects/{record['id']}", json={'project': {**project, **bad}}).status_code == 422, bad


def test_beats_are_found_in_music(tmp_path):
    clicks = tmp_path / 'clicks.wav'
    ffmpeg('-f', 'lavfi', '-i', "aevalsrc='0.8*sin(2*PI*60*t)*exp(-30*mod(t,0.5))':s=44100:d=16", '-f', 'lavfi', '-i', 'anoisesrc=d=16:c=pink:a=0.02:seed=7',
           '-filter_complex', 'amix=inputs=2', clicks)
    found = analysis.beats(clicks)
    assert found['bpm'] == pytest.approx(120, abs=1.5)
    gaps = [b - a for a, b in zip(found['beats'], found['beats'][1:])]
    assert len(found['beats']) >= 28 and all(abs(g - .5) < .05 for g in gaps)
    job = jobs.create(url='local://c', kind='audio', container='wav', quality='best', directory=str(tmp_path), status='completed', filename=str(clicks))
    assert client.post('/api/studio/analyze/beats', json={'source_job_id': job.id, 'end': 16}).json()['bpm'] == pytest.approx(120, abs=1.5)
    assert analysis.tempo_and_beats([0.0] * 50) == (0.0, [])


def test_youtube_word_timings_are_kept():
    segments = transcripts.parse(ROLLING)
    assert segments[0]['words'] == [.32, .64, 1.12, 1.36] and segments[1]['words'] == [2.879, 3.12, 3.36]
    assert 'words' not in transcripts.parse('1\n00:00:01,000 --> 00:00:02,000\nplain line\n')[0]
