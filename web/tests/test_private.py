"""A private instance: the access code, the owner's cookies, and what makes the page installable on a phone."""
import dataclasses
import json
import subprocess

import pytest
from fastapi.testclient import TestClient

from server import runner
from server.app import create_app
from server.auth import COOKIE, Sessions
from server.errors import ApiError, RunError
from tests.conftest import fake_info, fake_run, spec

CODE = "correct horse"
COOKIES = "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tsecret-session-value\n"
VIDEO = {"url": "https://vimeo.com/123", "kind": "video", "height": 720, "format": "mp4"}


def make_client(settings, **overrides):
    s = dataclasses.replace(settings, access_code=CODE, **overrides)
    return TestClient(create_app(s, run_fn=fake_run, info_fn=fake_info, background=False))


@pytest.fixture
def client(settings):
    with make_client(settings) as c:
        yield c


@pytest.fixture
def no_delay(monkeypatch):
    from server import app as app_module
    monkeypatch.setattr(app_module.time, "sleep", lambda seconds: None)


# --------------------------------------------------------------------------- nothing works without the code
def test_everything_asks_for_the_code_first(client):
    health = client.get("/api/health").json()
    assert health["auth"] == {"required": True, "ok": False}
    assert client.get("/").status_code == 200                                   # the page itself loads, to show the sign-in box
    for call in (lambda: client.post("/api/info", json={"url": "https://vimeo.com/1"}), lambda: client.post("/api/jobs", json=VIDEO),
                 lambda: client.get("/api/jobs/anything12345678901234"), lambda: client.get("/api/jobs/anything12345678901234/file"),
                 lambda: client.post("/api/jobs/anything12345678901234/cancel"), lambda: client.delete("/api/jobs/anything12345678901234")):
        r = call()
        assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"


def test_wrong_code_then_right_code(client, no_delay):
    bad = client.post("/api/login", json={"code": "wrong"})
    assert bad.status_code == 401 and bad.json()["error"]["code"] == "login_failed" and COOKIE not in bad.headers.get("set-cookie", "")
    good = client.post("/api/login", json={"code": CODE})
    assert good.status_code == 200
    cookie = good.headers["set-cookie"].lower()
    assert COOKIE in cookie and "httponly" in cookie and "samesite=lax" in cookie and "secure" not in cookie
    assert client.get("/api/health").json()["auth"] == {"required": True, "ok": True}
    assert client.post("/api/info", json={"url": "https://vimeo.com/1"}).status_code == 200


def test_the_cookie_is_secure_over_https(client):
    r = client.post("/api/login", json={"code": CODE}, headers={"x-forwarded-proto": "https"})
    assert "secure" in r.headers["set-cookie"].lower()


def test_a_full_download_after_signing_in(client):
    client.post("/api/login", json={"code": CODE})
    job_id = client.post("/api/jobs", json=VIDEO).json()["id"]
    from tests.conftest import wait_for
    wait_for(lambda: client.get(f"/api/jobs/{job_id}").json()["status"] == "done")
    assert client.get(f"/api/jobs/{job_id}/file").status_code == 200
    client.cookies.clear()                                                     # someone with the link but not the code
    assert client.get(f"/api/jobs/{job_id}/file").status_code == 401


def test_signing_out_ends_the_session_everywhere(client):
    client.post("/api/login", json={"code": CODE})
    token = client.cookies.get(COOKIE)
    assert client.post("/api/logout").status_code == 200
    assert client.post("/api/info", json={"url": "https://vimeo.com/1"}).status_code == 401
    client.cookies.set(COOKIE, token)                                           # replaying the old cookie must not work
    assert client.post("/api/info", json={"url": "https://vimeo.com/1"}).status_code == 401


def test_guessing_the_code_is_throttled(client, no_delay):
    codes = [client.post("/api/login", json={"code": f"guess-{n}"}).status_code for n in range(8)]
    assert codes == [401] * 8
    blocked = client.post("/api/login", json={"code": CODE})                    # even the right code waits once the limit is hit
    assert blocked.status_code == 429 and int(blocked.headers["retry-after"]) >= 1


