"""Phone Link: pairing, the network and host guards, phone downloads, sending files, and the YouTube sign-in store."""
import json
import os
import socket
import time
import urllib.request
from pathlib import Path
from unittest.mock import patch

import pytest

os.environ['DROPDL_PHONE_TEST_CLIENT'] = '192.168.1.50'
from fastapi.testclient import TestClient

from app import main, phone_link, youtube_account
from app.jobs import jobs

PHONE = 'http://192.168.1.10:17330'
local = TestClient(main.app, base_url='http://127.0.0.1:17321')


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    monkeypatch.setenv('DROPDL_PHONE_TEST_CLIENT', '192.168.1.50')
    with phone_link.state.lock:
        phone_link.state.data.update(enabled=False, devices=[], inbox=[])
    phone_link.pairing.attempts.clear()
    phone_link.pairing.global_attempts.clear()
    phone_link.pairing.current(renew=True)
    yield


def phone():
    return TestClient(phone_link.phone_app, base_url=PHONE)


def paired():
    client = phone()
    code, _ = phone_link.pairing.current()
    r = client.post('/api/pair', json={'code': f'{code[:4]}-{code[4:].lower()}', 'name': 'Test phone'})
    assert r.status_code == 200, r.text
    return client


def test_an_unpaired_phone_sees_only_the_pairing_screen():
    client = phone()
    session = client.get('/api/session').json()
    assert session['paired'] is False and session['version'] == main.VERSION
    for path in ('/api/jobs', '/api/library'):
        assert client.get(path).status_code == 401
    assert client.post('/api/info', json={'url': 'https://example.com/v'}).status_code == 401


def test_pairing_codes_work_once_and_wrong_codes_are_refused():
    client = phone()
    assert client.post('/api/pair', json={'code': 'WRONG-CODE'}).status_code == 403
    code, _ = phone_link.pairing.current()
    first = client.post('/api/pair', json={'code': code, 'name': 'My phone'})
    assert first.status_code == 200 and first.json()['device']['name'] == 'My phone'
    assert 'httponly' in first.headers['set-cookie'].lower() and 'samesite=strict' in first.headers['set-cookie'].lower()
    assert phone().post('/api/pair', json={'code': code}).status_code == 403          # used up
    assert client.get('/api/session').json()['paired'] is True
    stored = json.loads((main.CONFIG_ROOT / 'phone.json').read_text())
    assert stored['devices'][0]['token'] != client.cookies.get(phone_link.COOKIE)   # only a hash is kept


def test_pairing_is_rate_limited():
    client = phone()
    codes = [client.post('/api/pair', json={'code': 'AAAA-AAAA'}).status_code for _ in range(7)]
    assert codes[:6] == [403] * 6 and codes[6] == 429


def test_devices_outside_the_home_network_are_refused(monkeypatch):
    monkeypatch.setenv('DROPDL_PHONE_TEST_CLIENT', '8.8.8.8')
    assert phone().get('/api/session').status_code == 403
    monkeypatch.setenv('DROPDL_PHONE_TEST_CLIENT', '100.101.102.103')                # Tailscale is fine
    assert phone().get('/api/session').status_code == 200


def test_rebinding_hosts_and_cross_site_posts_are_refused():
    assert TestClient(phone_link.phone_app, base_url='http://evil.example:17330').get('/api/session').status_code == 400
    client = paired()
    r = client.post('/api/info', json={'url': 'https://example.com/v'}, headers={'origin': 'http://evil.example'})
    assert r.status_code == 403


def test_the_web_app_is_served_with_a_strict_policy():
    r = phone().get('/')
    assert r.status_code == 200 and 'script-src \'self\'' in r.headers['content-security-policy']
    assert r.headers['cache-control'] == 'no-store' and b'DropDL' in r.content
    assert phone().get('/share?text=https://youtu.be/x').status_code == 200
    assert phone().get('/phone_link.py').status_code == 404
    assert phone().get('/..%2Fphone_link.py').status_code == 404
    assert phone().get('/manifest.webmanifest').headers['content-type'].startswith('application/manifest+json')


