"""Bounded, isolated playlist extraction; no webview or app state in the worker."""
import faulthandler
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import traceback
from .settings import CONFIG_ROOT

log = logging.getLogger('dropdl.playlist')
MAX_RESULT_BYTES = 2 * 1024 * 1024


def worker_main():
    request_path, result_path = map(Path, sys.argv[-2:])
    CONFIG_ROOT.mkdir(parents=True, exist_ok=True)
    with (CONFIG_ROOT / 'playlist-worker-crash.log').open('a', encoding='utf-8') as fault_file:
        fault_file.write(f'Playlist worker started: pid={os.getpid()}\n')
        fault_file.flush()
        faulthandler.enable(file=fault_file, all_threads=True)
        try:
            from .downloader import inspect_playlist
            request = json.loads(request_path.read_text(encoding='utf-8'))
            result = {'ok': True, 'data': inspect_playlist(**request)}
        except Exception as exc:
            result = {'ok': False, 'error': str(exc)[:2000], 'trace': traceback.format_exc()[-12000:]}
        result_path.write_text(json.dumps(result, ensure_ascii=False, allow_nan=False), encoding='utf-8')


def inspect_playlist_isolated(url, start=1, limit=100):
    with tempfile.TemporaryDirectory(prefix='dropdl-playlist-') as folder:
        request_path = Path(folder) / 'request.json'
        result_path = Path(folder) / 'result.json'
        request_path.write_text(json.dumps({'url':url,'start':start,'limit':limit}), encoding='utf-8')
        if getattr(sys, 'frozen', False):
            command = [sys.executable, '--playlist-worker', str(request_path), str(result_path)]
        else:
            command = [sys.executable, '-u', '-m', 'app.playlist_process', '--worker', str(request_path), str(result_path)]
        log.info('Starting isolated playlist extraction: start=%s limit=%s', start, limit)
        try:
            process = subprocess.run(command, cwd=Path(__file__).resolve().parents[1],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=50, creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        except subprocess.TimeoutExpired as exc:
            log.exception('Playlist worker exceeded 50 seconds and was terminated')
            raise ValueError('Playlist loading timed out. Check your connection and try again.') from exc
        if process.returncode != 0:
            log.error('Playlist worker exited unexpectedly: code=%s (0x%08X)', process.returncode, process.returncode & 0xffffffff)
            raise ValueError(f'Playlist worker stopped unexpectedly (code {process.returncode}). See diagnostics.log and playlist-worker-crash.log.')
        if not result_path.is_file() or result_path.stat().st_size > MAX_RESULT_BYTES:
            raise ValueError('Playlist worker returned a missing or oversized response.')
        result = json.loads(result_path.read_text(encoding='utf-8'))
        if not result.get('ok'):
            log.error('Playlist extraction failed: %s\n%s', result.get('error'), result.get('trace'))
            raise ValueError(result.get('error') or 'Playlist loading failed.')
        data = result['data']
        if not isinstance(data, dict) or not isinstance(data.get('entries'), list) or len(data['entries']) > limit:
            raise ValueError('Playlist worker returned an invalid response.')
        log.info('Playlist extraction completed: %s entries, more=%s',len(data['entries']),data.get('has_more'))
        return data


if __name__ == '__main__':
    worker_main()