def test_other_sites_cannot_act_with_your_cookie(client):
    evil = {"origin": "https://evil.example"}
    assert client.post("/api/login", json={"code": CODE}, headers=evil).status_code == 403
    assert client.post("/api/login", json={"code": CODE}, headers=evil).json()["error"]["code"] == "bad_origin"
    assert client.post("/api/login", json={"code": CODE}, headers={"origin": "null"}).status_code == 403
    assert client.post("/api/login", json={"code": CODE}, headers={"origin": "http://testserver"}).status_code == 200
    assert client.delete("/api/jobs/anything12345678901234", headers=evil).status_code == 403


def test_a_public_instance_is_unchanged(settings):
    with TestClient(create_app(settings, run_fn=fake_run, info_fn=fake_info, background=False)) as c:
        assert c.get("/api/health").json()["auth"] == {"required": False, "ok": True}
        assert c.post("/api/info", json={"url": "https://vimeo.com/1"}, headers={"origin": "https://other.example"}).status_code == 200
        assert c.post("/api/login", json={"code": "anything"}).status_code == 200


def test_sessions_expire_and_are_capped():
    s = Sessions("longenough", ttl=100, max_sessions=3)
    token = s.create(now=0)
    assert s.valid(token, now=50) and not s.valid(token, now=101) and not s.valid(token, now=102)
    assert not s.valid(None) and not s.valid("") and not s.valid("made-up")
    first = s.create(now=1000)
    for n in range(3):
        s.create(now=1001 + n)
    assert not s.valid(first, now=1002)                                         # the oldest is dropped when the cap is reached
    assert s.check_code("longenough") and not s.check_code("longenough ") and not s.check_code("") and not s.check_code(None)


def test_unsafe_settings_are_refused_at_start_up(settings, tmp_path):
    cookies = tmp_path / "cookies.txt"
    cookies.write_text(COOKIES)
    for bad in (dict(access_code="short"), dict(cookies_file=cookies), dict(access_code=CODE, cookies_file=tmp_path / "missing.txt")):
        with pytest.raises(ValueError):
            create_app(dataclasses.replace(settings, **bad), background=False)
    create_app(dataclasses.replace(settings, access_code=CODE, cookies_file=cookies), background=False)       # the safe combination starts


# --------------------------------------------------------------------------- the owner's cookies
@pytest.fixture
def cookie_settings(settings, tmp_path):
    cookies = tmp_path / "my-cookies.txt"
    cookies.write_text(COOKIES)
    return dataclasses.replace(settings, access_code=CODE, cookies_file=cookies, youtube="on")


def test_cookies_are_only_passed_when_configured(settings):
    assert "--cookies" not in runner.build_download_args(spec(), settings, runner.Path("/w"))
    args = runner.build_download_args(spec(), settings, runner.Path("/w"), "/w/cookies.txt")
    assert args[args.index("--cookies") + 1] == "/w/cookies.txt"
    assert "--cookies" in runner.build_info_args("https://vimeo.com/1", settings, "/w/c.txt") and "--cookies" not in runner.build_info_args("https://vimeo.com/1", settings)


def test_node_is_switched_on_for_youtube_only_if_installed(settings, monkeypatch):
    monkeypatch.setattr(runner.shutil, "which", lambda name: "/usr/bin/node" if name == "node" else None)
    a = runner.build_info_args("https://vimeo.com/1", settings)
    assert a[a.index("--js-runtimes") + 1] == "node"
    monkeypatch.setattr(runner.shutil, "which", lambda name: None)
    assert "--js-runtimes" not in runner.build_info_args("https://vimeo.com/1", settings)


class FakeStdout:
    def __iter__(self):
        return iter(())

    def close(self):
        pass


class FakeProcess:
    stdout = FakeStdout()
    returncode = 0

    def poll(self):
        return 0

    def wait(self):
        return 0


def test_a_download_gets_a_private_copy_and_it_is_removed(cookie_settings, tmp_path, monkeypatch):
    outdir, seen = tmp_path / "job", {}

    def fake_spawn(cmd, cwd, env, settings):
        seen["cmd"] = cmd
        seen["copy"] = (cwd / "cookies.txt").read_text()
        (cwd / "media.mp4").write_bytes(b"video")
        (cwd / "media.info.json").write_text(json.dumps({"title": "T"}))
        return FakeProcess()
    monkeypatch.setattr(runner, "_spawn", fake_spawn)
    result = runner.run_download(spec(), outdir, cookie_settings, {}, __import__("threading").Event(), lambda u: None)
    used = seen["cmd"][seen["cmd"].index("--cookies") + 1]
    assert used == str(outdir / "cookies.txt") and used != str(cookie_settings.cookies_file) and seen["copy"] == COOKIES
    assert [p.name for p in outdir.iterdir()] == ["media.mp4"] and result.title == "T"            # the copy is gone, only the video is left
    assert cookie_settings.cookies_file.read_text() == COOKIES                                      # the original is untouched


