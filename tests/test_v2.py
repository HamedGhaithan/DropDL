"""DropDL Studio 2.0: format planning, extras, network, self-healing,
stall watchdog, smarter retries, queue revisions and shutdown recovery."""
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from fastapi.testclient import TestClient

from app import main, media_worker
from app.downloader import (ProgressTracker, build_options, fallback_for, format_plan, network_options)
from app.jobs import Job, JobStore, jobs
from app.scheduler import Scheduler, retry_delay
from app.settings import Settings, valid_network_value
from app.task_errors import classify

client = TestClient(main.app)


def make_job(tmp_path, **changes):
    values = dict(id='a' * 32, url='https://example.com/v', kind='video', container='mp4', quality='720p',
                  directory=str(tmp_path / 'work'))
    values.update(changes)
    return Job(**values)


# ------------------------------------------------------------------ formats

def test_format_plan_never_hard_filters():
    fmt, sort = format_plan('video', 'mp4', '720p')
    assert fmt == 'bv*+ba/b' and sort[0] == 'vcodec:h264' and 'res:720' in sort
    fmt, sort = format_plan('video', 'mkv', 'best')
    assert fmt == 'bv*+ba/b' and sort[0] == 'res' and 'vcodec:h264' not in sort
    fmt, sort = format_plan('video', 'mp4', '1080p', 'any')
    assert sort[0] == 'res:1080'
    assert format_plan('video', 'webm', '480p')[1][:1] == ['res:480']
    assert format_plan('audio', 'm4a', 'best') == ('ba/b', ['acodec:aac', 'abr', 'asr'])
    assert format_plan('audio', 'mp3', 'best')[0] == 'ba/b'


def test_audio_formats_and_bitrates(tmp_path):
    for container, quality, expected in [('mp3', '192', '192'), ('mp3', 'best', '0'), ('flac', '320', '0'), ('opus', '128', '128'), ('wav', 'best', '0')]:
        job = make_job(tmp_path, kind='audio', container=container, quality='best', download_options={'audio_quality': quality})
        pp = [p for p in build_options(job, tmp_path)['postprocessors'] if p['key'] == 'FFmpegExtractAudio'][0]
        assert pp['preferredcodec'] == container and pp['preferredquality'] == expected


def test_sponsorblock_and_cover_art(tmp_path):
    job = make_job(tmp_path, download_options={'sponsorblock': 'remove', 'embed_thumbnail': True})
    options = build_options(job, tmp_path)
    keys = [p['key'] for p in options['postprocessors']]
    assert keys.index('SponsorBlock') < keys.index('FFmpegVideoRemuxer') < keys.index('ModifyChapters') < keys.index('EmbedThumbnail')
    modify = next(p for p in options['postprocessors'] if p['key'] == 'ModifyChapters')
    assert modify['remove_sponsor_segments'] == {'sponsor', 'selfpromo', 'interaction'}
    assert options['writethumbnail'] is True
    # A clip range must not shift: removal is downgraded to chapter marks.
    clipped = build_options(make_job(tmp_path, clip_start=1.0, clip_end=5.0, download_options={'sponsorblock': 'remove'}), tmp_path)
    modify = next(p for p in clipped['postprocessors'] if p['key'] == 'ModifyChapters')
    assert modify['remove_sponsor_segments'] == set()
    assert any(p['key'] == 'FFmpegMetadata' and p['add_chapters'] for p in clipped['postprocessors'])
    # WebM cannot embed cover art; option is ignored instead of failing.
    webm = build_options(make_job(tmp_path, container='webm', download_options={'embed_thumbnail': True}), tmp_path)
    assert 'writethumbnail' not in webm and all(p['key'] != 'EmbedThumbnail' for p in webm['postprocessors'])


def test_embedded_subtitles_need_languages(tmp_path):
    with_langs = build_options(make_job(tmp_path, subtitle_languages=['en'], download_options={'embed_subtitles': True}), tmp_path)
    assert any(p['key'] == 'FFmpegEmbedSubtitle' for p in with_langs['postprocessors'])
    without = build_options(make_job(tmp_path, download_options={'embed_subtitles': True}), tmp_path)
    assert all(p['key'] != 'FFmpegEmbedSubtitle' for p in without['postprocessors'])


