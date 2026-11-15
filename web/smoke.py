"""End-to-end check of a running DropDL Web server, using only the standard library.

  python web/smoke.py http://127.0.0.1:7860                        # health, page, refused links
  python web/smoke.py http://127.0.0.1:7860 --download             # also trims 6 seconds from a public-domain video and fetches the file
  python web/smoke.py http://127.0.0.1:7860 --code YOURCODE --url "https://www.youtube.com/watch?v=..." --download
                                                                   # a private instance: sign in first, and try your own link

Exits non-zero on the first failure, so it works in CI and as a post-deploy check.
"""
import http.cookiejar
import json
import sys
import time
import urllib.error
import urllib.request

SAMPLE = "https://archive.org/details/BigBuckBunny_124"
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def option(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv and sys.argv.index(name) + 1 < len(sys.argv) else default


def call(base, path, body=None, method=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method or ("POST" if data else "GET"), headers={"Content-Type": "application/json"})
    try:
        with OPENER.open(req, timeout=timeout) as res:
            return res.status, res.headers, res.read()
    except urllib.error.HTTPError as err:
        return err.code, err.headers, err.read()


def check(ok, message):
    print(("ok    " if ok else "FAIL  ") + message, flush=True)
    if not ok:
        sys.exit(1)


def main():
    base = (sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "http://127.0.0.1:7860").rstrip("/")
    status, _, body = call(base, "/api/health")
    health = json.loads(body)
    check(status == 200 and health["ok"], f"health: version {health.get('version')}, yt-dlp {health.get('engine')}, YouTube {health.get('youtube')}")
    status, headers, body = call(base, "/")
    check(status == 200 and b"DropDL" in body and "default-src 'none'" in headers.get("content-security-policy", ""), "page is served with a strict content policy")
    auth = health.get("auth", {})
    if auth.get("required"):
        status, _, body = call(base, "/api/info", {"url": "https://vimeo.com/1"})
        check(status == 401, "a private instance refuses requests without the access code")
        code = option("--code")
        check(code is not None, "this instance needs --code YOURCODE") if not auth.get("ok") else None
        if code:
            status, _, body = call(base, "/api/login", {"code": code})
            check(status == 200, "signed in with the access code")
    for url, expected in (("http://169.254.169.254/latest/meta-data/", "ip_literal"), ("file:///etc/passwd", "bad_scheme"), ("https://example.com/video.mp4", "unsupported")):
        status, _, body = call(base, "/api/info", {"url": url})
        found = json.loads(body).get("error", {}).get("code")
        check(status in (400, 422) and found == expected, f"refuses {url} ({found})")
    if "--download" in sys.argv:
        link = option("--url", SAMPLE)
        status, _, body = call(base, "/api/info", {"url": link}, timeout=90)
        info = json.loads(body)
        check(status == 200, f"looked up the link: {info.get('title') or info.get('error')}")
        kind = "video" if info.get("has_video") else "audio"
        request = {"url": link, "kind": kind, "start": 5 if option("--url") else 30, "end": 11 if option("--url") else 36}
        if kind == "video":
            request.update(height=360, format="mp4")
        status, _, body = call(base, "/api/jobs", request)
        check(status == 202, f"download accepted ({kind}, 6 seconds)")
        job = json.loads(body)["id"]
        view = {}
        for _ in range(180):
            view = json.loads(call(base, f"/api/jobs/{job}")[2])
            if view["status"] in ("done", "error", "cancelled"):
                break
            time.sleep(1)
        check(view.get("status") == "done", f"download finished ({view.get('status')}, {view.get('error')})")
        status, headers, body = call(base, f"/api/jobs/{job}/file", timeout=120)
        check(status == 200 and len(body) > 20_000, f"file received: {len(body):,} bytes, {headers.get('content-type')}")
        check(call(base, f"/api/jobs/{job}", method="DELETE")[0] == 204, "file deleted on request")
    print("all checks passed")


if __name__ == "__main__":
    main()