def test_a_link_lookup_uses_and_removes_a_temporary_copy(cookie_settings, monkeypatch):
    seen = {}

    def fake_run(cmd, **kw):
        path = cmd[cmd.index("--cookies") + 1]
        seen["path"], seen["text"] = path, open(path).read()
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"title": "T", "formats": []}), stderr="")
    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    runner.fetch_info("https://www.youtube.com/watch?v=x", cookie_settings, {})
    assert seen["text"] == COOKIES and seen["path"] != str(cookie_settings.cookies_file)
    assert not runner.Path(seen["path"]).exists() and not [p for p in (cookie_settings.data_dir / "work").glob("info-*")]


def test_a_rejected_cookie_gets_its_own_message(cookie_settings, settings, monkeypatch):
    def bot_check(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="ERROR: [youtube] x: Sign in to confirm you're not a bot")
    monkeypatch.setattr(runner.subprocess, "run", bot_check)
    with pytest.raises(ApiError) as caught:
        runner.fetch_info("https://www.youtube.com/watch?v=x", cookie_settings, {})
    assert caught.value.code == "youtube_cookies" and "cookies.txt" in caught.value.message
    with pytest.raises(ApiError) as caught:
        runner.fetch_info("https://www.youtube.com/watch?v=x", dataclasses.replace(settings, youtube="on"), {})
    assert caught.value.code == "youtube_blocked"


def test_a_cookie_file_that_vanished_is_reported(cookie_settings, tmp_path):
    cookie_settings.cookies_file.unlink()
    with pytest.raises(ApiError) as caught:
        runner.fetch_info("https://www.youtube.com/watch?v=x", cookie_settings, {})
    assert caught.value.code == "cookies_missing"
    with pytest.raises(RunError) as run_caught:
        runner.run_download(spec(), tmp_path / "job", cookie_settings, {}, __import__("threading").Event(), lambda u: None)
    assert run_caught.value.code == "cookies_missing"


def test_cookies_never_end_up_in_a_served_file(cookie_settings, monkeypatch):
    """Only the finished media file is ever served; the job folder (which briefly held the cookie copy) is not browsable."""
    with TestClient(create_app(cookie_settings, run_fn=fake_run, info_fn=fake_info, background=False)) as c:
        c.post("/api/login", json={"code": CODE})
        job_id = c.post("/api/jobs", json=VIDEO).json()["id"]
        from tests.conftest import wait_for
        wait_for(lambda: c.get(f"/api/jobs/{job_id}").json()["status"] == "done")
        for path in (f"/api/jobs/{job_id}/cookies.txt", f"/api/jobs/{job_id}/../../cookies.txt", f"/jobs/{job_id}/cookies.txt", "/cookies.txt"):
            assert "secret-session-value" not in c.get(path).text


# --------------------------------------------------------------------------- installing it on a phone
def test_the_page_can_be_installed_and_receives_shared_links(settings):
    with TestClient(create_app(settings, run_fn=fake_run, info_fn=fake_info, background=False)) as c:
        manifest = c.get("/manifest.json").json()
        assert manifest["display"] == "standalone" and manifest["start_url"] == "/"
        assert manifest["share_target"] == {"action": "/", "method": "GET", "params": {"title": "title", "text": "text", "url": "url"}}
        assert {i["sizes"] for i in manifest["icons"]} >= {"192x192", "512x512"}
        for icon in manifest["icons"]:
            png = c.get(icon["src"])
            assert png.status_code == 200 and png.content[:4] == b"\x89PNG"
        assert c.get("/icon-180.png").status_code == 200
        worker = c.get("/sw.js")
        assert worker.status_code == 200 and "fetch" in worker.text and "caches." not in worker.text      # it must never cache the page
        page = c.get("/").text
        assert 'rel="manifest"' in page and 'id="login"' in page