def test_network_options_mapping():
    options = network_options({'proxy': 'socks5h://127.0.0.1:9050', 'force_ipv4': True, 'cookies_browser': 'firefox', 'concurrent_fragments': 40})
    assert options['proxy'] == 'socks5h://127.0.0.1:9050' and options['source_address'] == '0.0.0.0'
    assert options['cookiesfrombrowser'] == ('firefox', None, None, None)
    assert options['concurrent_fragment_downloads'] == 16
    assert network_options({'cookies_browser': 'netscape'}).get('cookiesfrombrowser') is None
    assert 'proxy' not in network_options({})


# ------------------------------------------------------------------ self-healing

def test_fallbacks_apply_once_each():
    options = {'format': 'bv*+ba/b', 'format_sort': ['vcodec:h264'], 'merge_output_format': 'mp4',
               'postprocessors': [{'key': 'SponsorBlock'}, {'key': 'ModifyChapters'}, {'key': 'EmbedThumbnail'}],
               'writethumbnail': True, 'cookiesfrombrowser': ('chrome', None, None, None)}
    used = set()
    assert fallback_for('ERROR: Requested format is not available', options, used) == 'format'
    assert 'format_sort' not in options
    used.add('format')
    assert fallback_for('ERROR: Requested format is not available', options, used) is None
    assert fallback_for('SponsorBlock API request failed', options, used) == 'sponsorblock'
    assert [p['key'] for p in options['postprocessors']] == ['EmbedThumbnail']
    assert fallback_for('EmbedThumbnail: thumbnail format unsupported', options, used) == 'thumbnail'
    assert 'writethumbnail' not in options and options['postprocessors'] == []
    assert fallback_for('Could not copy Chrome cookie database', options, used) == 'cookies'
    assert 'cookiesfrombrowser' not in options
    assert fallback_for('HTTP Error 403: Forbidden', options, used) == 'forbidden' and options['_clear_cache']
    assert fallback_for('Video unavailable', options, used | {'forbidden'}) is None


def test_worker_falls_back_on_unavailable_format(tmp_path):
    attempts = []

    class Downloader:
        def __init__(self, options): self.options = options; attempts.append(dict(options))
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def add_progress_hook(self, hook): pass
        def download(self, urls):
            from yt_dlp.utils import DownloadError
            if 'format_sort' in self.options:
                raise DownloadError('ERROR: [generic] Requested format is not available')
            out = Path(self.options['outtmpl']).parent / 'Clip [x].mp4'
            out.write_bytes(b'video')
            for hook in self.options['post_hooks']: hook(str(out))

    from app.downloader import run_download
    with patch('app.downloader.YoutubeDL', Downloader):
        job = jobs.create(url='https://example.com/v', kind='video', container='mp4', quality='720p',
                          directory=str(tmp_path / 'work'), destination=str(tmp_path / 'out'))
        run_download(job)
    assert job.status == 'completed', job.error
    assert len(attempts) == 2 and 'format_sort' not in attempts[1]
    assert Path(job.filename).read_bytes() == b'video' and job.total_bytes == 5


def test_merged_progress_is_monotonic():
    tracker = ProgressTracker()
    info = {'requested_formats': [{'filesize': 800}, {'filesize': 200}]}
    seen = []
    for done in (0, 400, 800):
        seen.append(tracker.update({'filename': 'v', 'downloaded_bytes': done, 'total_bytes': 800, 'info_dict': info, 'speed': 100}))
    tracker.update({'filename': 'v', 'downloaded_bytes': 800, 'total_bytes': 800, 'info_dict': info}, finished=True)
    assert tracker.pending()
    for done in (0, 100, 200):
        seen.append(tracker.update({'filename': 'a', 'downloaded_bytes': done, 'total_bytes': 200, 'info_dict': info, 'speed': 100}))
    tracker.update({'filename': 'a', 'downloaded_bytes': 200, 'total_bytes': 200, 'info_dict': info}, finished=True)
    assert not tracker.pending()
    fractions = [done / total for done, total, _ in seen]
    assert fractions == sorted(fractions) and fractions[-1] == 1.0 and all(total == 1000 for _, total, _ in seen)
    assert seen[1][2] == 6  # (1000-400)/100 seconds remaining overall


# ------------------------------------------------------------------ errors & retries

