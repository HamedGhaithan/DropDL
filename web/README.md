# DropDL Web

The browser version of DropDL Studio: paste a link, pick a format, download. No account, no cookies, no tracking. It is a small server (Python, FastAPI, [yt-dlp](https://github.com/yt-dlp/yt-dlp), FFmpeg) plus a plain HTML/JS page with no build step, in English and Arabic, dark and light.

It is meant to run on a **free host**, so it is deliberately modest and locked down. To use it for YouTube from your phone, run it privately on your own PC (see [YouTube on your phone](#youtube-on-your-phone)). For playlists, no limits and the video editor, use the [desktop app](https://github.com/HamedGhaithan/DropDL/releases/latest).

| | Web | Desktop |
| --- | :---: | :---: |
| Single video or song, MP4/WebM/MKV/MP3/M4A/Opus/FLAC/WAV | ✅ | ✅ |
| Trim a section before downloading | ✅ | ✅ |
| Quality choice with size estimates | ✅ | ✅ |
| Playlists, channels, batches, subscriptions | ❌ | ✅ |
| YouTube | ❌ on free hosts · ✅ in private mode on your own PC | ✅ |
| Resume, retries, pause, scheduling, library, convert, timeline editor | ❌ | ✅ |
| Size and length limits | yes (configurable) | none |

## Try it

```bash
# from the repository root
pip install -r web/requirements.txt          # also needs FFmpeg on your PATH
python web/serve.py                          # http://127.0.0.1:7860
```

or with Docker:

```bash
docker build -f web/Dockerfile -t dropdl-web .
docker run --rm -p 7860:7860 dropdl-web
```

Check a running server end to end (health, page, refused links, and optionally a real trimmed download):

```bash
python web/smoke.py http://127.0.0.1:7860 --download
```

## Deploy it for free

No account can be created for you, so deploying is a few clicks you do yourself. Read your host's terms first: some free hosts don't allow media-downloader services, and this project can't promise any of them does.

| Host | Cost | Good for | Catches |
| --- | --- | --- | --- |
| **Oracle Cloud Always Free** (VM) | free | most capable and stable; you control the network | you run a small server; Oracle can reclaim idle instances; needs a card for sign-up |
| **Render** (free web service) | free | easiest start, deploys from this repo | 512 MB RAM, sleeps after 15 min idle (first visit then takes up to a minute), 750 free hours per month shared across your services |
| Hugging Face Spaces (Docker) | free tier uncertain | works with this Dockerfile (port 7860) | as of late 2026 its docs say creating Docker Spaces needs a paid plan |

> The Render and Oracle files in this repository were written from those platforms' documentation. They have not yet been run on live accounts. Please open an issue if a step doesn't work.

### Render

1. Fork this repository (or use it directly) and sign in at [render.com](https://render.com).
2. **New → Blueprint**, pick the repository. Render reads [`render.yaml`](../render.yaml) and creates a free Docker web service.
3. When it is live, **set the proxy count correctly.** Add the environment variable `DEBUG_CLIENT_IP=1`, redeploy, and open `https://<your-service>.onrender.com/api/whoami`. `detected` must be **your own public address**. If it shows a Render or Cloudflare address, raise `TRUSTED_PROXY_HOPS` (try 2) until it shows yours. If it is wrong, every visitor shares one rate limit. Then remove `DEBUG_CLIENT_IP`.
4. Run `python web/smoke.py https://<your-service>.onrender.com`.

### Oracle Cloud (or any Linux VM)

See [`deploy/oracle`](../deploy/oracle). In short: install Docker, copy the folder, set `DOMAIN` in `.env`, `docker compose up -d --build`, then `sudo bash harden.sh` to stop the container from reaching the cloud metadata service and private networks. Caddy gets a free HTTPS certificate automatically.

## YouTube on your phone

YouTube now asks for a signed-in session from everyone. From a datacenter (every free host) it refuses outright, and in tests from an ordinary home connection all of yt-dlp's access methods also ended in "Sign in to confirm you're not a bot". The desktop app copes because you give it your cookies. DropDL Web can do the same in **private mode**: it runs on **your own PC**, behind a code only you know, with your cookies, and your phone connects to it.

```
phone  ──(Wi-Fi, Tailscale or a tunnel)──▶  your PC: DropDL Web + your cookies  ──▶  YouTube
```

On a free public host `YOUTUBE` stays `off`: the page says so immediately and points to the desktop app.

**You need** a Windows PC that stays on while you download, with Python, FFmpeg and Node.js (Node is what YouTube's checks run on). The DropDL desktop app's setup installs all three, and the launcher reuses its Python.

1. **Export your YouTube cookies** as `cookies.txt`. A spare Google account is wise: YouTube can limit accounts it sees downloading. Open a **private/incognito** window, sign in to YouTube, go to `https://www.youtube.com/robots.txt`, export the cookies for youtube.com with a cookies.txt browser extension (for example "Get cookies.txt LOCALLY"), then close the window. That keeps YouTube from rotating the session out from under the file. Leave it in **Downloads**: the launcher finds it, checks that it is signed in to YouTube, and moves it to `%LOCALAPPDATA%\DropDLWeb\cookies.txt` (you can also put it there yourself). If you already imported cookies into the desktop app, the launcher finds and reuses those.
2. **Double-click `Start-DropDL-Web.bat`** in the repository folder. It makes an access code once (kept in `%LOCALAPPDATA%\DropDLWeb\access-code.txt`) and prints the addresses to open. If Windows asks about the firewall, allow Python on **private** networks.
3. **On your phone**, on the same Wi-Fi, open the printed address, enter the code, paste a YouTube link. Then add it to your home screen (Chrome: ⋮ → *Install app*; Safari: Share → *Add to Home Screen*).
   - **Android:** DropDL now appears in the Share sheet. In the YouTube app tap Share → DropDL and it starts analyzing by itself.
   - **iPhone** can't add web apps to the Share sheet, so make a Shortcut: *Receive URLs from Share Sheet* → *Open URL* `http://YOUR-PC-ADDRESS:7860/?url=` followed by the shared URL.
4. **Away from home?** Install [Tailscale](https://tailscale.com/) (free for personal use) on the PC and the phone. The launcher prints the PC's Tailscale address and nothing is exposed to the internet. Or use a free Cloudflare quick tunnel: `winget install Cloudflare.cloudflared`, then start with `Start-DropDL-Web.bat -Tunnel`. A tunnel is a public address, so keep the access code secret.

Good to know:

- **Your cookies are your login.** They stay on your PC, in a file only you can read, and are never uploaded. Each download works from a private temporary copy that is deleted with the job. The server refuses to start with cookies unless an access code is set, because otherwise anyone who found the address could download with your account.
- Cookies expire. When the page says YouTube "rejected the saved cookies", export a fresh `cookies.txt` to Downloads and restart; the newer file replaces the old one.
- Your PC does the work over your home connection; the phone only receives the finished file.
- To check the setup: `python web\smoke.py http://127.0.0.1:7860 --code YOURCODE --url "https://www.youtube.com/watch?v=..." --download` (trims 6 seconds, so it is quick).
- The launcher's options: `-Tunnel`, `-LocalOnly` (this PC only), `-DryRun` (show the settings and addresses, start nothing), `-Port`.

## Settings

All settings are environment variables.

| Variable | Default | Meaning |
| --- | --- | --- |
| `PORT` | `7860` | Port the container listens on (Render sets it for you) |
| `DATA_DIR` | system temp folder | Where jobs, cache and engine copies live. Wiped of old jobs at start-up |
| `MAX_HEIGHT` / `DEFAULT_HEIGHT` | `1080` / `720` | Tallest video offered / preselected |
| `MAX_FILESIZE_MB` | `300` | Largest file produced. Bigger formats are skipped automatically; a bigger result is refused |
| `MAX_DURATION_MIN` | `60` | Longest source video (a trimmed download may come from up to 6 hours) |
| `MAX_CLIP_MIN` | `10` | Longest trimmed section |
| `JOB_TTL_MIN` | `20` | Minutes a finished file stays downloadable |
| `DISK_QUOTA_MB` | `2048` | Total space for all files; oldest finished files are deleted first |
| `MAX_ACTIVE` / `MAX_QUEUE` | `2` / `20` | Downloads running at once / waiting. Use `1` on 512 MB hosts |
| `PER_IP_ACTIVE` | `2` | Downloads one visitor may have queued or running |
| `INFO_PER_MIN` / `JOBS_PER_HOUR` / `POLL_PER_MIN` | `15` / `20` / `240` | Per-visitor rate limits |
| `JOB_TIMEOUT_SEC` | `900` | Wall-clock limit for one download |
| `TRUSTED_PROXY_HOPS` | `1` | Reverse proxies in front of the app (`0` if none). See the Render step above |
| `ALLOWED_SITES` | empty | Comma-separated domains. If set, **only** these work (a strict way to run a small private service) |
| `BLOCKED_SITES` | empty | Comma-separated domains to refuse |
| `YOUTUBE` | `off` | `on` to allow YouTube links |
| `YTDLP_PROXY` | empty | Outbound proxy for yt-dlp (`http`, `https`, `socks4`, `socks5`, `socks5h`) |
| `ACCESS_CODE` | empty | At least 8 characters. If set, visitors must enter it first (a private instance) |
| `YTDLP_COOKIES_FILE` | empty | Your own exported `cookies.txt`, needed for YouTube. **Requires `ACCESS_CODE`**; the server won't start without it |
| `ENGINE_UPDATE_HOURS` | `12` | How often to fetch a newer yt-dlp (`0` disables) |
| `ABUSE_CONTACT` | empty | `https://` or `mailto:` link shown as "Report abuse" in the footer |
| `ENABLE_DOCS` | off | `1` serves interactive API docs at `/api/docs` |
| `DEBUG_CLIENT_IP` | off | `1` enables `/api/whoami` for checking `TRUSTED_PROXY_HOPS` |

## How it protects the host (and the people using it)

A public downloader can be abused as an open proxy, so the server assumes every link is hostile:

- **Only public sites on standard ports.** Links must be `http(s)` to a real DNS name on port 80/443. IP addresses, `localhost`, `.local`/`.internal` names and `user:pass@` links are refused. Every address a name resolves to must be globally routable (this also catches IPv4 tucked inside IPv6 forms), which blocks cloud-metadata and internal addresses.
- **No "fetch any URL".** yt-dlp's generic extractor is turned off, so only sites yt-dlp has a dedicated extractor for work.
- **No visitor-controlled flags.** The command line is built from validated values; the link always goes after `--`. Sizes, qualities, formats and times are clamped.
- **Each download is a separate process** with a hard timeout, a size watchdog, OS limits on file size and CPU (Linux), and a minimal environment that does not contain the server's secrets.
- **Limits per visitor and overall:** rate limits, a cap on active downloads, a queue, a disk quota, files deleted after minutes. Visitors are identified by a salted hash of their network, kept only in memory.
- **Safe file serving.** Downloads are sent as attachments with `nosniff` and a sandboxing policy; file names are cleaned (no path characters, no bidirectional-override tricks).
- **Strict browser policy.** A content-security policy with no inline scripts or styles, no framing, no referrer. Text from other sites is only ever inserted as text.
- **Always-current yt-dlp.** Sites change every few weeks. A fresh copy is installed into a new folder, checked, and only then switched to. A bad release can't take the service down.

## Privacy

No accounts, cookies or analytics. Links and files exist only for the life of a job and are deleted after `JOB_TTL_MIN`. Addresses are never written to disk or logs; the server doesn't log requests. In private mode your cookies file is copied into a job's temporary folder only while it runs and is deleted with it. The browser remembers your recent downloads in its own local storage so the list survives a refresh. Video thumbnails load directly from the source site's servers.

## Responsible use

Only download content you own, content in the public domain or under a licence that allows it, or content you have permission to save. Follow each site's terms and your local law. DropDL does not bypass DRM. If you run a public instance you are the operator: set `ABUSE_CONTACT`, respond to reports, and consider `ALLOWED_SITES`.

## Development

```bash
pip install -r web/requirements.txt -r requirements-dev.txt
python -m pytest web/tests -q                              # fast, offline (a fake downloader stands in for yt-dlp)
RUN_NETWORK_TESTS=1 python -m pytest web/tests/test_network.py   # real downloads from archive.org
```

```
web/
  server/    app.py (API + page) · safety.py (link and file-name rules) · runner.py (yt-dlp commands, progress, errors, cookies)
             auth.py (access code and sessions) ·              jobs.py (queue, limits, clean-up) · engine.py (yt-dlp updates) · ratelimit.py · config.py
  static/    index.html · app.js · i18n.js (English/Arabic) · style.css · fonts · manifest.json + sw.js (install on a phone)
  start-private.ps1   the Windows launcher behind Start-DropDL-Web.bat
  tests/     pytest suites · smoke.py runs against a live server
```

### API

| Method and path | Purpose |
| --- | --- |
| `GET /api/health` | status, limits and supported formats |
| `POST /api/info` `{url}` | look a link up: title, thumbnail, duration, qualities with size estimates |
| `POST /api/jobs` `{url, kind, height?, format?, start?, end?}` | start a download (`kind` is `video` or `audio`) |
| `GET /api/jobs/{id}` | status, progress, queue position, time left |
| `GET /api/jobs/{id}/file` | the finished file (supports ranges) |
| `POST /api/jobs/{id}/cancel`, `DELETE /api/jobs/{id}` | stop / delete now |
| `POST /api/login` `{code}`, `POST /api/logout` | private instances only: sign in (HttpOnly cookie) / out |

Errors are `{"error": {"code", "message"}}` with stable codes that the page translates.
