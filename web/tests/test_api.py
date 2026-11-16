import dataclasses
import subprocess
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient

from server import config, engine as engine_module
from server.app import create_app
from server.engine import Engine
from tests.conftest import Gate, fake_info, fake_run, wait_for

JSON = {"content-type": "application/json"}
VIDEO = {"url": "https://vimeo.com/123", "kind": "video", "height": 720, "format": "mp4"}


def client_for(settings, run_fn=fake_run, **overrides):
    app = create_app(dataclasses.replace(settings, **overrides), run_fn=run_fn, info_fn=fake_info, background=False)
    return TestClient(app)


@pytest.fixture
def client(settings):
    with client_for(settings) as c:
        yield c


def finish(client, body=VIDEO):
    created = client.post("/api/jobs", json=body)
    assert created.status_code == 202, created.text
    job_id = created.json()["id"]
    wait_for(lambda: client.get(f"/api/jobs/{job_id}").json()["status"] == "done")
    return job_id


# --------------------------------------------------------------------------- the page and its protection
def test_health_reports_the_limits(client):
    body = client.get("/api/health").json()
    assert body["ok"] and body["youtube"] == "off" and body["limits"]["max_height"] == 1080
    assert "mp4" in body["limits"]["video_formats"] and "mp3" in body["limits"]["audio_formats"]
    assert "hostname" not in str(body).lower()                          # nothing about the machine leaks


def test_every_response_carries_security_headers(client):
    for path in ("/", "/api/health", "/style.css", "/api/jobs/nope"):
        h = client.get(path).headers
        assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY" and h["referrer-policy"] == "no-referrer"
        csp = h["content-security-policy"]
        assert "default-src 'none'" in csp and "script-src 'self'" in csp and "frame-ancestors 'none'" in csp and "unsafe-inline" not in csp
    assert client.get("/api/health").headers["cache-control"] == "no-store"
    assert "strict-transport-security" not in client.get("/").headers
    assert "max-age" in client.get("/", headers={"x-forwarded-proto": "https"}).headers["strict-transport-security"]


def test_the_page_is_served(client):
    page = client.get("/")
    assert page.status_code == 200 and "DropDL" in page.text and 'type="module"' in page.text
    assert "onclick=" not in page.text and "style=" not in page.text     # the strict content policy forbids inline code and styles
    for asset in ("/app.js", "/i18n.js", "/style.css", "/logo.svg", "/fonts/inter.woff2"):
        assert client.get(asset).status_code == 200, asset


def test_api_docs_are_off_by_default(client):
    for path in ("/api/docs", "/api/openapi.json", "/docs", "/redoc"):
        assert client.get(path).status_code == 404


def test_no_path_traversal(client):
    for path in ("/%2e%2e/server/app.py", "/..%2fserver%2fapp.py", "/fonts/..%2f..%2fserver%2fapp.py", "/api/jobs/..%2f..%2fetc"):
        r = client.get(path)
        assert "create_app" not in r.text and r.status_code in (404, 400, 422)


def test_oversized_and_malformed_requests(client):
    assert client.post("/api/info", content=b"x" * 20000, headers=JSON).status_code == 413
    bad = client.post("/api/jobs", json={"url": "https://secret.example/abc", "height": "tall"})
    assert bad.status_code == 422 and "secret.example" not in bad.text and bad.json()["error"]["code"] == "bad_request"
    assert client.post("/api/info", content=b"{not json", headers=JSON).status_code == 422
    assert client.post("/api/info", json={}).status_code == 422


# --------------------------------------------------------------------------- looking up a link
def test_info_for_a_good_link(client):
    r = client.post("/api/info", json={"url": "https://vimeo.com/123"})
    assert r.status_code == 200 and r.json()["title"] == "Demo" and r.json()["heights"] == [360, 720]


@pytest.mark.parametrize("url,code", [("file:///etc/passwd", "bad_scheme"), ("http://169.254.169.254/", "ip_literal"), ("http://localhost:22/", "bad_port"),
                                      ("https://www.youtube.com/watch?v=x", "youtube_off"), ("ytsearch5:cats", "bad_scheme")])
def test_info_refuses_dangerous_links(client, url, code):
    r = client.post("/api/info", json={"url": url})
    assert r.status_code == 400 and r.json()["error"]["code"] == code