@pytest.mark.parametrize('text,code', [
    ('HTTP Error 429: Too Many Requests', 'rate_limited'),
    ("Sign in to confirm you're not a bot", 'bot_check'),
    ('The uploader has not made this video available in your country', 'geo'),
    ('Requested format is not available', 'format'),
    ('Download stalled: no data received for 90 seconds.', 'stalled'),
    ('HTTP Error 403: Forbidden', 'forbidden'),
    ('[Errno 11001] getaddrinfo failed', 'network'),
    ('Video unavailable', 'unavailable'),
])
def test_error_classification(text, code):
    assert classify(text) == code


def test_retry_backoff():
    assert retry_delay(0, 'network') == 10 and retry_delay(3, 'network') == 80 and retry_delay(9, 'network') == 300
    assert retry_delay(0, 'stalled') == 3 and retry_delay(0, 'rate_limited') == 60


def test_scheduler_retries_transient_failures_only(tmp_path):
    prefs = {'max_auto_retries': 2}
    scheduler = Scheduler(1, lambda: prefs)
    scheduler.close()
    job = jobs.create(url='https://example.com/a', kind='video', container='mp4', quality='best', directory=str(tmp_path / 'a'))
    jobs.update_attempt(job, status='failed', error='Read timed out.')
    replacement = scheduler.maybe_retry(lambda job: None, job)
    assert replacement and replacement.status == 'queued' and replacement.auto_retries == 1
    assert replacement.phase == 'retry_wait' and replacement.retry_at > time.time() + 5
    assert 'Automatic retry 1/2' in replacement.error and replacement.public()['retry_at'] == replacement.retry_at
    jobs.update_attempt(replacement, status='failed', error='Read timed out.')
    second = scheduler.maybe_retry(lambda job: None, replacement)
    jobs.update_attempt(second, status='failed', error='Read timed out.')
    assert scheduler.maybe_retry(lambda job: None, second) is None  # limit reached
    permanent = jobs.create(url='https://example.com/b', kind='video', container='mp4', quality='best', directory=str(tmp_path / 'b'))
    jobs.update_attempt(permanent, status='failed', error='Video unavailable')
    assert scheduler.maybe_retry(lambda job: None, permanent) is None
    prefs['max_auto_retries'] = 0
    off = jobs.create(url='https://example.com/c', kind='video', container='mp4', quality='best', directory=str(tmp_path / 'c'))
    jobs.update_attempt(off, status='failed', error='Read timed out.')
    assert scheduler.maybe_retry(lambda job: None, off) is None


def test_parallel_slots_follow_preferences():
    prefs = {'max_concurrent_downloads': 5}
    scheduler = Scheduler(2, lambda: prefs)
    scheduler.close()
    assert scheduler.slots() == 5
    prefs['max_concurrent_downloads'] = 99
    assert scheduler.slots() == 8
    assert Scheduler(1, lambda: {}).slots() == 1


# ------------------------------------------------------------------ stall watchdog

FAKE_WORKER = r'''
import json, sys, time
from pathlib import Path
status, control = Path(sys.argv[1]), Path(sys.argv[2])
while not control.exists():
    status.write_text(json.dumps({"status": "downloading", "phase": "downloading", "downloaded_bytes": 1000, "total_bytes": 5000, "percent": 20}))
    time.sleep(0.1)
status.write_text(json.dumps({"status": "cancelled", "error": None}))
'''


def test_stall_watchdog_restarts_silent_transfer(tmp_path):
    script = tmp_path / 'fake_worker.py'
    script.write_text(FAKE_WORKER, encoding='utf-8')
    job = jobs.create(url='https://example.com/stall', kind='video', container='mp4', quality='best',
                      directory=str(tmp_path / 'work'), network={'stall_timeout': 1})
    with patch('app.media_worker.command', lambda request, status, control: [sys.executable, str(script), str(status), str(control)]):
        started = time.monotonic()
        media_worker.run_isolated(job)
    assert time.monotonic() - started < 15
    assert job.status == 'failed' and job.phase == 'stalled' and job.stalls == 1
    assert classify(job.error) == 'stalled'


# ------------------------------------------------------------------ queue sync & shutdown

def test_jobs_endpoint_skips_unchanged_revisions(tmp_path):
    first = client.get('/api/jobs').json()
    assert 'jobs' in first and isinstance(first['revision'], int)
    assert client.get(f"/api/jobs?revision={first['revision']}").json() == {'revision': first['revision'], 'unchanged': True}
    jobs.create(url='https://example.com/r', kind='video', container='mp4', quality='best', directory=str(tmp_path / 'r'))
    changed = client.get(f"/api/jobs?revision={first['revision']}").json()
    assert changed['revision'] > first['revision'] and changed['jobs']
    health = client.get('/api/health').json()
    assert health['version'] == main.VERSION and health['revision'] == changed['revision'] and 'disk_free' in health


