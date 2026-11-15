"""End-to-end check of a running DropDL Web server, using only the standard library.

  python web/smoke.py http://127.0.0.1:7860            # health, page, refused links
  python web/smoke.py http://127.0.0.1:7860 --download  # also trims 6 seconds from a public-domain video and fetches the file

Exits non-zero on the first failure, so it works in CI and as a post-deploy check.
"""
import json
import sys
import time
import urllib.error
import urllib.request

SAMPLE = "https://archive.org/details/BigBuckBunny_124"


def call(base, path, body=None, method=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method or ("POST" if data else "GET"), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.status, res.headers, res.read()
    except urllib.error.HTTPError as err:
        return err.code, err.headers, err.read()


def check(ok, message):
    print(("ok    " if ok else "FAIL  ") + message, flush=True)
    if not ok:
        sys.exit(1)


def main():
    base = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:7860").rstrip("/")
    status, _, body = call(base, "/api/health")
    health = json.loads(body)
    check(status == 200 and health["ok"], f"health: version {health.get('version')}, yt-dlp {health.get('engine')}, YouTube {health.get('youtube')}")
    status, headers, body = call(base, "/")
    check(status == 200 and b"DropDL" in body and "default-src 'none'" in headers.get("content-security-policy", ""), "page is served with a strict content policy")
    for url, code in (("http://169.254.169.254/latest/meta-data/", "ip_literal"), ("file:///etc/passwd", "bad_scheme"), ("https://example.com/video.mp4", "unsupported")):
        status, _, body = call(base, "/api/info", {"url": url})
        found = json.loads(body).get("error", {}).get("code")
        check(status in (400, 422) and found == code, f"refuses {url} ({found})")
    if "--download" in sys.argv:
        status, _, body = call(base, "/api/jobs", {"url": SAMPLE, "kind": "video", "height": 360, "format": "mp4", "start": 30, "end": 36})
        check(status == 202, "download accepted")
        job = json.loads(body)["id"]
        for _ in range(120):
            view = json.loads(call(base, f"/api/jobs/{job}")[2])
            if view["status"] in ("done", "error", "cancelled"):
                break
            time.sleep(1)
        check(view["status"] == "done", f"download finished ({view['status']}, {view.get('error')})")
        status, headers, body = call(base, f"/api/jobs/{job}/file", timeout=120)
        check(status == 200 and len(body) > 50_000 and body[4:8] == b"ftyp", f"file received: {len(body):,} bytes, {headers.get('content-type')}")
        check(call(base, f"/api/jobs/{job}", method="DELETE")[0] == 204, "file deleted on request")
    print("all checks passed")


if __name__ == "__main__":
    main()