def test_a_download_started_on_the_phone_runs_on_the_pc_and_can_be_saved(tmp_path):
    client = paired()
    with patch('app.main.checked_url', side_effect=lambda u: u), patch('app.main.submit_task') as submit:
        r = client.post('/api/download', json={'url': 'https://example.com/clip', 'kind': 'audio', 'container': 'mp3', 'quality': 'best'})
    assert r.status_code == 202 and submit.called
    view = r.json()
    assert view['mine'] and view['from_phone'] and view['kind'] == 'audio'
    job = jobs.get(view['id'])
    assert job.origin.startswith('phone:')
    listed = client.get('/api/jobs').json()
    assert listed['jobs'][0]['id'] == job.id
    assert client.get(f'/api/jobs/{job.id}/file').status_code == 409                 # not finished yet
    media = tmp_path / 'song.mp3'
    media.write_bytes(b'ID3' + b'\0' * 100)
    jobs.update(job.id, status='completed', filename=str(media), title='Song')
    got = client.get(f'/api/jobs/{job.id}/file')
    assert got.status_code == 200 and got.content == media.read_bytes()
    assert got.headers['content-disposition'].startswith('attachment')
    assert client.get(f'/api/jobs/{job.id}/file?inline=1').headers['content-disposition'].startswith('inline')
    # the desktop sends it to the phone's inbox
    sent = local.post('/api/phone/send', json={'job_id': job.id})
    assert sent.status_code == 200 and sent.json()['inbox'] == 1
    inbox = client.get('/api/jobs').json()['inbox']
    assert inbox[0]['title'] == 'Song'
    assert client.get(f"/api/inbox/{inbox[0]['id']}/file").content == media.read_bytes()
    assert client.post(f"/api/inbox/{inbox[0]['id']}/done").json()['inbox'] == []


def test_phone_rules_match_the_desktop_rules():
    client = paired()
    with patch('app.main.checked_url', side_effect=lambda u: u), patch('app.main.submit_task'):
        assert client.post('/api/download', json={'url': 'https://example.com/v', 'kind': 'audio', 'container': 'mp4'}).status_code == 400
    assert client.post('/api/download', json={'url': 'http://192.168.1.1/x'}).status_code == 400   # private targets stay blocked


def test_the_desktop_can_remove_a_phone():
    client = paired()
    status = local.get('/api/phone/status').json()
    assert status['devices'][0]['name'] == 'Test phone' and status['pairing']['code'].count('-') == 1
    local.post(f"/api/phone/devices/{status['devices'][0]['id']}/remove")
    assert client.get('/api/jobs').status_code == 401


def test_the_local_api_only_answers_this_pc():
    assert TestClient(main.app, base_url='http://192.168.1.10:17321').get('/api/phone/status').status_code == 403
    status = local.get('/api/phone/status').json()
    if status['pairing']['url']:
        assert status['pairing']['qr'].startswith('<svg') and '#pair=' in status['pairing']['url']


def test_the_phone_server_starts_and_stops(monkeypatch):
    monkeypatch.setattr(phone_link, 'BIND_HOST', '127.0.0.1')
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    assert phone_link.server.start(port)
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/session', timeout=5) as response:
            assert json.load(response)['paired'] is False
    finally:
        phone_link.server.stop()
    assert not phone_link.server.running


# ---------------------------------------------------------------- YouTube sign-in store
def _cookie(name, domain='.youtube.com', **extra):
    return {'domain': domain, 'name': name, 'value': 'v-' + name, 'path': '/', 'secure': True, 'httponly': name == 'LOGIN_INFO', 'expires': time.time() + 86400, **extra}


def test_signed_in_cookies_are_stored_for_youtube_only(monkeypatch):
    monkeypatch.setenv('DROPDL_NATIVE_TOKEN', 'native-test')
    file = youtube_account.cookie_file()
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text('# Netscape HTTP Cookie File\n.instagram.com\tTRUE\t/\tTRUE\t0\tsessionid\tkeep-me\n.youtube.com\tTRUE\t/\tTRUE\t0\tOLD\tgone\n')
    headers = {'X-DropDL-Native-Token': 'native-test'}
    assert local.post('/api/native/youtube/cookies', json={'cookies': [_cookie('LOGIN_INFO')]}).status_code == 403
    r = local.post('/api/native/youtube/cookies', headers=headers,
                   json={'cookies': [_cookie('LOGIN_INFO'), _cookie('SAPISID'), _cookie('NID', domain='.google.com'), _cookie('YSC', expires=0)]})
    assert r.status_code == 200 and r.json()['signed_in'] and r.json()['source'] == 'signin'
    text = file.read_text()
    assert 'keep-me' in text and 'OLD' not in text and '.google.com' not in text
    assert '#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t' in text and '\tYSC\tv-YSC' in text
    import http.cookiejar
    jar = http.cookiejar.MozillaCookieJar(str(file))
    jar.load(ignore_discard=True, ignore_expires=True)
    assert {c.name for c in jar} >= {'sessionid', 'SAPISID', 'YSC'}
    assert local.get('/api/youtube/status').json()['youtube_cookies'] == 3
    after = local.post('/api/youtube/disconnect').json()
    assert after['signed_in'] is False and 'keep-me' in file.read_text()


def test_a_session_without_a_sign_in_is_not_accepted(monkeypatch):
    monkeypatch.setenv('DROPDL_NATIVE_TOKEN', 'native-test')
    r = local.post('/api/native/youtube/cookies', headers={'X-DropDL-Native-Token': 'native-test'}, json={'cookies': [_cookie('YSC')]})
    assert r.status_code == 409