def test_shutdown_keeps_active_downloads_resumable(tmp_path):
    store = JobStore()
    store.enable_persistence(tmp_path / 'queue.json')
    active = store.create(url='https://example.com/x', kind='video', container='mp4', quality='best', directory=str(tmp_path / 'x'))
    store.update(active.id, status='downloading')
    waiting = store.create(url='https://example.com/y', kind='video', container='mp4', quality='best', directory=str(tmp_path / 'y'))
    store.checkpoint_for_shutdown()
    assert active.pause_requested and active.interrupted and active.cancel_event.is_set()
    # A worker that races the checkpoint and reports "cancelled" must not lose resumability.
    store.update(active.id, status='cancelled')
    reloaded = JobStore()
    reloaded.enable_persistence(tmp_path / 'queue.json')
    assert reloaded.get(active.id).status == 'paused' and reloaded.get(active.id).interrupted
    assert reloaded.get(waiting.id).status == 'paused' and reloaded.get(waiting.id).interrupted
    assert {job.id for job in reloaded.recover_interrupted()} == {active.id, waiting.id}


def test_native_shutdown_checkpoints_before_stopping(tmp_path):
    job = jobs.create(url='https://example.com/z', kind='video', container='mp4', quality='best', directory=str(tmp_path / 'z'))
    jobs.update(job.id, status='downloading')
    with patch.dict(os.environ, {'DROPDL_NATIVE_TOKEN': 'token'}):
        assert client.post('/api/native/shutdown', json={}, headers={'X-DropDL-Native-Token': 'token'}).status_code == 200
    assert job.pause_requested and job.interrupted


# ------------------------------------------------------------------ settings & API

@pytest.mark.parametrize('proxy,ok', [('', True), ('http://127.0.0.1:8080', True), ('socks5h://user:pw@proxy.example:1080', True),
                                      ('ftp://x:1', False), ('127.0.0.1:8080', False), ('http://a b', False)])
def test_proxy_validation(proxy, ok):
    assert valid_network_value('proxy', proxy) is ok


def test_network_preferences_round_trip(tmp_path):
    preferences = Settings(tmp_path / 'settings.json', tmp_path / 'downloads')
    base = {'group_by_site': False, 'speed_limit_kbps': 0}
    with patch('app.main.settings', preferences):
        bad = client.post('/api/settings', json={**base, 'proxy': 'nonsense'})
        assert bad.status_code == 422
        bad = client.post('/api/settings', json={**base, 'stall_timeout': 10})
        assert bad.status_code == 422
        good = client.post('/api/settings', json={**base, 'proxy': ' socks5://127.0.0.1:1080 ', 'max_concurrent_downloads': 4,
                                                   'force_ipv4': True, 'cookies_browser': 'firefox', 'stall_timeout': 0})
        assert good.status_code == 200, good.text
        assert good.json()['proxy'] == 'socks5://127.0.0.1:1080' and good.json()['max_concurrent_downloads'] == 4
    again = Settings(tmp_path / 'settings.json', tmp_path / 'downloads').get()
    assert again['force_ipv4'] and again['cookies_browser'] == 'firefox' and again['stall_timeout'] == 0
    (tmp_path / 'settings.json').write_text(json.dumps({'proxy': 'bad', 'max_concurrent_downloads': 50, 'impersonate': 'x'}), encoding='utf-8')
    defaults = Settings(tmp_path / 'settings.json', tmp_path / 'downloads').get()
    assert defaults['proxy'] == '' and defaults['max_concurrent_downloads'] == 2 and defaults['impersonate'] == 'auto'


def test_batch_accepts_new_audio_formats_and_extras(tmp_path):
    preferences = Settings(tmp_path / 'settings.json', tmp_path / 'downloads')
    with patch('app.main.settings', preferences), patch('app.main.checked_batch_urls', lambda urls: urls), \
            patch.object(main.executor, 'submit', lambda function, job: None):
        response = client.post('/api/batch', json={'urls': ['https://example.com/song'], 'mode': 'audio', 'audio_container': 'flac',
                                                   'download_options': {'sponsorblock': 'mark', 'embed_thumbnail': True, 'codec': 'auto'}})
        assert response.status_code == 202, response.text
        created = response.json()['jobs'][0]
        assert created['container'] == 'flac' and created['download_options'] == {
            'sponsorblock': 'mark', 'embed_thumbnail': True, 'embed_subtitles': False, 'audio_quality': 'best'}
        rejected = client.post('/api/batch', json={'urls': ['https://example.com/song'], 'mode': 'audio', 'audio_container': 'exe'})
        assert rejected.status_code == 422
        rejected = client.post('/api/batch', json={'urls': ['https://example.com/song'], 'download_options': {'sponsorblock': 'all'}})
        assert rejected.status_code == 422