def test_private_addresses_behind_a_name_are_refused(client, monkeypatch):
    from server import safety
    monkeypatch.setattr(safety, "_resolve", lambda h, p: {"10.1.2.3"})
    r = client.post("/api/info", json={"url": "https://innocent.example.com/x"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_url"


def test_lookups_are_rate_limited(settings):
    with client_for(settings, info_per_min=2) as c:
        assert [c.post("/api/info", json={"url": "https://vimeo.com/1"}).status_code for _ in range(2)] == [200, 200]
        r = c.post("/api/info", json={"url": "https://vimeo.com/1"})
        assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited" and int(r.headers["retry-after"]) >= 1


# --------------------------------------------------------------------------- downloads
def test_full_download_lifecycle(client):
    job_id = finish(client)
    view = client.get(f"/api/jobs/{job_id}").json()
    assert view["status"] == "done" and view["filename"] == "A weird title ok.mp4" and view["expires_in"] > 0
    got = client.get(f"/api/jobs/{job_id}/file")
    assert got.status_code == 200 and got.content == b"0123456789" * 100
    assert got.headers["content-type"] == "video/mp4" and got.headers["x-content-type-options"] == "nosniff"
    assert got.headers["content-disposition"].startswith("attachment") and "A weird title ok.mp4" in unquote(got.headers["content-disposition"])
    assert got.headers["content-security-policy"].startswith("sandbox") and "no-store" in got.headers["cache-control"]
    part = client.get(f"/api/jobs/{job_id}/file", headers={"range": "bytes=0-9"})
    assert part.status_code == 206 and part.content == b"0123456789"
    assert client.delete(f"/api/jobs/{job_id}").status_code == 204
    assert client.get(f"/api/jobs/{job_id}").status_code == 404 and client.get(f"/api/jobs/{job_id}/file").status_code == 404


def test_audio_download_gets_the_right_type(client):
    job_id = finish(client, {"url": "https://soundcloud.com/a/b", "kind": "audio", "format": "mp3"})
    got = client.get(f"/api/jobs/{job_id}/file")
    assert got.headers["content-type"] == "audio/mpeg" and "A weird title ok.mp3" in unquote(got.headers["content-disposition"])


def test_file_is_not_available_before_it_is_ready(settings):
    gate = Gate()
    with client_for(settings, gate) as c:
        job_id = c.post("/api/jobs", json=VIDEO).json()["id"]
        assert c.get(f"/api/jobs/{job_id}/file").status_code == 409
        assert c.post(f"/api/jobs/{job_id}/cancel").json()["status"] in ("running", "cancelled", "queued")
        wait_for(lambda: c.get(f"/api/jobs/{job_id}").json()["status"] == "cancelled")
        assert c.get(f"/api/jobs/{job_id}").json()["error"]["code"] == "cancelled"


def test_unknown_and_malformed_ids(client):
    for job_id in ("doesnotexist1234567890", "x", "a" * 80):
        r = client.get(f"/api/jobs/{job_id}")
        assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
        assert client.delete(f"/api/jobs/{job_id}").status_code == 404 and client.get(f"/api/jobs/{job_id}/file").status_code == 404


def test_download_requests_are_validated(client):
    for body, code in [({**VIDEO, "url": "ftp://x.com/y"}, "bad_scheme"), ({**VIDEO, "format": "exe"}, "bad_format"), ({**VIDEO, "kind": "gif"}, "bad_request"),
                       ({**VIDEO, "start": 5}, "bad_clip"), ({**VIDEO, "start": 9, "end": 3}, "bad_clip"), ({**VIDEO, "start": 0, "end": 99999}, "bad_clip")]:
        r = client.post("/api/jobs", json=body)
        assert r.status_code in (400, 422) and r.json()["error"]["code"] == code, (body, r.text)


def test_height_is_capped_to_the_server_limit(settings):
    seen = []

    def spy(sp, *rest):
        seen.append(sp)
        return fake_run(sp, *rest)
    with client_for(settings, spy, max_height=720) as c:
        finish(c, {**VIDEO, "height": 2160})
    assert seen[0].height == 720


def test_one_visitor_is_limited_but_the_service_keeps_working(settings):
    gate = Gate()
    with client_for(settings, gate, per_ip_active=1) as c:
        assert c.post("/api/jobs", json=VIDEO).status_code == 202
        r = c.post("/api/jobs", json=VIDEO)
        assert r.status_code == 429 and r.json()["error"]["code"] == "too_many_active" and "retry-after" in r.headers
        gate.release.set()


def test_new_downloads_are_rate_limited(settings):
    with client_for(settings, jobs_per_hour=2, per_ip_active=10) as c:
        codes = [c.post("/api/jobs", json=VIDEO).status_code for _ in range(3)]
    assert codes == [202, 202, 429]


# --------------------------------------------------------------------------- the engine updater
def fake_pip(version="2026.11.01", pip_ok=True):
    def run(cmd, **kw):
        if "pip" in cmd:
            if pip_ok:
                (engine_module.Path(cmd[cmd.index("--target") + 1])).mkdir(parents=True)
            return subprocess.CompletedProcess(cmd, 0 if pip_ok else 1, stdout="", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout=version + "\n", stderr="")
    return run


def test_engine_environment_has_no_server_secrets(settings, monkeypatch):
    monkeypatch.setenv("SECRET_TOKEN", "hunter2")
    env = Engine(settings).env()
    assert "SECRET_TOKEN" not in env and "hunter2" not in str(env)
    assert env["HOME"].startswith(str(settings.data_dir))


def test_engine_update_installs_checks_and_switches(settings, monkeypatch):
    eng = Engine(settings)
    assert eng.path() is None and "PYTHONPATH" not in eng.env()
    monkeypatch.setattr(engine_module.subprocess, "run", fake_pip("2026.11.01"))
    assert eng.update() == "2026.11.01" and eng.version() == "2026.11.01"
    current = eng.path()
    assert current is not None and eng.env()["PYTHONPATH"] == str(current)
    monkeypatch.setattr(engine_module.subprocess, "run", fake_pip("2026.11.01"))
    assert eng.update() is None                                          # nothing newer: the extra copy is thrown away
    assert eng.path() == current and len(list(eng.root.glob("[0-9]*"))) == 1


def test_a_broken_update_changes_nothing(settings, monkeypatch):
    eng = Engine(settings)
    monkeypatch.setattr(engine_module.subprocess, "run", fake_pip(pip_ok=False))
    with pytest.raises(RuntimeError):
        eng.update()
    monkeypatch.setattr(engine_module.subprocess, "run", fake_pip(version="Traceback (most recent call last)"))
    with pytest.raises(RuntimeError):
        eng.update()
    assert eng.path() is None and not list(eng.root.glob("[0-9]*"))


def test_engine_pointer_cannot_escape_its_folder(settings):
    eng = Engine(settings)
    eng.root.mkdir(parents=True)
    (eng.root / "current").write_text("../../etc")
    assert eng.path() is None


def test_whoami_is_off_unless_asked_for(settings):
    with client_for(settings) as c:
        assert c.get("/api/whoami").status_code == 404
    with client_for(settings, debug_client_ip=True, trusted_proxy_hops=1) as c:
        body = c.get("/api/whoami", headers={"x-forwarded-for": "6.6.6.6, 203.0.113.9"}).json()
        assert body["detected"] == "203.0.113.9" and body["hops"] == 1 and body["forwarded_for"] == "6.6.6.6, 203.0.113.9"


def test_settings_from_the_environment(monkeypatch):
    monkeypatch.setenv("MAX_HEIGHT", "99999")
    monkeypatch.setenv("MAX_FILESIZE_MB", "banana")
    monkeypatch.setenv("YOUTUBE", "ON")
    monkeypatch.setenv("YTDLP_PROXY", "file:///etc/passwd")
    monkeypatch.setenv("ABUSE_CONTACT", "javascript:alert(1)")
    monkeypatch.setenv("ALLOWED_SITES", " Vimeo.com , .soundcloud.com ,")
    s = config.load()
    assert s.max_height == 4320 and s.max_filesize_mb == 300 and s.youtube == "on"
    assert s.proxy == "" and s.abuse_contact == "" and s.allowed_sites == ("vimeo.com", "soundcloud.com")
    monkeypatch.setenv("ABUSE_CONTACT", "mailto:abuse@example.org")
    monkeypatch.setenv("YTDLP_PROXY", "socks5h://127.0.0.1:9050")
    assert config.load().abuse_contact == "mailto:abuse@example.org" and config.load().proxy == "socks5h://127.0.0.1:9050"