def test_network_snapshot_taken_when_task_starts(tmp_path):
    preferences = Settings(tmp_path / 'settings.json', tmp_path / 'downloads')
    preferences.change(proxy='http://127.0.0.1:3128')
    job = make_job(tmp_path)
    with patch('app.main.settings', preferences), patch('app.main.run_isolated', lambda job: None):
        main.execute_task(job)
    assert job.network['proxy'] == 'http://127.0.0.1:3128' and job.network['stall_timeout'] == 90


def test_postprocessing_failures_heal_step_by_step():
    options = {'merge_output_format': 'mp4', 'writethumbnail': True,
               'postprocessors': [{'key': 'SponsorBlock'}, {'key': 'FFmpegVideoRemuxer', 'preferedformat': 'mp4'},
                                  {'key': 'ModifyChapters'}, {'key': 'EmbedThumbnail'}]}
    used = set()
    steps = []
    while (step := fallback_for('ERROR: Postprocessing: Conversion failed!', options, used)):
        used.add(step); steps.append(step)
    assert steps == ['convert', 'thumbnail', 'sponsorblock']
    assert [p['key'] for p in options['postprocessors']] == ['FFmpegVideoConvertor']
    assert options['postprocessors'][0]['preferedformat'] == 'mp4'


def test_mp4_prefers_mp4_container_when_codecs_are_unknown():
    assert format_plan('video', 'mp4', '720p')[1][:2] == ['vcodec:h264', 'ext:mp4:m4a']
    assert 'ext:mp4:m4a' in format_plan('video', 'mp4', 'best', 'any')[1]


def test_retry_ignores_empty_leftovers_and_heals_raw_postprocessor_errors(tmp_path):
    """Regression (found in a real archive.org download): a failed remux left a
    0-byte .mp4; the retry thought it was finished and crashed with KeyError."""
    work = tmp_path / 'work'; work.mkdir()
    (work / 'Clip [x].mp4').write_bytes(b'')
    calls = []

    class Downloader:
        def __init__(self, options): self.options = options; calls.append(options)
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def add_progress_hook(self, hook): pass
        def download(self, urls):
            target = work / 'Clip [x].mp4'
            assert not target.exists(), 'empty leftover must be removed before each attempt'
            if any(p['key'] == 'EmbedThumbnail' for p in self.options['postprocessors']):
                target.write_bytes(b'')
                job.status = 'processing'; job.phase = 'thumbnail'
                raise KeyError('streams')
            target.write_bytes(b'video')
            for hook in self.options['post_hooks']: hook(str(target))

    from app.downloader import run_download
    with patch('app.downloader.YoutubeDL', Downloader):
        job = jobs.create(url='https://example.com/v', kind='video', container='mp4', quality='720p', directory=str(work),
                          destination=str(tmp_path / 'out'), download_options={'embed_thumbnail': True})
        run_download(job)
    assert job.status == 'completed', job.error
    assert len(calls) == 2 and Path(job.filename).read_bytes() == b'video'


def test_unexpected_errors_are_named(tmp_path):
    from app.downloader import run_download

    class Broken:
        def __init__(self, options): pass
        def __enter__(self): raise KeyError('streams')
        def __exit__(self, *args): pass

    with patch('app.downloader.YoutubeDL', Broken):
        job = jobs.create(url='https://example.com/v', kind='video', container='mp4', quality='720p', directory=str(tmp_path / 'w'))
        run_download(job)
    assert job.status == 'failed' and job.error == "Unexpected KeyError: 'streams'"


def test_ladder_targets_the_failing_step_first():
    options = {'merge_output_format': 'mp4', 'writethumbnail': True,
               'postprocessors': [{'key': 'FFmpegVideoRemuxer', 'preferedformat': 'mp4'}, {'key': 'EmbedThumbnail'}]}
    assert fallback_for('ERROR: Postprocessing: Conversion failed! [phase: thumbnail]', options, set()) == 'thumbnail'
    assert [p['key'] for p in options['postprocessors']] == ['FFmpegVideoRemuxer']


def test_parent_watch_detects_backend_exit():
    import subprocess
    from app.media_worker import ParentWatch
    proc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(1.5)'])
    watch = ParentWatch(str(proc.pid)) if os.name == 'nt' else ParentWatch(str(os.getppid()))
    assert watch.gone() is False
    if os.name == 'nt':
        proc.wait(); watch.checked = 0
        assert watch.gone() is True
    else:
        proc.wait()
    assert ParentWatch(None).gone() is False


# ------------------------------------------------------------------ 2.1 posters

def _ffmpeg(*args):
    import subprocess
    subprocess.run(['ffmpeg', '-v', 'error', '-y', *args], check=True, capture_output=True, timeout=60)


def _mean_rgb(path):
    import subprocess
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path), '-vf', 'scale=1:1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1'],
                         capture_output=True, timeout=30).stdout
    return tuple(raw[:3])


def test_video_poster_skips_black_opening(tmp_path):
    from app.posters import make_poster
    video = tmp_path / 'fade-in.mp4'
    _ffmpeg('-f', 'lavfi', '-i', 'color=black:s=160x90:d=3', '-f', 'lavfi', '-i', 'color=red:s=160x90:d=27',
            '-filter_complex', '[0][1]concat=n=2:v=1[v]', '-map', '[v]', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(video))
    target = tmp_path / 'poster.jpg'
    assert make_poster(str(video), target, 160)
    red, green, blue = _mean_rgb(target)
    assert red > 150 and green < 80 and blue < 80, (red, green, blue)


def test_audio_poster_uses_embedded_cover_art(tmp_path):
    from app.posters import make_poster
    cover, song, plain = tmp_path / 'cover.png', tmp_path / 'song.mp3', tmp_path / 'plain.mp3'
    _ffmpeg('-f', 'lavfi', '-i', 'color=blue:s=64x64:d=1', '-frames:v', '1', str(cover))
    _ffmpeg('-f', 'lavfi', '-i', 'sine=d=2', '-i', str(cover), '-map', '0:a', '-map', '1:v', '-c:a', 'libmp3lame',
            '-c:v', 'png', '-disposition:v', 'attached_pic', str(song))
    _ffmpeg('-f', 'lavfi', '-i', 'sine=d=2', '-c:a', 'libmp3lame', str(plain))
    assert make_poster(str(song), tmp_path / 'art.jpg', 64)
    assert _mean_rgb(tmp_path / 'art.jpg')[2] > 150
    assert make_poster(str(plain), tmp_path / 'none.jpg', 64) is False


def test_poster_endpoint_for_completed_task(tmp_path):
    video = tmp_path / 'clip.mp4'
    _ffmpeg('-f', 'lavfi', '-i', 'testsrc=s=160x90:d=4', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(video))
    job = jobs.create(url='https://example.com/p', kind='video', container='mp4', quality='best', directory=str(tmp_path),
                      status='completed', filename=str(video))
    response = client.get(f'/api/jobs/{job.id}/poster')
    assert response.status_code == 200 and response.headers['content-type'] == 'image/jpeg' and response.content[:2] == b'\xff\xd8'
    pending = jobs.create(url='https://example.com/q', kind='video', container='mp4', quality='best', directory=str(tmp_path))
    assert client.get(f'/api/jobs/{pending.id}/poster').status_code == 409


def test_waveform_strip_variant(tmp_path):
    clip = tmp_path / 'tone.mp4'
    _ffmpeg('-f', 'lavfi', '-i', 'testsrc=s=160x90:d=3', '-f', 'lavfi', '-i', 'sine=d=3', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', str(clip))
    job = jobs.create(url='https://example.com/w', kind='video', container='mp4', quality='best', directory=str(tmp_path), status='completed', filename=str(clip))
    strip = client.get(f'/api/jobs/{job.id}/waveform?variant=strip')
    assert strip.status_code == 200 and strip.content[:4] == b'\x89PNG'
    import struct
    assert struct.unpack('>II', strip.content[16:24]) == (4000, 96)
    assert client.get(f'/api/jobs/{job.id}/waveform').status_code == 200
    assert client.get(f'/api/jobs/{job.id}/waveform?variant=huge').status_code == 400
